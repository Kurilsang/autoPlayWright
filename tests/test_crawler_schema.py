"""爬虫配置与快照 schema 校验测试（票 06）。"""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from apw.crawler.schema import CrawlConfig, Snapshot


def _config(**overrides) -> dict:
    data = {
        "name": "demo",
        "targets": [
            {
                "id": "t1",
                "route": "/chat",
                "steps": [
                    {"do": {"page": "aml_chat", "action": "new_session"},
                     "label": "new_session", "capture": True},
                    {"do": {"page": "aml_chat", "action": "send_message",
                            "args": {"text": "hi"}}},
                ],
                "signals": [
                    {"name": "stop", "selector": {"by": "text", "value": "停止"}},
                ],
            }
        ],
    }
    data.update(overrides)
    return data


class TestCrawlConfig:
    def test_full_config_parses(self):
        config = CrawlConfig.model_validate(_config())
        target = config.targets[0]
        assert target.steps[0].label == "new_session" and target.steps[0].capture
        assert target.steps[1].label == "" and not target.steps[1].capture  # 默认值
        assert target.signals[0].selector.by == "text"

    def test_targets_required(self):
        with pytest.raises(ValidationError):
            CrawlConfig.model_validate(_config(targets=[]))

    def test_unknown_selector_by_rejected(self):
        data = _config()
        data["targets"][0]["signals"][0]["selector"] = {"by": "magic", "value": "x"}
        with pytest.raises(ValidationError):
            CrawlConfig.model_validate(data)


class TestSnapshotSchema:
    def test_candidates_map_to_locator_repo_format(self):
        snapshot = Snapshot.model_validate(
            {
                "env": "test",
                "state_path": ["new_session", "done"],
                "elements": [
                    {
                        "name_hint": "message_input",
                        "region": "composer",
                        "role": "textbox",
                        "placeholder": "输入消息",
                        "tag": "textarea",
                        "candidates": [
                            {"by": "placeholder", "value": "输入消息"},
                            {"by": "css", "value": "textarea"},
                        ],
                    }
                ],
                "signals": {"stop_button": {"present": False, "count": 0}},
                "screenshots": ["t.png"],
            }
        )
        assert snapshot.schema_version == 1
        assert snapshot.elements[0].candidates[0].by == "placeholder"
        assert snapshot.elements[0].candidates[0].exact is True  # 与 Selector 约定一致

    def test_bad_region_rejected(self):
        with pytest.raises(ValidationError):
            Snapshot.model_validate({"env": "t", "elements": [{"region": "火星"}]})
