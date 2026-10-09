"""桌面客户端会话页（Electron 打包的 Web 界面，CDP attach 驱动）。

由爬虫快照探查生成（2026-10-08）。与 web 版 AmlChatPage 语义对齐但结构不同：
组合器是 contenteditable 富输入（真实键入 + Enter 发送）；生成中发送键变
「停止生成」（button.btn-send.btn-stop）；完成态渲染 Thought 折叠块 + 回答气泡 + 操作行。
完成判定要求「完整回答」（见 wait_reply_done）；失败即取证，不自愈。
"""
from __future__ import annotations

from apw.pages.base import BasePage, SignalWatch

# 结构采集专用 DOM 内省：按语义标记取对话上下文（容忍样式改名，尽力而为）
_CAPTURE_JS = """
() => {
  const turns = [];
  document.querySelectorAll('div.chat-turn').forEach(turn => {
    turn.querySelectorAll('div.message').forEach(msg => {
      if (msg.classList.contains('user')) {
        const bubble = msg.querySelector('div.user-message-content div.bubble');
        if (bubble) turns.push({role: 'user', text: (bubble.textContent || '').trim()});
        return;
      }
      const thinkingEl = msg.querySelector('details.msg-thinking');
      const thinkingBody = msg.querySelector('.msg-thinking-body');
      const tools = [...msg.querySelectorAll('.msg-tool-title')]
        .map(e => (e.textContent || '').trim()).filter(Boolean);
      const bubble = msg.querySelector('div.bubble.markdown-bubble')
        || msg.querySelector('div.bubble');
      turns.push({
        role: 'assistant',
        reasoning_steps: thinkingBody ? (thinkingBody.textContent || '').trim() : '',
        thinking_label: thinkingEl ? (thinkingEl.textContent || '').trim().slice(0, 40) : '',
        tool_calls: tools.join(' | '),
        answer: bubble ? (bubble.textContent || '').trim() : '',
      });
    });
  });
  return {url: location.href, turns};
}
"""

_MSG_ID_JS = """
() => {
  const rows = document.querySelectorAll('div.message.user');
  const el = rows[rows.length - 1];
  return el ? (el.getAttribute('data-message-id') || '') : '';
}
"""

# Thought 折叠块结构内省：正文仅展开后渲染（探查事实 2026-10-08）
_THINKING_JS = """
() => {
  const blocks = [...document.querySelectorAll('details.msg-thinking')];
  const states = blocks.map(el => ({
    open: el.hasAttribute('open'),
    body_text: (el.querySelector('.msg-thinking-body') || {}).textContent
      ? el.querySelector('.msg-thinking-body').textContent.trim() : '',
  }));
  return {count: blocks.length, states, last: states[states.length - 1] || null};
}
"""


def classify_incomplete(signals: dict) -> tuple[str, str]:
    """归因「完整回答未达成」：(分类, 说明)。归因与复现线索随证据入报告。"""
    if not signals.get("user_echo", True):
        return (
            "send_stuck",
            "用户消息未落列：输入未提交成功或会话区未渲染（组合器提交链路异常）",
        )
    if not signals.get("stop_cleared", True):
        return (
            "streaming_stuck",
            "「停止生成」按钮仍在：生成未结束（服务端生成挂起或超长）",
        )
    missing = [
        k
        for k in ("assistant_reply", "thinking", "reply_actions")
        if not signals.get(k)
    ]
    if missing:
        return "reply_incomplete", f"回答结构不完整（半截渲染）：缺 {', '.join(missing)}"
    return "content_unstable", "回答内容持续变化未稳定（文本长度未收敛）"


