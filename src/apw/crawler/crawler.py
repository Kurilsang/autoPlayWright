"""快照爬虫：复用 AppDriver/页面动作推进状态，逐状态采集快照（票 06）。

每个页面状态一份快照（state_path 标注到达路径）——弹窗/流式/完成态等
「状态里的结构」必须分别采集（SPEC D18）。
"""
from __future__ import annotations

import re
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

from apw.crawler.extract import extract_page
from apw.crawler.schema import CrawlConfig, CrawlTarget, Snapshot
from apw.dsl.schema import DoAction
from apw.locators.repo import build_locator

if TYPE_CHECKING:
    from playwright.sync_api import Page

    from apw.engine.registry import PageRegistry
    from apw.locators.repo import LocatorRepo


def _slug(text: str) -> str:
    return re.sub(r"[^\w\-.]+", "_", text).strip("_")[:40] or "state"


class Crawler:
    def __init__(
        self,
        *,
        page: Page,
        repo: LocatorRepo,
        pages: PageRegistry,
        env: str,
        out_dir: str | Path,
        prepare: Callable[[], None] | None = None,
    ) -> None:
        self.page = page
        self.repo = repo
        self.pages = pages
        self.env = env
        self.out_dir = Path(out_dir) / env
        self.prepare = prepare

    def run_config(self, config: CrawlConfig) -> list[Path]:
        produced: list[Path] = []
        for target in config.targets:
            if self.prepare:
                self.prepare()
            produced += self._run_target(config, target)
        return produced

    def _run_target(self, config: CrawlConfig, target: CrawlTarget) -> list[Path]:
        paths: list[Path] = []
        state_path: list[str] = []
        total = max(len(target.steps), 1)
        for index, step in enumerate(target.steps):
            self._exec_do(step.do)
            state_path.append(step.label or f"{step.do.page}.{step.do.action}")
            if step.capture or index == len(target.steps) - 1:
                paths.append(self._capture(config, target, state_path, len(paths), total))
        if not target.steps:
            paths.append(self._capture(config, target, state_path, 0, total))
        return paths

    def _exec_do(self, action: DoAction) -> None:
        obj = self.pages.create(action.page, page=self.page, repo=self.repo)
        obj.screenshot_dir = self.out_dir  # 动作失败取证（EvidenceError 冻结截图）落快照目录
        fn = getattr(obj, action.action, None)
        if not callable(fn):
            raise AttributeError(f"页面 {action.page} 没有动作 {action.action!r}")
        fn(**action.args)

    def _capture(
        self,
        config: CrawlConfig,
        target: CrawlTarget,
        state_path: list[str],
        seq: int,
        total: int,
    ) -> Path:
        data = extract_page(self.page)
        excerpt = data.pop("dom_excerpt", "")[: config.dom_excerpt_chars]
        signals = {}
        for probe in target.signals:
            loc = build_locator(self.page, probe.selector)
            count = loc.count()
            # 在场性 = UI 信号可见（hidden/隐藏元素不算在场），count 保留原始匹配数
            signals[probe.name] = {
                "present": bool(count) and loc.first.is_visible(),
                "count": count,
            }
        state_label = state_path[-1] if state_path else "initial"
        stem = f"{target.id}_{seq + 1:02d}of{total:02d}_{_slug(state_label)}"
        self.out_dir.mkdir(parents=True, exist_ok=True)
        shot = self.out_dir / f"{stem}.png"
        try:
            self.page.screenshot(path=str(shot))
        except Exception:  # noqa: BLE001 - 截图失败不影响快照产出
            shot = None
        snapshot = Snapshot(
            env=self.env,
            route=target.route or data.get("route", ""),
            url=data.get("url", ""),
            title=data.get("title", ""),
            state_path=list(state_path),
            captured_at=datetime.now().isoformat(timespec="seconds"),
            elements=data.get("elements", []),
            signals=signals,
            screenshots=[shot.name] if shot else [],
            dom_excerpt=excerpt,
        )
        path = self.out_dir / f"{stem}.json"
        path.write_text(snapshot.model_dump_json(indent=2), encoding="utf-8")
        return path
