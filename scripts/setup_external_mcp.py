#!/usr/bin/env python3
"""落地「外部真实 MCP」npm 包到 .scratch/mcp_servers（gitignored）。

为什么需要
----------
`flows/desktop_mcp_stdio.yaml` 的「外部 MCP」段要挂两个真实第三方 MCP 服务器：
  @modelcontextprotocol/server-everything  官方参考实现（能力面全、返回值确定）
  @mcpcn/12306-ticket-search-mcp           真实业务（12306 火车票查询）

为什么不用 npx
--------------
实测客户端 StdioClientTransport 以 `shell:false` spawn，Node 24 下：
  `npx`      → ENOENT（裸命令找不到）
  `npx.cmd`  → EINVAL（Node 24 安全策略拒绝 .cmd）
故安装为本地固定副本，用 `node <entry>` 直接执行（实测可跑通）。

用法
----
    .venv/Scripts/python scripts/setup_external_mcp.py          # 幂等，已装则跳过
    .venv/Scripts/python scripts/setup_external_mcp.py --force  # 强制重装
    .venv/Scripts/python scripts/setup_external_mcp.py --check  # 只校验不安装
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
TARGET = REPO_ROOT / ".scratch" / "mcp_servers"

PACKAGES = [
    "@modelcontextprotocol/server-everything",
    "@mcpcn/12306-ticket-search-mcp",
]

# 每个包的入口（相对 node_modules），供安装后握手自检
ENTRIES = {
    "everything": "@modelcontextprotocol/server-everything/dist/index.js",
    "12306": "@mcpcn/12306-ticket-search-mcp/dist/index.js",
}

PROBE = json.dumps(
    {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "setup-probe", "version": "1"},
        },
    }
)


def info(msg: str) -> None:
    print(f"[setup-mcp] {msg}", flush=True)


def entry_path(label: str) -> Path:
    return TARGET / "node_modules" / ENTRIES[label]


def handshake(label: str, timeout: int = 40) -> tuple[bool, str]:
    """对入口跑一次 MCP initialize 握手，确认真的能起。"""
    path = entry_path(label)
    if not path.exists():
        return False, f"入口缺失 {path}"
    try:
        proc = subprocess.run(  # noqa: S603 - 固定 node + 本地入口
            ["node", str(path)],
            input=PROBE + "\n",
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            shell=False,
        )
    except subprocess.TimeoutExpired:
        return False, "握手超时"
    except FileNotFoundError:
        return False, "未找到 node"
    first = next((ln for ln in proc.stdout.splitlines() if ln.strip()), "")
    if '"serverInfo"' not in first:
        return False, f"响应异常: {first[:120] or proc.stderr[:120]}"
    try:
        name = json.loads(first)["result"]["serverInfo"]["name"]
    except Exception:  # noqa: BLE001
        name = "?"
    return True, f"server={name}"


def installed() -> bool:
    return all(entry_path(label).exists() for label in ENTRIES)


def install(force: bool) -> int:
    if not shutil.which("node"):
        info("✗ 未找到 node。外部 MCP 需要 Node.js（实测 v24 可用）。")
        return 1

    node_ver = subprocess.run(  # noqa: S603
        ["node", "--version"], capture_output=True, text=True, timeout=20
    ).stdout.strip()
    info(f"仓库: {REPO_ROOT}")
    info(f"目标: {TARGET}")
    info(f"node: {shutil.which('node')} {node_ver}")

    if installed() and not force:
        info("已安装，跳过（--force 可强制重装）")
        return 0

    TARGET.mkdir(parents=True, exist_ok=True)
    manifest = TARGET / "package.json"
    # 私有 package.json：避免 npm 向上查找宿主工程的 package.json
    manifest.write_text(
        '{"name":"apw-external-mcp","private":true,"version":"1.0.0"}\n', encoding="utf-8"
    )

    info(f"npm install {' '.join(PACKAGES)} ...")
    proc = subprocess.run(  # noqa: S603
        ["npm", "install", *PACKAGES, "--no-fund", "--no-audit", "--loglevel=error"],
        cwd=str(TARGET),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        shell=True,  # npm 是 .cmd，Windows 下需 shell
        timeout=900,
    )
    if proc.returncode != 0:
        info(f"✗ npm install 失败（退出码 {proc.returncode}）")
        info((proc.stdout or "")[-800:])
        info((proc.stderr or "")[-800:])
        return 1
    info("npm install 完成")
    return 0


def verify() -> bool:
    all_ok = True
    for label in ENTRIES:
        ok, detail = handshake(label)
        info(f"{'✓' if ok else '✗'} {label}: {detail}")
        all_ok = all_ok and ok
    return all_ok


def main() -> int:
    ap = argparse.ArgumentParser(description="落地外部真实 MCP（npm）到 .scratch/mcp_servers")
    ap.add_argument("--force", action="store_true", help="强制重装")
    ap.add_argument("--check", action="store_true", help="只校验（不安装）")
    args = ap.parse_args()

    if not args.check:
        rc = install(args.force)
        if rc != 0:
            return rc

    if not verify():
        info("✗ 存在未就绪的外部 MCP —— 用例会 fail_evidence 指出该缺口")
        return 1
    info(f"完成。入口根目录: {TARGET / 'node_modules'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
