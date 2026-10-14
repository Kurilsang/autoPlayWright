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

    def find_windows(self, cls: str, title_contains: str = "") -> list[tuple[int, str]]:
        """返回 (hwnd, 标题) 列表。标题随行：句柄会被 Windows 复用，靠标题辨别新旧窗。"""
        found: list[tuple[int, str]] = []

        def callback(hwnd, _lparam):  # noqa: ANN001, ANN202
            buf = self._ctypes.create_unicode_buffer(256)
            self.u.GetClassNameW(hwnd, buf, 256)
            if buf.value != cls:
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
        found: list[int] = []

        def walk(child, _lparam):  # noqa: ANN001, ANN202
            buf = self._ctypes.create_unicode_buffer(128)
            self.u.GetClassNameW(child, buf, 128)
            if buf.value == cls:
                found.append(int(child))
            return True

        self.u.EnumChildWindows(self._wt.HWND(hwnd), self.WNDENUMPROC(walk), 0)
        return bool(found)

    def is_window(self, hwnd: int) -> bool:
        return bool(self.u.IsWindow(self._wt.HWND(hwnd)))

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
    """组装 mailto: URL（收件人逗号分隔，主题/正文 URL 编码）。"""
    quote = urllib.parse.quote
    return (
        f"mailto:{','.join(to)}"
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
) -> str:
    """经 Foxmail 写信窗发信，返回 'foxmail:hwnd=<n>'。"""
    if attachments:
        raise NotImplementedError("foxmail 通道暂不支持附件（请用 smtp 通道）")
    recipients = list(to or cfg.to)
    if not recipients:
        raise ValueError("收件人为空：配置 smtp.to / APW_NOTIFY_TO / --to 至少其一")

    win32 = _Win32()
    exe = (cfg.foxmail_path or "").strip() or find_foxmail_exe()
    url = build_mailto_url(recipients, subject, body)
    existing = dict(win32.find_windows(COMPOSE_CLASS))
    _debug(f"existing before launch: {existing}")

    subprocess.Popen([exe, url])  # noqa: S603 - 本机邮件客户端，参数非 shell
    hwnd = _wait_compose(win32, existing, subject, appear=True)
    _wait_ready(win32, hwnd)
    for _attempt in range(3):
        # 每轮重新抢前台再按键：新邮件弹窗等会瞬时偷焦点（2026-10-14 实测）
        _acquire_foreground(win32, hwnd)
        win32.ctrl_enter()
        titles = dict(win32.find_windows(COMPOSE_CLASS))
        if _wait_compose(
            win32, {hwnd: titles.get(hwnd, "")}, subject,
            appear=False, timeout=6.0, quiet=True,
        ):
            return f"foxmail:hwnd={hwnd}"
    raise RuntimeError(
        f"Foxmail 写信窗 3 次键击后仍未关闭（subject={subject!r} hwnd={hwnd}，现场保留）"
    )


def _wait_ready(win32: _Win32, hwnd: int, timeout: float = 15.0) -> None:
    """等写信窗就绪（CEF 正文编辑器子窗出现=控件树加载完成）。

    窗口太新就发键会被吞（2026-10-14 实测），故显式等待。
    """
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if win32.has_child_class(hwnd, "TCEFWindowParent"):
            time.sleep(0.5)
            return
        time.sleep(0.3)
    raise RuntimeError(f"Foxmail 写信窗 {timeout:.0f}s 未就绪（CEF 编辑器未加载，现场保留）")


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


def _wait_compose(
    win32: _Win32,
    known: dict[int, str],
    subject: str,
    *,
    appear: bool,
    timeout: float = 20.0,
    quiet: bool = False,
) -> int | None:
    """等写信窗出现（appear=True 返回新窗）或关闭（appear=False 返回已关窗）。

    known = {hwnd: 标题} 快照；句柄复用免疫靠标题比对（同句柄不同标题=新窗）。
    quiet=True 超时返回 None 不抛（用于「先试一次」场景）。
    """
    deadline = time.monotonic() + timeout
    hint = subject[:40]
    last: list[tuple[int, str]] = []
    while time.monotonic() < deadline:
        current = win32.find_windows(COMPOSE_CLASS, hint) or win32.find_windows(
            COMPOSE_CLASS
        )
        last = current
        if appear:
            fresh = [h for h, title in current if known.get(h) != title]
            _debug(f"appear poll: known={known} current={current} fresh={fresh}")
            if fresh:
                return fresh[0]
        else:
            current_map = dict(current)
            closed = [h for h, title in known.items() if current_map.get(h) != title]
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
