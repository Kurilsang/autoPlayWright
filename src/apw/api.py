"""回归触发 API：外部服务定时触发跑测、取 zip 产物、由其自建邮件通道外发。

定位同 reporter/notify——引擎与 pytest 的**下游消费者**，不反向依赖：

    POST /runs                     触发一轮（异步排队，立即返回 run_id）
    GET  /runs/<run_id>            查状态与结果摘要
    GET  /runs/<run_id>/report.zip 下载产物包（report.html + JSON + 截图）
    GET  /runs                     最近若干轮（外部服务对账/补拉）
    GET  /health                   存活探针

设计取舍（与框架口径一致）：
- 单飞队列：同时只跑一轮（框架硬约束 worker ≤5，后端 LLM 限流，叠加必炸）
- 完成回调：跑完 POST callback_url（对方不必轮询），失败静默留日志不影响结果
- 鉴权：Bearer token（APW_API_TOKEN / secrets.local.yaml），默认只绑 127.0.0.1
- 调度归属外部服务：本模块不做定时，`apw.scheduler` 保留但二者不并用

用法：
    python -m apw.api --host 127.0.0.1 --port 18787 [--token <t>]
"""
from __future__ import annotations

import io
import json
import os
import queue
import secrets as pysecrets
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
import zipfile
from dataclasses import dataclass, field
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from apw.notify.mail import repo_root

_ARTIFACT_EXCLUDE = {".pyc"}
_MAX_BODY = 64 * 1024


# ---------- 任务模型 ----------


@dataclass
class RunRequest:
    """一轮回归的触发参数（外部服务传什么就跑什么）。"""

    env: str = "fixture"
    targets: list[str] = field(default_factory=lambda: ["flows"])
    tags: list[str] = field(default_factory=list)
    flows_dir: str = "flows"
    headed: bool = False
    slowmo: int = 0
    extra_args: list[str] = field(default_factory=list)
    callback_url: str = ""
    callback_token: str = ""

    def to_pytest_args(self) -> list[str]:
        args = list(self.targets) or ["flows"]
        args += ["--apw-env", self.env, "--apw-flows-dir", self.flows_dir]
        if self.headed:
            args.append("--apw-headed")
        if self.slowmo:
            args += ["--apw-slowmo", str(self.slowmo)]
        if self.tags:
            args += ["-m", " or ".join(self.tags)]
        return args + list(self.extra_args)


@dataclass
class RunState:
    run_id: str
    request: RunRequest
    status: str = "queued"  # queued | running | finished | failed
    exit_code: int | None = None
    started_at: str = ""
    finished_at: str = ""
    run_dir: str = ""
    error: str = ""

    def snapshot(self, base: str = "") -> dict[str, Any]:
        out: dict[str, Any] = {
            "run_id": self.run_id,
            "status": self.status,
            "exit_code": self.exit_code,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "error": self.error,
            "request": {
                "env": self.request.env,
                "targets": self.request.targets,
                "tags": self.request.tags,
            },
        }
        summary = _read_summary(self.run_dir)
        if summary:
            out["summary"] = {
                "total": summary.get("total", 0),
                "passed": summary.get("passed", 0),
                "failed": summary.get("failed", 0),
                "skipped": summary.get("skipped", 0),
            }
            out["flows"] = [
                {
                    "flow_id": f.get("flow_id"),
                    "name": f.get("name"),
                    "status": f.get("status"),
                    "skip_reason": f.get("skip_reason"),
                    "duration_ms": f.get("duration_ms"),
                }
                for f in summary.get("flows", [])
            ]
            out["failed_flows"] = [
                f for f in out["flows"] if f.get("status") == "failed"
            ]
        if base and self.status == "finished":
            out["report_zip"] = f"{base}/runs/{self.run_id}/report.zip"
        return out


# ---------- 产物 ----------


