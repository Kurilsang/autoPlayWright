"""Foxmail 代发后端（免微软登录）：mailto 拉起写信窗 + Ctrl+Enter 发送。

利用本机 Foxmail 已有登录态（其 OAuth 令牌由 Foxmail 自行维护），完全不
经过微软登录/授权流程。Foxmail 为 Delphi 程序（UIA 全盲），窗口交互走
Win32 三步：
  1. Foxmail.exe "mailto:<to>?subject=..&body=.." → 写信窗（TFoxComposeForm，预填）
  2. 还原（防最小化）并强制置前台 → Ctrl+Enter（写信窗发送快捷键）
  3. 写信窗关闭 = 已发送；超时未关判失败（不重试不自愈，留窗给人工收尾）

注意：发件身份 = Foxmail 默认账号；附件本通道暂不支持。
"""
from __future__ import annotations

import ctypes
import re
import subprocess
import time
import urllib.parse
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from apw.notify.mail import MailConfig

COMPOSE_CLASS = "TFoxComposeForm.UnicodeClass"
_REG_KEY = r"foxmail.Url.mailto\shell\open\command"
_VK_CONTROL = 0x11
_VK_RETURN = 0x0D
_KEYEVENTF_KEYUP = 0x0002
_WM_CLOSE = 0x0010


class _Win32:
    """最小 Win32 封装（仅 Windows；惰性加载）。"""

    def __init__(self) -> None:
        # 平台检查必须在 import ctypes.wintypes 之前：非 Windows 该 import 会抛
        # ValueError（_type_ 'v' not supported），掩盖真实原因。
        if not hasattr(ctypes, "WinDLL"):
            raise RuntimeError(
                "foxmail 通道仅支持 Windows（依赖本机 Foxmail 客户端 + Win32 窗口交互）；"
                "Linux/服务器请改用 smtp 或 ews 通道"
            )
        import ctypes.wintypes as wintypes

        self._ctypes = ctypes
        self._wt = wintypes
        self.u = ctypes.WinDLL("user32", use_last_error=True)
        self.k = ctypes.WinDLL("kernel32", use_last_error=True)
        self.WNDENUMPROC = ctypes.WINFUNCTYPE(
            wintypes.BOOL, wintypes.HWND, wintypes.LPARAM
        )
        self.u.EnumWindows.argtypes = [self.WNDENUMPROC, wintypes.LPARAM]
        self.u.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
        self.u.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
        self.u.IsWindow.argtypes = [wintypes.HWND]
        self.u.IsWindow.restype = wintypes.BOOL
        self.u.IsWindowVisible.argtypes = [wintypes.HWND]
        self.u.IsWindowVisible.restype = wintypes.BOOL
        self.u.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
        self.u.SetForegroundWindow.argtypes = [wintypes.HWND]
        self.u.GetForegroundWindow.restype = wintypes.HWND
        self.u.GetWindowThreadProcessId.argtypes = [wintypes.HWND, wintypes.LPDWORD]
        self.u.AttachThreadInput.argtypes = [
            wintypes.DWORD,
            wintypes.DWORD,
            wintypes.BOOL,
        ]
        self.u.keybd_event.argtypes = [
            wintypes.BYTE,
            wintypes.BYTE,
            wintypes.DWORD,
            ctypes.c_void_p,
        ]
        self.k.GetCurrentThreadId.restype = wintypes.DWORD

    def find_windows(
        self, cls: str, title_contains: str = "", *, visible_only: bool = True
    ) -> list[tuple[int, str]]:
        """返回 (hwnd, 标题) 列表。标题随行：句柄会被 Windows 复用，靠标题辨别新旧窗。

        visible_only=True 跳过不可见窗：Foxmail 关闭写信窗后会留下**不可见的空壳窗**
        （类名照旧、无子窗、标题空），不去掉会把它们当现存写信窗，导致
        「已知窗」快照污染与清窗死循环（2026-10-14 实测）。
        """
        found: list[tuple[int, str]] = []

        def callback(hwnd, _lparam):  # noqa: ANN001, ANN202
            buf = self._ctypes.create_unicode_buffer(256)
            self.u.GetClassNameW(hwnd, buf, 256)
            if buf.value != cls:
                return True
            if visible_only and not self.u.IsWindowVisible(hwnd):
                return True
            text = self._ctypes.create_unicode_buffer(512)
            self.u.GetWindowTextW(hwnd, text, 512)
            if title_contains and title_contains not in text.value:
                return True
            found.append((int(hwnd), text.value))
            return True

        self.u.EnumWindows(self.WNDENUMPROC(callback), 0)
        return found

    def has_child_class(self, hwnd: int, cls: str) -> bool:
        """子孙窗口里是否有指定类名（EnumChildWindows 全子孙枚举）。"""
        return cls in self.child_classes(hwnd)

    def child_classes(self, hwnd: int) -> list[str]:
        """子孙窗口类名列表（就绪判定与失败归因共用同一枚举）。"""
        found: list[str] = []

        def walk(child, _lparam):  # noqa: ANN001, ANN202
            buf = self._ctypes.create_unicode_buffer(128)
            self.u.GetClassNameW(child, buf, 128)
            found.append(buf.value)
            return True

        self.u.EnumChildWindows(self._wt.HWND(hwnd), self.WNDENUMPROC(walk), 0)
        return found

    def is_window(self, hwnd: int) -> bool:
        return bool(self.u.IsWindow(self._wt.HWND(hwnd)))

    def is_visible(self, hwnd: int) -> bool:
        return bool(self.u.IsWindowVisible(self._wt.HWND(hwnd)))

    def force_foreground(self, hwnd: int) -> None:
        """还原 + 置前台。

        Windows 前台锁下 AttachThreadInput+SetForegroundWindow 实测无效
        （2026-10-14 实测）；有效序列 = SW_RESTORE → 空敲一次 ALT 解锁 →
        SetForegroundWindow。
        """
        handle = self._wt.HWND(hwnd)
        self.u.ShowWindow(handle, 9)  # SW_RECOVER（最小化窗口必须先还原）
        self.u.keybd_event(0x12, 0, 0, None)  # ALT down/up 空敲解锁前台
        time.sleep(0.03)
        self.u.keybd_event(0x12, 0, _KEYEVENTF_KEYUP, None)
        time.sleep(0.03)
        self.u.SetForegroundWindow(handle)

    def is_foreground(self, hwnd: int) -> bool:
        return int(self.u.GetForegroundWindow() or 0) == hwnd

    def ctrl_enter(self) -> None:
        """合成 Ctrl+Enter（写信窗发送快捷键）；键间留间隔，Delphi 零间隔连发吃不到。"""
        pause = lambda: time.sleep(0.05)  # noqa: E731
        self.u.keybd_event(_VK_CONTROL, 0, 0, None)
        pause()
        self.u.keybd_event(_VK_RETURN, 0, 0, None)
        pause()
        self.u.keybd_event(_VK_RETURN, 0, _KEYEVENTF_KEYUP, None)
        pause()
        self.u.keybd_event(_VK_CONTROL, 0, _KEYEVENTF_KEYUP, None)


