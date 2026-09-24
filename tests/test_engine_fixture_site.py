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
        assert [e.status for e in result.events] == ["passed"] * 6 + ["planned"]
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
                {"assert": {"type": "text_contains", "page": "agent_chat",
                            "target": "message_list",
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


class TestStepContext:
    def test_step_cm_factory_receives_titles(self, runner):
        titles: list[str] = []

        from contextlib import contextmanager

        @contextmanager
        def factory(title: str):
            titles.append(title)
            yield

        runner.step_cm_factory = factory
        spec = load_flow(Path("flows/example_chat.yaml"))
        result = runner.run(spec)
        assert result.status == "passed"
        assert titles == [
            "do: agent_chat.new_session",
            "do: agent_chat.send_message",
            "do: agent_chat.wait_reply_done",
            "do: agent_chat.capture_context",
            "assert: visible message_list",
            "assert: text_contains message_list",
        ]


class TestEvidenceCapture:
    """动作返回的结构化采集数据（对话上下文）进事件证据，供报告核对输入输出。"""

    def test_capture_context_records_turns(self, runner):
        spec = load_flow(Path("flows/example_chat.yaml"))
        result = runner.run(spec)
        assert result.status == "passed"
        capture = next(
            e for e in result.events if e.detail.endswith("capture_context")
        )
        assert capture.evidence["turn_count"] == 2
        turns = capture.evidence["turns"]
        assert [t["role"] for t in turns] == ["user", "assistant"]
        assert turns[0]["text"] == "你好，夹具"
        assert turns[1]["answer"]  # 回答正文完整采集
        assert capture.evidence["url"] and capture.evidence["captured_at"]

    def test_non_capture_action_has_empty_evidence(self, runner):
        spec = load_flow(Path("flows/example_chat.yaml"))
        result = runner.run(spec)
        send = next(e for e in result.events if e.detail.endswith("send_message"))
        assert send.evidence == {}


class TestEvidenceOnFailure:
    """失败动作携带的归因证据（EvidenceError.evidence）进失败事件。"""

    def test_failed_action_records_evidence_and_screenshot(
        self, apw_driver, apw_repo, tmp_path
    ):
        from apw.engine.registry import PageRegistry
        from apw.engine.runner import FlowRunner
        from apw.pages.base import EvidenceError

        class HangPage:
            def __init__(self, *, page, repo):
                self.page = page
                self.repo = repo

            def explode(self):
                raise EvidenceError(
                    "完整回答未达成［归因: hang_loading］",
                    {"classification": "hang_loading", "repro": {"url": "x"}},
                )

        registry = PageRegistry()
        registry.register("hang", HangPage)
        runner = FlowRunner(
            page=apw_driver.page,
            repo=apw_repo,
            pages=registry,
            screenshot_dir=tmp_path,
        )
        spec = FlowSpec(
            meta=FlowMeta(id="neg4", name="负例4"),
            steps=[parse_step({"do": {"page": "hang", "action": "explode"}}, 0)],
        )
        result = runner.run(spec)
        event = result.events[-1]
        assert event.status == "failed"
        assert "hang_loading" in event.error
        assert event.evidence["classification"] == "hang_loading"
        assert event.screenshot and Path(event.screenshot).exists()


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

    def test_prepare_failure_records_failed_event_and_report(
        self, apw_driver, apw_repo, apw_pages, tmp_path
    ):
        """准备（导航）失败也是终态留痕：失败事件 + 明细 JSON + 汇总 failed，不再凭空消失。"""
        from apw.engine.runner import FlowRunner
        from apw.reporter.json_report import JsonReporter

        def boom():
            raise RuntimeError("导航失败")

        reporter = JsonReporter(tmp_path / "reports")
        runner = FlowRunner(
            page=apw_driver.page,
            repo=apw_repo,
            pages=apw_pages,
            prepare=boom,
            reporter=reporter,
            screenshot_dir=tmp_path,
        )
        spec = FlowSpec(
            meta=FlowMeta(id="prep-fail", name="准备失败"),
            steps=[parse_step({"judge": {}}, 0)],
        )
        result = runner.run(spec)
        assert result.status == "failed"
        event = result.events[0]
        assert event.status == "failed"
        assert "导航失败" in event.error
        assert event.screenshot and Path(event.screenshot).exists()
        assert event.evidence == {}  # 普通异常证据为空（与步骤失败一致）
        detail = reporter.out_dir / "prep-fail.json"
        assert detail.exists() and "prep-fail" in detail.read_text(encoding="utf-8")
        summary_path = reporter.write_summary()
        assert summary_path and summary_path.exists()
        import json

        summary = json.loads(summary_path.read_text(encoding="utf-8"))
        assert summary["failed"] == 1 and summary["total"] == 1

    def test_prepare_failure_propagates_evidence(
        self, apw_driver, apw_repo, apw_pages, tmp_path
    ):
        """prepare 抛 EvidenceError 时结构化证据原样入失败事件（与步骤失败同构）。"""
        from apw.engine.runner import FlowRunner
        from apw.pages.base import EvidenceError

        def boom():
            raise EvidenceError(
                "导航冻结［归因: hang_loading］",
                {"classification": "hang_loading", "repro": {"url": "x"}},
            )

        runner = FlowRunner(
            page=apw_driver.page,
            repo=apw_repo,
            pages=apw_pages,
            prepare=boom,
            screenshot_dir=tmp_path,
        )
        spec = FlowSpec(
            meta=FlowMeta(id="prep-evi", name="准备取证"),
            steps=[parse_step({"judge": {}}, 0)],
        )
        result = runner.run(spec)
        event = result.events[0]
        assert event.status == "failed"
        assert event.evidence["classification"] == "hang_loading"
        assert event.evidence["repro"] == {"url": "x"}


class TestTriStateSummary:
    """跳过也是终态留痕：明细带原因，汇总三态分列，skipped 不计入 passed。"""

    def test_skipped_flow_recorded_with_reason(self, tmp_path):
        import json

        from apw.engine.events import FlowResult
        from apw.reporter.json_report import JsonReporter

        reporter = JsonReporter(tmp_path / "reports")
        reporter.write_flow(
            FlowResult(
                flow_id="s1",
                name="跳过例",
                platforms=["desktop"],
                status="skipped",
                skip_reason="平台不匹配：flow 需要 ['desktop']，当前 web",
            )
        )
        summary = json.loads(reporter.write_summary().read_text(encoding="utf-8"))
        assert summary["skipped"] == 1
        assert summary["passed"] == 0 and summary["failed"] == 0
        assert summary["flows"][0]["skip_reason"].startswith("平台不匹配")

    def test_empty_steps_fails_not_passed(self, runner):
        """引擎兜底：即使绕过加载校验拿到空步骤，也判 failed 而非刷绿。"""
        from apw.dsl.schema import FlowSpec

        spec = FlowSpec.model_construct(
            meta=FlowMeta(id="empty", name="空壳"), steps=[]
        )
        result = runner.run(spec)
        assert result.status == "failed"
        assert result.error  # 明确错误信息，不得为 passed
