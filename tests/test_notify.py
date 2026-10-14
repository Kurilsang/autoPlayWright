"""通知邮件模块自测（离线：不连 SMTP、不发信）。"""
from __future__ import annotations

import json

import pytest

from apw.notify import mail
from apw.notify.mail import (
    MailConfig,
    build_message,
    build_summary_mail,
    load_mail_config,
    notify_from_summary,
    send_mail,
    should_send,
)


def _write_secrets(tmp_path, **smtp_extra):
    section = {
        "host": "smtp.example.com",
        "port": 587,
        "security": "starttls",
        "username": "<user>@<domain>",
        "password": "<password>",
        "from": "<user>@<domain>",
        "to": ["<user>@<domain>"],
    }
    section.update(smtp_extra)
    path = tmp_path / "secrets.local.yaml"
    path.write_text(
        "username: <user>\npassword: <password>\nsmtp:\n"
        + "".join(
            f"  {k}: {json.dumps(v) if isinstance(v, list) else v}\n"
            for k, v in section.items()
        ),
        encoding="utf-8",
    )
    return path


class TestConfig:
    def test_load_from_secrets_file(self, tmp_path):
        cfg = load_mail_config(_write_secrets(tmp_path))
        assert cfg.host == "smtp.example.com"
        assert cfg.port == 587
        assert cfg.security == "starttls"
        assert cfg.to == ["<user>@<domain>"]
        assert cfg.from_addr == "<user>@<domain>"

    def test_env_overrides_secrets(self, tmp_path, monkeypatch):
        path = _write_secrets(tmp_path)
        monkeypatch.setenv("APW_SMTP_HOST", "smtp.override.example")
        monkeypatch.setenv("APW_SMTP_PORT", "465")
        monkeypatch.setenv("APW_SMTP_SECURITY", "ssl")
        monkeypatch.setenv("APW_NOTIFY_TO", "a@example.com, b@example.com")
        cfg = load_mail_config(path)
        assert cfg.host == "smtp.override.example"
        assert cfg.port == 465
        assert cfg.security == "ssl"
        assert cfg.to == ["a@example.com", "b@example.com"]

    def test_missing_file_yields_empty_config(self, tmp_path):
        cfg = load_mail_config(tmp_path / "absent.yaml")
        assert cfg.host == ""
        assert cfg.to == []


class TestMessage:
    def test_build_message_headers_and_body(self):
        cfg = MailConfig(
            host="smtp.example.com",
            username="user@example.com",
            from_addr="user@example.com",
            to=["to@example.com"],
        )
        msg, recipients = build_message(cfg, subject="主题", body="正文内容")
        assert recipients == ["to@example.com"]
        assert msg["Subject"] == "主题"
        assert msg["From"] == "user@example.com"
        assert msg["To"] == "to@example.com"
        assert "正文内容" in msg.get_content()

    def test_build_message_requires_recipient(self):
        cfg = MailConfig(host="smtp.example.com")
        with pytest.raises(ValueError, match="收件人"):
            build_message(cfg, subject="s", body="b")

    def test_summary_mail_lists_flows(self):
        summary = {
            "run_id": "20261014-101010-1",
            "total": 2,
            "passed": 1,
            "failed": 1,
            "skipped": 0,
            "flows": [
                {"flow_id": "f-a", "name": "甲", "status": "passed", "duration_ms": 10},
                {
                    "flow_id": "f-b",
                    "name": "乙",
                    "status": "failed",
                    "duration_ms": 20,
                    "skip_reason": None,
                },
            ],
        }
        subject, body = build_summary_mail(summary)
        assert "1/2 通过" in subject and "1 失败" in subject
        assert "[passed] f-a 甲" in body
        assert "[failed] f-b 乙" in body


