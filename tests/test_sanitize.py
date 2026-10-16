"""脱敏器纯函数测试：敏感串→占位符，结构保留，映射可配置。"""
from __future__ import annotations

from apw.sanitize import load_mapping, sanitize_text

MAPPING = {"内部产品名": "<product>", "taylor.smith": "<user-me>"}


class TestSanitizeText:
    def test_replaces_mapped_strings(self):
        out = sanitize_text("欢迎使用 内部产品名 与 taylor.smith 的空间", MAPPING)
        assert out == "欢迎使用 <product> 与 <user-me> 的空间"

    def test_clean_text_unchanged(self):
        text = "最终答案：结构未变，无敏感内容"
        assert sanitize_text(text, MAPPING) == text

    def test_email_like_becomes_placeholder(self):
        out = sanitize_text("联系 someone@example.com 处理", MAPPING)
        assert out == "联系 <user> 处理"

    def test_at_handle_becomes_placeholder(self):
        out = sanitize_text("账号 @taylor.smith 已登录", MAPPING)
        assert out == "账号 <user> 已登录"

    def test_word_substrings_untouched(self):
        """词内子串不误伤：yaml/YAML 不因映射键 aml/AML 被改写。"""
        text = "yaml YAML Yaml"
        assert sanitize_text(text, {"aml": "<p>", "AML": "<p>", "Aml": "<p>"}) == text

    def test_at_decorator_not_masked(self):
        """无点句柄（代码装饰器等）不误伤；有点账号句柄仍脱敏。"""
        code = "@property def f(): ..."
        assert sanitize_text(code, MAPPING) == code

    def test_url_host_masked_path_kept(self):
        """内网主机替换为占位符，路径保留（复现线索的诊断价值不丢）。"""
        out = sanitize_text('{"url": "https://intranet.example.com/app/chat/42"}', MAPPING)
        assert out == '{"url": "https://<host>/app/chat/42"}'

    def test_structure_preserved_for_json_payload(self):
        payload = (
            '{"title": "内部产品名", "signals": {"stop_cleared": true}, '
            '"screenshots": ["x-1.png"], "url": "https://intranet.example.com/a"}'
        )
        import json

        out = sanitize_text(payload, MAPPING)
        data = json.loads(out)  # 结构对拍不变
        assert data["signals"] == {"stop_cleared": True}
        assert data["screenshots"] == ["x-1.png"]
        assert data["title"] == "<product>"
        assert data["url"] == "https://<host>/a"

    def test_longer_mapping_key_wins(self):
        out = sanitize_text(
            "Gadget 与 Gadget 产品线", {"Gadget 产品线": "<product>", "Gadget": "<p>"}
        )
        assert out == "<p> 与 <product>"


class TestLoadMapping:
    def test_load_from_yaml(self, tmp_path):
        f = tmp_path / "sanitize.local.yaml"
        f.write_text("产品甲: <product>\nuser.a: <user-me>\n", encoding="utf-8")
        assert load_mapping(f) == {"产品甲": "<product>", "user.a": "<user-me>"}

    def test_missing_file_returns_empty(self, tmp_path):
        assert load_mapping(tmp_path / "nope.yaml") == {}
