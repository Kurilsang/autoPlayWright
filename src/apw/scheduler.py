"""定时执行调度器：按固定间隔循环跑一轮 pytest 用例（测试阶段默认 30 分钟）。

两种部署形态（同一模块）：

- 常驻：`python -m apw.scheduler`（前台 / tmux / systemd service 均可）
- cron：`*/30 * * * * ... python -m apw.scheduler --once`（--once 单跑一轮退出）

用法：

    python -m apw.scheduler                        # 每 30 分钟跑 flows --apw-env test
    python -m apw.scheduler --interval-minutes 60  # 调整间隔
    python -m apw.scheduler --once                 # 只跑一轮（cron / 联调）
    python -m apw.scheduler -- --apw-env fixture   # `--` 后透传 pytest 参数（替换默认）
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
    parser.add_argument("--root", default=".", help="仓库根目录（pytest 在此目录下执行）")
    parser.add_argument("--once", action="store_true", help="只跑一轮就退出（cron/联调用）")
    args = parser.parse_args(own)

    pytest_args = rest or DEFAULT_PYTEST_ARGS
    root = Path(args.root).resolve()
    log_dir = root / "reports" / "scheduler"
    cmd = build_command(pytest_args)

    stop = threading.Event()
    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, lambda *_: stop.set())

    interval = timedelta(minutes=args.interval_minutes)
    print(
        f"[scheduler] 每 {args.interval_minutes} 分钟一轮：{' '.join(cmd)}（cwd={root}）",
        flush=True,
    )
    slot = datetime.now()  # 首轮立即执行
    while not stop.is_set():
        started = datetime.now()
        print(f"[scheduler] ▶ {started:%Y-%m-%d %H:%M:%S} 开始", flush=True)
        code, log_path = run_once(cmd, root, log_dir, stop)
        duration = int((datetime.now() - started).total_seconds())
        print(f"[scheduler] 完成：退出码 {code}，用时 {duration}s，日志 {log_path}", flush=True)
        if args.once:
            return code
        slot = next_slot(slot, interval, datetime.now())
        delay = max(0.0, (slot - datetime.now()).total_seconds())
        print(f"[scheduler] 下一轮 {slot:%H:%M:%S}（{delay / 60:.1f} 分钟后）", flush=True)
        stop.wait(delay)
    print("[scheduler] 收到停止信号，退出", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
