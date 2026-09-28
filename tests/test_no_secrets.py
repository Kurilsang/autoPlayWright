"""敏感信息红线门禁：入库文件不得含内网 IP / 凭据值 / 产品名（AGENTS 硬约束的机器化）。

治理依据：红线两度返工（e659178 敏感信息出库、2026-09-24 快照脱敏批），
散文约束不足 → 确定性门禁。本文件自身含模式字面量，扫描时跳过。
"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

_ALLOW_VALUE = ("example", "your", "placeholder", "<", "${", "apw_")

_PATTERNS = {
    "内网 IP": re.compile(
        r"\b(?:10\.\d+\.\d+\.\d+|192\.168\.\d+\.\d+|172\.(?:1[6-9]|2\d|3[01])\.\d+\.\d+)\b"
    ),
    "产品名": re.compile(r"Aml Agent|Amlcowork|AML Code"),
    "凭据值": re.compile(
        r"(?im)^\s*[\"']?(?:password|passwd|secret_key|api_token|token)[\"']?\s*[:=]\s*"
        r"[\"']?([^\"'\s<#$`=][^\"'\s=]{4,})"
    ),
}
_SKIP_SUFFIX = {".png", ".jpg", ".jpeg", ".gif", ".ico", ".woff", ".woff2", ".pdf", ".zip"}
_SELF = Path(__file__).name


def _tracked_files() -> list[str]:
    out = subprocess.run(
        ["git", "ls-files"], capture_output=True, text=True, encoding="utf-8"
    )
    return out.stdout.split() if out.returncode == 0 else []


def test_tracked_files_have_no_secrets() -> None:
    violations: list[str] = []
    for name in _tracked_files():
        if Path(name).name == _SELF or Path(name).suffix.lower() in _SKIP_SUFFIX:
            continue
        text = Path(name).read_text(encoding="utf-8", errors="ignore")
        for label, pattern in _PATTERNS.items():
            for match in pattern.finditer(text):
                if label == "凭据值":
                    value = match.group(1).lower()
                    if any(allow in value for allow in _ALLOW_VALUE):
                        continue
                violations.append(f"{name}: [{label}] {match.group(0)[:80]}")
    assert not violations, "敏感信息红线违规（内网 IP / 凭据值 / 产品名不得入库）：\n" + "\n".join(
        violations
    )
