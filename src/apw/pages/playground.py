"""操练场页面对象（套组调试沙箱：会话列表 + 调试 IDE）。

由 playground_probe{,2,3} 与 workspace 探查产物生成（2026-09-30）。产品事实：
- 入口 = 侧边栏「更多场景」→「创作与调试」组场景卡「操练场」；会话卡绑一个套组；
- 「新建会话」弹窗 = 会话名称 + 原生 select「从套组加载（可选）」，确定后**直接进 IDE**
  （无需再点「进入调试」；从列表恢复既有会话才走「进入调试」）；
- IDE 身份锚 = 「📦 已加载：<套组名>」徽标（清除提示按钮壳限定）+ 顶栏会话名；
- 底部模式：Agent 助手（读写工作区文件）/ ▶ 测试套组（用当前配置快照运行一次套组）；
- 测试套组运行 = 输入用户消息 Enter 运行 → 运行日志逐行渲染：
  「▶ 操练场运行开始」→「Prompt: <消息>」回显 → 初始化/推理输出（「│」行）→
  「✅ 运行完成，用时 Ns，Token: N」；顶栏状态 空闲→已完成 + Token 统计。

硬红线（用例约定）：
- 套组必须为私有（create_suite 内建核对）；不点「更新套组/另存为新套组/导入配置/导出配置/
  重置工作区」等写操作，不动工具开关/推理模式/系统 Prompts（保持套组快照纯度）；
- 调试消息只作确定性测试文本，不断言 LLM 措辞（回复质量留 LLM-as-Judge）。
"""
from __future__ import annotations

import time
from datetime import datetime
from urllib.parse import urljoin

from apw.pages.base import BasePage, EvidenceError


def classify_run_failure(signals: dict) -> tuple[str, str]:
    """归因「调试运行未达成」：(分类, 说明)。"""
    if not signals.get("running_cleared", True):
        return "run_stuck", "底部模式条「运行中」持续在场：运行未结束（执行挂起或超长）"
    return "run_incomplete", "运行结束但完成信号未齐（无完成行/无回复输出/状态非已完成）"


