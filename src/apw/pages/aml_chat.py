"""被测 Agent 会话页（真实环境）。

由 AI 爬取页面结构生成（T07 预演）。动作语义与夹具 AgentChatPage 对齐，
选择器差异由定位器仓库吸收；完成判定要求「完整回答」：思考过程与最终答案
的结构标记都渲染出来才算结束（见 wait_reply_done）。
"""
from __future__ import annotations

import time

from apw.pages.base import BasePage, SignalWatch

_DISMISS_TEXTS = ("稍后再看", "我已熟悉", "关闭提示", "关闭", "我已知晓")

# 弹窗选项名 → 定位器仓库条目
_MODE_LOCATORS = {
    "专家模式": "agent_mode_expert",
    "快速模式": "agent_mode_quick",
    "工程模式": "agent_mode_engineer",
}


def classify_incomplete(signals: dict) -> tuple[str, str]:
    """归因「完整回答未达成」：(分类, 说明)。归因与复现线索随证据入报告。"""
    if not signals.get("history_cleared", True):
        return (
            "hang_loading",
            "会话区卡「加载对话历史中」：前端加载卡死/历史接口无响应。"
            "复现线索：新建会话确认 Agent 模式后随即发送时偶发，页面保持卡死原状",
        )
    if not signals.get("stop_cleared", True):
        return (
            "streaming_stuck",
            "「停止」按钮仍在：流式生成未结束（服务端生成挂起或超长）",
        )
    missing = [
        k
        for k in ("reasoning_steps", "final_answer_card", "reply_actions")
        if not signals.get(k)
    ]
    if missing:
        return "reply_incomplete", f"回答结构不完整（半截渲染）：缺 {', '.join(missing)}"
    return "content_unstable", "回答内容持续变化未稳定（文本长度未收敛）"

# 结构采集专用 DOM 内省：按语义标记取对话上下文（容忍样式改名，尽力而为）
_CAPTURE_JS = """
() => {
  const turns = [];
  document.querySelectorAll('div.w-full.user-message').forEach(row => {
    const userEl = row.querySelector('div.text-white.whitespace-pre-wrap');
    if (userEl) {
      turns.push({role: 'user', text: (userEl.textContent || '').trim()});
      return;
    }
    const card = row.querySelector('div.markdown-prose');
    if (!card) return;
    let reasoning = '';
    const btn = [...card.querySelectorAll('button')]
      .find(b => (b.textContent || '').includes('推理步骤'));
    if (btn && btn.parentElement) {
      reasoning = (btn.parentElement.textContent || '').trim();
    }
    let answer = '';
    const h3 = [...card.querySelectorAll('h3')]
      .find(e => (e.textContent || '').trim() === '最终答案');
    if (h3) {
      const header = h3.closest('div.border-b') || h3.parentElement;
      const body = header ? header.nextElementSibling : null;
      answer = body ? (body.textContent || '').trim() : '';
    }
    if (!answer) answer = (card.textContent || '').trim();
    const m = (card.textContent || '').match(/\\d{4}\\/\\d{2}\\/\\d{2} \\d{2}:\\d{2}:\\d{2}/);
    turns.push({
      role: 'assistant',
      reasoning_steps: reasoning,
      answer: answer,
      timestamp: m ? m[0] : '',
    });
  });
  return {url: location.href, turns};
}
"""


def _session_id(url: str) -> str:
    """从会话 URL（/chat/<uuid>）取会话 id，作切换前后身份对号锚点。"""
    path = url.split("?", 1)[0].split("#", 1)[0].rstrip("/")
    return path.rsplit("/", 1)[-1] if "/" in path else ""