def build_mailto_url(to: list[str], subject: str, body: str) -> str:
    """组装 mailto: URL（收件人逗号分隔，主题/正文 URL 编码）。

    safe="" 关键：`quote` 默认 safe='/' 会把 `/` 原样留在查询串里，Foxmail 收到
    含裸 `/` 的 mailto 会**整条丢弃**（不报错、不开窗，2026-10-14 实测——摘要主题里的
    「7/16 通过」正好踩中，表现为「写信窗永不出现」）。查询串里 `/` 必须编码成 %2F。
    同理收件人里的 `+`/空格等一并交给编码处理，避免被当成分隔符。
    """
    quote = lambda value: urllib.parse.quote(value, safe="")  # noqa: E731
    recipients = ",".join(quote(addr) for addr in to)
    return (
        f"mailto:{recipients}"
        f"?subject={quote(subject)}&body={quote(body)}"
    )


def _exe_from_command(command: str) -> str:
    """从注册表命令行提取 exe 路径（'"...exe" "%1"' → ...exe）。"""
    match = re.match(r'^\s*"([^"]+)"', command)
    if match:
        return match.group(1)
    return command.strip().split(" ")[0] if command.strip() else ""


def find_foxmail_exe() -> str:
    """从 mailto 关联注册表发现 Foxmail 安装路径（仅 Windows）。"""
    if not hasattr(ctypes, "WinDLL"):
        raise RuntimeError(
            "foxmail 通道仅支持 Windows（注册表发现不可用）；Linux/服务器请改用 smtp 或 ews 通道"
        )
    import winreg

    try:
        with winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, _REG_KEY) as key:
            value, _ = winreg.QueryValueEx(key, "")
    except OSError as exc:
        raise RuntimeError(
            "未找到 Foxmail（注册表无 foxmail.Url.mailto 关联）；"
            "可在配置 smtp.foxmail_path 指定安装路径"
        ) from exc
    exe = _exe_from_command(value or "")
    if not exe:
        raise RuntimeError(f"Foxmail 注册表命令行无法解析: {value!r}")
    return exe


