"""Page Object 层：元素定位全部来自定位器仓库，平台无关。"""
from __future__ import annotations

from typing import TYPE_CHECKING

from apw.locators.repo import build_locator

if TYPE_CHECKING:
    from playwright.sync_api import Locator, Page

    from apw.locators.repo import LocatorRepo


class BasePage:
    """子类只需声明 page_name 并组合仓库中的命名定位器。"""

    page_name: str = ""

    def __init__(self, *, page: Page, repo: LocatorRepo) -> None:
        self.page = page
        self.repo = repo

    def loc(self, name: str) -> Locator:
        return self.repo.resolve(self.page, self.page_name, name)

    def count(self, name: str) -> int:
        """软计数：元素不存在返回 0 而非抛错（用于完成信号等预期缺席的探测）。"""
        entry = self.repo.page(self.page_name).locators[name]
        return build_locator(self.page, entry.candidates[0]).count()
