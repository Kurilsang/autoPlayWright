"""调度器自测：排期逻辑、命令构造、单轮执行与停止终止。"""
from __future__ import annotations

import sys
import threading
from datetime import datetime, timedelta
from pathlib import Path

from apw.scheduler import DEFAULT_PYTEST_ARGS, build_command, next_slot, run_once


class TestBuildCommand:
    def test_uses_current_interpreter_and_passthrough(self):
        cmd = build_command(["flows", "--apw-env", "fixture"])
        assert cmd == [sys.executable, "-m", "pytest", "flows", "--apw-env", "fixture"]

    def test_default_args(self):
        assert build_command(DEFAULT_PYTEST_ARGS) == [
            sys.executable,
            "-m",
            "pytest",
            "flows",
            "--apw-env",
            "test",
        ]


class TestNextSlot:
    def test_advances_one_interval(self):
        t0 = datetime(2026, 1, 1, 12, 0, 0)
        assert next_slot(t0, timedelta(minutes=30), datetime(2026, 1, 1, 12, 10)) == datetime(
            2026, 1, 1, 12, 30
        )

    def test_overrun_skips_missed_slots(self):
        # 一轮跑了 70 分钟：错过的 12:30/13:00 槽不补跑，排到最近的未来槽 13:30
        t0 = datetime(2026, 1, 1, 12, 0, 0)
        assert next_slot(t0, timedelta(minutes=30), datetime(2026, 1, 1, 13, 10)) == datetime(
            2026, 1, 1, 13, 30
        )

    def test_overrun_keeps_one_interval_gap(self):
        # 超长跑结束后不立刻叠跑下一轮，仍留一个完整间隔
        t0 = datetime(2026, 1, 1, 12, 0, 0)
        assert next_slot(t0, timedelta(minutes=30), datetime(2026, 1, 1, 12, 30, 1)) == datetime(
            2026, 1, 1, 13, 0
        )


class TestRunOnce:
    def test_captures_output_and_exit_code(self, tmp_path):
        code, log_path = run_once(
            [sys.executable, "-c", "print('hello apw')"], Path.cwd(), tmp_path
        )
        assert code == 0
        content = log_path.read_text(encoding="utf-8")
        assert "hello apw" in content
        assert "exit=0" in content

    def test_nonzero_exit_reported(self, tmp_path):
        code, log_path = run_once(
            [sys.executable, "-c", "raise SystemExit(3)"], Path.cwd(), tmp_path
        )
        assert code == 3
        assert "exit=3" in log_path.read_text(encoding="utf-8")

    def test_stop_terminates_long_run(self, tmp_path):
        stop = threading.Event()
        stop.set()
        code, _ = run_once(
            [sys.executable, "-c", "import time; time.sleep(30)"], Path.cwd(), tmp_path, stop
        )
        assert code != 0  # 被 terminate，非正常退出
