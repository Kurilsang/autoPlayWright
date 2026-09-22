"""DSL schema：flow YAML 的 pydantic 模型与解析。

步骤三态：do（页面动作/钩子）、assert（确定性断言）、judge（v1 预留，执行时标记 planned）。
"""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

Platform = Literal["web", "desktop"]


class FlowMeta(BaseModel):
    id: str
    name: str
    platforms: list[Platform] = ["web"]
    tags: list[str] = Field(default_factory=list)
    owner: str = ""


class DoAction(BaseModel):
    page: str
    action: str
    args: dict[str, Any] = Field(default_factory=dict)


class DoStep(BaseModel):
    """执行一个 Page Object 动作。"""

    do: DoAction
    kind: Literal["do"] = "do"


class AssertAction(BaseModel):
    """确定性断言（v1）。target 为定位器仓库中的命名定位器。"""

    type: Literal["visible", "text_contains"]
    target: str
    page: str = ""  # 留空时使用仓库中唯一注册的页面
    expected: str = ""  # text_contains 必填
    timeout_ms: int = 10_000


class AssertStep(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    assert_: AssertAction = Field(alias="assert")
    kind: Literal["assert"] = "assert"


class JudgeStep(BaseModel):
    """LLM-as-Judge 预留字段：schema 放行，v1 执行时标记 planned 并写入报告。"""

    judge: dict[str, Any] = Field(default_factory=dict)
    kind: Literal["judge"] = "judge"


Step = DoStep | AssertStep | JudgeStep

_STEP_KEYS = {"do", "assert", "judge"}


def parse_step(raw: Any, index: int) -> Step:
    """校验单个步骤：必须且只能包含 do/assert/judge 之一。收集期非法即报错。"""
    if not isinstance(raw, dict):
        raise ValueError(f"steps[{index}] 必须是映射，得到 {type(raw).__name__}")
    keys = set(raw) & _STEP_KEYS
    if len(keys) != 1 or len(raw) != 1:
        raise ValueError(
            f"steps[{index}] 必须且只能包含 do/assert/judge 之一，实际键: {sorted(raw)}"
        )
    key = keys.pop()
    if key == "do":
        return DoStep.model_validate(raw)
    if key == "assert":
        return AssertStep.model_validate(raw)
    return JudgeStep.model_validate(raw)


class FlowSpec(BaseModel):
    """一条业务链路的完整描述。"""

    meta: FlowMeta
    steps: list[Step] = Field(default_factory=list)
    # TODO(T04): vars 在步骤 args/钩子中以 {{name}} 占位引用
    vars: dict[str, Any] = Field(default_factory=dict)
