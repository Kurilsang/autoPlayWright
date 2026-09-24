"""HTML 渲染层测试：从 run 目录产物渲染单文件报告。"""
from __future__ import annotations

import json
from pathlib import Path

from apw.reporter.html_report import render_html


def _write_run(tmp_path: Path) -> Path:
    run_dir = tmp_path / "20260922-000000"
    run_dir.mkdir(parents=True)
    flow = {
        "flow_id": "demo",
        "name": "演示链路",
        "platforms": ["web"],
        "status": "failed",
        "duration_ms": 1234,
        "events": [
            {"flow_id": "demo", "index": 0, "kind": "do",
             "detail": "agent_chat.capture_context", "status": "passed",
             "evidence": {
                 "url": "file:///demo", "captured_at": "2026-09-23T00:00:00",
                 "turn_count": 2,
                 "turns": [
                     {"role": "user", "text": "你好，夹具"},
                     {"role": "assistant", "answer": "思考过程：想一想\n最终答案：收到",
                      "thinking": "想一想", "final_answer": "收到",
                      "timestamp": "2026/09/23 00:00:00"},
                 ],
             },
             "duration_ms": 40},
            {"flow_id": "demo", "index": 1, "kind": "assert",
             "detail": "", "status": "failed",
             "error": "AssertionError: 期望 <不存在的文本>",
             "evidence": {"classification": "hang_loading",
                          "cause": "会话区卡加载",
                          "repro": {"url": "http://demo/chat", "observed": "复现步骤"}},
             "screenshot": "demo-step01.png", "duration_ms": 900},
            {"flow_id": "demo", "index": 2, "kind": "judge",
             "detail": "预留", "status": "planned", "duration_ms": 0},
        ],
    }
    (run_dir / "demo.json").write_text(
        json.dumps(flow, ensure_ascii=False), encoding="utf-8"
    )
    summary = {"run_id": "20260922-000000", "total": 1, "passed": 0, "failed": 1,
               "flows": [{"flow_id": "demo", "name": "演示链路",
                          "status": "failed", "duration_ms": 1234,
                          "detail": "demo.json"}]}
    (run_dir / "run-summary.json").write_text(
        json.dumps(summary, ensure_ascii=False), encoding="utf-8"
    )
    return run_dir


class TestRenderHtml:
    def test_renders_report(self, tmp_path):
        run_dir = _write_run(tmp_path)
        out = render_html(run_dir)
        assert out == run_dir / "report.html"
        text = out.read_text(encoding="utf-8")
        assert "demo" in text and "演示链路" in text
        # 三种步骤状态都有徽章
        for token in ("passed", "failed", "planned"):
            assert token in text
        # 失败明细与截图引用
        assert "不存在的文本" in text
        assert 'src="demo-step01.png"' in text
        # HTML 转义生效（错误文本不会被当标签）
        assert "<不存在的文本>" not in text
        # 对话上下文证据按轮渲染（用户输入 / 思考过程 / 最终答案）
        assert "上下文采集 · 2 轮" in text
        assert "用户输入" in text and "你好，夹具" in text
        assert "[思考过程]" in text and "[最终答案]" in text
        # 失败归因与复现信息渲染
        assert "归因与复现" in text and "hang_loading" in text
        # 旧格式汇总（无 skipped 键）向后兼容：三态统计卡默认 0
        assert "跳过</span>" in text

    def test_missing_summary_raises(self, tmp_path):
        import pytest

        with pytest.raises(FileNotFoundError):
            render_html(tmp_path)

    def test_renders_skipped_with_reason(self, tmp_path):
        """三态渲染：skipped 徽章 + 跳过原因 + 汇总三态统计卡。"""
        run_dir = tmp_path / "20260922-000001"
        run_dir.mkdir(parents=True)
        reason = "平台不匹配：flow 需要 ['desktop']，当前 web"
        flow = {
            "flow_id": "skip1", "name": "跳过例", "platforms": ["desktop"],
            "status": "skipped", "skip_reason": reason,
            "duration_ms": 0, "events": [],
        }
        (run_dir / "skip1.json").write_text(
            json.dumps(flow, ensure_ascii=False), encoding="utf-8"
        )
        summary = {
            "run_id": "20260922-000001", "total": 1,
            "passed": 0, "failed": 0, "skipped": 1,
            "flows": [{"flow_id": "skip1", "name": "跳过例", "status": "skipped",
                       "duration_ms": 0, "detail": "skip1.json",
                       "skip_reason": reason}],
        }
        (run_dir / "run-summary.json").write_text(
            json.dumps(summary, ensure_ascii=False), encoding="utf-8"
        )
        text = render_html(run_dir).read_text(encoding="utf-8")
        assert "- skipped" in text  # 徽章图标+状态对（非裸文本）
        assert "跳过原因" in text and "平台不匹配" in text
        assert "跳过</span>" in text  # 三态统计卡
