"""通知邮件模块自测（离线：不连 SMTP、不发信）。"""
from __future__ import annotations

import json
import zipfile
from io import BytesIO

import pytest

from apw.notify import mail
from apw.notify.mail import (
    MailConfig,
    attach_run_zip,
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


def _write_recipients(tmp_path, section: str):
    """收件人专用配置固定从 <repo_root>/configs/notify.local.yaml 读，故按相对路径落盘。"""
    directory = tmp_path / "configs"
    directory.mkdir(exist_ok=True)
    path = directory / "notify.local.yaml"
    path.write_text(section, encoding="utf-8")
    return path


class TestConfig:
    def test_load_from_secrets_file(self, tmp_path, monkeypatch):
        monkeypatch.setattr(mail, "repo_root", lambda: tmp_path)  # 隔离真实收件人配置
        cfg = load_mail_config(_write_secrets(tmp_path))
        assert cfg.host == "smtp.example.com"
        assert cfg.port == 587
        assert cfg.security == "starttls"
        assert cfg.to == ["<user>@<domain>"]
        assert cfg.from_addr == "<user>@<domain>"

    def test_env_overrides_secrets(self, tmp_path, monkeypatch):
        path = _write_secrets(tmp_path)
        monkeypatch.setattr(mail, "repo_root", lambda: tmp_path)
        monkeypatch.setenv("APW_SMTP_HOST", "smtp.override.example")
        monkeypatch.setenv("APW_SMTP_PORT", "465")
        monkeypatch.setenv("APW_SMTP_SECURITY", "ssl")
        monkeypatch.setenv("APW_NOTIFY_TO", "a@example.com, b@example.com")
        cfg = load_mail_config(path)
        assert cfg.host == "smtp.override.example"
        assert cfg.port == 465
        assert cfg.security == "ssl"
        assert cfg.to == ["a@example.com", "b@example.com"]

    def test_missing_file_yields_empty_config(self, tmp_path, monkeypatch):
        monkeypatch.setattr(mail, "repo_root", lambda: tmp_path)  # 隔离真实收件人配置
        cfg = load_mail_config(tmp_path / "absent.yaml")
        assert cfg.host == ""
        assert cfg.to == []

    def test_recipients_come_from_smtp_section(self, tmp_path, monkeypatch):
        monkeypatch.setattr(mail, "repo_root", lambda: tmp_path)
        cfg = load_mail_config(_write_secrets(tmp_path))
        assert cfg.to == ["<user>@<domain>"]
        assert cfg.cc == []
        assert cfg.report_to == []


class TestRecipients:
    """收件人集中配置：专用文件覆盖 secrets、report_to 取代 to、cc 进信封。"""

    def test_recipient_file_overrides_secrets_to(self, tmp_path, monkeypatch):
        secrets = _write_secrets(tmp_path)
        _write_recipients(tmp_path, "notify:\n  report_to:\n    - a@example.com\n")
        monkeypatch.setattr(mail, "repo_root", lambda: tmp_path)
        cfg = load_mail_config(secrets)
        assert cfg.to == ["a@example.com"]  # report_to 整体取代 secrets 的 to
        assert cfg.report_to == ["a@example.com"]

    def test_recipient_file_cc(self, tmp_path, monkeypatch):
        secrets = _write_secrets(tmp_path)
        _write_recipients(tmp_path, "notify:\n  cc:\n    - b@example.com\n")
        monkeypatch.setattr(mail, "repo_root", lambda: tmp_path)
        cfg = load_mail_config(secrets)
        assert cfg.to == ["<user>@<domain>"]  # secrets 的 to 保留
        assert cfg.cc == ["b@example.com"]

    def test_env_to_beats_files(self, tmp_path, monkeypatch):
        secrets = _write_secrets(tmp_path)
        _write_recipients(tmp_path, "notify:\n  to:\n    - file@example.com\n")
        monkeypatch.setattr(mail, "repo_root", lambda: tmp_path)
        monkeypatch.setenv("APW_NOTIFY_TO", "a@example.com,b@example.com")
        cfg = load_mail_config(secrets)
        assert cfg.to == ["a@example.com", "b@example.com"]  # 环境变量点对点覆盖

    def test_string_addresses_are_normalized(self, tmp_path, monkeypatch):
        secrets = _write_secrets(tmp_path)
        _write_recipients(
            tmp_path, 'notify:\n  to: "a@example.com, b@example.com"\n'
        )
        monkeypatch.setattr(mail, "repo_root", lambda: tmp_path)
        cfg = load_mail_config(secrets)
        assert cfg.to == ["a@example.com", "b@example.com"]

    def test_cc_joins_envelope_and_header(self):
        cfg = MailConfig(
            host="smtp.example.com",
            username="u@example.com",
            from_addr="u@example.com",
            to=["a@example.com"],
            cc=["b@example.com"],
        )
        msg, recipients = build_message(cfg, subject="s", body="b")
        assert recipients == ["a@example.com", "b@example.com"]  # 信封含抄送
        assert msg["To"] == "a@example.com"  # To 头只列主收件人
        assert msg["Cc"] == "b@example.com"

    def test_cc_only_config_counts_as_recipient(self):
        cfg = MailConfig(host="smtp.example.com", cc=["b@example.com"])
        _, recipients = build_message(cfg, subject="s", body="b")
        assert recipients == ["b@example.com"]


class TestReportZipAttachment:
    """邮件附件必须与 apw.api 的 GET /runs/<id>/report.zip 同内容（同函数产物）。"""

    def _run_dir(self, tmp_path):
        run = tmp_path / "20261014-160959-abc123"
        (run / "sub").mkdir(parents=True)
        (run / "run-summary.json").write_text('{"total": 1}', encoding="utf-8")
        (run / "report.html").write_text("<html></html>", encoding="utf-8")
        (run / "sub" / "x.png").write_bytes(b"\x89PNG")
        (run / "junk.pyc").write_bytes(b"junk")
        return run

    def test_attach_run_zip_matches_api_bytes(self, tmp_path):
        from apw.api import build_report_zip

        run = self._run_dir(tmp_path)
        (name, blob), = attach_run_zip(run)
        assert name == "20261014-160959-abc123-report.zip"
        assert blob == build_report_zip(run)  # 同一函数 → 逐字节一致
        with zipfile.ZipFile(BytesIO(blob)) as zf:
            names = zf.namelist()
        assert "20261014-160959-abc123/report.html" in names
        assert "20261014-160959-abc123/run-summary.json" in names
        assert not any(n.endswith(".pyc") for n in names)

    def test_attach_run_zip_sanitize_flag_passes_through(self, tmp_path, monkeypatch):
        run = self._run_dir(tmp_path)
        seen = {}

        def fake(run_dir, *, sanitize=False):
            seen["sanitize"] = sanitize
            return b"zip"

        monkeypatch.setattr("apw.api.build_report_zip", fake)
        attach_run_zip(run, sanitize=True)
        assert seen["sanitize"] is True

    def test_summary_mail_mentions_attachment_and_failures(self):
        summary = {
            "run_id": "r1",
            "total": 2,
            "passed": 1,
            "failed": 1,
            "skipped": 0,
            "flows": [
                {"flow_id": "b", "name": "乙", "status": "failed", "duration_ms": 20},
                {"flow_id": "a", "name": "甲", "status": "passed", "duration_ms": 10},
            ],
        }
        subject, body = build_summary_mail(
            summary, env="test", targets=["tests", "flows"], report_zip_name="r1-report.zip"
        )
        assert "1/2 通过" in subject and "1 失败" in subject
        assert "环境: test" in body and "目标: tests, flows" in body
        assert "附件: r1-report.zip" in body
        assert "失败 1 条" in body
        # 明细按 flow_id 稳定排序（worker 完成顺序不定）
        assert body.index("[passed] a 甲") < body.index("[failed] b 乙")

    def test_notify_from_summary_attaches_run_zip(self, tmp_path, monkeypatch):
        run = self._run_dir(tmp_path)
        summary_path = run / "run-summary.json"
        summary_path.write_text(
            json.dumps({"run_id": run.name, "total": 1, "passed": 0, "failed": 1, "flows": []}),
            encoding="utf-8",
        )
        captured = {}
        monkeypatch.setattr(
            mail, "send_mail", lambda cfg, **kw: captured.update(kw) or "mid"
        )
        sent = notify_from_summary(
            summary_path,
            policy="always",
            cfg=MailConfig(host="smtp.example.com", to=["a@example.com"]),
            report_zip=True,
            env="test",
        )
        assert sent is True
        (name, blob), = captured["attachments_blob"]
        assert name == f"{run.name}-report.zip"
        assert blob[:2] == b"PK"
        assert "环境: test" in captured["body"]

    def test_notify_from_summary_without_zip_has_no_attachment(self, tmp_path, monkeypatch):
        path = tmp_path / "run-summary.json"
        path.write_text(
            json.dumps({"run_id": "r", "total": 1, "passed": 1, "failed": 0, "flows": []}),
            encoding="utf-8",
        )
        captured = {}
        monkeypatch.setattr(
            mail, "send_mail", lambda cfg, **kw: captured.update(kw) or "mid"
        )
        notify_from_summary(
            path, policy="always", cfg=MailConfig(host="smtp.example.com", to=["a@example.com"])
        )
        assert captured["attachments_blob"] == []


class TestFoxmailRejectsBlobAttachments:
    def test_blob_attachment_also_rejected(self, monkeypatch):
        from apw.notify import foxmail

        monkeypatch.setattr(foxmail, "_Win32", lambda: pytest.fail("不应初始化 Win32"))
        cfg = MailConfig(transport="foxmail", to=["to@example.com"])
        with pytest.raises(NotImplementedError, match="附件"):
            send_mail(cfg, subject="s", body="b", attachments_blob=[("r.zip", b"PK")])


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
        head, query = url.split("?", 1)
        assert head == "mailto:a%40example.com,b%40example.com"  # 收件人整体编码
        assert query.startswith("subject=")
        assert "%0A" in query  # 正文换行已编码
        assert " " not in query  # 查询串无裸空格

    def test_mailto_query_has_no_raw_slash(self):
        """Foxmail 会整条丢弃含裸 `/` 的 mailto（主题「7/16 通过」曾踩中）。

        urllib.parse.quote 默认 safe='/'，必须显式 safe="" 才能把 `/` 编成 %2F。
        """
        from apw.notify.foxmail import build_mailto_url

        subject = "[APW] 测试摘要 20261014-160959-94d821ef：7/16 通过，4 失败"
        url = build_mailto_url(["a@example.com"], subject, "正文")
        query = url.split("?", 1)[1]
        assert "/" not in query, f"查询串仍有裸斜杠: {query}"
        assert "%2F" in query
        # 解码回来必须与原文一致（编码没吃掉字符）
        from urllib.parse import parse_qs

        assert parse_qs(query)["subject"][0] == subject

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
