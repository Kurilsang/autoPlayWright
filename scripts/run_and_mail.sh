#!/usr/bin/env bash
# apw 一键跑业务链路并发报告邮件（本机/Linux 通用）。
#
#   bash run_and_mail.sh                 # 跑 flows @ 真实测试环境 + 发带附件报告邮件
#   bash run_and_mail.sh --no-mail       # 只跑，不发信
#   bash run_and_mail.sh --env fixture   # 换环境（夹具站点自测）
#   bash run_and_mail.sh -k smoke        # 其余参数原样透传 pytest
#   bash run_and_mail.sh --to a@x,b@y    # 临时改收件人
#
# 收件人集中配置在 configs/notify.local.yaml 的 notify: 段（gitignored），
# 改名单不用动本脚本，也不用动凭据文件。
#
# 注意：本脚本只跑 flows（业务链路）。tests 是框架自测，需要 --apw-env fixture，
# 与真实环境混跑会出一批假红，故不在这里跑（要跑请单独 pytest tests）。
set -euo pipefail
cd "$(dirname "$0")/.."

PY=".venv/bin/python"
[ -x "$PY" ] || PY=".venv/Scripts/python.exe"
if [ ! -x "$PY" ]; then
    echo "[run_and_mail] 未找到 .venv，先跑：bash setup_linux.sh（Linux）或 python -m venv .venv" >&2
    exit 1
fi
export PYTHONIOENCODING=utf-8

# 自有开关解析，其余透传
SEND_MAIL=1
ENV_NAME="test"
TO=""
CC=""
PASSTHRU=()
while [ $# -gt 0 ]; do
    case "$1" in
        --no-mail) SEND_MAIL=0; shift ;;
        --env) ENV_NAME="$2"; shift 2 ;;
        --env=*) ENV_NAME="${1#*=}"; shift ;;
        --to) TO="$2"; shift 2 ;;
        --to=*) TO="${1#*=}"; shift ;;
        --cc) CC="$2"; shift 2 ;;
        --cc=*) CC="${1#*=}"; shift ;;
        *) PASSTHRU+=("$1"); shift ;;
    esac
done

if [ "$ENV_NAME" = "test" ] && [ ! -f "configs/envs/test.yaml" ]; then
    echo "[run_and_mail] configs/envs/test.yaml 不存在（gitignored），参考 test.example.yaml 配置" >&2
    exit 1
fi

echo "[run_and_mail] 环境=$ENV_NAME 收件人=${TO:-（取自 configs/notify.local.yaml）}"
set +e
"$PY" -m pytest flows --apw-env "$ENV_NAME" -p no:randomly "${PASSTHRU[@]+"${PASSTHRU[@]}"}"
EXITCODE=$?
set -e

# 定位本轮 run 目录（reports/<时间戳>/，取最新且含汇总的一份）
RUN_DIR=$("$PY" - "$EXITCODE" <<'PYEOF'
import sys
from pathlib import Path

reports = Path("reports")
cands = [
    p for p in reports.iterdir()
    if p.is_dir() and p.name[:8].isdigit() and (p / "run-summary.json").exists()
]
if cands:
    print(max(cands, key=lambda p: p.stat().st_mtime))
PYEOF
)
if [ -z "$RUN_DIR" ]; then
    echo "[run_and_mail] 未找到本轮报告目录（reports/<时间戳>/run-summary.json）" >&2
    exit "$EXITCODE"
fi
echo "[run_and_mail] 报告目录: $RUN_DIR"

if [ "$SEND_MAIL" -eq 1 ]; then
    MAIL_ARGS=(--summary "$RUN_DIR/run-summary.json" --policy always --report-zip --env-label "$ENV_NAME")
    [ -n "$TO" ] && MAIL_ARGS+=(--to "$TO")
    [ -n "$CC" ] && MAIL_ARGS+=(--cc "$CC")
    set +e
    "$PY" -m apw.notify "${MAIL_ARGS[@]}"
    MAILCODE=$?
    set -e
    if [ "$MAILCODE" -ne 0 ]; then
        echo "[run_and_mail] 邮件发送失败（测试结果不受影响，报告仍在 $RUN_DIR）" >&2
    fi
else
    echo "[run_and_mail] --no-mail：跳过发信"
fi

echo
if [ "$EXITCODE" -eq 0 ]; then
    echo "[run_and_mail] PASSED - 报告见 $RUN_DIR"
else
    echo "[run_and_mail] FAILED - 取证见 $RUN_DIR"
fi
exit "$EXITCODE"
