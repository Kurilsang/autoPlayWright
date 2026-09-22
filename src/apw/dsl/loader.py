"""flow YAML 加载与校验。非法 DSL 在 pytest 收集期即报错。"""
from __future__ import annotations

from pathlib import Path

import yaml

from apw.dsl.schema import FlowSpec, parse_step


def load_flow(path: str | Path) -> FlowSpec:
    path = Path(path)
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{path}: flow 文件必须是 YAML 映射")
    if "meta" not in data:
        raise ValueError(f"{path}: 缺少 meta 段")

    raw_steps = data.get("steps") or []
    if not isinstance(raw_steps, list):
        raise ValueError(f"{path}: steps 必须是列表")
    steps = [parse_step(raw, i) for i, raw in enumerate(raw_steps)]

    return FlowSpec.model_validate(
        {"meta": data["meta"], "steps": steps, "vars": data.get("vars") or {}}
    )
