"""爬虫配置与快照 schema（票 06）：pydantic 定义与校验。

字段宁多勿缺（SPEC D20）：`elements[].candidates` 直接映射 `locators/` 现成格式，
`signals` 喂完成判定类原语生成，`state_path` 标注状态到达路径（同页面多状态多份快照）。
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from apw.dsl.schema import DoAction
from apw.locators.repo import Selector

Region = Literal[
    "header", "sidebar", "composer", "message_list", "dialog", "content", "other"
]


class SignalProbe(BaseModel):
    """完成信号在场性探针：喂 wait_reply_done 类原语生成与票 08 diff。"""

    name: str
    selector: Selector


class CrawlStep(BaseModel):
    """状态步骤：执行 do 动作推进页面状态。

    label 进 state_path（留空用 page.action）；capture 控制本步后是否采集快照，
    最后一步默认采集。
    """

    do: DoAction
    label: str = ""
    capture: bool = False


class CrawlTarget(BaseModel):
    id: str
    route: str = ""
    steps: list[CrawlStep] = Field(default_factory=list)
    signals: list[SignalProbe] = Field(default_factory=list)


class CrawlConfig(BaseModel):
    name: str
    targets: list[CrawlTarget] = Field(min_length=1)
    dom_excerpt_chars: int = 50_000


class SnapshotElement(BaseModel):
    name_hint: str = ""
    region: Region = "other"
    role: str = ""
    accessible_name: str = ""
    testid: str = ""
    placeholder: str = ""
    tag: str = ""
    classes: list[str] = Field(default_factory=list)
    text: str = ""
    interactable: bool = False
    visible: bool = False
    candidates: list[Selector] = Field(default_factory=list)


class Snapshot(BaseModel):
    schema_version: int = 1
    env: str
    route: str = ""
    url: str = ""
    title: str = ""
    state_path: list[str] = Field(default_factory=list)
    captured_at: str = ""
    elements: list[SnapshotElement] = Field(default_factory=list)
    signals: dict[str, dict] = Field(default_factory=dict)
    screenshots: list[str] = Field(default_factory=list)
    dom_excerpt: str = ""
