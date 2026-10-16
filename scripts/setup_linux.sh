#!/usr/bin/env bash
# apw Linux 一次性安装：venv + 依赖 + Playwright chromium（网页端测试用）。
#
#   bash setup_linux.sh              # 常规（浏览器下载到 ~/.cache/ms-playwright）
#   bash setup_linux.sh --with-deps  # 另装 Chromium 系统库（需 root/sudo，全新服务器/容器推荐）
#
# Python 需 3.11+，可指定解释器：PYTHON=python3.12 bash setup_linux.sh
set -euo pipefail
cd "$(dirname "$0")/.."

PY="${PYTHON:-python3}"
"$PY" -m venv .venv
.venv/bin/pip install -e ".[dev]"

if [ "${1:-}" = "--with-deps" ]; then
    .venv/bin/playwright install --with-deps chromium
else
    .venv/bin/playwright install chromium
fi

echo "[setup] 完成。跑业务链路：bash run_flows.sh（无头）"
