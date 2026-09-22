"""定位器仓库：按页面组织的命名定位器，页面改版只改这里。

选择器候选按优先级排列（testid > role+name > text > css/xpath 的约定体现在仓库文件中），
解析时依序探测，命中即返回；全部未命中抛 LocatorNotFound。
"""
from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Literal

import yaml
from pydantic import BaseModel, Field, TypeAdapter

if TYPE_CHECKING:
    from playwright.sync_api import Locator, Page

SelectorBy = Literal["testid", "role", "label", "placeholder", "text", "css", "xpath"]


class Selector(BaseModel):
    by: SelectorBy
    value: str
    name: str = ""  # role 定位器的可访问名
    exact: bool = True


class LocatorEntry(BaseModel):
    name: str
    candidates: list[Selector] = Field(min_length=1)
    source: Literal["manual", "ai"] = "manual"  # ai = AI 爬虫候选（T07 产出）


class LocatorNotFound(LookupError):
    def __init__(self, page_name: str, locator_name: str) -> None:
        self.page_name = page_name
        self.locator_name = locator_name
        super().__init__(f"定位器未命中: {page_name}.{locator_name}")


class PageLocators(BaseModel):
    page: str
    locators: dict[str, LocatorEntry]


_entry_adapter = TypeAdapter(LocatorEntry)


def build_locator(page: Page, sel: Selector) -> Locator:
    """把 Selector 翻译为 Playwright 定位器。"""
    if sel.by == "testid":
        return page.get_by_test_id(sel.value)
    if sel.by == "role":
        return page.get_by_role(sel.value, name=sel.name or None, exact=sel.exact)
    if sel.by == "label":
        return page.get_by_label(sel.value, exact=sel.exact)
    if sel.by == "placeholder":
        return page.get_by_placeholder(sel.value, exact=sel.exact)
    if sel.by == "text":
        return page.get_by_text(sel.value, exact=sel.exact)
    if sel.by == "css":
        return page.locator(sel.value)
    return page.locator(f"xpath={sel.value}")


class LocatorRepo:
    def __init__(self, pages: dict[str, PageLocators]) -> None:
        self._pages = pages

    @classmethod
    def load(cls, locators_dir: str | Path) -> LocatorRepo:
        locators_dir = Path(locators_dir)
        if not locators_dir.exists():
            raise FileNotFoundError(f"定位器目录不存在: {locators_dir}")
        pages: dict[str, PageLocators] = {}
        for path in sorted(locators_dir.glob("*.yaml")):
            data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
            page_name = data.get("page") or path.stem
            raw = data.get("locators") or {}
            entries: dict[str, LocatorEntry] = {}
            if isinstance(raw, list):  # 列表形式
                for item in raw:
                    entry = _entry_adapter.validate_python(item)
                    entries[entry.name] = entry
            else:  # 映射形式 name -> entry
                for name, item in raw.items():
                    entry = _entry_adapter.validate_python({"name": name, **item})
                    entries[name] = entry
            pages[page_name] = PageLocators(page=page_name, locators=entries)
        return cls(pages)

    def page(self, page_name: str) -> PageLocators:
        if page_name not in self._pages:
            raise KeyError(
                f"页面 {page_name} 未在定位器仓库注册，已有: {sorted(self._pages)}"
            )
        return self._pages[page_name]

    @property
    def page_names(self) -> list[str]:
        return sorted(self._pages)

    def resolve(
        self,
        page: Page,
        page_name: str,
        locator_name: str,
        probe_timeout_ms: int = 500,
    ) -> Locator:
        """依序探测候选定位器：主候选即时命中零开销，回退仅在失败路径付出探测成本。"""
        entry = self.page(page_name).locators.get(locator_name)
        if entry is None:
            raise LocatorNotFound(page_name, locator_name)
        errors: list[str] = []
        for sel in entry.candidates:
            loc = build_locator(page, sel)
            if loc.count() > 0:
                return loc.first
            try:
                loc.first.wait_for(state="attached", timeout=probe_timeout_ms)
                return loc.first
            except Exception as exc:  # noqa: BLE001 - 收集所有候选失败原因
                errors.append(f"{sel.by}={sel.value!r}: {type(exc).__name__}")
        raise LocatorNotFound(page_name, locator_name)
