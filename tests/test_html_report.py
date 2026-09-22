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
             "detail": "agent_chat.send_message", "status": "passed",
             "duration_ms": 40},
            {"flow_id": "demo", "index": 1, "kind": "assert",
             "detail": "", "status": "failed",
             "error": "AssertionError: 期望 <不存在的文本>",
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

    def test_missing_summary_raises(self, tmp_path):
        import pytest

        with pytest.raises(FileNotFoundError):
            render_html(tmp_path)
