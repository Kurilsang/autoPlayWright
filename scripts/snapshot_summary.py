"""快照总结：把爬虫快照 JSON 汇总成人类/AI 可读的页面结构摘要。

生成侧工具（AI 复用）：探查新页面时先 dump 快照，再用本脚本快速过结构，
替代直接翻 50KB 的 dom_excerpt。

用法（路径按实际情况替换）：
    python scripts/snapshot_summary.py <snapshot.json> [more.json ...]
    python scripts/snapshot_summary.py <snapshots-dir>
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def summarize(path: Path, regions: set[str] | None = None) -> None:
    data = json.loads(path.read_text(encoding="utf-8"))
    print(f"===== {path.name} =====")
    print(f"route: {data.get('route')}  title: {data.get('title')}")
    print(f"state_path: {data.get('state_path')}")
    print("--- elements (region | tag | name | text | href) ---")
    for e in data.get("elements", []):
        if regions and e.get("region") not in regions:
            continue
        print(
            f"{e.get('region', ''):12} | {e.get('tag', ''):8} | "
            f"{e.get('accessible_name', '')[:48]:48} | {e.get('text', '')[:48]:48} | "
            f"{e.get('href', '')[:40]}"
        )
    print("--- signals (presence) ---")
    for name, probe in data.get("signals", {}).items():
        print(f"{name}: present={probe.get('present')} count={probe.get('count')}")
    print("--- screenshots ---")
    for shot in data.get("screenshots", []):
        print(f"{shot}")
    print()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paths", nargs="+", help="快照 JSON 文件或目录")
    parser.add_argument(
        "--regions",
        default="",
        help="只显示这些 region（逗号分隔，如 header,sidebar,dialog,content）",
    )
    args = parser.parse_args()
    regions = {r.strip() for r in args.regions.split(",") if r.strip()} or None
    files: list[Path] = []
    for raw in args.paths:
        path = Path(raw)
        files.extend(sorted(path.glob("*.json")) if path.is_dir() else [path])
    for path in files:
        summarize(path, regions)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
