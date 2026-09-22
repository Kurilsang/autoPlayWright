"""JSON 报告（第一公民）：run 目录下每条 flow 一份明细 + 一份 run 汇总。"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from apw.engine.events import FlowResult


class JsonReporter:
    def __init__(self, out_dir: str | Path) -> None:
        self.run_id = datetime.now().strftime("%Y%m%d-%H%M%S")
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
                "duration_ms": result.duration_ms,
                "detail": path.name,
            }
        )

    def write_summary(self) -> Path | None:
        if not self.results:
            return None
        self.out_dir.mkdir(parents=True, exist_ok=True)
        summary = {
            "run_id": self.run_id,
            "total": len(self.results),
            "passed": sum(1 for r in self.results if r["status"] == "passed"),
            "failed": sum(1 for r in self.results if r["status"] == "failed"),
            "flows": self.results,
        }
        path = self.out_dir / "run-summary.json"
        path.write_text(
            json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        return path
