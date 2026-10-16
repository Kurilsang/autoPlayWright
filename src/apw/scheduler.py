"""定时执行调度器：循环跑一轮 pytest 用例，排期支持固定间隔（默认 30 分钟）或 cron 表达式。

两种部署形态（同一模块）：

- 常驻：`python -m apw.scheduler`（前台 / tmux / systemd service 均可）
- 外部调度：`... python -m apw.scheduler --once`（--once 单跑一轮退出，立即执行）

用法：

    python -m apw.scheduler                        # 每 30 分钟跑 flows --apw-env test
    python -m apw.scheduler --interval-minutes 60  # 调整间隔
    python -m apw.scheduler --cron "0 21 * * *"    # 每天 21:00（cron 钟点锚定，常驻）
    python -m apw.scheduler --cron "0 18 * * 5"    # 每周五 18:00（周频率）
    python -m apw.scheduler --cron "0 21 * * *" --cron "0 18 * * 5"   # 多条并集：+周五 18:00
    python -m apw.scheduler --cron "0 21 * * 1"    # 每周一 21:00
    python -m apw.scheduler --cron "0 21 1 * *"    # 每月 1 日 21:00（月频率）
    python -m apw.scheduler --once                 # 只跑一轮（联调/冒烟；立即执行）
    python -m apw.scheduler -- --apw-env fixture   # `--` 后透传 pytest 参数（替换默认）

cron 语义（标准 5 字段：分 时 日 月 周，周 0/7=周日）：支持 `*`、`n`、`a-b`、`*/s`、
`a-b/s`、`n/s`、逗号列表、跨区间（如 `22-2`）；日与周同时限定时按经典语义取「或」。
排期语义：`--interval-minutes` 首轮启动即跑、此后按间隔顺延（错过的槽位不补跑）；
`--cron` 钟点锚定（**可给多次 = 多档排期并集**），首轮也等到下一个触发点才跑（不抢跑）。
`--cron` 与 `--interval-minutes` 互斥。
"""
from __future__ import annotations

import argparse
import os
import signal
import subprocess
import sys
import threading
from datetime import datetime, timedelta
from pathlib import Path

DEFAULT_PYTEST_ARGS = ["flows", "--apw-env", "test"]


def build_command(pytest_args: list[str]) -> list[str]:
    """调度执行的 pytest 命令：用当前解释器（venv 内即 venv 的 python）。"""
    return [sys.executable, "-m", "pytest", *pytest_args]


def next_slot(prev: datetime, interval: timedelta, now: datetime) -> datetime:
    """固定节奏排期：上一触发点顺延 interval；已错过多个槽位只取最近的未来槽（不叠跑、不补跑）。"""
    slot = prev + interval
    while slot <= now:
        slot += interval
    return slot


# ---------- cron 表达式（标准 5 字段，自包含解析，不依赖系统 crontab/第三方库） ----------

_FIELD_SPEC = (("minute", 0, 59), ("hour", 0, 23), ("day", 1, 31), ("month", 1, 12), ("dow", 0, 7))
_MAX_SEARCH = timedelta(days=366 * 5)  # 未来 5 年找不到触发点即报错（如 2 月 30 日）


