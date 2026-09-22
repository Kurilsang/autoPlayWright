"""Page Object 层：元素定位全部来自定位器仓库，平台无关。"""
from __future__ import annotations

from typing import TYPE_CHECKING

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
