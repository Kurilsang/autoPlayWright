"""run 目录身份测试：产物目录唯一化 + 汇总合并语义（缝：run 目录产物）。"""
from __future__ import annotations

import json
import re

from apw.engine.events import FlowResult
from apw.reporter.json_report import JsonReporter


def _result(flow_id: str, status: str = "passed") -> FlowResult:
    return FlowResult(flow_id=flow_id, name=flow_id, status=status)


class TestRunDirectoryIdentity:
    def test_run_dirs_unique_and_readable(self, tmp_path):
        """同秒两次构建也不重名（时间戳前缀可读 + 熵后缀唯一）。"""
        r1 = JsonReporter(tmp_path)
        r2 = JsonReporter(tmp_path)
        assert r1.out_dir != r2.out_dir
        for rep in (r1, r2):
            assert re.match(r"^\d{8}-\d{6}-\w+$", rep.out_dir.name)


class TestSummaryMerge:
    @staticmethod
    def _shared_writer(tmp_path, out_dir) -> JsonReporter:
        """模拟共享 run 目录的并行 writer（明细写同目录，汇总合并）。"""
        rep = JsonReporter(tmp_path)
        rep.out_dir = out_dir
        return rep

    def test_summary_merges_existing_entries(self, tmp_path):
        """汇总写入是合并语义：并行 writer 的既有明细保留，不互相覆盖。"""
        r1 = JsonReporter(tmp_path)
        r1.write_flow(_result("flow-a"))
        r1.write_summary()

        r2 = self._shared_writer(tmp_path, r1.out_dir)
        r2.write_flow(_result("flow-b", status="skipped"))
        summary = json.loads(r2.write_summary().read_text(encoding="utf-8"))

        assert summary["total"] == 2
        assert summary["passed"] == 1 and summary["skipped"] == 1
        assert {f["flow_id"] for f in summary["flows"]} == {"flow-a", "flow-b"}

    def test_summary_replaces_same_flow_id(self, tmp_path):
        """同 flow_id 的重写覆盖旧记录，计数不重复。"""
        r1 = JsonReporter(tmp_path)
        r1.write_flow(_result("flow-a", status="failed"))
        r1.write_summary()

        r2 = self._shared_writer(tmp_path, r1.out_dir)
        r2.write_flow(_result("flow-a"))
        summary = json.loads(r2.write_summary().read_text(encoding="utf-8"))
        assert summary["total"] == 1 and summary["passed"] == 1 and summary["failed"] == 0
