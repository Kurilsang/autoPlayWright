"""等待/判定基建（BasePage）纯逻辑测试：SignalWatch 多信号收敛 + 失败取证出口。

不依赖浏览器：Page/Repo 用最小假件，验证完成语义（gate/稳定采样/提前收场）、
时间线留痕与 EvidenceError 取证形制（classification/cause/repro/screenshots）。
"""
from __future__ import annotations

import itertools

import pytest

from apw.pages.base import BasePage, EvidenceError


class FakePage:
    """最小 Page 假件：settle/snap/url 用到的接口。"""

    def __init__(self) -> None:
        self.url = "https://fixture.local/chat/1"
        self.shots: list[str] = []

    def wait_for_timeout(self, ms: int) -> None:
        pass

    def screenshot(self, path: str) -> None:
        self.shots.append(path)


class FakeHost(BasePage):
    page_name = "fake"

    def __init__(self) -> None:
        super().__init__(page=FakePage(), repo=object())  # repo 被假件绕过
        self.screenshot_dir = None  # snap() 未配置目录返回空串

    def capture_context(self) -> dict:
        return {"turns": [{"role": "user", "text": "半截现场"}]}


def test_settles_when_gate_met_and_content_stable() -> None:
    host = FakeHost()
    ticks = {"n": 0}

    def signals() -> dict[str, bool]:
        ticks["n"] += 1
        return {"a": ticks["n"] >= 2}  # 第 2 轮起达成

    watch = host.watch_signals(
        signals=signals, size=lambda: 7, timeout_ms=5_000, interval_ms=0
    )
    assert watch.settled and not watch.gave_up
    assert watch.gate_ok
    # gate 达成的当轮即首个稳定样本，此后还需 stable_needed 轮
    assert ticks["n"] >= 1 + watch.stable_needed
    assert watch.timeline[0]["text_len"] == 7  # 时间线带内容长度观察值
    assert watch.timeline[-1]["a"] is True


def test_unstable_content_never_settles() -> None:
    host = FakeHost()
    counter = itertools.count()  # 长度每轮都变：稳定采样永远凑不齐

    watch = host.watch_signals(
        signals=lambda: {"a": True},
        size=lambda: next(counter),
        timeout_ms=60,
        interval_ms=0,
    )
    assert not watch.settled and not watch.gave_up
    assert watch.stable == 0


def test_gate_subset_ignores_non_gate_signals() -> None:
    host = FakeHost()
    watch = host.watch_signals(
        signals=lambda: {"a": True, "b": False},  # b 不在 gate 内
        size=lambda: 5,
        gate={"a"},
        timeout_ms=5_000,
        interval_ms=0,
    )
    assert watch.settled
    assert watch.gate_keys == {"a"}


def test_give_up_when_structure_missing() -> None:
    host = FakeHost()
    watch = host.watch_signals(
        signals=lambda: {"stop_cleared": True, "reply": False},
        size=lambda: 9,
        timeout_ms=5_000,
        interval_ms=0,
        stability_gate=lambda s: s["stop_cleared"],  # 流式已结束即可累计稳定
        give_up=lambda w: w.stable >= 5,  # 已稳定仍缺结构 = 半截渲染
    )
    assert watch.gave_up and not watch.settled
    assert watch.stable >= 5


def test_fail_incomplete_carries_evidence(tmp_path) -> None:
    host = FakeHost()
    host.screenshot_dir = tmp_path
    watch = host.watch_signals(
        signals=lambda: {"a": False}, size=lambda: 3, timeout_ms=30, interval_ms=0
    )
    assert not watch.settled
    with pytest.raises(EvidenceError) as excinfo:
        host.fail_incomplete(
            "完整回答未达成",
            classify=lambda s: ("reply_incomplete", "缺结构信号"),
            watch=watch,
            steps="send → wait",
            observed="30ms 未达成",
        )
    ev = excinfo.value.evidence
    assert ev["classification"] == "reply_incomplete"
    assert ev["cause"] == "缺结构信号"
    assert ev["signals"] == {"a": False}
    assert ev["timeline"] == watch.timeline
    assert ev["repro"]["steps"] == "send → wait"
    assert ev["repro"]["observed"] == "30ms 未达成"
    assert ev["screenshots"] and ev["screenshots"][0].endswith(".png")
    assert ev["turns"]  # 半截上下文（capture_context）一并取证
    assert "［归因: reply_incomplete］" in str(excinfo.value)


def test_fail_evidence_uniform_shape(tmp_path) -> None:
    host = FakeHost()
    host.screenshot_dir = tmp_path
    with pytest.raises(EvidenceError) as excinfo:
        host.fail_evidence(
            "会话区未就绪",
            classification="hang_loading",
            cause="占位持续",
            repro={"url": "u", "observed": "x"},
            detail="占位持续 30ms",
            shot_name="history-hang",
            extra={"phase": "send_message"},
        )
    ev = excinfo.value.evidence
    assert set(ev) == {"classification", "cause", "repro", "phase", "screenshots"}
    assert ev["screenshots"][0].endswith(".png")
    msg = str(excinfo.value)
    assert "［归因: hang_loading］" in msg
    assert "复现: url=u，observed=x" in msg
    assert "占位持续 30ms" in msg