def _read_summary(run_dir: str) -> dict:
    if not run_dir:
        return {}
    path = Path(run_dir) / "run-summary.json"
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def _latest_run_dir(reports_dir: Path, since: float) -> str:
    """取本轮新产出的 run 目录（reports/<run_id>/，按时间戳前缀过滤本次）。"""
    if not reports_dir.exists():
        return ""
    candidates = [
        p
        for p in reports_dir.iterdir()
        if p.is_dir() and p.name[:8].isdigit() and p.stat().st_mtime >= since - 5
    ]
    if not candidates:
        return ""
    return str(max(candidates, key=lambda p: p.stat().st_mtime))


def build_report_zip(run_dir: str | Path, *, sanitize: bool = False) -> bytes:
    """打包 run 目录：report.html + run-summary.json + 明细 JSON + 失败截图。

    sanitize=True 时对文本产物过 apw.sanitize（外发脱敏；默认关闭=内网可信调用）。
    """
    root = Path(run_dir)
    if not root.exists():
        raise FileNotFoundError(f"run 目录不存在: {root}")
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for path in sorted(root.rglob("*")):
            if not path.is_file() or path.suffix.lower() in _ARTIFACT_EXCLUDE:
                continue
            arcname = f"{root.name}/{path.relative_to(root).as_posix()}"
            if sanitize and path.suffix.lower() in {".json", ".html", ".txt", ".log"}:
                try:
                    from apw.sanitize import sanitize_text

                    zf.writestr(arcname, sanitize_text(path.read_text(encoding="utf-8")))
                    continue
                except Exception:  # noqa: BLE001 - 脱敏失败退回原文件（不静默丢产物）
                    pass
            zf.write(path, arcname)
    return buffer.getvalue()


# ---------- 单飞队列 ----------


class RunManager:
    """单飞执行器：同时只跑一轮，其余排队；结果留内存 + 磁盘产物。"""

    def __init__(self, root: Path, reports_dir: str = "reports") -> None:
        self.root = root
        self.reports_dir = root / reports_dir
        self.runs: dict[str, RunState] = {}
        self.order: list[str] = []
        self._queue: queue.Queue[str] = queue.Queue()
        self._lock = threading.Lock()
        self._worker = threading.Thread(target=self._loop, daemon=True)
        self._worker.start()

    def submit(self, req: RunRequest) -> RunState:
        run_id = f"{datetime.now():%Y%m%d-%H%M%S}-{pysecrets.token_hex(3)}"
        state = RunState(run_id=run_id, request=req)
        with self._lock:
            self.runs[run_id] = state
            self.order.append(run_id)
        self._queue.put(run_id)
        return state

    def get(self, run_id: str) -> RunState | None:
        return self.runs.get(run_id)

    def recent(self, limit: int = 20) -> list[RunState]:
        with self._lock:
            ids = list(reversed(self.order))[:limit]
        return [self.runs[i] for i in ids]

    def _loop(self) -> None:
        while True:
            run_id = self._queue.get()
            state = self.runs.get(run_id)
            if state is None:
                continue
            try:
                self._execute(state)
            except Exception as exc:  # noqa: BLE001 - 单轮异常不拖垮服务
                state.status = "failed"
                state.error = f"{type(exc).__name__}: {exc}"
                state.finished_at = _now()

    def _execute(self, state: RunState) -> None:
        state.status = "running"
        state.started_at = _now()
        since = time.time()
        cmd = [sys.executable, "-m", "pytest", *state.request.to_pytest_args()]
        env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
        proc = subprocess.run(
            cmd,
            cwd=str(self.root),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=env,
        )
        state.exit_code = proc.returncode
        state.run_dir = _latest_run_dir(self.reports_dir, since)
        state.status = "finished"
        state.finished_at = _now()
        self._notify(state, proc.stdout or "")

    def _notify(self, state: RunState, stdout: str) -> None:
        url = state.request.callback_url
        if not url:
            return
        payload = state.snapshot()
        payload["stdout_tail"] = stdout[-2000:]
        data = json.dumps(payload, ensure_ascii=False).encode()
        request = urllib.request.Request(
            url,
            data=data,
            headers={"Content-Type": "application/json; charset=utf-8"},
        )
        if state.request.callback_token:
            request.add_header("Authorization", f"Bearer {state.request.callback_token}")
        try:
            urllib.request.urlopen(request, timeout=15)
        except (urllib.error.URLError, OSError):
            pass  # 回调失败不影响本轮结果（外部服务可补拉 /runs/<id>）


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


