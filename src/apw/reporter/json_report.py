"""JSON 报告（第一公民）：run 目录下每条 flow 一份明细 + 一份 run 汇总。

run 标识 = 时间戳前缀（可读）+ 进程/随机熵后缀（全局唯一）：并发 worker 与同秒重跑
互不覆盖。汇总写入为合并语义：同目录既有明细保留，同 flow_id 以本次为准。
"""
from __future__ import annotations

import json
import os
import secrets
from datetime import datetime
from pathlib import Path

from apw.engine.events import FlowResult


class JsonReporter:
    def __init__(self, out_dir: str | Path) -> None:
        self.run_id = (
            f"{datetime.now():%Y%m%d-%H%M%S}-{os.getpid():x}{secrets.token_hex(2)}"
        )
        self.out_dir = Path(out_dir) / self.run_id
        self.results: list[dict] = []

    def write_flow(self, result: FlowResult) -> None:
        self.out_dir.mkdir(parents=True, exist_ok=True)
        path = self.out_dir / f"{result.flow_id}.json"
        path.write_text(result.model_dump_json(indent=2), encoding="utf-8")
        self.results.append(
            {
                "flow_id": result.flow_id,
                "name": result.name,
                "status": result.status,
                "skip_reason": result.skip_reason,
                "duration_ms": result.duration_ms,
                "detail": path.name,
            }
        )

    def write_summary(self) -> Path | None:
        if not self.results:
            return None
        self.out_dir.mkdir(parents=True, exist_ok=True)
        path = self.out_dir / "run-summary.json"
        flows = self._merge_flows(path)
        summary = {
            "run_id": self.run_id,
            "total": len(flows),
            "passed": sum(1 for f in flows if f["status"] == "passed"),
            "failed": sum(1 for f in flows if f["status"] == "failed"),
            "skipped": sum(1 for f in flows if f["status"] == "skipped"),
            "flows": flows,
        }
        path.write_text(
            json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        return path

    def _merge_flows(self, path: Path) -> list[dict]:
        """合并既有汇总（并行 writer 的明细保留）；同 flow_id 以本次为准。"""
        merged: dict[str, dict] = {}
        if path.exists():
            try:
                prior = json.loads(path.read_text(encoding="utf-8"))
                merged = {f["flow_id"]: f for f in prior.get("flows", [])}
            except (json.JSONDecodeError, TypeError, KeyError, ValueError):
                merged = {}
        for item in self.results:
            merged[item["flow_id"]] = item
        return list(merged.values())
