"""Aml Agent 会话页（真实环境）。

由 AI 爬取页面结构生成（T07 预演）。动作语义与夹具 AgentChatPage 对齐，
选择器差异由定位器仓库吸收；流式完成判定用「停止按钮消失 + 文本长度稳定」双信号。
"""
from __future__ import annotations

import time

from apw.pages.base import BasePage

_DISMISS_TEXTS = ("稍后再看", "我已熟悉", "关闭提示", "关闭")


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

    def new_session(self) -> None:
        self.loc("new_chat_button").click()

    def send_message(self, text: str) -> None:
        self.loc("message_input").fill(text)
        self.page.keyboard.press("Enter")  # 产品约定：Enter 发送

    def wait_reply_done(self, timeout_ms: int = 120_000) -> None:
        """等待流式回复完成。

        双信号（缺一不可，单信号会被 Agent 推理期误判）：
        1. 「停止」按钮消失（流式结束的 UI 状态）
        2. 会话区文本长度连续 3 次采样不变（内容稳定）
        """
        deadline = time.time() + timeout_ms / 1000
        stable, last_len = 0, -1
        while time.time() < deadline:
            time.sleep(1)
            stop = self.count("stop_button")
            length = self.page.evaluate(
                "() => { const m = document.querySelector('main');"
                " return m ? (m.innerText || '').length : 0; }"
            )
            if stop == 0 and length == last_len and length > 0:
                stable += 1
                if stable >= 3:
                    return
            else:
                stable = 0
            last_len = length
        raise TimeoutError(f"等待回复完成超时（{timeout_ms}ms）")
