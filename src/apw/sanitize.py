"""快照产物脱敏：敏感串 → 占位符，落盘前统一调用（敏感信息红线的第一道防线）。

映射表驱动：真实串只存在于本地 `configs/sanitize.local.yaml`（gitignored，禁止入库），
映射值即约定占位符（<product>/<user-me>/<host> 等）；另有通用模式兜底：
邮件/有点账号句柄 → <user>，http(s) 主机 → <host>（路径保留，复现线索的诊断价值不丢）。

脱敏只替换敏感串，JSON/HTML 结构、信号时间线、状态字段与截图引用原样保留。
映射按长键优先、词边界替换（yaml 不会被键 aml 误伤）。
"""
from __future__ import annotations

import re
from collections.abc import Mapping
from pathlib import Path

import yaml

DEFAULT_MAPPING_PATH = Path("configs/sanitize.local.yaml")

_EMAIL_RE = re.compile(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}")
_HANDLE_RE = re.compile(r"@[A-Za-z][\w\-]+(?:\.[\w\-]+)+")  # 有点句柄；无点（代码装饰器等）不脱
_HOST_RE = re.compile(r"(https?://)([^/\s\"'<>]+)")
_ASCII_WORD = "[A-Za-z0-9]"


def load_mapping(path: str | Path = DEFAULT_MAPPING_PATH) -> dict[str, str]:
    """读映射表（敏感串→占位符）。文件不存在返回空映射，通用模式仍生效。"""
    path = Path(path)
    if not path.exists():
        return {}
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return {str(k): str(v) for k, v in data.items()}


def _mapped_pattern(raw: str) -> re.Pattern[str]:
    """映射键的正则：仅在键的字母数字边缘加词边界，防 yaml 被键 aml 误伤。"""
    head = rf"(?<!{_ASCII_WORD})" if raw[0].isalnum() else ""
    tail = rf"(?!{_ASCII_WORD})" if raw[-1].isalnum() else ""
    return re.compile(head + re.escape(raw) + tail)


def sanitize_text(text: str, mapping: Mapping[str, str] | None = None) -> str:
    """把敏感串替换为占位符；只动敏感串，结构与其余内容原样保留。"""
    text = _EMAIL_RE.sub("<user>", text)
    text = _HANDLE_RE.sub("<user>", text)
    text = _HOST_RE.sub(r"\1<host>", text)
    for raw, placeholder in sorted(
        (mapping or {}).items(), key=lambda kv: len(kv[0]), reverse=True
    ):
        if raw:
            text = _mapped_pattern(raw).sub(str(placeholder), text)
    return text
