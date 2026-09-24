"""爬虫端到端测试：本地夹具站点上跑通 状态推进→逐状态快照 全链路（票 06）。"""
from __future__ import annotations

import json
from pathlib import Path

from apw.crawler.crawler import Crawler
from apw.crawler.schema import CrawlConfig, Snapshot


def _load_config() -> CrawlConfig:
    raw = Path("configs/crawl/fixture_chat.yaml").read_text(encoding="utf-8")
    import yaml

    return CrawlConfig.model_validate(yaml.safe_load(raw))


class TestCrawlerFixtureSite:
    def test_crawl_produces_snapshots_per_state(
        self, apw_driver, apw_repo, apw_pages, tmp_path
    ):
        crawler = Crawler(
            page=apw_driver.page,
            repo=apw_repo,
            pages=apw_pages,
            env="fixture",
            out_dir=tmp_path,
            prepare=apw_driver.goto_base,
        )
        paths = crawler.run_config(_load_config())
        assert [p.suffix for p in paths] == [".json", ".json"]  # new_session / reply_done
        for path in paths:
            assert path.exists()
            shot = json.loads(path.read_text(encoding="utf-8"))["screenshots"][0]
            assert (path.parent / shot).exists()

    def test_snapshot_semantics(self, apw_driver, apw_repo, apw_pages, tmp_path):
        crawler = Crawler(
            page=apw_driver.page,
            repo=apw_repo,
            pages=apw_pages,
            env="fixture",
            out_dir=tmp_path,
            prepare=apw_driver.goto_base,
        )
        paths = crawler.run_config(_load_config())
        snapshot = Snapshot.model_validate_json(paths[-1].read_text(encoding="utf-8"))
        # state_path 标注状态到达路径
        assert snapshot.state_path == ["new_session", "sent", "reply_done"]
        # 候选按优先级：testid 元素首候选即 testid，可直接映射 locators/ 格式
        by_testid = {e.testid: e for e in snapshot.elements if e.testid}
        assert {"new-chat", "chat-input", "chat-send"} <= set(by_testid)
        assert by_testid["chat-input"].candidates[0].by == "testid"
        assert by_testid["chat-input"].placeholder == "输入消息"
        # 完成信号在场性
        assert snapshot.signals["message_list"]["present"] is True
        assert snapshot.signals["streaming"]["present"] is False  # 完成态
        assert snapshot.url and snapshot.dom_excerpt

    def test_snapshot_sanitized_before_write(
        self, apw_driver, apw_repo, apw_pages, tmp_path
    ):
        """快照落盘前统一脱敏：敏感串→占位符，结构对拍不变。"""
        crawler = Crawler(
            page=apw_driver.page,
            repo=apw_repo,
            pages=apw_pages,
            env="fixture",
            out_dir=tmp_path,
            prepare=apw_driver.goto_base,
            sanitize_mapping={"Agent Chat Fixture": "<product>"},
        )
        paths = crawler.run_config(_load_config())
        raw = paths[0].read_text(encoding="utf-8")
        assert "<product>" in raw
        assert "Agent Chat Fixture" not in raw
        Snapshot.model_validate_json(raw)  # 结构保留
