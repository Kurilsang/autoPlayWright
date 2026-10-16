"""StepEvent / FlowResult：引擎产出的事件流，报告的唯一数据源。"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


class StepEvent(BaseModel):
    flow_id: str
    index: int
    kind: Literal["prepare", "do", "assert", "judge"]
    detail: str = ""
    status: Literal["passed", "failed", "skipped", "planned"]
    error: str = ""
    started_at: str = Field(default_factory=_now)
    duration_ms: int = 0
    screenshot: str = ""
    evidence: dict[str, Any] = Field(default_factory=dict)  # 动作返回的结构化采集数据


class FlowResult(BaseModel):
    flow_id: str
    name: str
    platforms: list[str] = Field(default_factory=list)
    status: Literal["passed", "failed", "skipped"]
    skip_reason: str = ""  # 跳过原因（平台/环境不匹配等），报告核对用例矩阵用
    events: list[StepEvent] = Field(default_factory=list)
    started_at: str = Field(default_factory=_now)
    duration_ms: int = 0
    error: str = ""

    @classmethod
    def from_spec(cls, spec, **kwargs) -> FlowResult:
        """按 flow spec 统一装配（三处终态共用：执行/空步骤/跳过）。"""
        return cls(
            flow_id=spec.meta.id,
            name=spec.meta.name,
            platforms=list(spec.meta.platforms),
            **kwargs,
        )
