#!/usr/bin/env python3
"""通用 stdio MCP 代理：透明转发到真实 MCP 服务器，并把 tools/call 记入流水账。

为什么需要
----------
夹具（`apw_test_mcp.py`）自己写调用流水账，故 `verify_tool_called` 能**确定性**核对
「工具真的被本地进程执行过」。真实外部 MCP（npm 包）不会写流水账 → 判定无据可依。
本代理插在客户端与真实服务器之间：逐帧透明转发 JSON-RPC，顺带按 id 配对记账，
产出与夹具**同一份**流水账（`.scratch/auto_playwright/mcp_calls.jsonl`）
→ 判定手段统一，且完全不改变真实服务器的行为与返回。

用法
----
    python mcp_proxy.py --server <name> -- <command> [args...]

例：
    python mcp_proxy.py --server apw-ext-everything -- node <entry.js>

设计要点
--------
- **纯字节转发**（stdin/stdout 走 buffer），不做任何编码/换行改写，避免污染协议帧；
- 仅对副本解码用于记账：请求侧记 `tools/call`，响应侧按 JSON-RPC id 配对取返回值；
- 诊断信息一律走 stderr（客户端收进自己的日志，不干扰协议流）；
- 子进程退出即退出并透传退出码；父进程被终止时尽力清理子进程。
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
from datetime import datetime
from pathlib import Path

# 与夹具同一份流水账（页面对象按此判定；产物落 .scratch，gitignored）
CALL_LOG = (
    Path(__file__).resolve().parents[2] / ".scratch" / "auto_playwright" / "mcp_calls.jsonl"
)


def log(msg: str) -> None:
    print(f"[mcp-proxy] {msg}", file=sys.stderr, flush=True)


def parse_argv(argv: list[str]) -> tuple[str, list[str]]:
    """解析 `--server <name> -- <command> [args...]`。"""
    server = ""
    if "--server" in argv:
        i = argv.index("--server")
        if i + 1 < len(argv):
            server = argv[i + 1]
    if "--" not in argv:
        log("缺少 `--` 分隔符；用法: mcp_proxy.py --server <name> -- <command> [args...]")
        raise SystemExit(2)
    cmd = argv[argv.index("--") + 1 :]
    if not cmd:
        log("`--` 之后未提供命令")
        raise SystemExit(2)
    return server, cmd


def record(server: str, tool: str, args: dict, result: str, is_error: bool) -> None:
    """追加一条调用记录（记账失败不影响协议转发）。

    **原子追加**：多个 MCP 进程（夹具 + 各外部代理）共用同一份流水账；
    Python 文本模式 open("a") 的 write 非原子，并发会出现损坏行（只余尾巴、
    JSON 解析失败）→ 用 os.O_APPEND + 单次 os.write 写完整行。
    """
    try:
        CALL_LOG.parent.mkdir(parents=True, exist_ok=True)
        line = (
            json.dumps(
                {
                    "ts": datetime.now().isoformat(timespec="seconds"),
                    "pid": os.getpid(),
                    "server": server,
                    "tool": tool,
                    "args": args,
                    "result": result,
                    "is_error": is_error,
                    "session": os.environ.get("APW_MCP_SESSION", ""),
                },
                ensure_ascii=False,
            )
            + "\n"
        ).encode("utf-8")
        fd = os.open(CALL_LOG, os.O_APPEND | os.O_CREAT | os.O_WRONLY | os.O_BINARY)
        try:
            os.write(fd, line)
        finally:
            os.close(fd)
    except Exception as exc:  # noqa: BLE001 - 记账失败不挡协议
        log(f"call log failed: {exc!r}")


def extract_text(result: dict) -> str:
    """从 tools/call 响应里取文本内容（尽力而为，取不到就序列化）。"""
    try:
        content = result.get("content")
        if isinstance(content, list):
            parts = [
                str(c.get("text", ""))
                for c in content
                if isinstance(c, dict) and c.get("type") == "text"
            ]
            if parts:
                return "\n".join(parts)
        return json.dumps(result, ensure_ascii=False)[:500]
    except Exception:  # noqa: BLE001
        return ""


def main() -> int:
    server, cmd = parse_argv(sys.argv[1:])
    log(f"start pid={os.getpid()} server={server!r} cmd={cmd!r}")

    proc = subprocess.Popen(  # noqa: S603 - 命令来自用例配置，非用户输入
        cmd,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=None,  # 子进程 stderr 直接继承 → 进客户端日志
        shell=False,
        bufsize=0,
    )
    pending: dict[object, dict] = {}
    lock = threading.Lock()

    def pump_stdin() -> None:
        """客户端 → 子进程：逐行转发，顺带记下 tools/call 请求。"""
        try:
            for line in sys.stdin.buffer:
                if proc.stdin is None:
                    break
                proc.stdin.write(line)
                proc.stdin.flush()
                stripped = line.strip()
                if not stripped:
                    continue
                try:
                    msg = json.loads(stripped.decode("utf-8", "replace"))
                except json.JSONDecodeError:
                    continue
                if msg.get("method") == "tools/call" and msg.get("id") is not None:
                    params = msg.get("params") or {}
                    with lock:
                        pending[msg["id"]] = {
                            "tool": str(params.get("name", "")),
                            "args": params.get("arguments") or {},
                        }
        except Exception as exc:  # noqa: BLE001
            log(f"stdin pump ended: {exc!r}")
        finally:
            try:
                if proc.stdin:
                    proc.stdin.close()
            except Exception:  # noqa: BLE001
                pass

    threading.Thread(target=pump_stdin, daemon=True).start()

    # 子进程 → 客户端：逐行转发，顺带按 id 配对写流水账
    assert proc.stdout is not None
    try:
        for line in proc.stdout:
            sys.stdout.buffer.write(line)
            sys.stdout.buffer.flush()
            stripped = line.strip()
            if not stripped:
                continue
            try:
                msg = json.loads(stripped.decode("utf-8", "replace"))
            except json.JSONDecodeError:
                continue
            if "id" not in msg or ("result" not in msg and "error" not in msg):
                continue
            with lock:
                info = pending.pop(msg["id"], None)
            if not info:
                continue
            if "error" in msg:
                err = msg["error"]
                text = f"ERROR {err.get('code')}: {err.get('message')}"
                record(server, info["tool"], info["args"], text, True)
            else:
                result = msg.get("result") or {}
                record(
                    server,
                    info["tool"],
                    info["args"],
                    extract_text(result),
                    bool(result.get("isError")),
                )
    except Exception as exc:  # noqa: BLE001
        log(f"stdout pump ended: {exc!r}")

    try:
        proc.terminate()
    except Exception:  # noqa: BLE001
        pass
    code = proc.wait()
    log(f"child exited rc={code}")
    return code


if __name__ == "__main__":
    raise SystemExit(main())
