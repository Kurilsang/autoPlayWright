"""引擎端到端测试：本地夹具站点上跑通 DSL→引擎→事件流全链路。"""
from __future__ import annotations

from pathlib import Path

import pytest

from apw.dsl.loader import load_flow
from apw.dsl.schema import FlowMeta, FlowSpec, parse_step


@pytest.fixture
def runner(apw_driver, apw_repo, apw_pages, tmp_path):
    from apw.engine.runner import FlowRunner

    return FlowRunner(
        page=apw_driver.page,
        repo=apw_repo,
        pages=apw_pages,
        prepare=apw_driver.goto_base,
        screenshot_dir=tmp_path,
    )


class TestExampleFlow:
    def test_passes_end_to_end(self, runner):
        spec = load_flow(Path("flows/example_chat.yaml"))
        result = runner.run(spec)
        assert result.status == "passed", result.model_dump_json(indent=2)
        assert [e.status for e in result.events] == ["passed"] * 5 + ["planned"]
        judge_event = result.events[-1]
        assert judge_event.kind == "judge"

    def test_report_written(self, runner, tmp_path):
        from apw.reporter.json_report import JsonReporter

        reporter = JsonReporter(tmp_path / "reports")
        runner.reporter = reporter
        spec = load_flow(Path("flows/example_chat.yaml"))
        runner.run(spec)
        summary = reporter.write_summary()
        assert summary and summary.exists()
        detail = reporter.out_dir / f"{spec.meta.id}.json"
        assert detail.exists()
        assert "example-chat" in detail.read_text(encoding="utf-8")


class TestFailurePath:
    def test_failed_assert_records_event_and_screenshot(self, runner):
        steps = [
            parse_step({"do": {"page": "agent_chat", "action": "new_session"}}, 0),
            parse_step(
                {"do": {"page": "agent_chat", "action": "send_message",
                        "args": {"text": "hi"}}},
                1,
            ),
            parse_step(
                {"assert": {"type": "text_contains", "target": "message_list",
                            "expected": "绝不存在的文本", "timeout_ms": 1500}},
                2,
            ),
        ]
        spec = FlowSpec(meta=FlowMeta(id="negative", name="负例"), steps=steps)
        result = runner.run(spec)
        assert result.status == "failed"
        failed = result.events[-1]
        assert failed.status == "failed"
        assert "绝不存在的文本" in failed.error
        assert failed.screenshot and Path(failed.screenshot).exists()

    def test_unknown_action_fails_step(self, runner):
        spec = FlowSpec(
            meta=FlowMeta(id="neg2", name="负例2"),
            steps=[parse_step(
                {"do": {"page": "agent_chat", "action": "no_such_action"}}, 0
            )],
        )
        result = runner.run(spec)
        assert result.status == "failed"
        assert "no_such_action" in result.events[-1].error

    def test_unknown_page_fails_step(self, runner):
        spec = FlowSpec(
            meta=FlowMeta(id="neg3", name="负例3"),
            steps=[parse_step({"do": {"page": "ghost", "action": "x"}}, 0)],
        )
        result = runner.run(spec)
        assert result.status == "failed"
        assert "ghost" in result.events[-1].error


class TestPrepare:
    def test_prepare_called_once_per_flow(self, runner):
        original = runner.prepare
        calls = []

        def prepare():
            calls.append(1)
            if original:
                original()

        runner.prepare = prepare
        spec = FlowSpec(
            meta=FlowMeta(id="p", name="prepare"),
            steps=[parse_step({"judge": {}}, 0)],
        )
        runner.run(spec)
        assert len(calls) == 1