# ---------- HTTP 层 ----------


def make_handler(manager: RunManager, token: str, base_url: str = ""):
    class Handler(BaseHTTPRequestHandler):
        server_version = "apw-api/1.0"

        def log_message(self, fmt, *args):  # noqa: ANN001, ANN002 - 精简访问日志
            message = fmt % args
            log = getattr(self.server, "apw_log", None)
            if log is not None:
                log(f"[apw-api] {self.address_string()} {message}")
                return
            print(f"[apw-api] {self.address_string()} {message}", flush=True)

        # ---- 工具 ----
        def _json(self, code: int, payload: dict) -> None:
            body = json.dumps(payload, ensure_ascii=False, indent=2).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _authorized(self) -> bool:
            if not token:
                return True
            header = self.headers.get("Authorization", "")
            return header == f"Bearer {token}"

        def _require_auth(self) -> bool:
            if self._authorized():
                return True
            self._json(401, {"error": "unauthorized", "hint": "Authorization: Bearer <token>"})
            return False

        # ---- 路由 ----
        def do_GET(self) -> None:  # noqa: N802 - http.server 命名约定
            path = self.path.split("?", 1)[0].rstrip("/")
            if path == "/health":
                self._json(200, {"status": "ok", "runs": len(manager.runs)})
                return
            if not self._require_auth():
                return
            if path == "/runs":
                self._json(200, {"runs": [s.snapshot(base_url) for s in manager.recent()]})
                return
            parts = [p for p in path.split("/") if p]
            if len(parts) == 2 and parts[0] == "runs":
                state = manager.get(parts[1])
                if state is None:
                    self._json(404, {"error": "run not found", "run_id": parts[1]})
                    return
                self._json(200, state.snapshot(base_url))
                return
            if len(parts) == 3 and parts[0] == "runs" and parts[2] == "report.zip":
                self._send_zip(parts[1])
                return
            self._json(404, {"error": "not found", "path": self.path})

        def do_POST(self) -> None:  # noqa: N802 - http.server 命名约定
            if not self._require_auth():
                return
            path = self.path.split("?", 1)[0].rstrip("/")
            if path != "/runs":
                self._json(404, {"error": "not found", "path": self.path})
                return
            length = int(self.headers.get("Content-Length") or 0)
            if length > _MAX_BODY:
                self._json(413, {"error": "body too large"})
                return
            raw = self.rfile.read(length) if length else b"{}"
            try:
                payload = json.loads(raw.decode("utf-8") or "{}")
            except (json.JSONDecodeError, UnicodeDecodeError) as exc:
                self._json(400, {"error": f"invalid json: {exc}"})
                return
            req = _parse_request(payload)
            state = manager.submit(req)
            self._json(
                202,
                {
                    "run_id": state.run_id,
                    "status": state.status,
                    "status_url": f"{base_url}/runs/{state.run_id}",
                    "report_zip": f"{base_url}/runs/{state.run_id}/report.zip",
                },
            )

        def _send_zip(self, run_id: str) -> None:
            state = manager.get(run_id)
            if state is None:
                self._json(404, {"error": "run not found", "run_id": run_id})
                return
            if state.status != "finished" or not state.run_dir:
                self._json(409, {"error": "run not finished", "status": state.status})
                return
            try:
                blob = build_report_zip(state.run_dir)
            except FileNotFoundError as exc:
                self._json(404, {"error": str(exc)})
                return
            self.send_response(200)
            self.send_header("Content-Type", "application/zip")
            self.send_header(
                "Content-Disposition",
                f'attachment; filename="{Path(state.run_dir).name}-report.zip"',
            )
            self.send_header("Content-Length", str(len(blob)))
            self.end_headers()
            self.wfile.write(blob)

    return Handler


