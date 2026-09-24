"""探查原语（生成侧）：未产品化页面的通用动作，供爬取配置推进未知页面状态。

以保留名 `page: probe` 由 Crawler 解释执行，**不注册进引擎页面注册表**：
流程用例必须走页面对象 + 定位器仓库，禁止散落裸选择器（硬约束）。

典型用法（新功能首轮探查）：
    goto/click/fill 推进状态 → dump_dom 捉全量结构 → 人工/AI 生成定位器与页面对象
    后，爬取配置里的 probe 步骤替换为产品化动作（page: <页面名>）。

args 中 selector 一律为 locators.repo.Selecter 映射，如 { by: text, value: 发送 }。
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Any
from urllib.parse import urljoin

from apw.locators.repo import Selector, build_locator
from apw.pages.base import BasePage, EvidenceError
from apw.sanitize import sanitize_text

if TYPE_CHECKING:
    from playwright.sync_api import Locator


class ProbePage(BasePage):
    """通用基础动作集合（goto/click/fill/press/wait/dump_dom）。"""

    page_name = "probe"

    # ---- 内部 ----
    def _locator(self, selector: dict[str, Any]) -> Locator:
        return build_locator(self.page, Selector.model_validate(selector))

    def _fail(self, action: str, selector: dict[str, Any], exc: Exception) -> EvidenceError:
        return EvidenceError(
            f"探查动作 {action} 失败: {selector}",
            evidence={
                "action": action,
                "selector": selector,
                "error": repr(exc),
                "screenshot": self.snap(f"{action}_fail"),
            },
        )

    # ---- 导航 ----
    def goto(self, route: str, *, settle_ms: int = 800) -> None:
        """导航到路由（相对当前源，建议以 / 开头）或绝对 URL；settle_ms 等 SPA 渲染。"""
        target = route if "://" in route else urljoin(self.page.url, route)
        self.page.goto(target, wait_until="load")
        self.page.wait_for_timeout(settle_ms)

    # ---- 元素动作 ----
    def click(
        self,
        selector: dict[str, Any],
        *,
        optional: bool = False,
        timeout_ms: int = 5_000,
        settle_ms: int = 400,
    ) -> None:
        """点击元素；optional=True 时未命中静默跳过（探查期多假设并行试错用）。"""
        try:
            self._locator(selector).first.click(timeout=timeout_ms)
        except Exception as exc:  # noqa: BLE001 - 失败归一 EvidenceError 冻结现场
            if optional:
                return
            raise self._fail("click", selector, exc) from exc
        self.page.wait_for_timeout(settle_ms)

    def fill(
        self,
        selector: dict[str, Any],
        text: str,
        *,
        optional: bool = False,
        timeout_ms: int = 5_000,
    ) -> None:
        try:
            self._locator(selector).first.fill(text, timeout=timeout_ms)
        except Exception as exc:  # noqa: BLE001
            if optional:
                return
            raise self._fail("fill", selector, exc) from exc

    def type(
        self,
        selector: dict[str, Any],
        text: str,
        *,
        optional: bool = False,
        timeout_ms: int = 5_000,
        settle_ms: int = 200,
    ) -> None:
        """点击后逐键输入（React 受控输入比 fill 更可靠）。"""
        try:
            loc = self._locator(selector).first
            loc.click(timeout=timeout_ms)
            loc.type(text, delay=20)
        except Exception as exc:  # noqa: BLE001
            if optional:
                return
            raise self._fail("type", selector, exc) from exc
        self.page.wait_for_timeout(settle_ms)

    def insert(
        self,
        selector: dict[str, Any] | None,
        text: str,
        *,
        optional: bool = False,
        timeout_ms: int = 5_000,
        settle_ms: int = 500,
    ) -> None:
        """整体插入文本（CDP insertText）：不产生逐键事件，避免代码编辑器自动缩进。

        selector 留空时插入到当前焦点（配合 click/press 先聚焦）。
        """
        try:
            if selector is not None:
                self._locator(selector).first.click(timeout=timeout_ms)
            self.page.keyboard.insert_text(text)
        except Exception as exc:  # noqa: BLE001
            if optional:
                return
            raise self._fail("insert", selector or {"focus": "current"}, exc) from exc
        self.page.wait_for_timeout(settle_ms)

    def press(
        self,
        key: str,
        selector: dict[str, Any] | None = None,
        *,
        optional: bool = False,
        timeout_ms: int = 5_000,
        settle_ms: int = 400,
    ) -> None:
        """按键（如 Enter）；selector 留空作用于当前焦点。"""
        try:
            if selector is None:
                self.page.keyboard.press(key)
            else:
                self._locator(selector).first.press(key, timeout=timeout_ms)
        except Exception as exc:  # noqa: BLE001
            if optional:
                return
            raise self._fail("press", selector or {"key": key}, exc) from exc
        self.page.wait_for_timeout(settle_ms)

    def wait(self, ms: int = 1_000) -> None:
        self.page.wait_for_timeout(ms)

    def wait_for(
        self,
        selector: dict[str, Any],
        *,
        state: str = "visible",
        timeout_ms: int = 10_000,
        optional: bool = False,
    ) -> None:
        try:
            self._locator(selector).first.wait_for(state=state, timeout=timeout_ms)
        except Exception as exc:  # noqa: BLE001
            if optional:
                return
            raise self._fail("wait_for", selector, exc) from exc

    # ---- 取证 ----
    def dump_dom(self, name: str = "dom", scope: str = "body") -> str:
        """把 scope 元素 outerHTML 落盘（默认 body，比快照 dom_excerpt 的 main 片段更全）。"""
        if not self.screenshot_dir:
            return ""
        html = self.page.locator(scope).first.evaluate("el => el.outerHTML")
        self.screenshot_dir.mkdir(parents=True, exist_ok=True)
        path = self.screenshot_dir / f"{self.page_name}-{name}.html"
        path.write_text(sanitize_text(html, self.sanitize_mapping), encoding="utf-8")
        return str(path)

    def shot(self, name: str = "probe") -> str:
        return self.snap(name)
