"""项目打包 + 部署（Linux 服务器）。

沿用既有部署流程（2026-10-13 首次部署口径）：
  - 平铺结构：包根直接是 src/ flows/ pyproject.toml …（**无顶层目录**，解压即覆盖部署目录）
  - 含 .git：服务器上可 git status/diff 看实际落地版本
  - 包名：apw-deploy-YYYYMMDD.tar.gz
  - 部署目标从 configs/deploy.local.yaml 读（gitignored，模板 deploy.example.yaml）；
    该目录经 SMB 挂载到开发机，故**直接写文件即可，无需 scp/ssh 密码**。

常用命令：

    # 只打包（产出 dist/apw-deploy-<日期>.tar.gz）
    python scripts/pack_release.py

    # 打包 + 直接部署（覆盖代码，保留 .venv/reports/configs 真实配置）
    python scripts/pack_release.py --deploy

    # 部署到指定目录（覆盖本地配置里的 target）
    python scripts/pack_release.py --deploy --target <盘符>:\\<目录>

    # 附带本地真实配置（内网直传；默认不带，凭据不入包）
    python scripts/pack_release.py --deploy --with-secrets

不入包：.venv、reports、.scratch、video、__pycache__、dist，以及 *.local.* 真实凭据
（除非显式 --with-secrets）。
"""
from __future__ import annotations

import argparse
import io
import shutil
import subprocess
import tarfile
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
# 部署目标从 configs/deploy.local.yaml 读（gitignored；模板 deploy.example.yaml）
DEPLOY_CONFIG = ROOT / "configs" / "deploy.local.yaml"
DEFAULT_TARGET_FALLBACK = Path(r"Z:\web_agent_test")


def load_deploy_config() -> dict:
    """读本地部署配置（真实值不入库）。缺文件时返回空 dict，由调用方回退。"""
    if not DEPLOY_CONFIG.exists():
        return {}
    try:
        import yaml

        return yaml.safe_load(DEPLOY_CONFIG.read_text(encoding="utf-8")) or {}
    except Exception:  # noqa: BLE001 - 配置坏了按未配置处理
        return {}

# 入包的一级条目（白名单：宁少勿多，避免把本地凭据/产物带出去）
INCLUDE = [
    "src",
    "tests",
    "flows",
    "examples",
    "locators",
    "configs",
    "scripts",
    "docs",
    "pyproject.toml",
    "README.md",
    "AGENTS.md",
    "setup_linux.sh",
    "run_flows.sh",
    "run_and_mail.sh",
    "run_and_mail.bat",
    "run_scheduler.sh",
    "run_api.sh",
    "run_debug.bat",
    "run_full_debug.bat",
    "run_slides.bat",
    "run_video.bat",
    ".gitignore",
    ".gitattributes",
]

# 二级排除（目录内命中即跳过）
EXCLUDE_DIRS = {"__pycache__", ".pytest_cache", ".ruff_cache", ".mypy_cache", "node_modules"}
EXCLUDE_SUFFIX = {".pyc", ".pyo", ".log"}
# 真实凭据/本机配置：默认不入包
SECRET_PATTERNS = ("*.local.yaml", "*.local.bat", "auth-state.json")
# 部署时绝不覆盖的目录（服务器本地资产/产物）
KEEP_ON_DEPLOY = {".venv", "reports", ".git", "configs"}


def _included_files(include_secrets: bool) -> list[Path]:
    files: list[Path] = []
    for entry in INCLUDE:
        path = ROOT / entry
        if not path.exists():
            continue
        if path.is_file():
            files.append(path)
            continue
        for child in sorted(path.rglob("*")):
            if not child.is_file():
                continue
            if any(part in EXCLUDE_DIRS for part in child.parts):
                continue
            if child.suffix.lower() in EXCLUDE_SUFFIX:
                continue
            if not include_secrets and any(child.match(p) for p in SECRET_PATTERNS):
                continue
            files.append(child)
    return files


def _add_git_snapshot(tar: tarfile.TarFile) -> int:
    """把 .git 目录打进包（沿用既有流程：服务器上可查实际落地版本）。"""
    git_dir = ROOT / ".git"
    if not git_dir.is_dir():
        return 0
    count = 0
    for child in sorted(git_dir.rglob("*")):
        if not child.is_file():
            continue
        # 跳过可能很大的对象包与日志（保留 refs/HEAD/index 足够看版本）
        if child.suffix in {".pack", ".idx"} and child.stat().st_size > 20 * 1024 * 1024:
            continue
        tar.add(child, arcname=child.relative_to(ROOT).as_posix())
        count += 1
    return count


def pack(version: str, include_secrets: bool) -> Path:
    dist = ROOT / "dist"
    dist.mkdir(exist_ok=True)
    archive = dist / f"apw-deploy-{version}.tar.gz"
    files = _included_files(include_secrets)
    if not files:
        raise SystemExit("没有可打包的文件（INCLUDE 白名单可能配错）")

    with tarfile.open(archive, "w:gz") as tar:
        for path in files:
            # 平铺：无顶层目录，解压即覆盖部署目录
            tar.add(path, arcname=path.relative_to(ROOT).as_posix())
        git_count = _add_git_snapshot(tar)
        payload = _deploy_readme(archive.name).encode("utf-8")
        info = tarfile.TarInfo("README_DEPLOY.md")
        info.size = len(payload)
        info.mode = 0o644
        tar.addfile(info, io.BytesIO(payload))

    size_mb = archive.stat().st_size / 1024 / 1024
    print(f"[pack] 产出: {archive}")
    print(f"[pack] 文件 {len(files)} + .git {git_count}，体积 {size_mb:.2f} MB，平铺结构")
    if include_secrets:
        print("[pack] 警告：已附带本地真实配置（*.local.*），请勿外传")
    return archive


