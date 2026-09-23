"""爬虫 CLI：按爬取配置产出页面状态快照（票 06）。

用法：
    python -m apw.crawler --env test --config configs/crawl/aml_chat.yaml
    python -m apw.crawler --env fixture --config configs/crawl/fixture_chat.yaml --headed
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import yaml

from apw.config import load_env
from apw.crawler.crawler import Crawler
from apw.crawler.schema import CrawlConfig
from apw.driver.app_driver import AppDriver
from apw.engine.registry import default_registry
from apw.locators.repo import LocatorRepo


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(prog="apw.crawler", description=__doc__)
    parser.add_argument("--env", default="test", help="环境名（configs/envs/<env>.yaml）")
    parser.add_argument(
        "--config", action="append", required=True, help="爬取配置 YAML，可多次指定"
    )
    parser.add_argument(
        "--out", default=".scratch/autoPlayWright/snapshots", help="快照输出目录"
    )
    parser.add_argument("--headed", action="store_true", help="浏览器窗口可见（调试）")
    parser.add_argument("--slowmo", type=int, default=0, metavar="MS", help="动作放慢毫秒")
    args = parser.parse_args()

    env = load_env(args.env)
    if args.headed:
        env.driver.headless = False
    if args.slowmo:
        env.driver.slow_mo = args.slowmo

    driver = AppDriver(env=env)
    driver.start()
    crawler = Crawler(
        page=driver.page,
        repo=LocatorRepo.load(Path("locators")),
        pages=default_registry(),
        env=args.env,
        out_dir=args.out,
        prepare=driver.goto_base,
    )
    try:
        for config_path in args.config:
            raw = yaml.safe_load(Path(config_path).read_text(encoding="utf-8")) or {}
            config = CrawlConfig.model_validate(raw)
            print(f"[crawler] {config_path}: {len(config.targets)} 个目标")
            for path in crawler.run_config(config):
                print(f"[crawler]   -> {path}")
    finally:
        driver.stop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
