"""Page Object 层：元素定位全部来自定位器仓库，平台无关。

等待/判定基建（settle / wait_until / SignalWatch）与失败取证出口
（fail_evidence / fail_incomplete）沉淀在本层，页面子类只写语义差异：
等待轮询不裸写 time.sleep/裸循环，失败取证不裸拼 EvidenceError。
"""
from __future__ import annotations

import time
from collections.abc import Callable, Iterable, Sequence
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, NoReturn

if TYPE_CHECKING:
    from playwright.sync_api import Locator, Page

    from apw.locators.repo import LocatorRepo


class EvidenceError(RuntimeError):
    """动作失败：携带结构化归因证据（复现信息/信号时间线/冻结截图）。

    引擎捕获后把 evidence 记入失败事件，报告里可直接核对失败现场。
    """

    def __init__(self, summary: str, evidence: dict | None = None) -> None:
        super().__init__(summary)
        self.evidence = evidence or {}


def split_marked_sections(answer: str) -> tuple[str, str]:
    """按模型 markdown 标记尽力拆出「思考过程」段与「最终答案」段。

    无标记或无法拆分时整体归入最终答案段（采集是证据，尽力而为不断言）。
    """
    final_tag = "最终答案："
    thinking_tag = "思考过程："
    f_idx = answer.find(final_tag)
    if f_idx < 0:
        return "", answer
    t_idx = answer.find(thinking_tag)
    thinking = (
        answer[t_idx + len(thinking_tag) : f_idx].strip()
        if 0 <= t_idx < f_idx
        else ""
    )
    return thinking, answer[f_idx + len(final_tag) :].strip()


class SignalWatch:
    """多信号收敛判定（决策 D24）：轮询信号 + 内容稳定采样 + 时间线留痕。

    完成语义：gate 内信号全达成，且内容长度连续 stable_needed 次采样不变（>0）。
    单信号会被推理期/半截渲染误判，故一律多信号收敛。判定未达成不自愈——
    调用方按最终信号分类取证（BasePage.fail_incomplete）。

    - gate：完成必需的信号键集合（缺省 = 全部信号；只看内容稳定可传空集）
    - stability_gate：稳定计数的准入条件（缺省 = gate 全达成；流式判定可放宽为
      「流式已结束」单信号，从而在结构信号长期缺失时由 give_up 提前收场）
    - on_tick：每轮观察钩子（如卡死现场冻结快照）
    - give_up：提前收场判定（如「已稳定但结构仍缺 = 半截渲染」）
    """

    def __init__(
        self,
        base: BasePage,
        *,
        signals: Callable[[], dict[str, bool]],
        size: Callable[[], int],
        timeout_ms: int,
        interval_ms: int = 1000,
        stable_needed: int = 3,
        gate: Iterable[str] | None = None,
        size_field: str = "text_len",
        stability_gate: Callable[[dict[str, bool]], bool] | None = None,
        on_tick: Callable[[SignalWatch], None] | None = None,
        give_up: Callable[[SignalWatch], bool] | None = None,
    ) -> None:
        self._base = base
        self._signals_fn = signals
        self._size_fn = size
        self._gate = set(gate) if gate is not None else None
        self._stability_gate = stability_gate
        self._on_tick = on_tick
        self._give_up = give_up
        self.timeout_ms = timeout_ms
        self.interval_ms = interval_ms
        self.stable_needed = stable_needed
        self.size_field = size_field
        self.signals: dict[str, bool] = {}
        self.timeline: list[dict] = []
        self.ticks = 0
        self.stable = 0
        self.elapsed_s = 0.0
        self.settled = False
        self.gave_up = False

    @property
    def gate_keys(self) -> set[str]:
        return set(self.signals) if self._gate is None else self._gate

    @property
    def gate_ok(self) -> bool:
        """gate 内信号是否全达成（gate 为空集时恒真——仅要求内容稳定）。"""
        return all(self.signals.get(k) for k in self.gate_keys)

    def run(self) -> SignalWatch:
        t0 = time.time()
        deadline = t0 + self.timeout_ms / 1000
        prev: dict[str, bool] | None = None
        last_size = -1
        while time.time() < deadline:
            self._base.settle(self.interval_ms)  # 泵事件循环：观察值才会推进
            self.ticks += 1
            self.elapsed_s = time.time() - t0
            self.signals = dict(self._signals_fn())
            size = self._size_fn()
            if self.signals != prev or self.ticks % 10 == 0:
                self.timeline.append(
                    {"t_s": self.ticks, self.size_field: size, **self.signals}
                )
                prev = dict(self.signals)
            if self._on_tick:
                self._on_tick(self)
            stable_gate = (
                self._stability_gate(self.signals)
                if self._stability_gate
                else self.gate_ok
            )
            if stable_gate and size == last_size and size > 0:
                self.stable += 1
                if self.gate_ok and self.stable >= self.stable_needed:
                    self.settled = True
                    return self
            else:
                self.stable = 0
            last_size = size
            if self._give_up and self._give_up(self):
                self.gave_up = True
                return self
        return self


