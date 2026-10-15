"""调度器自测：排期逻辑、命令构造、单轮执行与停止终止。"""
from __future__ import annotations

import sys
import threading
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from apw.scheduler import DEFAULT_PYTEST_ARGS, CronExpr, build_command, next_slot, run_once


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


class TestCronExprParse:
    """cron 解析：字段数/范围/步长非法都要拒绝，合法语法覆盖 * n a-b */s a-b/s n/s 列表 跨区间。"""

    def test_parse_rejects_bad_expressions(self):
        bad = [
            "* * * *",  # 4 字段
            "* * * * * *",  # 6 字段
            "60 * * * *",  # 分钟超界
            "* 24 * * *",  # 小时超界
            "* * 0 * *",  # 日从 1 起
            "* * * 13 *",  # 月到 12
            "* * * * 8",  # 周到 7
            "a * * * *",  # 非数字
            "*/0 * * * *",  # 步长 0
            "1-2-3 * * * *",  # 区间语法
            "1,,2 * * * *",  # 空项
        ]
        for expr in bad:
            with pytest.raises(ValueError):
                CronExpr(expr)

    def test_parse_accepts_standard_syntax(self):
        cron = CronExpr("10/20 9-18/3 1,15 */2 *")  # n/s、a-b/s、列表、*/s 都合法
        assert cron.minutes == frozenset({10, 30, 50})
        assert cron.hours == frozenset({9, 12, 15, 18})
        assert cron.doms == frozenset({1, 15})
        assert cron.months == frozenset({1, 3, 5, 7, 9, 11})


class TestCronExprNext:
    def test_daily_21(self):
        cron = CronExpr("0 21 * * *")
        assert cron.next_after(datetime(2026, 1, 1, 12, 0)) == datetime(2026, 1, 1, 21, 0)

    def test_daily_strictly_future_and_cross_day(self):
        cron = CronExpr("0 21 * * *")
        # 到点时刻不算下一次（严格未来），跨天顺延
        assert cron.next_after(datetime(2026, 1, 1, 21, 0)) == datetime(2026, 1, 2, 21, 0)

    def test_weekly_monday(self):
        cron = CronExpr("0 21 * * 1")
        # 2026-01-01 是周四，下一周一是 01-05
        assert cron.next_after(datetime(2026, 1, 1, 12, 0)) == datetime(2026, 1, 5, 21, 0)

    def test_weekly_sunday_via_7(self):
        cron = CronExpr("0 21 * * 7")
        # 2026-01-01 周四，周日 = 01-04（7 与 0 同义）
        assert cron.next_after(datetime(2026, 1, 1, 12, 0)) == datetime(2026, 1, 4, 21, 0)

    def test_monthly_first_day(self):
        cron = CronExpr("0 21 1 * *")
        assert cron.next_after(datetime(2026, 1, 15, 12, 0)) == datetime(2026, 2, 1, 21, 0)

    def test_yearly_cross_year(self):
        cron = CronExpr("30 9 1 1 *")
        assert cron.next_after(datetime(2026, 6, 1, 12, 0)) == datetime(2027, 1, 1, 9, 30)

    def test_step_and_wrap_hours(self):
        cron = CronExpr("0 22-2 * * *")  # 跨区间：22,23,0,1,2
        assert cron.next_after(datetime(2026, 1, 1, 23, 30)) == datetime(2026, 1, 2, 0, 0)

    def test_dom_dow_or_semantics(self):
        # 日与周同时限定 = 「或」：13 号或周五，谁先到算谁（01-02 是周五）
        cron = CronExpr("0 0 13 * 5")
        assert cron.next_after(datetime(2026, 1, 1, 12, 0)) == datetime(2026, 1, 2, 0, 0)

    def test_no_trigger_in_five_years(self):
        with pytest.raises(ValueError):
            CronExpr("0 0 30 2 *").next_after(datetime(2026, 1, 1))


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