def _parse_request(payload: dict) -> RunRequest:
    """宽松解析触发体：只取认识的字段，避免外部服务多传字段导致 400。"""
    def _str_list(key: str) -> list[str]:
        value = payload.get(key) or []
        if isinstance(value, str):
            return [value]
        return [str(v) for v in value]

    targets = _str_list("targets")
    return RunRequest(
        env=str(payload.get("env") or "fixture"),
        targets=targets or ["flows"],
        tags=_str_list("tags"),
        flows_dir=str(payload.get("flows_dir") or "flows"),
        headed=bool(payload.get("headed", False)),
        slowmo=int(payload.get("slowmo") or 0),
        extra_args=_str_list("extra_args"),
        callback_url=str(payload.get("callback_url") or ""),
        callback_token=str(payload.get("callback_token") or ""),
    )


def serve(host: str, port: int, token: str = "", reports_dir: str = "reports") -> None:
    root = repo_root()
    manager = RunManager(root, reports_dir)
    base_url = f"http://{host}:{port}"
    server = ThreadingHTTPServer((host, port), make_handler(manager, token, base_url))
    print(f"[apw-api] 监听 {base_url}（鉴权={'Bearer' if token else '关闭'}，仓库根={root}）")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[apw-api] 收到中断，退出")
    finally:
        server.server_close()


def resolve_token(cli_token: str = "") -> str:
    """token 解析顺序：--token → 环境变量 APW_API_TOKEN → secrets.local.yaml 的 api.token。

    与框架其余凭据同口径（见 auth/base.py）：真实值只存本地 gitignored 文件或环境变量。
    """
    if cli_token.strip():
        return cli_token.strip()
    env = os.environ.get("APW_API_TOKEN", "").strip()
    if env:
        return env
    path = repo_root() / "configs/secrets.local.yaml"
    if not path.exists():
        return ""
    try:
        import yaml

        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except Exception:  # noqa: BLE001 - 配置坏了按未配置处理，由启动校验兜底
        return ""
    return str((data.get("api") or {}).get("token") or "").strip()


def generate_token() -> str:
    """生成一个可用的 Bearer token（写进 configs/secrets.local.yaml 的 api.token）。"""
    return pysecrets.token_urlsafe(32)


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(prog="apw.api", description="APW 回归触发 API")
    parser.add_argument("--host", default="127.0.0.1", help="监听地址（默认仅本机）")
    parser.add_argument("--port", type=int, default=18787)
    parser.add_argument(
        "--token",
        default="",
        help="Bearer 令牌（缺省依次读 APW_API_TOKEN、configs/secrets.local.yaml 的 api.token）",
    )
    parser.add_argument(
        "--gen-token",
        action="store_true",
        help="生成一个随机 token 并退出（粘进 configs/secrets.local.yaml 的 api.token）",
    )
    parser.add_argument("--reports-dir", default="reports")
    args = parser.parse_args(argv)

    if args.gen_token:
        print(generate_token())
        return 0

    token = resolve_token(args.token)
    if args.host not in ("127.0.0.1", "localhost") and not token:
        print(
            "[apw-api] 拒绝启动：绑定非本机地址必须配置 token\n"
            "  --token <t> / APW_API_TOKEN=<t> / configs/secrets.local.yaml 的 api.token\n"
            "  生成：python -m apw.api --gen-token"
        )
        return 2
    if not token:
        print("[apw-api] 未配置 token：接口无鉴权（仅本机 127.0.0.1 可访问）")
    serve(args.host, args.port, token, args.reports_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
