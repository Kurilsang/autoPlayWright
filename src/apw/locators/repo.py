"""定位器仓库：按页面组织的命名定位器，页面改版只改这里。

选择器候选按优先级排列（testid > role+name > text > css/xpath 的约定体现在仓库文件中），
解析时依序探测，命中即返回；全部未命中抛 LocatorNotFound。
"""
from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Literal, NamedTuple

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
    def __init__(
        self, page_name: str, locator_name: str, errors: list[str] | None = None
    ) -> None:
        self.page_name = page_name
        self.locator_name = locator_name
        self.errors = errors or []
        detail = f"（候选失败明细: {'; '.join(self.errors)}）" if self.errors else ""
        super().__init__(f"定位器未命中: {page_name}.{locator_name}{detail}")


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


class _Hit(NamedTuple):
    """候选回退链的即时命中：哪个选择器、什么定位器、命中几处。"""

    sel: Selector
    loc: Locator
    count: int


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

    def _entry(self, page_name: str, locator_name: str) -> LocatorEntry:
        entry = self.page(page_name).locators.get(locator_name)
        if entry is None:
            raise LocatorNotFound(page_name, locator_name)
        return entry

    def _first_hit(self, page: Page, entry: LocatorEntry) -> _Hit | None:
        """候选回退链的即时探测：依序返回首个命中候选。"""
        for sel in entry.candidates:
            loc = build_locator(page, sel)
            n = loc.count()
            if n > 0:
                return _Hit(sel, loc, n)
        return None

    def count(self, page: Page, page_name: str, locator_name: str) -> int:
        """软计数：与 resolve 同一条候选回退链。

        预期缺席的探测语义保持——全候选未命中返回 0 而非抛错（完成信号依赖此语义）；
        未知定位器名抛 LocatorNotFound（名错是配置错误，缺席是预期状态）。
        """
        hit = self._first_hit(page, self._entry(page_name, locator_name))
        return hit.count if hit else 0

    def resolve(
        self,
        page: Page,
        page_name: str,
        locator_name: str,
        probe_timeout_ms: int = 500,
    ) -> Locator:
        """依序探测候选定位器：主候选即时命中零开销，回退仅在失败路径付出探测成本。"""
        entry = self._entry(page_name, locator_name)
        hit = self._first_hit(page, entry)
        if hit is not None:
            return hit.loc.first
        errors: list[str] = []
        for sel in entry.candidates:
            loc = build_locator(page, sel)
            try:
                loc.first.wait_for(state="attached", timeout=probe_timeout_ms)
                return loc.first
            except Exception as exc:  # noqa: BLE001 - 收集所有候选失败原因
                reason = str(exc)[:80]
                errors.append(f"{sel.by}={sel.value!r}: {type(exc).__name__}: {reason}")
        raise LocatorNotFound(page_name, locator_name, errors)
