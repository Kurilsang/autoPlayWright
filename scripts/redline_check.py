"""红线扫描（开发自检用，含未入库新文件）：内网 IP / 凭据值 / 产品名 / 个人路径。

    python scripts/redline_check.py
"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

PATTERNS = {
    "内网 IP": re.compile(
        r"\b(?:10\.\d+\.\d+\.\d+|192\.168\.\d+\.\d+|172\.(?:1[6-9]|2\d|3[01])\.\d+\.\d+)\b"
    ),
    "产品名": re.compile(r"Aml Agent|Amlcowork|AML Code"),
    "凭据值": re.compile(
        r"(?im)^\s*[\"']?(?:password|passwd|secret_key|api_token|token)[\"']?\s*[:=]\s*"
        r"[\"']([^\"'\s<#$`=][^\"'\s=]{4,})[\"']\s*$"
    ),
    "个人路径": re.compile(r"/mnt/fileroot/[a-z]+\.[a-z]+/|fileroot/[a-z]+\.[a-z]+"),
    "个人邮箱": re.compile(r"[\w.+-]+@(?:amlogic|1catai)[\w.-]*"),
}
ALLOW_VALUE = ("example", "your", "placeholder", "<", "${", "apw_")
SKIP_SUFFIX = {".png", ".jpg", ".jpeg", ".gif", ".ico", ".woff", ".woff2", ".pdf", ".zip", ".gz"}
# 这些文件自身含模式字面量（门禁/扫描器），按既有口径跳过
SKIP_NAMES = {Path(__file__).name, "test_no_secrets.py"}


def tracked_and_new() -> list[Path]:
    out = subprocess.run(["git", "ls-files"], capture_output=True, text=True, encoding="utf-8")
    names = out.stdout.split() if out.returncode == 0 else []
    # 补上尚未入库的新文件（提交前也会被门禁扫到）
    extra = subprocess.run(
        ["git", "ls-files", "--others", "--exclude-standard"],
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    names += extra.stdout.split() if extra.returncode == 0 else []
    return [ROOT / n for n in sorted(set(names))]


def main() -> int:
    violations: list[str] = []
    for path in tracked_and_new():
        if (
            not path.exists()
            or path.name in SKIP_NAMES
            or path.suffix.lower() in SKIP_SUFFIX
        ):
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        for label, pattern in PATTERNS.items():
            for match in pattern.finditer(text):
                if label == "凭据值" and any(a in match.group(1).lower() for a in ALLOW_VALUE):
                    continue
                rel = path.relative_to(ROOT).as_posix()
                violations.append(f"{rel}: [{label}] {match.group(0)[:70]}")
    print(f"扫描文件数: {len(tracked_and_new())}")
    print(f"违规数: {len(violations)}")
    for item in violations[:20]:
        print("  " + item)
    return 1 if violations else 0


if __name__ == "__main__":
    raise SystemExit(main())
