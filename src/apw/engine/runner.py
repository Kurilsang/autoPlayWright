"""DSL 引擎：flow spec 进，FlowResult（步骤级事件流）出。

引擎只依赖 Playwright Page / 定位器仓库 / 页面注册表；
pytest、报告、Allure 都是它下游的消费者，不在引擎内部出现。
"""
from __future__ import annotations

import time
from collections.abc import Callable
from contextlib import AbstractContextManager, nullcontext
from pathlib import Path
from typing import TYPE_CHECKING

from playwright.sync_api import expect

from apw.dsl.schema import DoStep, FlowSpec, JudgeStep
from apw.engine.events import FlowResult, StepEvent
from apw.engine.registry import PageRegistry
from apw.locators.repo import LocatorRepo

if TYPE_CHECKING:
    from playwright.sync_api import Page


def _elapsed_ms(t0: float) -> int:
    return int((time.perf_counter() - t0) * 1000)


class FlowRunner:
    """prepare: 每条 flow 开始前的回调（pytest 插件用它导航到 base_url）。

    step_cm_factory: 可选的步骤上下文工厂（如 allure.step），引擎自身不感知 Allure。
    """

    def __init__(
        self,
        *,
        page: Page,
        repo: LocatorRepo,
        pages: PageRegistry,
        reporter=None,
        prepare: Callable[[], None] | None = None,
        screenshot_dir: str | Path | None = None,
        step_cm_factory: Callable[[str], AbstractContextManager] | None = None,
    ) -> None:
        self.page = page
        self.repo = repo
        self.pages = pages
        self.reporter = reporter
        self.prepare = prepare
        self.screenshot_dir = Path(screenshot_dir) if screenshot_dir else None
        self.step_cm_factory = step_cm_factory

    def run(self, spec: FlowSpec) -> FlowResult:
        t0 = time.perf_counter()
        if self.prepare:
            self.prepare()
        events: list[StepEvent] = []
        for idx, step in enumerate(spec.steps):
            event = self._run_step(spec.meta.id, idx, step)
            events.append(event)
            if event.status == "failed":
                break
        result = FlowResult(
            flow_id=spec.meta.id,
            name=spec.meta.name,
            platforms=list(spec.meta.platforms),
            status="failed" if any(e.status == "failed" for e in events) else "passed",
            events=events,
            duration_ms=_elapsed_ms(t0),
        )
        if self.reporter:
            self.reporter.write_flow(result)
        return result

    def _run_step(self, flow_id: str, index: int, step) -> StepEvent:
        t0 = time.perf_counter()
        common = {"flow_id": flow_id, "index": index, "kind": step.kind}

        if isinstance(step, JudgeStep):
            note = step.judge.get("note") or "LLM-as-Judge 预留（待接入）"
            return StepEvent(
                detail=str(note), status="planned",
                duration_ms=_elapsed_ms(t0), **common,
            )

        if isinstance(step, DoStep):
            title = f"do: {step.do.page}.{step.do.action}"
        else:
            title = f"assert: {step.assert_.type} {step.assert_.target}"

        try:
            with self._step_context(title):
                if isinstance(step, DoStep):
                    detail, evidence = self._exec_do(step.do)
                else:
                    detail, evidence = self._exec_assert(step.assert_), {}
            return StepEvent(
                detail=detail,
                evidence=evidence,
                status="passed",
                duration_ms=_elapsed_ms(t0),
                **common,
            )
        except Exception as exc:  # noqa: BLE001 - 单步失败需转为事件而非中断引擎
            return StepEvent(
                detail="",
                status="failed",
                error=f"{type(exc).__name__}: {exc}",
                evidence=getattr(exc, "evidence", None) or {},
                screenshot=self._screenshot(flow_id, index),
                duration_ms=_elapsed_ms(t0),
                **common,
            )

    def _step_context(self, title: str) -> AbstractContextManager:
        return self.step_cm_factory(title) if self.step_cm_factory else nullcontext()

    def _exec_do(self, action) -> tuple[str, dict]:
        obj = self.pages.create(action.page, page=self.page, repo=self.repo)
        obj.screenshot_dir = self.screenshot_dir  # 动作可产出截图证据（如冻结现场）
        fn = getattr(obj, action.action, None)
        if not callable(fn):
            raise AttributeError(f"页面 {action.page} 没有动作 {action.action!r}")
        captured = fn(**action.args)
        # 约定：动作返回 dict 视为结构化采集数据（如对话上下文），进事件证据
        evidence = captured if isinstance(captured, dict) else {}
        return f"{action.page}.{action.action}", evidence

    def _exec_assert(self, assertion) -> str:
        page_name = assertion.page or self.pages.single()
        obj = self.pages.create(page_name, page=self.page, repo=self.repo)
        loc = obj.loc(assertion.target)
        if assertion.type == "visible":
            expect(loc).to_be_visible(timeout=assertion.timeout_ms)
            return f"visible {page_name}.{assertion.target}"
        if not assertion.expected:
            raise ValueError("text_contains 断言必须提供 expected")
        expect(loc).to_contain_text(assertion.expected, timeout=assertion.timeout_ms)
        return f"text_contains {page_name}.{assertion.target} ~ {assertion.expected!r}"

    def _screenshot(self, flow_id: str, index: int) -> str:
        if self.screenshot_dir is None:
            return ""
        try:
            path = self.screenshot_dir / f"{flow_id}-step{index:02d}.png"
            path.parent.mkdir(parents=True, exist_ok=True)
            self.page.screenshot(path=str(path))
            return str(path)
        except Exception:  # noqa: BLE001 - 截图失败不影响失败事件本身
            return ""