class BasePage:
    """子类只需声明 page_name 并组合仓库中的命名定位器。"""

    page_name: str = ""
    screenshot_dir: Path | None = None  # 引擎装配：动作可产出截图证据
    sanitize_mapping: dict[str, str] = {}  # 引擎装配：敏感串→占位符，产物落盘前脱敏

    def __init__(self, *, page: Page, repo: LocatorRepo) -> None:
        self.page = page
        self.repo = repo

    # ---- 等待基建 ----

    def settle(self, ms: int) -> None:
        """渲染/事件落定等待：走 Playwright API 泵事件循环。

        纯 time.sleep 不派发同步事件循环，page.url 等观察值会停在旧值
        （2026-09-29 做同款跳转实测踩坑）——等待一律经本方法。
        """
        self.page.wait_for_timeout(ms)

    def wait_until(
        self,
        predicate: Callable[[], bool],
        *,
        timeout_ms: int,
        interval_ms: int = 300,
    ) -> bool:
        """deadline 内轮询 predicate()：达成即真、超时即假（已达成零延迟）。"""
        deadline = time.time() + timeout_ms / 1000
        while True:
            if predicate():
                return True
            if time.time() >= deadline:
                return False
            self.settle(interval_ms)

    def watch_signals(
        self,
        *,
        signals: Callable[[], dict[str, bool]],
        size: Callable[[], int],
        timeout_ms: int,
        interval_ms: int = 1000,
        stable_needed: int = 3,
        gate: Iterable[str] | None = None,
        size_field: str = "text_len",
        stability_gate: Callable[[dict[str, bool]], bool] | None = None,
        on_tick: Callable[[SignalWatch], None] | None = None,
        give_up: Callable[[SignalWatch], bool] | None = None,
    ) -> SignalWatch:
        """多信号收敛判定器（构造并执行，语义见 SignalWatch）。"""
        return SignalWatch(
            self,
            signals=signals,
            size=size,
            timeout_ms=timeout_ms,
            interval_ms=interval_ms,
            stable_needed=stable_needed,
            gate=gate,
            size_field=size_field,
            stability_gate=stability_gate,
            on_tick=on_tick,
            give_up=give_up,
        ).run()

    # ---- 失败取证出口 ----

    def fail_evidence(
        self,
        headline: str,
        *,
        classification: str,
        cause: str,
        repro: dict,
        detail: str = "",
        shot_name: str = "",
        extra: dict | None = None,
        from_exc: BaseException | None = None,
    ) -> NoReturn:
        """冻结现场并抛 EvidenceError：失败取证统一出口。

        截图 + 归因分类 + 复现随证据入报告（evidence 统一形制：
        classification/cause/repro/screenshots + 页级 extra），取证失败不影响失败本身。
        from_exc：保留原始异常链（raise ... from）。
        """
        shot = self.snap(shot_name) if shot_name else ""
        evidence: dict = {
            "classification": classification,
            "cause": cause,
            "repro": repro,
            **(extra or {}),
        }
        evidence["screenshots"] = [shot] if shot else []
        lines = [f"{headline}［归因: {classification}］{cause}"]
        if detail:
            lines.append(f"  {detail}")
        lines.append(
            "  复现: " + "，".join(f"{k}={v}" for k, v in repro.items())
        )
        lines.append(f"  冻结截图: {shot or '（未捕获）'}")
        if from_exc is not None:
            raise EvidenceError("\n".join(lines), evidence) from from_exc
        raise EvidenceError("\n".join(lines), evidence)

    def fail_incomplete(
        self,
        headline: str,
        *,
        classify: Callable[[dict], tuple[str, str]],
        watch: SignalWatch,
        steps: str,
        observed: str,
        freeze_shots: Sequence[str] = (),
        shot_name: str = "timeout",
        extra: dict | None = None,
        with_context: bool = True,
    ) -> NoReturn:
        """完成判定未达成的统一取证出口：归因分类 + 信号/时间线 + 复现 + 冻结截图。

        半截现场（capture_context）尽力而为一并取证；取证失败不影响失败本身。
        """
        category, cause = classify(watch.signals)
        shots = [s for s in (*freeze_shots, self.snap(shot_name)) if s]
        repro = {"url": self.page.url, "observed": observed, "steps": steps}
        evidence: dict = {
            "classification": category,
            "cause": cause,
            "signals": watch.signals,
            "timeline": watch.timeline,
            "repro": repro,
            **(extra or {}),
        }
        evidence["screenshots"] = shots
        capture = getattr(self, "capture_context", None)
        if with_context and callable(capture):
            try:
                evidence.update(capture())  # 半截上下文一并取证
            except Exception:  # noqa: BLE001 - 取证尽力而为
                pass
        summary = (
            f"{headline}［归因: {category}］{cause}\n"
            f"  信号: {watch.signals}\n"
            f"  时间线: {len(watch.timeline)} 个采样点"
            f"（{watch.interval_ms}ms 粒度，0..{watch.timeout_ms // 1000}s）\n"
            f"  复现: {steps} @ {repro['url']}，观察: {observed}\n"
            f"  冻结截图: {', '.join(shots) if shots else '（未捕获）'}"
        )
        raise EvidenceError(summary, evidence)

    # ---- 元位器与证据 ----

    def snap(self, name: str) -> str:
        """冻结截图证据（如卡死现场），返回路径；未配置目录或失败返回空串。"""
        if not self.screenshot_dir:
            return ""
        try:
            stamp = datetime.now().strftime("%H%M%S")
            path = Path(self.screenshot_dir) / f"{self.page_name}-{name}-{stamp}.png"
            path.parent.mkdir(parents=True, exist_ok=True)
            self.page.screenshot(path=str(path))
            return str(path)
        except Exception:  # noqa: BLE001 - 取证失败不影响失败本身
            return ""

    def loc(self, name: str) -> Locator:
        return self.repo.resolve(self.page, self.page_name, name)

    def loc_all(self, name: str) -> Locator:
        """多元素定位器：需要 .filter/.nth 精确定位到具体元素时用（与 loc 同回退链）。

        注意 loc() 是单元素语义（内部取 first），其后接 .filter/.nth 会静默落空。
        """
        return self.repo.resolve_multi(self.page, self.page_name, name)

    @property
    def flow_state(self) -> dict:
        """流程级共享状态：页面对象每步新建，但同一流程共享同一个 Playwright Page。

        用于跨步骤传递确定性锚点（如会话 URL）。注意状态挂在 Page 上直到进程结束，
        读取方只认本流程写入的键（写入方约定唯一键，如 tag/固定锚名）。
        """
        store = getattr(self.page, "_apw_flow_state", None)
        if store is None:
            store = {}
            try:
                self.page._apw_flow_state = store
            except Exception:  # noqa: BLE001 - 不可写对象退化为独立状态
                pass
        return store

    def count(self, name: str) -> int:
        """软计数：元素不存在返回 0 而非抛错（用于完成信号等预期缺席的探测）。

        与硬解析同链（候选回退）；未知定位器名抛 LocatorNotFound。
        """
        return self.repo.count(self.page, self.page_name, name)

    def build_context(self, data: dict) -> dict:
        """把页面采集的原始 turns 规整为报告证据结构（对话上下文）。

        动作返回 dict 时由引擎写入 StepEvent.evidence，供人工核对输入输出。
        """
        turns: list[dict] = []
        for raw in data.get("turns", []):
            turn = dict(raw)
            if turn.get("role") == "assistant":
                turn.setdefault("answer", turn.get("text", ""))
                thinking, final = split_marked_sections(str(turn.get("answer", "")))
                turn.setdefault("thinking", thinking)
                turn.setdefault("final_answer", final)
            turns.append(turn)
        return {
            "url": data.get("url", ""),
            "captured_at": datetime.now().isoformat(timespec="seconds"),
            "turn_count": len(turns),
            "turns": turns,
        }
