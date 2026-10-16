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

from datetime import datetime
from urllib.parse import urljoin

from apw.pages.base import BasePage


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
        self.wait_until(
            lambda: self.count("new_session_button") > 0, timeout_ms=timeout_ms, interval_ms=400
        )
        if self.count("new_session_button") == 0:
            self.fail_evidence(
                "操练场未进入",
                classification="run_stuck",
                cause="操练场会话列表未渲染",
                repro={"url": self.page.url},
                detail=f"「新建会话」未渲染（{timeout_ms}ms）",
                shot_name="playground-not-loaded",
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
        self.wait_until(lambda: self.count("session_dialog") > 0, timeout_ms=8_000)
        if self.count("session_dialog") == 0:
            self.fail_evidence(
                "新建会话弹窗未打开",
                classification="run_stuck",
                cause="「新建会话」弹窗未弹出",
                repro={"url": self.page.url},
                detail="点击「新建会话」后 8s 弹窗未弹出",
                shot_name="session-dialog-missing",
            )
        # 受控输入真实键入（已知产品行为）
        self.loc("session_name_input").first.click()
        self.page.keyboard.type(full_name, delay=20)
        select = self.loc("session_suite_select")
        options = select.locator("option").all_inner_texts()
        if suite not in options:
            self.fail_evidence(
                "套组绑定失败：选择器无目标套组",
                classification="identity_mismatch",
                cause="刚创建的套组未出现在操练场「从套组加载」选择器",
                repro={"url": self.page.url, "steps": "create_suite → new_session"},
                detail=f"选择器无 {suite!r}",
                shot_name="suite-not-in-select",
                extra={"suite": suite, "options": options},
            )
        select.select_option(label=suite)
        self.page.wait_for_timeout(300)
        self.loc("dialog_confirm").first.click()
        # 确定后直接进 IDE（产品行为）：等身份锚徽标渲染
        badge = ""

        def badge_rendered() -> bool:
            nonlocal badge
            badge = self._loaded_badge_text()
            return bool(badge)

        self.wait_until(badge_rendered, timeout_ms=timeout_ms, interval_ms=400)
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
            self.fail_evidence(
                "会话绑定未达成",
                classification=category,
                cause="身份锚（已加载徽标/会话名回显）核对未全过",
                repro={"url": self.page.url, "observed": "新建会话绑定"},
                detail=f"checks={checks}",
                shot_name="session-bind-mismatch",
                extra=evidence,
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
        log_box: dict[str, str] = {"text": ""}

        def read_signals() -> dict[str, bool]:
            log_box["text"] = log = self._log_text()
            return {
                "done_line": self.count("run_done_marker") > 0,
                "status_completed": self.count("run_status_done") > 0,
                "token_stat": self.count("run_token_stat") > 0,
                "prompt_echo": f"Prompt: {message}" in log,
                "reply_output": "\n" in log and "│" in log,
                "running_cleared": self.count("run_running_marker") == 0,
            }

        watch = self.watch_signals(
            signals=read_signals,
            size=lambda: len(log_box["text"]),
            timeout_ms=timeout_ms,
            size_field="log_len",
            # running_cleared 是流式态观测：完成必需信号不含它（缺失结构由分类取证兜住）
            gate={"done_line", "status_completed", "token_stat", "prompt_echo", "reply_output"},
        )
        if watch.settled:  # ⑥ 日志稳定（watch 内已多信号收敛）
            return self._run_evidence(message, watch.signals, watch.timeline)
        self.fail_incomplete(
            "调试运行未达成",
            classify=classify_run_failure,
            watch=watch,
            steps="new_session → send_debug_message",
            observed=f"运行启动后 {timeout_ms}ms 内完成信号未达成",
            shot_name="debug-run-timeout",
            extra=self._run_facts(message),
        )

    def _run_facts(self, message: str) -> dict:
        """调试运行现场事实（日志尾/行数/身份锚/URL）：成功证据与失败取证共用。"""
        log = self._log_text()
        return {
            "message": message,
            "log_tail": log[-600:],
            "log_lines": len(log.splitlines()),
            "session_name": self._title_text(),
            "loaded_badge": self._loaded_badge_text(),
            "url": self.page.url.split("?")[0],
        }

    def _run_evidence(self, message: str, signals: dict, timeline: list[dict]) -> dict:
        return {
            "run_signals": signals,
            "timeline": timeline[-5:],
            **self._run_facts(message),
        }