class TestPolicy:
    @pytest.mark.parametrize(
        ("policy", "failed", "expect"),
        [
            ("off", 1, False),
            ("always", 0, True),
            ("on-fail", 0, False),
            ("on-fail", 1, True),
            ("on-change", 1, False),  # 无上一轮基线不发
        ],
    )
    def test_should_send(self, policy, failed, expect):
        assert should_send(policy, failed) is expect

    def test_on_change_needs_baseline(self):
        assert should_send("on-change", 1, prev_failed=0) is True
        assert should_send("on-change", 1, prev_failed=1) is False

    def test_unknown_policy_raises(self):
        with pytest.raises(ValueError, match="未知发信策略"):
            should_send("nope", 0)

    def test_notify_from_summary_respects_policy(self, tmp_path, monkeypatch):
        path = tmp_path / "run-summary.json"
        path.write_text(
            json.dumps({"run_id": "r", "total": 1, "passed": 1, "failed": 0, "flows": []}),
            encoding="utf-8",
        )
        sent = []
        monkeypatch.setattr(mail, "send_mail", lambda *a, **k: sent.append(a))
        assert notify_from_summary(path, policy="on-fail", cfg=MailConfig()) is False
        assert sent == []

        path.write_text(
            json.dumps({"run_id": "r", "total": 1, "passed": 0, "failed": 1, "flows": []}),
            encoding="utf-8",
        )
        monkeypatch.setattr(mail, "load_mail_config", lambda: MailConfig(host="smtp.example.com"))
        assert notify_from_summary(path, policy="on-fail") is True
        assert len(sent) == 1


class TestOAuth:
    def test_xoauth2_initial_response_encoding(self):
        from apw.notify.oauth import xoauth2_initial_response

        encoded = xoauth2_initial_response("u@example.com", "tok123")
        decoded = __import__("base64").b64decode(encoded).decode()
        assert decoded == "user=u@example.com\x01auth=Bearer tok123\x01\x01"

    def test_token_cache_roundtrip(self, tmp_path, monkeypatch):
        from apw.notify import oauth

        monkeypatch.setattr(oauth, "cache_path", lambda: tmp_path / "tok.json")
        oauth.save_cached("u@example.com", {"access_token": "a", "refresh_token": "r"})
        cached = oauth.load_cached("u@example.com")
        assert cached["access_token"] == "a" and cached["refresh_token"] == "r"

    def test_get_token_refreshes_when_expired(self, tmp_path, monkeypatch):
        from apw.notify import oauth

        monkeypatch.setattr(oauth, "cache_path", lambda: tmp_path / "tok.json")
        monkeypatch.setattr(oauth, "discover_tenant", lambda addr: "tenant-x")
        oauth.save_cached(
            "u@example.com",
            {"access_token": "old", "refresh_token": "r", "expires_at": 1},
        )
        calls = {}

        def fake_post(url, payload):
            calls["url"], calls["payload"] = url, payload
            return 200, {"access_token": "new", "expires_in": 3600}

        monkeypatch.setattr(oauth, "_post", fake_post)
        cfg = MailConfig(username="u@example.com", auth="xoauth2")
        assert oauth.get_token(cfg) == "new"
        assert calls["payload"]["grant_type"] == "refresh_token"
        assert oauth.load_cached("u@example.com")["access_token"] == "new"

    def test_get_token_requires_login_first(self, tmp_path, monkeypatch):
        from apw.notify import oauth

        monkeypatch.setattr(oauth, "cache_path", lambda: tmp_path / "absent.json")
        with pytest.raises(RuntimeError, match="--login"):
            oauth.get_token(MailConfig(username="u@example.com", auth="xoauth2"))

    def test_pkce_pair_is_s256(self):
        import base64
        import hashlib

        from apw.notify.oauth import _pkce_pair

        verifier, challenge = _pkce_pair()
        assert 43 <= len(verifier) <= 128
        expect = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode()
        assert challenge == expect.rstrip("=")


