"""页面注册表：DSL 中的 page 名 → Page Object 工厂。"""
from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from playwright.sync_api import Page

    from apw.locators.repo import LocatorRepo
    from apw.pages.base import BasePage

PageFactory = Callable[..., "BasePage"]


class PageRegistry:
    def __init__(self) -> None:
        self._factories: dict[str, PageFactory] = {}

    def register(self, name: str, factory: PageFactory) -> None:
        self._factories[name] = factory

    def create(self, name: str, *, page: Page, repo: LocatorRepo) -> BasePage:
        if name not in self._factories:
            raise KeyError(f"页面 {name} 未注册，已有: {sorted(self._factories)}")
        return self._factories[name](page=page, repo=repo)

    def single(self) -> str:
        """assert.page 留空时使用；仓库注册了多个页面则必须显式指定。"""
        if len(self._factories) != 1:
            raise ValueError(
                f"assert.page 留空时仓库必须只注册一个页面，当前: {sorted(self._factories)}"
            )
        return next(iter(self._factories))


def default_registry() -> PageRegistry:
    from apw.pages.agent_chat import AgentChatPage
    from apw.pages.aml_chat import AmlChatPage

    registry = PageRegistry()
    registry.register("agent_chat", AgentChatPage)
    registry.register("aml_chat", AmlChatPage)
    return registry
