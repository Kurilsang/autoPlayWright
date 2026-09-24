"""定位器仓库测试：加载、列表/映射两种形式、候选优先级结构。"""
from __future__ import annotations

import pytest

from apw.locators.repo import LocatorRepo
from apw.pages.base import BasePage


class FakeLoc:
    """可控命中数的假定位器：count 立即返回，wait_for 模拟未附着。"""

    def __init__(self, n: int) -> None:
        self._n = n

    def count(self) -> int:
        return self._n

    @property
    def first(self) -> FakeLoc:
        return self

    def wait_for(self, **kwargs) -> None:
        raise TimeoutError("not attached")


class FakePage:
    """命中数按 (定位方式, 值) 配置，缺省 0。"""

    def __init__(self, hits: dict[tuple[str, str], int]) -> None:
        self.hits = hits

    def _loc(self, by: str, value: str) -> FakeLoc:
        return FakeLoc(self.hits.get((by, value), 0))

    def get_by_test_id(self, value: str) -> FakeLoc:
        return self._loc("testid", value)

    def locator(self, value: str) -> FakeLoc:
        return self._loc("css", value)

    def get_by_text(self, value: str, exact: bool = True) -> FakeLoc:
        return self._loc("text", value)


@pytest.fixture
def repo_dir(tmp_path):
    (tmp_path / "agent_chat.yaml").write_text(
        """
page: agent_chat
locators:
  - name: chat_input
    candidates:
      - { by: testid, value: chat-input }
      - { by: css, value: "textarea" }
  - name: send_button
    candidates:
      - { by: testid, value: chat-send }
""",
        encoding="utf-8",
    )
    (tmp_path / "mapping_form.yaml").write_text(
        """
page: other_page
locators:
  box:
    candidates:
      - { by: testid, value: box }
""",
        encoding="utf-8",
    )
    return tmp_path


class TestLoad:
    def test_list_form(self, repo_dir):
        repo = LocatorRepo.load(repo_dir)
        assert repo.page_names == ["agent_chat", "other_page"]
        entry = repo.page("agent_chat").locators["chat_input"]
        assert entry.candidates[0].by == "testid"
        assert entry.candidates[1].by == "css"

    def test_mapping_form(self, repo_dir):
        repo = LocatorRepo.load(repo_dir)
        assert repo.page("other_page").locators["box"].candidates[0].value == "box"

    def test_missing_dir(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            LocatorRepo.load(tmp_path / "nope")

    def test_unknown_page(self, repo_dir):
        repo = LocatorRepo.load(repo_dir)
        with pytest.raises(KeyError, match="未在定位器仓库注册"):
            repo.page("ghost")


class TestResolveErrors:
    def test_unknown_locator_raises_lookup(self, repo_dir):
        repo = LocatorRepo.load(repo_dir)
        with pytest.raises(LookupError, match="chat_input"):
            repo.resolve(
                FakePage({}), "agent_chat", "chat_input", probe_timeout_ms=1
            )

    def test_resolve_all_miss_reports_each_candidate(self, repo_dir):
        """全候选未命中：异常携带逐候选失败明细（选择器 + 异常类型 + 原因）。"""
        repo = LocatorRepo.load(repo_dir)
        with pytest.raises(LookupError) as excinfo:
            repo.resolve(FakePage({}), "agent_chat", "chat_input", probe_timeout_ms=1)
        msg = str(excinfo.value)
        assert "chat-input" in msg and "textarea" in msg
        assert "TimeoutError" in msg and "not attached" in msg


class FakeChatPage(BasePage):
    page_name = "agent_chat"


class TestSoftCountChain:
    """软计数与硬解析同链：主候选未命中自动回退，未知定位器名抛定位器未找到。"""

    def test_count_falls_back_to_next_candidate(self, repo_dir):
        repo = LocatorRepo.load(repo_dir)
        page = FakePage({("css", "textarea"): 2})  # 主候选 testid 未命中
        assert FakeChatPage(page=page, repo=repo).count("chat_input") == 2

    def test_count_all_miss_returns_zero(self, repo_dir):
        """预期缺席的探测语义保持：全候选未命中返回 0，不抛错（完成信号依赖此语义）。"""
        repo = LocatorRepo.load(repo_dir)
        assert FakeChatPage(page=FakePage({}), repo=repo).count("chat_input") == 0

    def test_count_unknown_name_raises_not_found(self, repo_dir):
        repo = LocatorRepo.load(repo_dir)
        with pytest.raises(LookupError, match="ghost"):
            FakeChatPage(page=FakePage({}), repo=repo).count("ghost")
