"""Page Object 层：元素定位全部来自定位器仓库，平台无关。"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

from apw.locators.repo import build_locator

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


class BasePage:
    """子类只需声明 page_name 并组合仓库中的命名定位器。"""

    page_name: str = ""
    screenshot_dir: Path | None = None  # 引擎装配：动作可产出截图证据

    def __init__(self, *, page: Page, repo: LocatorRepo) -> None:
        self.page = page
        self.repo = repo

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

    def count(self, name: str) -> int:
        """软计数：元素不存在返回 0 而非抛错（用于完成信号等预期缺席的探测）。"""
        entry = self.repo.page(self.page_name).locators[name]
        return build_locator(self.page, entry.candidates[0]).count()

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
