"""本机端到端验收：跑全量 → 起 apw.api → 取 report.zip → 发同内容邮件（联调用，非产品代码）。

用途只有一个：**证明邮件附件的字节 = 外部服务从 `GET /runs/<id>/report.zip` 拿到的字节**。
做法是让 apw.api 真的跑一遍 pytest（不额外消耗 LLM：`--targets tests`），把它 HTTP 吐出的
zip 与本地 `build_report_zip` 的产物逐字节比对，再用同一个产物发摘要邮件。

用法（本机全量 + 发信）：
    python scripts/console_summary.py --targets tests flows --env test --mail

用法（只发已有 run 目录，不重跑）：
    python scripts/console_summary.py --run-dir reports/20261014-160959-xxx --mail

收件人来自集中配置（configs/notify.local.yaml 的 notify: 段），也可 --to 覆盖。
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.request
import zipfile
from io import BytesIO
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))
sys.path.insert(0, str(REPO_ROOT))


def _load_summary(run_dir: Path) -> dict:
    return json.loads((run_dir / "run-summary.json").read_text(encoding="utf-8"))


def _api_zip(run_id: str, host: str, port: int) -> bytes:
    """起 apw.api（本机免鉴权）→ POST /runs → 轮询 → GET report.zip。"""
    from http.server import ThreadingHTTPServer

    from apw.api import RunManager, make_handler

    manager = RunManager(REPO_ROOT)
    server = ThreadingHTTPServer((host, port), make_handler(manager, "", f"http://{host}:{port}"))
    server.apw_log = lambda msg: print(msg, flush=True)
    import threading

    threading.Thread(target=server.serve_forever, daemon=True).start()
    print(f"[accept] apw.api 监听 http://{host}:{port}")

    body = json.dumps({"env": "fixture", "targets": ["tests"]}).encode()
    request = urllib.request.Request(
        f"http://{host}:{port}/runs",
        data=body,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=30) as resp:
        queued = json.loads(resp.read().decode("utf-8"))
    api_run_id = queued["run_id"]
    print(f"[accept] API 侧跑 run_id={api_run_id}（targets=tests，不额外消耗 LLM）")

    deadline = time.monotonic() + 1800
    while time.monotonic() < deadline:
        with urllib.request.urlopen(f"http://{host}:{port}/runs/{api_run_id}", timeout=30) as r:
            state = json.loads(r.read().decode("utf-8"))
        if state["status"] in ("finished", "failed"):
            break
        time.sleep(5)
    else:
        raise TimeoutError("API 侧 run 未在 30 分钟内结束")

    with urllib.request.urlopen(
        f"http://{host}:{port}/runs/{api_run_id}/report.zip", timeout=60
    ) as r:
        blob = r.read()
    print(f"[accept] 取到 report.zip {len(blob)} 字节（run_dir={state.get('run_dir')}）")
    server.shutdown()
    return blob


def _compare(api_blob: bytes, run_dir: Path) -> Path:
    from apw.api import build_report_zip

    local = build_report_zip(run_dir)
    same = local == api_blob
    print(
        f"[accept] 邮件附件口径核对: {'一致' if same else '不一致'}"
        f"（{len(local)} vs {len(api_blob)} 字节）"
    )
    if not same:
        with zipfile.ZipFile(BytesIO(api_blob)) as zf:
            print("[accept] API zip 内容:", zf.namelist())
        raise SystemExit("[accept] 附件口径不一致，中止（这正是本脚本要拦住的问题）")
    return run_dir


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="console_summary", description="APW 全量跑测 + 邮件验收")
    parser.add_argument("--targets", nargs="*", default=["tests", "flows"])
    parser.add_argument("--env", default="test")
    parser.add_argument("--run-dir", help="跳过跑测，直接用已有 run 目录发信")
    parser.add_argument("--to", help="收件人覆盖（逗号分隔）")
    parser.add_argument("--cc", help="抄送（逗号分隔）")
    parser.add_argument("--mail", action="store_true", help="发送摘要邮件（附 report.zip）")
    parser.add_argument("--no-zip", action="store_true", help="不带附件（仅正文）")
    parser.add_argument("--sanitize", action="store_true", help="zip 内文本产物脱敏后再发")
    parser.add_argument("--api-port", type=int, default=18789)
    parser.add_argument("--skip-accept", action="store_true", help="跳过 API 口径核对")
    args = parser.parse_args(argv)

    if args.run_dir:
        run_dir = Path(args.run_dir).resolve()
        print(f"[accept] 使用已有 run 目录 {run_dir}")
        run_id = run_dir.name
    else:
        import os
        import subprocess

        cmd = [
            sys.executable, "-m", "pytest", *args.targets,
            "--apw-env", args.env, "-p", "no:randomly",
        ]
        print(f"[accept] 跑全量: {' '.join(cmd)}")
        started = time.time()
        proc = subprocess.run(
            cmd, cwd=str(REPO_ROOT), env={**os.environ, "PYTHONIOENCODING": "utf-8"}
        )
        print(f"[accept] pytest 退出码 {proc.returncode}（用时 {time.time() - started:.0f}s）")

        reports = REPO_ROOT / "reports"
        candidates = [
            p for p in reports.iterdir()
            if p.is_dir() and p.name[:8].isdigit() and p.stat().st_mtime >= started - 5
        ]
        if not candidates:
            print("[accept] 未找到本轮 run 目录", file=sys.stderr)
            return 2
        run_dir = max(candidates, key=lambda p: p.stat().st_mtime)
        run_id = run_dir.name
        print(f"[accept] run_id={run_id}")

    if not args.skip_accept:
        api_blob = _api_zip(run_id, "127.0.0.1", args.api_port)
        _compare(api_blob, run_dir)

    if not args.mail:
        print("[accept] 未指定 --mail，仅产出 report.zip 口径核对")
        return 0

    from apw.notify import load_mail_config, notify_from_summary

    cfg = load_mail_config()
    if args.cc:
        cfg = cfg.model_copy(update={"cc": [a.strip() for a in args.cc.split(",") if a.strip()]})
    to = [a.strip() for a in args.to.split(",") if a.strip()] if args.to else None
    sent = notify_from_summary(
        run_dir / "run-summary.json",
        policy="always",
        cfg=cfg,
        to=to,
        report_zip=not args.no_zip,
        sanitize=args.sanitize,
        env=args.env,
        targets=args.targets,
    )
    summary = _load_summary(run_dir)
    print(
        f"[accept] 邮件{'已发送' if sent else '未发送'} → {to or cfg.to}"
        f"（{summary['passed']}/{summary['total']} 通过，transport={cfg.transport}）"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
