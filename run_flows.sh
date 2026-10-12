#!/usr/bin/env bash
# apw 网页端链路运行器（Linux/服务器）：默认无头跑业务链路，参数透传 pytest。
#
#   bash run_flows.sh                    # flows @ 真实测试环境（configs/envs/test.yaml）
#   bash run_flows.sh --apw-env fixture  # 本地夹具站点（零配置自测）
#   bash run_flows.sh --debug            # 调试：窗口可见 + 250ms 慢动作（需显示环境）
#   bash run_flows.sh -k smoke           # 按关键词筛选（任意位置均可）
#
# 容器 root 跑 Chromium 需要 --no-sandbox：
#   APW_CHROMIUM_ARGS="--no-sandbox --disable-dev-shm-usage" bash run_flows.sh
set -euo pipefail
cd "$(dirname "$0")"
export PYTHONIOENCODING=utf-8

if [ ! -x ".venv/bin/pytest" ]; then
    echo "[run_flows] .venv 不存在，先跑：bash setup_linux.sh" >&2
    exit 1
fi

# 解析自有开关（--debug），其余参数原样透传 pytest
DEBUG=0
HAS_ENV=0
PASSTHRU=()
for a in "$@"; do
    case "$a" in
        --debug) DEBUG=1 ;;
        --apw-env|--apw-env=*) HAS_ENV=1; PASSTHRU+=("$a") ;;
        *) PASSTHRU+=("$a") ;;
    esac
done

ARGS=(flows)
if [ "$HAS_ENV" -eq 0 ]; then
    ARGS+=(--apw-env test)
    if [ ! -f "configs/envs/test.yaml" ]; then
        echo "[run_flows] configs/envs/test.yaml 不存在（gitignored），参考 configs/envs/test.example.yaml 配置" >&2
        exit 1
    fi
fi
if [ "$DEBUG" -eq 1 ]; then
    ARGS+=(--apw-headed --apw-slowmo 250)
fi
ARGS+=("${PASSTHRU[@]+"${PASSTHRU[@]}"}")

set +e
.venv/bin/pytest "${ARGS[@]}"
EXITCODE=$?
set -e

echo
if [ "$EXITCODE" -eq 0 ]; then
    echo "[run_flows] PASSED - 报告见 reports/ 最新目录"
else
    echo "[run_flows] FAILED - 取证见 reports/ 最新目录"
fi
exit "$EXITCODE"