class TestEws:
    def test_envelope_escapes_and_addresses(self):
        from apw.notify.ews import build_ews_envelope

        xml = build_ews_envelope(
            subject="a<b>&c", body="第一行\n第二行", to=["to@example.com", "x&y@example.com"]
        )
        assert "a&lt;b&gt;&amp;c" in xml
        assert "<t:EmailAddress>to@example.com</t:EmailAddress>" in xml
        assert "<t:EmailAddress>x&amp;y@example.com</t:EmailAddress>" in xml
        assert 'MessageDisposition="SendAndSaveCopy"' in xml

    def test_parse_response_success(self):
        from apw.notify.ews import parse_ews_response

        xml = """<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/"
          xmlns:m="http://schemas.microsoft.com/exchange/services/2006/messages"
          xmlns:t="http://schemas.microsoft.com/exchange/services/2006/types">
          <s:Body><m:CreateItemResponse>
            <m:ResponseMessages>
              <m:CreateItemResponseMessage ResponseClass="Success">
                <m:ResponseCode>NoError</m:ResponseCode>
                <m:Items><t:Message><t:ItemId Id="abc" /></t:Message></m:Items>
              </m:CreateItemResponseMessage>
            </m:ResponseMessages>
          </m:CreateItemResponse></s:Body></s:Envelope>"""
        # RootItemId 缺失时返回空串（仅成功校验）
        assert parse_ews_response(xml) == ""

    def test_parse_response_failure_raises(self):
        import pytest

        from apw.notify.ews import parse_ews_response

        xml = """<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/"
          xmlns:m="http://schemas.microsoft.com/exchange/services/2006/messages">
          <s:Body><m:CreateItemResponse><m:ResponseMessages>
            <m:CreateItemResponseMessage ResponseClass="Error">
              <m:ResponseCode>ErrorSenderDenied</m:ResponseCode>
              <m:MessageText>denied</m:MessageText>
            </m:CreateItemResponseMessage>
          </m:ResponseMessages></m:CreateItemResponse></s:Body></s:Envelope>"""
        with pytest.raises(RuntimeError, match="ErrorSenderDenied"):
            parse_ews_response(xml)


class TestFoxmail:
    def test_build_mailto_url(self):
        from apw.notify.foxmail import build_mailto_url

        url = build_mailto_url(["a@example.com", "b@example.com"], "主题 x", "第一行\n第二行")
        assert url.startswith("mailto:a@example.com,b@example.com?subject=")
        assert "%0A" in url  # 正文换行已编码
        assert " " not in url.split("?", 1)[1]  # 查询串无裸空格

    def test_exe_from_command(self):
        from apw.notify.foxmail import _exe_from_command

        cmd = '"D:\\Program Files\\Foxmail 7.2\\Foxmail.exe" "%1"'
        assert _exe_from_command(cmd) == "D:\\Program Files\\Foxmail 7.2\\Foxmail.exe"
        assert _exe_from_command("C:\\fox.exe %1") == "C:\\fox.exe"

    def test_send_mail_dispatches_foxmail(self, monkeypatch):
        from apw.notify import foxmail

        calls = []
        monkeypatch.setattr(
            foxmail, "send_foxmail", lambda cfg, **kw: calls.append(kw) or "foxmail:hwnd=1"
        )
        cfg = MailConfig(transport="foxmail", to=["to@example.com"])
        result = send_mail(cfg, subject="s", body="b")
        assert result == "foxmail:hwnd=1"
        assert calls[0]["subject"] == "s"

    def test_foxmail_rejects_attachments(self, monkeypatch):
        from apw.notify import foxmail

        monkeypatch.setattr(
            foxmail, "_Win32", lambda: pytest.fail("不应初始化 Win32")
        )
        cfg = MailConfig(transport="foxmail", to=["to@example.com"])
        with pytest.raises(NotImplementedError, match="附件"):
            send_mail(cfg, subject="s", body="b", attachments=["x.txt"])

    def test_foxmail_reports_platform_clearly_on_non_windows(self, monkeypatch):
        """Linux/服务器上必须给人话报错（而非 ctypes.wintypes 的隐晦 ValueError）。"""
        import ctypes

        from apw.notify.foxmail import _Win32, find_foxmail_exe

        monkeypatch.delattr(ctypes, "WinDLL", raising=False)
        with pytest.raises(RuntimeError, match="仅支持 Windows"):
            _Win32()
        with pytest.raises(RuntimeError, match="仅支持 Windows"):
            find_foxmail_exe()
