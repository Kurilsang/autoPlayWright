#!/usr/bin/env bash
# apw 定时执行守护（Linux/服务器）：默认每 30 分钟跑一轮业务链路（前台常驻）。
#
#   bash run_scheduler.sh                          # 常驻：每 30 分钟 flows --apw-env test
#   bash run_scheduler.sh --interval-minutes 60    # 调整间隔
#   bash run_scheduler.sh --cron "0 21 * * *"      # cron 钟点锚定：每天 21:00（周/月频率同理）
#   bash run_scheduler.sh --cron "0 21 * * *" --cron "0 18 * * 5"   # 多档并集：+每周五 18:00
#   bash run_scheduler.sh --once                   # 单跑一轮就退出（联调/冒烟，立即执行）
#   bash run_scheduler.sh -- --apw-env fixture     # `--` 后透传 pytest 参数（替换默认）
#
# 常驻建议挂 tmux/systemd（service 示例见 README「定时执行」）；Ctrl+C / SIGTERM 优雅停。
# 每轮输出落 reports/scheduler/run-<ts>.log；轮内运行的报告照常落 reports/<run_id>/。
set -euo pipefail
cd "$(dirname "$0")"
export PYTHONIOENCODING=utf-8

if [ ! -x ".venv/bin/python" ]; then
    echo "[run_scheduler] .venv 不存在，先跑：bash setup_linux.sh" >&2
    exit 1
fi

exec .venv/bin/python -m apw.scheduler --root . "$@"
