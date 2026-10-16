"""BasePage 纯函数测试：回答正文按标记拆分 + 未达成归因分类。"""
from __future__ import annotations

from apw.pages.aml_chat import classify_incomplete
from apw.pages.base import split_marked_sections


class TestClassifyIncomplete:
    """「完整回答未达成」归因分类：卡死/挂流式/半截渲染/未收敛。"""

    def test_hang_loading(self):
        category, cause = classify_incomplete(
            {"history_cleared": False, "stop_cleared": True}
        )
        assert category == "hang_loading"
        assert "加载对话历史中" in cause and "复现线索" in cause

    def test_streaming_stuck(self):
        category, cause = classify_incomplete(
            {"history_cleared": True, "stop_cleared": False}
        )
        assert category == "streaming_stuck"
        assert "停止" in cause

    def test_reply_incomplete_lists_missing(self):
        category, cause = classify_incomplete(
            {
                "history_cleared": True,
                "stop_cleared": True,
                "reasoning_steps": True,
                "final_answer_card": False,
                "reply_actions": False,
            }
        )
        assert category == "reply_incomplete"
        assert "final_answer_card" in cause and "reply_actions" in cause

    def test_content_unstable(self):
        category, _ = classify_incomplete(
            {
                "history_cleared": True,
                "stop_cleared": True,
                "reasoning_steps": True,
                "final_answer_card": True,
                "reply_actions": True,
            }
        )
        assert category == "content_unstable"


class TestSplitMarkedSections:
    def test_splits_thinking_and_final(self):
        thinking, final = split_marked_sections(
            "思考过程：先判断因数\n最终答案：是质数"
        )
        assert thinking == "先判断因数"
        assert final == "是质数"

    def test_final_only(self):
        thinking, final = split_marked_sections("最终答案：42")
        assert thinking == ""
        assert final == "42"

    def test_no_marker_keeps_whole(self):
        thinking, final = split_marked_sections("普通回答，无标记")
        assert thinking == ""
        assert final == "普通回答，无标记"

    def test_reversed_markers_fallback(self):
        thinking, final = split_marked_sections("最终答案：结论\n思考过程：晚到的段")
        assert thinking == ""
        assert final.startswith("结论")
