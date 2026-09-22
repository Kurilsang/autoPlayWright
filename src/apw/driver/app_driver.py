"""AppDriver：平台接缝。Web 与 Electron 两种模式统一输出 Playwright Page。

上层（pages/dsl/engine）完全不感知平台差异。
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from apw.auth.base import build_auth
from apw.config import EnvConfig, resolve_base_url

if TYPE_CHECKING:
    from playwright.sync_api import Browser, BrowserContext, Page, Playwright


class AppDriver:
    def __init__(self, env: EnvConfig, root: str = ".") -> None:
        self.env = env
        self.root = root
        self._pw: Playwright | None = None
        self._browser: Browser | None = None
        self._context: BrowserContext | None = None
        self._page: Page | None = None

    # ---- 生命周期 ----
    def start(self) -> AppDriver:
        from playwright.sync_api import sync_playwright

        self._pw = sync_playwright().start()
        if self.env.driver.mode == "electron":
            self._context = self._start_electron()
            pages = self._context.pages
            self._page = pages[0] if pages else self._context.new_page()
        else:
            self._context = self._start_web()
            self._page = self._context.new_page()
        return self

    def stop(self) -> None:
        for closer in (
            lambda: self._context and self._context.close(),
            lambda: self._browser and self._browser.close(),
            lambda: self._pw and self._pw.stop(),
        ):
            try:
                closer()
            except Exception:  # noqa: BLE001 - 退出清理尽力而为
                pass
        self._pw = self._browser = self._context = self._page = None

    # ---- 模式实现 ----
    def _start_web(self) -> BrowserContext:
        assert self._pw is not None
        launch_kwargs: dict = {"headless": self.env.driver.headless}
        if self.env.driver.channel:
            launch_kwargs["channel"] = self.env.driver.channel
        self._browser = self._pw.chromium.launch(**launch_kwargs)
        auth = build_auth(self.env.auth)
        return self._browser.new_context(**auth.context_kwargs())

    def _start_electron(self) -> BrowserContext:
        assert self._pw is not None
        cfg = self.env.driver.electron
        if not cfg.cdp_endpoint:
            raise NotImplementedError(
                "Electron launch 模式留空：未配置 executable_path（待 T03 落地）；"
                "当前仅支持 cdp_endpoint attach 已运行客户端"
            )
        self._browser = self._pw.chromium.connect_over_cdp(cfg.cdp_endpoint)
        if not self._browser.contexts:
            raise RuntimeError(f"CDP {cfg.cdp_endpoint} 上没有可用的 BrowserContext")
        return self._browser.contexts[0]

    # ---- 访问 ----
    @property
    def page(self) -> Page:
        if self._page is None:
            raise RuntimeError("驱动未启动：先调用 start()")
        return self._page

    def goto_base(self) -> Page:
        return self.page.goto(resolve_base_url(self.env, self.root))
