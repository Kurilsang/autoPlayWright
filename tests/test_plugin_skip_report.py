"""插件接线集成：跳过留痕从 runtest 贯通到 run 汇总（一次真实 pytest 会话的产物）。"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import yaml

_REPO_ROOT = Path(__file__).resolve().parents[1]


def _write_flow(path: Path, meta: dict) -> None:
    path.write_text(
        yaml.safe_dump({"meta": meta, "steps": [{"judge": {}}]}, allow_unicode=True),
        encoding="utf-8",
    )


class TestSkipRecordedInRunSummary:
    def test_mismatched_flows_land_in_summary(self, tmp_path):
        flows = tmp_path / "flows"
        flows.mkdir()
        _write_flow(
            flows / "desktop_only.yaml",
            {"id": "desk-only", "name": "桌面限定", "platforms": ["desktop"]},
        )
        _write_flow(
            flows / "env_limited.yaml",
            {"id": "env-only", "name": "环境限定", "envs": ["no-such-env"]},
        )
        reports = tmp_path / "reports"
        proc = subprocess.run(
            [
                sys.executable, "-m", "pytest", str(flows),
                f"--apw-flows-dir={flows}",
                f"--apw-reports-dir={reports}",
                "-p", "no:cacheprovider",
            ],
            capture_output=True, text=True, cwd=_REPO_ROOT, timeout=300,
        )
        assert proc.returncode == 0, proc.stdout + proc.stderr  # 全部 skip 不算失败
        summaries = list(reports.glob("*/run-summary.json"))
        assert len(summaries) == 1
        summary = json.loads(summaries[0].read_text(encoding="utf-8"))
        assert summary["skipped"] == 2 and summary["total"] == 2
        assert summary["passed"] == 0 and summary["failed"] == 0
        reasons = {f["flow_id"]: f.get("skip_reason", "") for f in summary["flows"]}
        assert "平台不匹配" in reasons["desk-only"]
        assert "环境不匹配" in reasons["env-only"]
