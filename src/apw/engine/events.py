"""StepEvent / FlowResult：引擎产出的事件流，报告的唯一数据源。"""
from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


class StepEvent(BaseModel):
    flow_id: str
    index: int
    kind: Literal["do", "assert", "judge"]
    detail: str = ""
    status: Literal["passed", "failed", "skipped", "planned"]
    error: str = ""
    started_at: str = Field(default_factory=_now)
    duration_ms: int = 0
    screenshot: str = ""


class FlowResult(BaseModel):
    flow_id: str
    name: str
    platforms: list[str] = Field(default_factory=list)
    status: Literal["passed", "failed"]
    events: list[StepEvent] = Field(default_factory=list)
    started_at: str = Field(default_factory=_now)
    duration_ms: int = 0
    error: str = ""