def send_foxmail(
    cfg: MailConfig,
    *,
    subject: str,
    body: str,
    to: list[str] | None = None,
    html: str | None = None,  # noqa: ARG001 - mailto 正文为纯文本
    attachments: list | None = None,
    attachments_blob: list | None = None,
) -> str:
    """经 Foxmail 写信窗发信，返回 'foxmail:hwnd=<n>'。"""
    if attachments or attachments_blob:
        raise NotImplementedError("foxmail 通道暂不支持附件（请用 smtp 通道）")
    recipients = list(dict.fromkeys(list(to or cfg.to) + list(cfg.cc)))
    if not recipients:
        raise ValueError(
            "收件人为空：配置 smtp.to（或 smtp.report_to）/ APW_NOTIFY_TO / --to 至少其一"
        )

    win32 = _Win32()
    exe = (cfg.foxmail_path or "").strip() or find_foxmail_exe()
    url = build_mailto_url(recipients, subject, body)
    # 先清残留（上一轮失败的遗留窗）：不清会让本次 mailto 被灌进旧窗，
    # 表现为「新写信窗永不出现」的连锁失败（2026-10-14 实测）。
    stale = close_stale_compose(win32)
    if stale:
        _debug(f"closed {stale} stale compose window(s) before launch")
    existing = dict(win32.find_windows(COMPOSE_CLASS))
    _debug(f"existing before launch: {existing}")

    subprocess.Popen([exe, url])  # noqa: S603 - 本机邮件客户端，参数非 shell
    hwnd = _wait_compose(win32, existing, subject, appear=True)
    _wait_ready(win32, hwnd, subject)
    for _attempt in range(3):
        # 每轮重新抢前台再按键：新邮件弹窗等会瞬时偷焦点（2026-10-14 实测）
        _acquire_foreground(win32, hwnd)
        win32.ctrl_enter()
        if _wait_compose(
            win32, {hwnd: ""}, subject,
            appear=False, timeout=8.0, quiet=True,
        ):
            return f"foxmail:hwnd={hwnd}"
    raise RuntimeError(
        f"Foxmail 写信窗 3 次键击后仍未关闭（subject={subject!r} hwnd={hwnd}，现场保留）"
    )


def _wait_ready(win32: _Win32, hwnd: int, subject: str = "", timeout: float = 60.0) -> None:
    """等写信窗真正可发：CEF 正文编辑器就绪 **且标题已填上主题**。

    两个就绪条件缺一不可（2026-10-14 实测）：
    - `TCEFWindowParent` 子窗出现 = 控件树加载完（窗太新就发键会被吞）
    - 标题变成 `<主题> - 写邮件` = Foxmail 已把 mailto 参数灌进控件；
      标题仍为空/仍旧值时按键会落到尚未初始化的编辑器上被丢弃。

    冷启动（Foxmail 刚起来 / 首次写信）CEF 子进程初始化明显更慢，实测可超 15s，
    故默认给到 60s；超时保留现场报错，不静默继续。
    """
    deadline = time.monotonic() + timeout
    wanted = _compose_title_re(subject) if subject else None
    last_title = ""
    last_child = ""
    while time.monotonic() < deadline:
        cef_ready = win32.has_child_class(hwnd, "TCEFWindowParent")
        title = dict(win32.find_windows(COMPOSE_CLASS)).get(hwnd, "")
        last_title, last_child = title, ",".join(win32.child_classes(hwnd)[:6])
        title_ready = wanted.search(title) is not None if wanted else bool(title.strip())
        if cef_ready and title_ready:
            time.sleep(0.5)
            return
        time.sleep(0.3)
    raise RuntimeError(
        f"Foxmail 写信窗 {timeout:.0f}s 未就绪（CEF={last_child!r}，"
        f"标题={last_title!r}，期望含 {subject[:30]!r}；现场保留）"
    )