class PlaygroundPage(BasePage):
    page_name = "playground"

    # ---- 内部 ----
    def _log_text(self) -> str:
        rows = self.loc_all("run_log_line")
        try:
            return "\n".join(rows.all_inner_texts())
        except Exception:  # noqa: BLE001 - 日志缺席按空（稳定性判据会兜住）
            return ""

    def _loaded_badge_text(self) -> str:
        try:
            return self.loc("suite_loaded_badge").first.inner_text(timeout=1_500)
        except Exception:  # noqa: BLE001 - 徽标缺席按空（身份核对会兜住）
            return ""

    def _title_text(self) -> str:
        try:
            return self.loc("ide_title").first.inner_text(timeout=1_500).strip()
        except Exception:  # noqa: BLE001 - 观察字段
            return ""

    # ---- 入口：更多场景 → 操练场 ----

    def open_playground(self, timeout_ms: int = 15_000) -> dict:
        """侧边栏「更多场景」→ 场景卡「操练场」进入会话列表，等「新建会话」渲染。

        入口在会话页侧边栏；不在会话页（如套组广场）先回会话页再进。
        """
        if self.count("nav_more_scenes") == 0:
            self.page.goto(urljoin(self.page.url, "/"), wait_until="load")
            self.page.wait_for_timeout(800)
        self.loc("nav_more_scenes").click()
        self.page.wait_for_timeout(600)
        self.loc("nav_playground").click()
        deadline = time.time() + timeout_ms / 1000
        while self.count("new_session_button") == 0 and time.time() < deadline:
            time.sleep(0.4)
        if self.count("new_session_button") == 0:
            shot = self.snap("playground-not-loaded")
            raise EvidenceError(
                "操练场未进入［归因: run_stuck］「新建会话」未渲染"
                f"（{timeout_ms}ms）\n  复现: url={self.page.url}\n"
                f"  冻结截图: {shot or '（未捕获）'}",
                {
                    "classification": "run_stuck",
                    "cause": "操练场会话列表未渲染",
                    "repro": {"url": self.page.url},
                    "screenshots": [shot] if shot else [],
                },
            )
        return {
            "surface": "playground",
            "url": self.page.url,
            "cards": self.count("session_card"),
        }

    # ---- 新建会话：绑定刚创建的套组（确定后直接进 IDE）----

    def new_session(
        self, name: str = "apw调试会话", suite: str = "", timeout_ms: int = 20_000
    ) -> dict:
        """新建操练场会话并绑定套组（suite 留空取 flow_state 里刚创建的套组名）。

        身份锚（identity_mismatch 冻结取证）：
        - 刚创建的套组必须出现在「从套组加载」选择器（缺失=产品缺陷）；
        - 进入 IDE 后「已加载：<套组名>」徽标必须回显所选套组；
        - 顶栏会话名回显（时间戳后缀防重名）。
        """
        suite = suite or self.flow_state.get("suite_name", "")
        if not suite:
            raise ValueError("未指定套组：suite 参数或 flow_state['suite_name'] 至少一个")
        full_name = f"{name}-{datetime.now().strftime('%m%d%H%M%S')}"
        self.loc("new_session_button").click()
        deadline = time.time() + 8
        while self.count("session_dialog") == 0 and time.time() < deadline:
            time.sleep(0.3)
        if self.count("session_dialog") == 0:
            shot = self.snap("session-dialog-missing")
            raise EvidenceError(
                "新建会话弹窗未打开［归因: run_stuck］（8s）\n"
                f"  复现: url={self.page.url}\n  冻结截图: {shot or '（未捕获）'}",
                {
                    "classification": "run_stuck",
                    "cause": "「新建会话」弹窗未弹出",
                    "repro": {"url": self.page.url},
                    "screenshots": [shot] if shot else [],
                },
            )
        # 受控输入真实键入（已知产品行为）
        self.loc("session_name_input").first.click()
        self.page.keyboard.type(full_name, delay=20)
        select = self.loc("session_suite_select")
        options = select.locator("option").all_inner_texts()
        if suite not in options:
            shot = self.snap("suite-not-in-select")
            evidence = {
                "classification": "identity_mismatch",
                "cause": "刚创建的套组未出现在操练场「从套组加载」选择器",
                "suite": suite,
                "options": options,
                "repro": {"url": self.page.url, "steps": "create_suite → new_session"},
                "screenshots": [shot] if shot else [],
            }
            raise EvidenceError(
                f"套组绑定失败［归因: identity_mismatch］选择器无 {suite!r}\n"
                f"  复现: 新建会话绑定 @ {self.page.url}\n  冻结截图: {shot or '（未捕获）'}",
                evidence,
            )
        select.select_option(label=suite)
        self.page.wait_for_timeout(300)
        self.loc("dialog_confirm").first.click()
        # 确定后直接进 IDE（产品行为）：等身份锚徽标渲染
        deadline = time.time() + timeout_ms / 1000
        badge = ""
        while time.time() < deadline:
            time.sleep(0.4)
            badge = self._loaded_badge_text()
            if badge:
                break
        title = self._title_text()
        checks = {
            "badge_rendered": bool(badge),
            "suite_echo": suite in badge,
            "session_echo": full_name in title,
        }
        evidence = {
            "session_name": full_name,
            "suite": suite,
            "loaded_badge": badge,
            "ide_title": title,
            **checks,
        }
        if not all(checks.values()):
            category = "identity_mismatch" if checks["badge_rendered"] else "run_stuck"
            shot = self.snap("session-bind-mismatch")
            evidence["screenshots"] = [shot] if shot else []
            raise EvidenceError(
                f"会话绑定未达成［归因: {category}］{checks}\n"
                f"  复现: 新建会话 @ {self.page.url}\n  冻结截图: {shot or '（未捕获）'}",
                evidence,
            )
        return evidence

    # ---- 简单对话调试：测试套组模式跑一条消息 ----

    def send_debug_message(self, message: str, timeout_ms: int = 300_000) -> dict:
        """测试套组模式发一条调试消息并等待运行完成（AI 一次完整推理）。

        完成判定 = 六信号（全部确定性）：
        ① 日志「✅ 运行完成」完成行 ② 顶栏状态「已完成」③ Token 统计在场
        ④ 日志「Prompt: <消息>」输入回显 ⑤ 回复输出行（「│」）在场 ⑥ 日志文本稳定。
        未达成即判失败冻结现场（run_stuck / run_incomplete），绝不自愈重试。
        """
        self.loc("mode_test_button").click()  # 幂等：已在测试套组模式也无副作用
        self.page.wait_for_timeout(300)
        box = self.loc("run_input")
        box.first.click()
        self.page.keyboard.type(message, delay=20)  # 受控输入真实键入
        self.page.keyboard.press("Enter")
        deadline = time.time() + timeout_ms / 1000
        stable, last_len, signals, prev, tick = 0, -1, {}, None, 0
        timeline: list[dict] = []
        while time.time() < deadline:
            time.sleep(1)
            tick += 1
            log = self._log_text()
            signals = {
                "done_line": self.count("run_done_marker") > 0,
                "status_completed": self.count("run_status_done") > 0,
                "token_stat": self.count("run_token_stat") > 0,
                "prompt_echo": f"Prompt: {message}" in log,
                "reply_output": "\n" in log and "│" in log,
                "running_cleared": self.count("run_running_marker") == 0,
            }
            length = len(log)
            if signals != prev or tick % 10 == 0:
                timeline.append({"t_s": tick, "log_len": length, **signals})
                prev = dict(signals)
            gate = {k: v for k, v in signals.items() if k != "running_cleared"}
            if all(gate.values()) and length == last_len and length > 0:
                stable += 1
                if stable >= 3:  # ⑥ 日志稳定
                    return self._run_evidence(message, signals, timeline)
            else:
                stable = 0
            last_len = length
        category, cause = classify_run_failure(signals)
        shot = self.snap("debug-run-timeout")
        evidence = self._run_evidence(message, signals, timeline)
        evidence.update(
            {
                "classification": category,
                "cause": cause,
                "repro": {
                    "url": self.page.url,
                    "observed": f"运行启动后 {timeout_ms}ms 内完成信号未达成",
                    "steps": "new_session → send_debug_message",
                },
                "screenshots": [shot] if shot else [],
            }
        )
        raise EvidenceError(
            f"调试运行未达成［归因: {category}］{cause}\n  信号: {signals}\n"
            f"  冻结截图: {shot or '（未捕获）'}",
            evidence,
        )

    def _run_evidence(self, message: str, signals: dict, timeline: list[dict]) -> dict:
        log = self._log_text()
        return {
            "message": message,
            "run_signals": signals,
            "timeline": timeline[-5:],
            "log_tail": log[-600:],
            "log_lines": len(log.splitlines()),
            "session_name": self._title_text(),
            "loaded_badge": self._loaded_badge_text(),
            "url": self.page.url.split("?")[0],
        }
