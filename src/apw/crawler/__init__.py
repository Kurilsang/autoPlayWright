"""AI 生成侧：页面快照爬虫（票 06）。

快照是 AI 生成 flow 草稿的事实依据（票 07 输入），也是页面改版 diff 的基线（票 08）。
"""
from apw.crawler.schema import (
    CrawlConfig,
    CrawlStep,
    CrawlTarget,
    SignalProbe,
    Snapshot,
    SnapshotElement,
)

__all__ = [
    "CrawlConfig",
    "CrawlStep",
    "CrawlTarget",
    "SignalProbe",
    "Snapshot",
    "SnapshotElement",
]
