"""Agent 会话页：夹具站点与真实环境共用同一组动作语义，选择器差异由仓库吸收。"""
from __future__ import annotations

from apw.pages.base import BasePage


class AgentChatPage(BasePage):
    page_name = "agent_chat"

    def new_session(self) -> None:
        """新建会话，清空当前消息列表。"""
        self.loc("new_chat_button").click()

    def send_message(self, text: str) -> None:
        self.loc("chat_input").fill(text)
        self.loc("send_button").click()

    def wait_reply_done(self, timeout_ms: int = 30_000) -> None:
        """等待流式输出结束。

        v1 信号：生成中指示器隐藏。可配置多信号（发送按钮状态等）在断言体系票中补全。
        """
        self.loc("streaming_indicator").wait_for(state="hidden", timeout=timeout_ms)
