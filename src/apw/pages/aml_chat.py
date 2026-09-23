"""被测 Agent 会话页（真实环境）。

由 AI 爬取页面结构生成（T07 预演）。动作语义与夹具 AgentChatPage 对齐，
选择器差异由定位器仓库吸收；完成判定要求「完整回答」：思考过程与最终答案
的结构标记都渲染出来才算结束（见 wait_reply_done）。
"""
from __future__ import annotations

import time

from apw.pages.base import BasePage, EvidenceError

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
        deadline = time.time() + timeout_ms / 1000
        while self.count("agent_mode_dialog") == 0 and time.time() < deadline:
            time.sleep(0.5)
        if self.count("agent_mode_dialog") == 0:
            return
        if mode not in _MODE_LOCATORS:
            raise ValueError(
                f"未知 Agent 模式 {mode!r}，可选 {sorted(_MODE_LOCATORS)}"
            )
        self.loc(_MODE_LOCATORS[mode]).click()
        self.loc("agent_mode_confirm").click()
        close_deadline = time.time() + 5
        while self.count("agent_mode_dialog") and time.time() < close_deadline:
            time.sleep(0.3)

    def new_session(self) -> None:
        self.loc("new_chat_button").click()

    def send_message(self, text: str, ready_timeout_ms: int = 30_000) -> None:
        """输入并发送消息（Enter）。

        发送前等待会话区就绪（「加载对话历史中」占位消失）；持续卡住则判失败，
        页面原状冻结取证（不自愈——卡住本身就是缺陷）。
        """
        deadline = time.time() + ready_timeout_ms / 1000
        while self.count("history_loading") and time.time() < deadline:
            time.sleep(0.3)
        if self.count("history_loading"):
            shot = self.snap("send-blocked")
            raise EvidenceError(
                "消息未发送［归因: hang_loading］会话区持续「加载对话历史中」"
                f"（{ready_timeout_ms}ms），页面保持原状待查\n"
                f"  复现: url={self.page.url}\n"
                f"  冻结截图: {shot or '（未捕获）'}",
                {
                    "classification": "hang_loading",
                    "cause": "会话区持续「加载对话历史中」，发送被阻塞",
                    "repro": {"url": self.page.url, "observed": "send_message 阶段"},
                    "screenshots": [shot] if shot else [],
                },
            )
        self.loc("message_input").fill(text)
        self.page.keyboard.press("Enter")  # 产品约定：Enter 发送

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
        t0 = time.time()
        deadline = t0 + timeout_ms / 1000
        stable, last_len, signals, prev = 0, -1, {}, None
        timeline: list[dict] = []
        hang_since: float | None = None
        hang_shot = ""
        tick = 0
        while time.time() < deadline:
            time.sleep(1)
            tick += 1
            signals = {
                "stop_cleared": self.count("stop_button") == 0,
                "reasoning_steps": self.count("reasoning_steps") > 0,
                "final_answer_card": self.count("final_answer_card") > 0,
                "reply_actions": self.count("reply_actions") > 0,
                "history_cleared": self.count("history_loading") == 0,
            }
            length = self.page.evaluate(
                "() => { const m = document.querySelector('main');"
                " return m ? (m.innerText || '').length : 0; }"
            )
            if signals != prev or tick % 10 == 0:
                timeline.append({"t_s": tick, "text_len": length, **signals})
                prev = dict(signals)
            if not signals["history_cleared"]:
                hang_since = hang_since or time.time()
                if not hang_shot and time.time() - hang_since > 10:
                    hang_shot = self.snap("hang-onset")  # 卡死现场冻结
            else:
                hang_since = None
            if all(signals.values()) and length == last_len and length > 0:
                stable += 1
                if stable >= 3:
                    return
            else:
                stable = 0
            last_len = length
        self._fail_incomplete(signals, timeline, timeout_ms, hang_shot)

    def _fail_incomplete(
        self, signals: dict, timeline: list[dict], timeout_ms: int, hang_shot: str
    ) -> None:
        """完整回答未达成：归因分类 + 复现信息 + 冻结取证，抛 EvidenceError。"""
        category, cause = classify_incomplete(signals)
        shots = [s for s in (hang_shot, self.snap("timeout")) if s]
        repro = {
            "url": self.page.url,
            "observed": f"send_message 后 {timeout_ms}ms 内完整回答未达成",
            "steps": "new_session → select_agent_mode → send_message → wait_reply_done",
        }
        evidence: dict = {
            "classification": category,
            "cause": cause,
            "signals": signals,
            "timeline": timeline,
            "repro": repro,
            "screenshots": shots,
        }
        try:
            evidence.update(self.capture_context())  # 半截上下文一并取证
        except Exception:  # noqa: BLE001 - 取证尽力而为
            pass
        summary = (
            f"完整回答未达成［归因: {category}］{cause}\n"
            f"  信号: {signals}\n"
            f"  时间线: {len(timeline)} 个采样点（1s 粒度，0..{timeout_ms // 1000}s）\n"
            f"  复现: {repro['steps']} @ {repro['url']}，观察: {repro['observed']}\n"
            f"  冻结截图: {', '.join(shots) if shots else '（未捕获）'}"
        )
        raise EvidenceError(summary, evidence)

    def capture_context(self) -> dict:
        """采集完整对话上下文：用户输入 + 推理步骤 + 思考过程 + 最终答案。

        返回结构化 dict，由引擎写入 StepEvent.evidence 进报告，供人工核对输入输出。
        """
        return self.build_context(self.page.evaluate(_CAPTURE_JS))