def _acquire_foreground(win32: _Win32, hwnd: int, timeout: float = 10.0) -> None:
    """循环抢前台直到成功（前台锁行为非确定性，单次尝试会偶发失败）。"""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        win32.force_foreground(hwnd)
        time.sleep(1.5)  # 焦点落定（实测 0.4s 偶发不够）
        if win32.is_foreground(hwnd):
            return
    raise RuntimeError(
        f"Foxmail 写信窗无法置前台（hwnd={hwnd}，键击会被其他窗口吞掉，现场保留）"
    )


def _debug(msg: str) -> None:
    import os

    if os.environ.get("APW_NOTIFY_DEBUG"):
        print(f"[notify-debug] {msg}", flush=True)


def _compose_title_re(subject: str):
    """写信窗标题形如 '<主题> - 写邮件'；主题里可能有正则元字符，必须转义。"""
    return re.compile(re.escape(subject[:40]))


def _wait_compose(
    win32: _Win32,
    known: dict[int, str],
    subject: str,
    *,
    appear: bool,
    timeout: float = 20.0,
    quiet: bool = False,
) -> int | None:
    """等写信窗出现（appear=True 返回承载本封邮件的窗口）或关闭。

    两个必须处理的 Foxmail 行为（2026-10-14 实测）：

    1. **句柄会被 Windows 复用**：known = {hwnd: 标题} 快照，同句柄换标题也算新窗。
    2. **同一进程内 mailto 会复用已有写信窗**：残留窗在场时不再新建，直接把内容灌进旧窗。
       此时「等新窗出现」永远等不到，但**旧窗标题会变成当前主题**——所以判定以
       「标题匹配本封主题」为准，而不是「是不是新窗口」。

    标题优先匹配（主题最长 40 字符），匹配不到再退回「任意新窗」，避免主题被截断/改写时
    误判成失败。quiet=True 超时返回 None 不抛（用于「先试一次」场景）。
    """
    deadline = time.monotonic() + timeout
    wanted = _compose_title_re(subject)
    last: list[tuple[int, str]] = []
    while time.monotonic() < deadline:
        current = win32.find_windows(COMPOSE_CLASS)
        last = current
        if appear:
            matching = [h for h, title in current if wanted.search(title)]
            if matching:
                _debug(f"appear matched by subject: {matching}")
                return matching[0]
            fresh = [h for h, title in current if known.get(h) != title]
            _debug(f"appear poll: known={known} current={current} fresh={fresh}")
            if fresh:
                return fresh[0]
        else:
            # 关闭判定用「句柄是否还在」而不是标题比对：标题在灌参数前后的空/变值
            # 会造成假「已关闭」（2026-10-14 实测，曾把未发出的窗判成已发）。
            current_handles = {h for h, _t in current}
            closed = [h for h in known if h not in current_handles]
            if closed:
                return closed[0]
        time.sleep(0.5)
    if quiet:
        return None
    action = "出现" if appear else "关闭"
    raise RuntimeError(
        f"Foxmail 写信窗未在 {timeout:.0f}s 内{action}（subject={subject!r}，"
        f"现存窗口={last}，现场保留请人工收尾）"
    )


def close_stale_compose(win32: _Win32, *, attempts: int = 4) -> int:
    """清掉残留写信窗（上一轮失败留下的），返回清掉的个数。

    不清理会让后续 mailto 被 Foxmail 灌进旧窗，出现「新窗永不出现」的连锁失败
    （2026-10-14 实测）。只关写信窗本身，不动主窗口、不碰已保存邮件。
    """
    closed = 0
    for _ in range(attempts):
        windows = win32.find_windows(COMPOSE_CLASS)
        if not windows:
            return closed
        for hwnd, _title in windows:
            win32.u.SendMessageW(win32._wt.HWND(hwnd), _WM_CLOSE, 0, 0)
            closed += 1
        time.sleep(1.5)
    return closed