class CronExpr:
    """解析并按标准 cron 语义计算下一次触发时刻（精确到分，服务器本地时区）。"""

    def __init__(self, expr: str) -> None:
        parts = expr.split()
        if len(parts) != 5:
            raise ValueError(f"cron 表达式须为 5 个字段（分 时 日 月 周）：{expr!r}")
        self.expr = expr
        self.minutes = _parse_field(parts[0], 0, 59, "分钟")
        self.hours = _parse_field(parts[1], 0, 23, "小时")
        self.doms = _parse_field(parts[2], 1, 31, "日")
        self.months = _parse_field(parts[3], 1, 12, "月")
        self.dows = frozenset(0 if d == 7 else d for d in _parse_field(parts[4], 0, 7, "周"))
        # 日/周经典语义：两者都限定（都不是字面 *）时取「或」，否则取「与」
        self._dom_star = parts[2].strip() == "*"
        self._dow_star = parts[4].strip() == "*"

    def _day_matches(self, day: datetime) -> bool:
        dom_ok = day.day in self.doms
        dow_ok = (day.weekday() + 1) % 7 in self.dows  # cron 周 0=周日
        if self._dom_star and self._dow_star:
            return True
        if self._dom_star:
            return dow_ok
        if self._dow_star:
            return dom_ok
        return dom_ok or dow_ok

    def next_after(self, now: datetime) -> datetime:
        """now 之后最近的触发时刻（严格大于 now，精确到分）。找不到（5 年内无解）抛 ValueError。"""
        t = (now + timedelta(minutes=1)).replace(second=0, microsecond=0)
        limit = now + _MAX_SEARCH
        while t <= limit:
            if t.month not in self.months:
                t = (t.replace(day=1, hour=0, minute=0) + timedelta(days=32)).replace(day=1)
            elif not self._day_matches(t):
                t = (t + timedelta(days=1)).replace(hour=0, minute=0)
            elif t.hour not in self.hours:
                t = (t + timedelta(hours=1)).replace(minute=0)
            elif t.minute not in self.minutes:
                t += timedelta(minutes=1)
            else:
                return t
        raise ValueError(f"cron 表达式 {self.expr!r} 在未来 5 年内没有触发点")


def _parse_field(text: str, lo: int, hi: int, name: str) -> frozenset[int]:
    """解析单个 cron 字段：`*`、`n`、`a-b`、`*/s`、`a-b/s`、`n/s`、列表；支持跨区间 `22-2`。"""
    values: set[int] = set()
    for part in text.split(","):
        part = part.strip()
        if not part:
            raise ValueError(f"cron {name}字段含空项：{text!r}")
        step = 1
        if "/" in part:
            part, _, step_text = part.partition("/")
            if not step_text.isdigit() or int(step_text) <= 0:
                raise ValueError(f"cron {name}字段步长非法：{text!r}")
            step = int(step_text)
        if part == "*":
            start, end = lo, hi
        elif "-" in part:
            start_text, _, end_text = part.partition("-")
            if not (start_text.lstrip("-").isdigit() and end_text.lstrip("-").isdigit()):
                raise ValueError(f"cron {name}字段区间非法：{text!r}")
            start, end = int(start_text), int(end_text)
        elif part.isdigit():
            start = end = int(part)
            if "/" in text:  # `n/s` = 从 n 到上限按步长取（标准 cron 语义）
                end = hi
        else:
            raise ValueError(f"cron {name}字段非法：{text!r}")
        if not (lo <= start <= hi and lo <= end <= hi):
            raise ValueError(f"cron {name}字段超出范围 {lo}-{hi}：{text!r}")
        if start <= end:
            values.update(range(start, end + 1, step))
        else:  # 跨区间（如 22-2）：绕回
            values.update(range(start, hi + 1, step))
            values.update(range(lo, end + 1, step))
    return frozenset(values)


def next_cron_slot(crons: list[CronExpr], now: datetime) -> datetime:
    """多条 cron 表达式取并集：最近的未来触发点，由任意一条命中都算。"""
    return min(cron.next_after(now) for cron in crons)


def run_once(
    cmd: list[str],
    cwd: Path,
    log_dir: Path,
    stop: threading.Event | None = None,
) -> tuple[int, Path]:
    """跑一轮：输出同时落控制台与 reports/scheduler/run-<ts>.log，返回 (退出码, 日志路径)。

    stop 置位时终止本轮子进程（调度器收到 SIGINT/SIGTERM 时不留孤儿进程）。
    """
    stop = stop if stop is not None else threading.Event()
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / f"run-{stamp}.log"
    env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
    with log_path.open("w", encoding="utf-8") as log:
        log.write(f"# cmd: {' '.join(cmd)}\n")
        log.write(f"# cwd: {cwd}\n")
        log.write(f"# started: {datetime.now().isoformat(timespec='seconds')}\n")
        log.flush()
        proc = subprocess.Popen(
            cmd,
            cwd=str(cwd),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=env,
        )

        def pump() -> None:
            assert proc.stdout is not None
            for line in proc.stdout:
                sys.stdout.write(line)
                log.write(line)

        threading.Thread(target=pump, daemon=True).start()
        while proc.poll() is None:
            if stop.wait(0.5):
                proc.terminate()
                try:
                    proc.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    proc.kill()
                break
        code = proc.wait()
        log.write(f"# finished: {datetime.now().isoformat(timespec='seconds')}  exit={code}\n")
    return code, log_path


