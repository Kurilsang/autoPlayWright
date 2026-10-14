#!/usr/bin/env bash
# apw 回归触发 API（Linux/服务器）：外部服务定时调用触发跑测、取 zip 产物自行外发邮件。
#
#   bash run_api.sh                                  # 本机监听 18787（仅本机可访问）
#   APW_API_TOKEN=xxx bash run_api.sh --host 0.0.0.0 # 跨机暴露（必须配 token）
#
# 端口约定：默认 18787（避开常见服务占用的 8787）；被占用时 --port <空闲端口>
# 启动前自检：ss -lntp | grep 18787   （有输出=已被占用，换端口）
#
# 接口：
#   POST /runs                     触发一轮（异步，返回 run_id/status_url/report_zip）
#   GET  /runs/<run_id>            查状态与结果摘要（summary/flows/failed_flows）
#   GET  /runs/<run_id>/report.zip 下载产物包（report.html + JSON + 失败截图）
#   GET  /runs                     最近若干轮      GET /health  存活探针
set -euo pipefail
cd "$(dirname "$0")"
export PYTHONIOENCODING=utf-8

if [ ! -x ".venv/bin/python" ]; then
    echo "[run_api] .venv 不存在，先跑：bash setup_linux.sh" >&2
    exit 1
fi

exec .venv/bin/python -m apw.api "$@"
