"""定位器仓库测试：加载、列表/映射两种形式、候选优先级结构。"""
from __future__ import annotations

import pytest

from apw.locators.repo import LocatorRepo


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

        class FakeFirst:
            def count(self):
                return 0

            def wait_for(self, **kw):
                raise TimeoutError("nope")

        class FakeLoc:
            first = FakeFirst()

            def count(self):
                return 0

        class FakePage:
            def get_by_test_id(self, v):
                return FakeLoc()

            def locator(self, v):
                return FakeLoc()

        with pytest.raises(LookupError, match="chat_input"):
            repo.resolve(FakePage(), "agent_chat", "chat_input", probe_timeout_ms=1)