def main(argv: list[str] | None = None) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError, ValueError):  # 被捕获流替换时无 reconfigure，忽略
        pass
    argv = list(sys.argv[1:] if argv is None else argv)
    # `--` 之后原样透传 pytest 参数（替换默认），避免与调度器自有选项纠缠
    if "--" in argv:
        split = argv.index("--")
        own, rest = argv[:split], argv[split + 1 :]
    else:
        own, rest = argv, []

    parser = argparse.ArgumentParser(prog="apw.scheduler", description=__doc__.splitlines()[0])
    parser.add_argument(
        "--interval-minutes", type=int, default=30, help="执行间隔分钟数（默认 30，测试阶段口径）"
    )
    parser.add_argument(
        "--cron",
        action="append",
        default=[],
        metavar="EXPR",
        help=(
            "cron 表达式钟点锚定（分 时 日 月 周）：如 '0 21 * * *' 每天 21:00、"
            "'0 18 * * 5' 每周五 18:00、'0 21 1 * *' 每月 1 日；"
            "可给多次 = 多档排期并集；与 --interval-minutes 互斥"
        ),
    )
    parser.add_argument("--root", default=".", help="仓库根目录（pytest 在此目录下执行）")
    parser.add_argument(
        "--once",
        action="store_true",
        help="只跑一轮就退出（联调/冒烟；立即执行，不受 --cron 影响）",
    )
    args = parser.parse_args(own)

    crons: list[CronExpr] = []
    if args.cron:
        if any(a == "--interval-minutes" or a.startswith("--interval-minutes=") for a in own):
            parser.error("--cron 与 --interval-minutes 互斥：钟点锚定与固定间隔二选一")
        for raw in args.cron:
            try:
                crons.append(CronExpr(raw.strip()))
            except ValueError as exc:
                parser.error(str(exc))

    pytest_args = rest or DEFAULT_PYTEST_ARGS
    root = Path(args.root).resolve()
    log_dir = root / "reports" / "scheduler"
    cmd = build_command(pytest_args)

    stop = threading.Event()
    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, lambda *_: stop.set())

    interval = timedelta(minutes=args.interval_minutes)
    schedule = "cron " + " ∪ ".join(c.expr for c in crons) if crons else (
        f"每 {args.interval_minutes} 分钟一轮"
    )
    print(f"[scheduler] {schedule}：{' '.join(cmd)}（cwd={root}）", flush=True)
    if crons and not args.once:
        try:
            slot = next_cron_slot(crons, datetime.now())
        except ValueError as exc:  # 无解表达式（如 2 月 30 日）启动即报错，不留空转服务
            parser.error(str(exc))
        print(f"[scheduler] 首轮 {slot:%Y-%m-%d %H:%M}（cron 到点触发，不抢跑）", flush=True)
        stop.wait(max(0.0, (slot - datetime.now()).total_seconds()))
    slot = datetime.now()  # 首轮：interval 启动即跑 / cron 到点即跑 / --once 立即跑
    while not stop.is_set():
        started = datetime.now()
        print(f"[scheduler] ▶ {started:%Y-%m-%d %H:%M:%S} 开始", flush=True)
        code, log_path = run_once(cmd, root, log_dir, stop)
        duration = int((datetime.now() - started).total_seconds())
        print(f"[scheduler] 完成：退出码 {code}，用时 {duration}s，日志 {log_path}", flush=True)
        if args.once:
            return code
        if crons:
            slot = next_cron_slot(crons, datetime.now())
        else:
            slot = next_slot(slot, interval, datetime.now())
        delay = max(0.0, (slot - datetime.now()).total_seconds())
        print(f"[scheduler] 下一轮 {slot:%Y-%m-%d %H:%M:%S}（{delay / 60:.1f} 分钟后）", flush=True)
        stop.wait(delay)
    print("[scheduler] 收到停止信号，退出", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