class AmlChatPage(BasePage):
    page_name = "aml_chat"

    def dismiss_onboarding(self) -> None:
        """关闭新手引导弹窗/横幅（幂等：不存在时直接返回）。"""
        for _ in range(3):
            for label in _DISMISS_TEXTS:
                btn = self.page.get_by_text(label, exact=True)
                if btn.count():
                    try:
                        btn.first.click(timeout=2000)
                        self.page.wait_for_timeout(800)
                        break
                    except Exception:  # noqa: BLE001 - 单个按钮失效尝试下一个
                        continue
            else:
                return

    def select_agent_mode(
        self, mode: str = "专家模式", timeout_ms: int = 30000
    ) -> None:
        """处理延迟弹出的「选择 Agent 类型」弹窗：选定模式并确认（幂等）。

        弹窗是全屏遮罩（fixed inset-0），出现时盖住会话区、拦截点击，
        且出现时机有延迟；在 timeout_ms 内等待，未出现视为本会话已选过。
        """
        if not self.wait_until(
            lambda: self.count("agent_mode_dialog") > 0,
            timeout_ms=timeout_ms,
            interval_ms=500,
        ):
            return
        if mode not in _MODE_LOCATORS:
            raise ValueError(
                f"未知 Agent 模式 {mode!r}，可选 {sorted(_MODE_LOCATORS)}"
            )
        self.loc(_MODE_LOCATORS[mode]).click()
        self.loc("agent_mode_confirm").click()
        self.wait_until(
            lambda: self.count("agent_mode_dialog") == 0, timeout_ms=5_000, interval_ms=300
        )

    def new_session(self) -> None:
        self.loc("new_chat_button").click()

    def switch_session(
        self,
        tag: str = "",
        title: str = "",
        expect_text: str = "",
        forbid_text: str = "",
        timeout_ms: int = 30_000,
    ) -> dict:
        """切换到指定会话并做逐会话身份核对（多会话并行切换语义原语）。

        身份锚点 = 会话 URL（/chat/<uuid>，探查事实 2026-09-28）：会话标题异步生效
        （首条消息/LLM 生成，繁忙时滞后分钟级），只作行定位快路径与观察证据。
        切换路径：先试点击侧边栏会话行（真实用户手势，标题就绪即命中），
        超时回退 goto 记录的会话 URL（send_message 时写入 flow_state）。
        核对三点：URL 对号、会话内含 expect_text 回显、不含 forbid_text；
        串台 / 切换未生效即 EvidenceError 冻结取证（不自愈）。
        """
        state = self.flow_state
        key = tag or title or expect_text
        recorded_url = state.get(key, "")
        if not recorded_url and title:
            for k, v in state.items():
                if title in k or k in title:
                    recorded_url = v
                    break

        switched_by = ""
        row_budget = min(timeout_ms / 1000, 12)
        if title and self.wait_until(
            lambda: self.loc_all("session_row").filter(has_text=title).count() > 0,
            timeout_ms=int(row_budget * 1000),
            interval_ms=500,
        ):
            self.loc_all("session_row").filter(has_text=title).first.click()
            switched_by = "row_click"
        if not switched_by:
            if not recorded_url:
                self.fail_evidence(
                    "会话未切换：无可用锚点",
                    classification="identity_mismatch",
                    cause="切换目标无锚点（标题未生效且无记录 URL）",
                    repro={"url": self.page.url, "tag": key, "title": title},
                    detail=(
                        f"tag={key!r} 无记录 URL，标题 {title!r} 的会话行 "
                        f"{row_budget:.0f}s 内也未出现"
                    ),
                    shot_name="session-switch-no-anchor",
                )
            self.page.goto(recorded_url, wait_until="domcontentloaded")
            switched_by = "goto_url"

        # 切换落定 + 身份三点核对（确定性内容，不看 LLM 措辞）
        # 注：切换期「加载对话历史中」是产品已知偶发缺陷占位（AGENTS.md），
        # 不在此处判死——内容未渲染时放行给 wait_reply_done（六信号含 history_cleared）
        # 接力判定，保证用例等到最终回答才收尾；URL 对号 / 串台仍判 fail。
        now_url, body, header = self.page.url, "", ""
        url_ok = expect_ok = forbid_ok = False
        msgs = 0
        t0 = time.time()
        deadline = t0 + 25
        while True:
            now_url = self.page.url
            msgs = self.count("user_message")  # 软计数：重载水化期元素暂缺不抛错
            body = (
                "\n".join(self.loc("user_message").all_inner_texts()) if msgs else ""
            )
            try:
                header = self.loc("session_header_title").first.inner_text(timeout=1500)
            except Exception:  # noqa: BLE001 - 顶栏未就绪仅影响观察字段
                header = ""
            url_ok = (not recorded_url) or (_session_id(now_url) == _session_id(recorded_url))
            expect_ok = (expect_text in body) if expect_text else True
            forbid_ok = (forbid_text not in body) if forbid_text else True
            if url_ok and expect_ok and forbid_ok:
                break
            # 串台（对方标记混入）需 URL 已对号 + 内容有 5s 交换窗口后才作数，防误判
            if not forbid_ok and url_ok and time.time() - t0 > 5:
                break
            if time.time() >= deadline:
                break
            self.settle(500)
        loading = self.count("history_loading") > 0
        deferred = bool(url_ok and forbid_ok and not expect_ok and (msgs == 0 or loading))
        evidence = {
            "switched_to": key,
            "switched_by": switched_by,
            "session_url": now_url,
            "recorded_url": recorded_url,
            "header_title": header.strip(),
            "url_ok": url_ok,
            "expect_found": expect_ok,
            "forbid_found": not forbid_ok,
            "body_check": "deferred_loading" if deferred else "checked",
        }
        if deferred:
            return evidence  # 内容未渲染完：放行，最终回答完成判定接力核验
        if not (url_ok and expect_ok and forbid_ok):
            self.fail_evidence(
                f"会话切换串台：期望 {key!r}",
                classification="identity_mismatch",
                cause="切换后身份三点核对未过",
                repro={"url": self.page.url, "observed": "切换后身份三点核对未过"},
                detail=(
                    f"url_ok={url_ok}（{now_url} vs {recorded_url}），"
                    f"expect_found={expect_ok}，forbid_found={not forbid_ok}，"
                    f"顶栏={header.strip()!r}"
                ),
                shot_name="session-switch-mismatch",
                extra=evidence,
            )
        return evidence

    def send_message(
        self,
        text: str,
        ready_timeout_ms: int = 30_000,
        tag: str = "",
    ) -> dict:
        """输入并发送消息（Enter），并记录本会话 URL 供 switch_session 精确切换。

        发送前等待会话区就绪（「加载对话历史中」占位消失）；持续卡住则判失败，
        页面原状冻结取证（不自愈——卡住本身就是缺陷）。
        tag：会话身份标记（多会话并行切换用例用；缺省用消息文本作键）。
        """
        self._wait_history_ready(ready_timeout_ms, phase="send_message")
        self.loc("message_input").fill(text)
        self.page.keyboard.press("Enter")  # 产品约定：Enter 发送
        self.page.wait_for_timeout(1500)  # 等路由落到会话 URL（/chat/<uuid>）
        session_url = self.page.url
        self.flow_state[tag or text] = session_url
        return {"sent": text, "session_tag": tag or text, "session_url": session_url}

    def _wait_history_ready(
        self, ready_timeout_ms: int = 30_000, phase: str = "send_message"
    ) -> None:
        """等会话区「加载对话历史中」占位清除；持续卡住即冻结取证（hang_loading）。"""
        if not self.wait_until(
            lambda: self.count("history_loading") == 0,
            timeout_ms=ready_timeout_ms,
            interval_ms=300,
        ):
            self.fail_evidence(
                "会话区未就绪：持续「加载对话历史中」",
                classification="hang_loading",
                cause="会话区持续「加载对话历史中」，操作被阻塞",
                repro={"url": self.page.url, "observed": f"{phase} 阶段"},
                detail=f"占位持续 {ready_timeout_ms}ms，页面保持原状待查",
                shot_name="history-hang",
            )

    def wait_reply_done(self, timeout_ms: int = 120_000) -> None:
        """等待「完整回答」生成结束：思考过程与最终答案都采集到才算完成。

        完成信号（缺一不可，单信号会被 Agent 推理期/半截渲染误判）：
        1. 「停止」按钮消失（流式结束的 UI 状态）
        2. 思考过程组件在场：「推理步骤 · 共 N 步」折叠卡
        3. 最终答案标识在场：「最终答案」卡头
        4. 完成态操作行在场：「重新回答」等按钮（渲染完成才出现）
        5. 会话区文本长度连续 3 次采样不变（内容稳定）
        6. 「加载对话历史中」占位不在场（历史加载完成）

        未达成即判失败，绝不自愈重载（卡死/半截渲染本身就是缺陷，页面原状冻结）。
        失败携带归因分类、复现信息、信号时间线、冻结截图与半截上下文，
        经 EvidenceError.evidence 进报告，供归因总结与复现跟进。
        """
        hang_since: float | None = None
        hang_shot = ""

        def on_tick(w: SignalWatch) -> None:
            nonlocal hang_since, hang_shot
            if not w.signals.get("history_cleared", True):
                hang_since = hang_since if hang_since is not None else w.elapsed_s
                if not hang_shot and w.elapsed_s - hang_since > 10:
                    hang_shot = self.snap("hang-onset")  # 卡死现场冻结
            else:
                hang_since = None

        watch = self.watch_signals(
            signals=lambda: {
                "stop_cleared": self.count("stop_button") == 0,
                "reasoning_steps": self.count("reasoning_steps") > 0,
                "final_answer_card": self.count("final_answer_card") > 0,
                "reply_actions": self.count("reply_actions") > 0,
                "history_cleared": self.count("history_loading") == 0,
            },
            size=lambda: self.page.evaluate(
                "() => { const m = document.querySelector('main');"
                " return m ? (m.innerText || '').length : 0; }"
            ),
            timeout_ms=timeout_ms,
            on_tick=on_tick,
        )
        if watch.settled:
            return
        self.fail_incomplete(
            "完整回答未达成",
            classify=classify_incomplete,
            watch=watch,
            steps="new_session → select_agent_mode → send_message → wait_reply_done",
            observed=f"send_message 后 {timeout_ms}ms 内完整回答未达成",
            freeze_shots=[hang_shot],
        )

    def capture_context(self) -> dict:
        """采集完整对话上下文：用户输入 + 推理步骤 + 思考过程 + 最终答案。

        返回结构化 dict，由引擎写入 StepEvent.evidence 进报告，供人工核对输入输出。
        """
        return self.build_context(self.page.evaluate(_CAPTURE_JS))