class DesktopChatPage(BasePage):
    page_name = "desktop_chat"

    def new_task(self, ready_timeout_ms: int = 10_000) -> dict:
        """新建任务（新会话）：点击侧边栏「新任务」并等会话区清空落定。

        新任务应清空会话区（探查事实 2026-10-08）；未清空即旧会话残留，
        后续判定会串台——判失败冻结取证（不自愈）。
        """
        self.loc("new_task_button").click()
        if not self.wait_until(
            lambda: self.count("user_message") == 0,
            timeout_ms=ready_timeout_ms,
            interval_ms=300,
        ):
            self.fail_evidence(
                "新建任务未清空会话区：仍有历史消息",
                classification="identity_mismatch",
                cause="新任务未清空会话区，旧会话残留会串台",
                repro={"observed": "new_task 后 user_message 仍在场"},
                detail=f"「新任务」后 {ready_timeout_ms}ms 会话区未重置，页面原状冻结",
                shot_name="new-task-not-fresh",
            )
        return {"new_task": "cleared"}

    def send_message(self, text: str, tag: str = "") -> dict:
        """真实键入并 Enter 发送（产品约定：Enter 发送，Shift+Enter 换行）。

        组合器是 contenteditable 富输入，走真实键入（与工作流编辑器同陷阱）；
        发送后记录用户消息 data-message-id 作身份锚点（无会话 URL 可用）。
        """
        self.loc("message_input").click()
        self.loc("message_input").type(text, delay=20)
        self.page.keyboard.press("Enter")
        self.page.wait_for_timeout(1500)  # 等消息落列 + 生成启动
        message_id = self.page.evaluate(_MSG_ID_JS)
        self.flow_state[tag or text] = message_id
        return {"sent": text, "message_tag": tag or text, "message_id": message_id}

    def expand_thinking(self, timeout_ms: int = 5_000) -> dict:
        """展开末条回答的 Thought 折叠块并核对展开生效。

        探查事实（2026-10-08）：折叠态 details 仅 summary（正文不渲染），
        点击 summary 后 details[open] + .msg-thinking-body 渲染思考正文。
        核对两点：块已 open、正文渲染且非空；未生效即 EvidenceError 冻结取证。
        """
        state = self.page.evaluate(_THINKING_JS)
        if not state.get("count"):
            self.fail_evidence(
                "Thought 块缺失：无法展开",
                classification="reply_incomplete",
                cause="Thought 折叠块缺失，展开无从谈起",
                repro={"url": self.page.url, "observed": "expand_thinking 前置检查"},
                detail="末条回答无 details.msg-thinking（产品口径应恒在场），页面原状冻结",
                shot_name="thinking-missing",
            )
        if not (state["last"] or {}).get("body_text"):
            try:
                self.loc_all("thinking_summary").last.click()
            except Exception:  # noqa: BLE001 - 点击失败走下方统一取证
                pass

            def body_rendered() -> bool:
                nonlocal state
                state = self.page.evaluate(_THINKING_JS)
                return bool((state["last"] or {}).get("body_text"))

            self.wait_until(body_rendered, timeout_ms=timeout_ms, interval_ms=200)
        last = state.get("last") or {}
        if not (last.get("open") and last.get("body_text")):
            self.fail_evidence(
                "Thought 展开未生效",
                classification="thinking_expand_failed",
                cause="点击 Thought summary 后 details 未 open 或思考正文未渲染",
                repro={
                    "url": self.page.url,
                    "observed": (
                        f"open={last.get('open')} "
                        f"body_chars={len(last.get('body_text') or '')}"
                    ),
                },
                detail=(
                    f"open={last.get('open')}，正文字符数={len(last.get('body_text') or '')}"
                    f"（点击 summary 后 {timeout_ms}ms 内未渲染思考正文），页面原状冻结"
                ),
                shot_name="thinking-expand-failed",
            )
        return {
            "thinking_expanded": True,
            "thinking_blocks": state.get("count"),
            "body_chars": len(last.get("body_text") or ""),
        }

    def wait_reply_done(self, timeout_ms: int = 120_000) -> None:
        """等待「完整回答」生成结束（判定信号缺一不可，稳定采样收敛才算完成）：

        1. 用户消息在场：发送已落列（user_echo）
        2. 「停止生成」按钮消失（btn-stop 清除 = 流式结束的 UI 状态）
        3. 回答气泡在场：最终回答已渲染
        4. Thought 折叠块在场：思考过程组件已渲染（产品口径恒在场；正文展开才渲染，
           展开交互见 expand_thinking）
        5. 完成态操作行在场（复制/从此处分叉/喜欢…，渲染完成才出现）
        6. 会话区文本长度连续 3 次采样不变（内容稳定）

        流式已结束且内容稳定 5 采样仍缺结构信号 = 半截渲染，立即判失败取证
        （不空等满超时）。未达成即判失败，绝不自愈重载（页面原状冻结）。
        """
        stall_shot = ""

        def on_tick(w: SignalWatch) -> None:
            nonlocal stall_shot
            # 发送后长时间零回复渲染 = 卡死现场，冻结一份快照供归因
            if (
                not stall_shot
                and w.signals.get("user_echo")
                and not w.signals.get("assistant_reply")
                and w.elapsed_s > 20
            ):
                stall_shot = self.snap("stall-onset")

        watch = self.watch_signals(
            signals=lambda: {
                "user_echo": self.count("user_message") > 0,
                "stop_cleared": self.count("stop_button") == 0,
                "assistant_reply": self.count("assistant_reply") > 0,
                "thinking": self.count("thinking") > 0,
                "reply_actions": self.count("reply_actions") > 0,
            },
            size=lambda: self.page.evaluate(
                "() => { const m = document.querySelector('div.messages');"
                " return m ? (m.innerText || '').length : 0; }"
            ),
            timeout_ms=timeout_ms,
            # 稳定计数只认「流式已结束」：结构信号长期缺失时由 give_up 提前收场
            stability_gate=lambda s: s.get("stop_cleared", False),
            on_tick=on_tick,
            give_up=lambda w: w.stable >= 5,  # 已稳定仍缺结构 = 半截渲染，立即取证
        )
        if watch.settled:
            return
        self.fail_incomplete(
            "完整回答未达成",
            classify=classify_incomplete,
            watch=watch,
            steps="new_task → send_message → wait_reply_done",
            observed=f"send_message 后 {timeout_ms}ms 内完整回答未达成",
            freeze_shots=[stall_shot],
        )

    def capture_context(self) -> dict:
        """采集完整对话上下文：用户输入 + Thought 正文/工具调用 + 最终回答。

        思考正文仅展开时渲染（探查事实）——取证前把未展开的 Thought 块点开，
        尽力而为不影响失败本身。返回结构化 dict，由引擎写入 StepEvent.evidence。
        """
        self._expand_all_thinking()
        return self.build_context(self.page.evaluate(_CAPTURE_JS))

    def _expand_all_thinking(self) -> None:
        """逐个点开尚无思考正文的 Thought 折叠块（取证尽力而为，单块失败跳过）。"""
        try:
            states = self.page.evaluate(_THINKING_JS).get("states") or []
            summaries = self.loc_all("thinking_summary")
            for i, st in enumerate(states):
                if st.get("body_text") or i >= summaries.count():
                    continue
                try:
                    summaries.nth(i).click(timeout=2_000)
                    self.page.wait_for_timeout(150)
                except Exception:  # noqa: BLE001 - 单块展开失败不挡取证
                    continue
        except Exception:  # noqa: BLE001 - 取证尽力而为
            pass
