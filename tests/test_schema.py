"""DSL schema 测试：合法/非法 flow 的解析行为。"""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from apw.dsl.loader import load_flow
from apw.dsl.schema import AssertStep, DoStep, JudgeStep, parse_step


def _minimal_flow_dict(steps: list[dict]) -> dict:
    return {
        "meta": {"id": "t", "name": "测试链路"},
        "steps": steps,
    }


class TestParseStep:
    def test_do_step(self):
        step = parse_step({"do": {"page": "agent_chat", "action": "send_message"}}, 0)
        assert isinstance(step, DoStep)
        assert step.do.page == "agent_chat"

    def test_assert_step_with_alias(self):
        step = parse_step({"assert": {"type": "visible", "target": "message_list"}}, 0)
        assert isinstance(step, AssertStep)
        assert step.assert_.type == "visible"

    def test_judge_step_reserved(self):
        step = parse_step({"judge": {"note": "预留"}}, 0)
        assert isinstance(step, JudgeStep)

    def test_multiple_keys_rejected(self):
        raw = {
            "do": {"page": "p", "action": "a"},
            "assert": {"type": "visible", "target": "t"},
        }
        with pytest.raises(ValueError, match="必须且只能包含"):
            parse_step(raw, 0)

    def test_unknown_key_rejected(self):
        with pytest.raises(ValueError, match="必须且只能包含"):
            parse_step({"sleep": 3}, 0)

    def test_non_dict_rejected(self):
        with pytest.raises(ValueError, match="必须是映射"):
            parse_step("click", 0)


class TestAssertAction:
    def test_unknown_assert_type_rejected(self):
        with pytest.raises(ValidationError):
            parse_step({"assert": {"type": "screenshot_equals", "target": "x"}}, 0)

    def test_text_contains_defaults(self):
        step = parse_step({"assert": {"type": "text_contains", "target": "list"}}, 0)
        assert step.assert_.timeout_ms == 10_000


class TestLoadFlow:
    def test_minimal_flow(self, tmp_path):
        f = tmp_path / "t.yaml"
        f.write_text(
            "meta:\n  id: t\n  name: n\nsteps:\n"
            "  - do: {page: agent_chat, action: new_session}\n",
            encoding="utf-8",
        )
        spec = load_flow(f)
        assert spec.meta.id == "t"
        assert spec.meta.platforms == ["web"]
        assert len(spec.steps) == 1

    def test_missing_meta_rejected(self, tmp_path):
        f = tmp_path / "bad.yaml"
        f.write_text("steps: []\n", encoding="utf-8")
        with pytest.raises(ValueError, match="缺少 meta"):
            load_flow(f)

    def test_bad_step_fails_at_load(self, tmp_path):
        f = tmp_path / "bad.yaml"
        f.write_text(
            "meta: {id: t, name: n}\nsteps:\n  - click: x\n", encoding="utf-8"
        )
        with pytest.raises(ValueError, match="必须且只能包含"):
            load_flow(f)

    def test_empty_steps_rejected_at_load(self, tmp_path):
        """空壳用例收集期即拒绝（非法 DSL 收集期报错），不得进入执行。"""
        f = tmp_path / "empty.yaml"
        f.write_text("meta: {id: t, name: n}\nsteps: []\n", encoding="utf-8")
        with pytest.raises(ValueError, match="不能为空"):
            load_flow(f)

    def test_missing_steps_rejected_at_load(self, tmp_path):
        f = tmp_path / "nosteps.yaml"
        f.write_text("meta: {id: t, name: n}\n", encoding="utf-8")
        with pytest.raises(ValueError, match="不能为空"):
            load_flow(f)

    def test_platforms_desktop(self, tmp_path):
        f = tmp_path / "d.yaml"
        f.write_text(
            "meta: {id: d, name: n, platforms: [desktop]}\n"
            "steps:\n  - judge: {}\n",
            encoding="utf-8",
        )
        assert load_flow(f).meta.platforms == ["desktop"]
