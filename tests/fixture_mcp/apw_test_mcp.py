#!/usr/bin/env python3
"""桌面端 stdio MCP 链路用例的测试夹具服务器（零依赖，仅标准库）。

用途：`flows/desktop_mcp_stdio.yaml` 通过桌面客户端「设置 → MCP → 添加服务器（stdio）」
挂载本进程，验证「本地进程被真实拉起 → 工具可见 → 工具可被调用 → 调用结果回显」。

设计要点：
- **不依赖任何第三方包**（不装 mcp SDK），手写 JSON-RPC 2.0 + 换行分隔帧，
  符合 MCP stdio transport 规范，客户端可直接握手。
- **stdout 只出协议帧**，诊断信息一律走 stderr（否则污染 JSON-RPC 流）。
- 强制 UTF-8：Windows 默认 cp936，不 reconfigure 会导致中文乱码 / 参数解码错误。
- 工具返回值带唯一前缀标记（`APW_STDIO_*_OK`），使「工具真的被调用」可在 UI 上
  确定性断言，而不必依赖 LLM 措辞。

工具（`apwfix_` 前缀：与被测环境里其他 MCP 服务器可能提供的同名工具严格区分，
避免模型选错目标服务器 —— 实测踩坑）：
  apwfix_echo   原样回显（验证参数透传）
  apwfix_add    两数相加（验证计算正确性）
  apwfix_time   返回本机时间 + 进程 pid（验证本地进程真实存在）
资源：
  apw://probe/info   探针说明（验证浏览面板 Resources 标签）
提示词：
  apw_greet          问候语（验证浏览面板 Prompts 标签 + 参数表单）
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime
from pathlib import Path

PROTOCOL_VERSION = "2024-11-05"
SERVER_NAME = "apw-stdio-probe"
SERVER_VERSION = "0.2.0"

# 工具返回前缀：UI 断言锚点（确定性，不含 LLM 措辞）
ECHO_PREFIX = "APW_STDIO_ECHO_OK"
ADD_PREFIX = "APW_STDIO_ADD_OK"
TIME_PREFIX = "APW_STDIO_TIME_OK"

# 调用流水账：页面对象据此**确定性**核对「工具真的被本地进程执行过」，
# 不依赖 LLM 是否把返回内容贴进回答（产物落 .scratch，gitignored）。
CALL_LOG = (
    Path(__file__).resolve().parents[2] / ".scratch" / "auto_playwright" / "mcp_calls.jsonl"
)

TOOLS = [
    {
        "name": "apwfix_echo",
        "description": "APW 回显工具：原样返回输入的文本（stdio 链路验证专用）",
        "inputSchema": {
            "type": "object",
            "properties": {"text": {"type": "string", "description": "要回显的文本"}},
            "required": ["text"],
        },
    },
    {
        "name": "apwfix_add",
        "description": "APW 加法工具：返回两个数之和（stdio 链路验证专用）",
        "inputSchema": {
            "type": "object",
            "properties": {
                "a": {"type": "number", "description": "第一个加数"},
                "b": {"type": "number", "description": "第二个加数"},
            },
            "required": ["a", "b"],
        },
    },
    {
        "name": "apwfix_time",
        "description": "APW 时间工具：返回本机当前时间与进程 pid（证明本地进程被真实拉起）",
        "inputSchema": {"type": "object", "properties": {}},
    },
]

RESOURCES = [
    {
        "uri": "apw://probe/info",
        "name": "APW 探针说明",
        "description": "APW stdio 链路验证用资源（用于检验浏览面板详情展示）",
        "mimeType": "text/plain",
    },
    {
        "uri": "apw://probe/tools",
        "name": "APW 工具清单",
        "description": "本服务器提供的工具清单（文本形式）",
        "mimeType": "text/plain",
    },
]

PROMPTS = [
    {
        "name": "apw_greet",
        "description": "APW 问候提示词（用于检验 Prompts 标签详情展示）",
        "arguments": [{"name": "who", "description": "问候对象", "required": True}],
    },
]


def log(msg: str) -> None:
    print(f"[{SERVER_NAME}] {msg}", file=sys.stderr, flush=True)


def force_utf8_stdio() -> None:
    """MCP stdio 按规范是 UTF-8；Windows 默认 cp936 会让中文变乱码。

    stdout 不修 → 客户端渲染乱码；stdin 不修 → 客户端发来的 UTF-8 参数被误解码。
    """
    for name in ("stdin", "stdout", "stderr"):
        stream = getattr(sys, name, None)
        if stream is None:
            continue
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
    try:
        sys.stdout.reconfigure(newline="\n")
    except (AttributeError, ValueError):
        pass


def send(obj: dict) -> None:
    sys.stdout.write(json.dumps(obj, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def ok(req_id, payload) -> None:
    send({"jsonrpc": "2.0", "id": req_id, "result": payload})


def err(req_id, code: int, message: str) -> None:
    send({"jsonrpc": "2.0", "id": req_id, "error": {"code": code, "message": message}})


def resource_text(uri: str) -> str:
    if uri == "apw://probe/info":
        return (
            "APW_STDIO_RESOURCE_OK\n"
            f"server={SERVER_NAME} version={SERVER_VERSION}\n"
            f"pid={os.getpid()}\n"
            f"time={datetime.now().isoformat(timespec='seconds')}\n"
            "本资源由本地 stdio MCP 进程提供，用于验证桌面端浏览面板。"
        )
    if uri == "apw://probe/tools":
        return "APW 工具清单：\n" + "\n".join(
            f"- {t['name']}: {t['description']}" for t in TOOLS
        )
    return f"未知资源: {uri}"


def record_call(name: str, args: dict, result: str, is_error: bool) -> None:
    """把每次工具调用追加到流水账（只追加，失败不影响协议应答）。

    **原子追加**：客户端会同时拉起多个 MCP 进程（夹具 + 外部 MCP 代理），
    它们都往这一份流水账写入。Python 文本模式 open("a") 的 write 非原子，
    并发时会出现「记录只剩尾巴、JSON 解析失败」的损坏行（实测 2026-10-13：
    一次运行里 apwfix_time 记录丢失，用例误判 tool_not_invoked）。
    故改用 os.O_APPEND + 单次 os.write（一次系统调用写完整行，避免交错）。
    """
    try:
        CALL_LOG.parent.mkdir(parents=True, exist_ok=True)
        line = (
            json.dumps(
                {
                    "ts": datetime.now().isoformat(timespec="seconds"),
                    "pid": os.getpid(),
                    "tool": name,
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


def call_tool(name: str, args: dict) -> tuple[str, bool]:
    if name == "apwfix_echo":
        text = str(args.get("text", ""))
        out = (f"{ECHO_PREFIX}: {text}", False)
    elif name == "apwfix_add":
        try:
            total = float(args.get("a", 0)) + float(args.get("b", 0))
        except (TypeError, ValueError):
            out = ("参数 a/b 必须是数字", True)
        else:
            if total == int(total):
                total = int(total)
            out = (f"{ADD_PREFIX}: {total}", False)
    elif name == "apwfix_time":
        out = (
            f"{TIME_PREFIX}: {datetime.now().isoformat(timespec='seconds')} "
            f"(pid={os.getpid()})",
            False,
        )
    else:
        out = (f"未知工具: {name}", True)
    record_call(name, args, out[0], out[1])
    return out


def handle(msg: dict) -> None:
    method = msg.get("method")
    req_id = msg.get("id")

    if method == "initialize":
        ok(
            req_id,
            {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {
                    "tools": {"listChanged": False},
                    "resources": {"listChanged": False},
                    "prompts": {"listChanged": False},
                },
                "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION},
            },
        )
        return

    if method in ("notifications/initialized", "initialized"):
        log("client initialized")
        return

    if method == "tools/list":
        ok(req_id, {"tools": TOOLS})
        return

    if method == "tools/call":
        params = msg.get("params") or {}
        text, is_error = call_tool(params.get("name", ""), params.get("arguments") or {})
        ok(req_id, {"content": [{"type": "text", "text": text}], "isError": is_error})
        return

    if method == "resources/list":
        ok(req_id, {"resources": RESOURCES})
        return

    if method == "resources/read":
        uri = (msg.get("params") or {}).get("uri", "")
        ok(
            req_id,
            {
                "contents": [
                    {"uri": uri, "mimeType": "text/plain", "text": resource_text(uri)}
                ]
            },
        )
        return

    if method == "prompts/list":
        ok(req_id, {"prompts": PROMPTS})
        return

    if method == "prompts/get":
        params = msg.get("params") or {}
        who = (params.get("arguments") or {}).get("who", "世界")
        ok(
            req_id,
            {
                "description": "APW 问候提示词",
                "messages": [
                    {
                        "role": "user",
                        "content": {
                            "type": "text",
                            "text": f"APW_STDIO_PROMPT_OK: 请向 {who} 问好。",
                        },
                    }
                ],
            },
        )
        return

    if method == "ping":
        ok(req_id, {})
        return

    if req_id is not None:
        err(req_id, -32601, f"Method not found: {method}")


def main() -> int:
    force_utf8_stdio()
    log(f"started pid={os.getpid()} stdout={sys.stdout.encoding}")
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except json.JSONDecodeError as exc:
            log(f"bad json: {exc}")
            continue
        try:
            handle(msg)
        except Exception as exc:  # noqa: BLE001
            log(f"handler error: {exc!r}")
            if msg.get("id") is not None:
                err(msg["id"], -32603, f"Internal error: {exc}")
    log("stdin closed, exiting")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
