"""探查原语测试（生成侧工具）：fixture 站点验证 probe 动作与爬虫 probe 通道。"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from apw.crawler.crawler import Crawler
from apw.crawler.extract import extract_page
from apw.crawler.probe import ProbePage
from apw.crawler.schema import CrawlConfig
from apw.pages.base import EvidenceError

_INPUT = {"by": "testid", "value": "chat-input"}
_SEND = {"by": "testid", "value": "chat-send"}


def _probe(apw_driver, apw_repo) -> ProbePage:
    apw_driver.goto_base()
    return ProbePage(page=apw_driver.page, repo=apw_repo)


class TestProbeActions:
    def test_fill_and_click(self, apw_driver, apw_repo):
        probe = _probe(apw_driver, apw_repo)
        probe.fill(_INPUT, "探查消息")
        probe.click(_SEND)
        probe.wait_for({"by": "testid", "value": "chat-messages"})
        text = apw_driver.page.inner_text('[data-testid="chat-messages"]')
        assert "探查消息" in text

    def test_type_keys_in(self, apw_driver, apw_repo):
        probe = _probe(apw_driver, apw_repo)
        probe.type(_INPUT, "逐键输入")
        assert apw_driver.page.input_value('[data-testid="chat-input"]') == "逐键输入"

    def test_insert_text(self, apw_driver, apw_repo):
        probe = _probe(apw_driver, apw_repo)
        probe.insert(_INPUT, "整体插入")
        assert apw_driver.page.input_value('[data-testid="chat-input"]') == "整体插入"

    def test_optional_click_swallows_miss(self, apw_driver, apw_repo):
        probe = _probe(apw_driver, apw_repo)
        probe.click({"by": "text", "value": "不存在的按钮"}, optional=True, timeout_ms=300)

    def test_failure_freezes_evidence(self, apw_driver, apw_repo, tmp_path):
        probe = _probe(apw_driver, apw_repo)
        probe.screenshot_dir = tmp_path
        with pytest.raises(EvidenceError) as excinfo:
            probe.click({"by": "testid", "value": "missing"}, timeout_ms=300)
        shot = excinfo.value.evidence["screenshot"]
        assert shot and Path(shot).exists()

    def test_dump_dom_captures_structure(self, apw_driver, apw_repo, tmp_path):
        probe = _probe(apw_driver, apw_repo)
        probe.screenshot_dir = tmp_path
        path = probe.dump_dom("base")
        assert Path(path).exists()
        assert "chat-input" in Path(path).read_text(encoding="utf-8")

    def test_dump_dom_sanitized(self, apw_driver, apw_repo, tmp_path):
        """探查产物（HTML）落盘前同样脱敏：敏感串→占位符，结构保留。"""
        probe = _probe(apw_driver, apw_repo)
        probe.screenshot_dir = tmp_path
        probe.sanitize_mapping = {"帮助": "<nav>"}
        path = probe.dump_dom("base")
        raw = Path(path).read_text(encoding="utf-8")
        assert "<nav>" in raw and "帮助" not in raw
        assert "chat-input" in raw  # 结构保留

    def test_extract_captures_href(self, apw_driver, apw_repo):
        _probe(apw_driver, apw_repo)
        data = extract_page(apw_driver.page)
        assert any(e["href"] == "/help" for e in data["elements"])


class TestCrawlerProbeChannel:
    def test_probe_steps_advance_state_and_capture(
        self, apw_driver, apw_repo, apw_pages, tmp_path
    ):
        config = CrawlConfig.model_validate(
            {
                "name": "probe-fixture",
                "targets": [
                    {
                        "id": "probe-main",
                        "route": "/",
                        "steps": [
                            {
                                "do": {
                                    "page": "probe",
                                    "action": "fill",
                                    "args": {"selector": _INPUT, "text": "你好探查"},
                                },
                                "label": "filled",
                                "capture": True,
                            },
                            {
                                "do": {
                                    "page": "probe",
                                    "action": "click",
                                    "args": {"selector": _SEND},
                                },
                                "label": "sent",
                            },
                        ],
                        "signals": [
                            {
                                "name": "message_list",
                                "selector": {"by": "testid", "value": "chat-messages"},
                            }
                        ],
                    }
                ],
            }
        )
        crawler = Crawler(
            page=apw_driver.page,
            repo=apw_repo,
            pages=apw_pages,
            env="fixture",
            out_dir=tmp_path,
            prepare=apw_driver.goto_base,
        )
        paths = crawler.run_config(config)
        assert len(paths) == 2
        snapshot = json.loads(paths[-1].read_text(encoding="utf-8"))
        assert snapshot["state_path"] == ["filled", "sent"]
        assert snapshot["signals"]["message_list"]["present"] is True
