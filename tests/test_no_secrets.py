"""敏感信息红线门禁：入库文件不得含内网 IP / 凭据值 / 产品名（AGENTS 硬约束的机器化）。

治理依据：红线两度返工（e659178 敏感信息出库、2026-09-24 快照脱敏批），
散文约束不足 → 确定性门禁。

两处豁免（2026-10-15 修，此前恒误报 5 条，噪音会把真违规淹掉）：
- 跳过本文件与 `scripts/redline_check.py`：两者都是扫描规则的**载体**，
  正文必然含产品名模式串，不是泄漏。
- 「凭据值」只在**配置取值语境**匹配（YAML/ini 的 `key: value`），
  不再匹配 `token = oauth.get_token(cfg)` 这类**赋值语句 / 函数调用**。
"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

_ALLOW_VALUE = ("example", "your", "placeholder", "<", "${", "apw_")

# 扫描规则的载体：正文含模式字面量属正常，不算泄漏
_SELF = Path(__file__).name
_RULE_CARRIERS = {_SELF, "redline_check.py"}

_PATTERNS = {
    "内网 IP": re.compile(
        r"\b(?:10\.\d+\.\d+\.\d+|192\.168\.\d+\.\d+|172\.(?:1[6-9]|2\d|3[01])\.\d+\.\d+)\b"
    ),
    "产品名": re.compile(r"Aml Agent|Amlcowork|AML Code"),
    # 只认「key: 值」/「key = 值」里**看起来像真实凭据的字面量**：
    # 排除函数调用/属性访问（含 `(` 或以 `)` 结尾）、占位符、变量引用。
    "凭据值": re.compile(
        r"""(?im)^[ \t]*["']?(?:password|passwd|secret_key|api_token|token)["']?[ \t]*[:=][ \t]*
        (?P<quote>["']?)(?P<value>[^"'\s<#$`=][^"'\s=]{4,})(?P=quote)[ \t]*$""",
        re.VERBOSE,
    ),
}
_SKIP_SUFFIX = {".png", ".jpg", ".jpeg", ".gif", ".ico", ".woff", ".woff2", ".pdf", ".zip"}

# 值里出现这些 = 不是硬编码凭据（占位符/变量/调用/示例）
_NOT_A_LITERAL = re.compile(r"[()\[\]]|^[$%{]|\$\{|example|your|placeholder|<|apw_")


def _tracked_files() -> list[str]:
    out = subprocess.run(
        ["git", "ls-files"], capture_output=True, text=True, encoding="utf-8"
    )
    return out.stdout.split() if out.returncode == 0 else []


def test_tracked_files_have_no_secrets() -> None:
    violations: list[str] = []
    for name in _tracked_files():
        if Path(name).name in _RULE_CARRIERS:
            continue
        if Path(name).suffix.lower() in _SKIP_SUFFIX:
            continue
        text = Path(name).read_text(encoding="utf-8", errors="ignore")
        for label, pattern in _PATTERNS.items():
            for match in pattern.finditer(text):
                if label == "凭据值":
                    value = match.group("value")
                    if any(allow in value.lower() for allow in _ALLOW_VALUE):
                        continue
                    if _NOT_A_LITERAL.search(value):
                        continue
                violations.append(f"{name}: [{label}] {match.group(0)[:80]}")
    assert not violations, "敏感信息红线违规（内网 IP / 凭据值 / 产品名不得入库）：\n" + "\n".join(
        violations
    )