def deploy(archive: Path, target: Path, keep_configs: bool = True) -> None:
    """解压到部署目录（覆盖代码，保留 .venv/reports/configs）。"""
    if not target.exists():
        raise SystemExit(
            f"部署目录不存在: {target}\n"
            f"  该路径来自 configs/deploy.local.yaml 的 target（模板 deploy.example.yaml）\n"
            f"  挂载缺失时先在资源管理器访问该 UNC 路径，或用 scp 传包后手动解压"
        )
    print(f"[deploy] 目标: {target}")
    print(f"[deploy] 保留: {', '.join(sorted(KEEP_ON_DEPLOY))}")
    subprocess.run(
        ["tar", "-xzf", str(archive), "-C", str(target)],
        check=True,
    )
    # 包内若误带本地凭据（--with-secrets），落到 configs 下即生效；此处不额外动作
    print("[deploy] 解压完成（代码已覆盖，.venv/reports/configs 未动）")
    if keep_configs:
        missing = [
            p
            for p in ("configs/envs/test.yaml", "configs/secrets.local.yaml")
            if not (target / p).exists()
        ]
        if missing:
            print(f"[deploy] 提示：目标缺配置 {missing}（服务器上从 *.example.yaml 复制填写）")


def _deploy_readme(archive_name: str) -> str:
    remote = load_deploy_config().get("remote_path") or "<部署目录>"
    return f"""# 部署说明（服务器）

部署目录：`{remote}`（开发机经 SMB 挂载访问；真实路径见 `configs/deploy.local.yaml`）

## 服务器上操作（SSH 登录后）

```bash
cd {remote}

# 解压覆盖（包已在目录里；若是从本机新传的包，路径按实际调整）
tar -xzf {archive_name}

# 首次部署才需要装环境；已有 .venv 可跳过
bash setup_linux.sh --with-deps

# 配置真实环境（首次）
cp configs/envs/test.example.yaml configs/envs/test.yaml
cp configs/notify.example.yaml configs/secrets.local.yaml

# 跑起来
bash run_flows.sh
bash run_scheduler.sh

# 回归触发 API（外部服务调用；端口约定 18787）
nohup bash run_api.sh --host 0.0.0.0 --port 18787 > reports/api.log 2>&1 &
curl http://127.0.0.1:18787/health     # 返回 {{"status": "ok", ...}}
```

容器/root 跑 Chromium 需加：

```bash
APW_CHROMIUM_ARGS="--no-sandbox --disable-dev-shm-usage" bash run_flows.sh
```

## 注意

- 解压**不会**动 `.venv/`、`reports/`、`configs/`（服务器本地资产与真实配置）
- 包内 `.git` 可用于核对实际落地版本：`git log --oneline -3`
- 报告产物在 `reports/<run_id>/`（含 `report.html`）
- API 起不来先看 `reports/api.log`：`Errno 98` = 端口被占（换 `--port`）；
  调用方 `Errno 113` = 对方网络不通，与 API 无关（详见 `docs/API.md`）
"""


def resolve_target(cli_target: str = "") -> Path:
    """部署目标解析：--target → configs/deploy.local.yaml 的 target → 回退默认。"""
    if cli_target.strip():
        return Path(cli_target)
    configured = load_deploy_config().get("target")
    if configured:
        return Path(str(configured))
    return DEFAULT_TARGET_FALLBACK


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="pack_release", description="apw 打包/部署")
    parser.add_argument("--version", default=datetime.now().strftime("%Y%m%d"))
    parser.add_argument("--with-secrets", action="store_true", help="附带本地真实配置")
    parser.add_argument("--deploy", action="store_true", help="打包后直接部署到目标目录")
    parser.add_argument(
        "--target",
        default="",
        help="部署目录（缺省读 configs/deploy.local.yaml 的 target）",
    )
    parser.add_argument("--verify", action="store_true", help="打包后校验（列内容/查泄漏）")
    args = parser.parse_args(argv)

    archive = pack(args.version, args.with_secrets)

    if args.verify:
        out = subprocess.run(
            ["tar", "-tzf", str(archive)], capture_output=True, text=True, encoding="utf-8"
        )
        names = [n for n in out.stdout.splitlines() if n]
        tops = sorted({n.split("/")[0] for n in names})
        leaked = [
            n
            for n in names
            if (".local." in n and ".example." not in n) or "auth-state.json" in n
        ]
        print("\n[verify] 顶层条目: " + ", ".join(tops[:25]))
        leak_note = f" -> {leaked[:5]}" if leaked else "（干净）"
        print(f"[verify] 凭据类文件: {len(leaked)} 个{leak_note}")
        print(f"[verify] 总条目: {len(names)}")

    if args.deploy:
        target = resolve_target(args.target)
        # 包拷到部署目录，便于服务器侧留档与手动解压
        try:
            shutil.copy2(archive, target / archive.name)
            print(f"[deploy] 包已放入: {target / archive.name}")
        except OSError as exc:
            print(f"[deploy] 拷贝包失败（不影响解压）: {exc}")
        deploy(archive, target)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
