"""SMTP 发信实现与 run 摘要邮件组装。

凭据解析顺序：环境变量 APW_SMTP_* / APW_NOTIFY_* → secrets 文件
（默认 configs/secrets.local.yaml 的 smtp: 段，模板 configs/notify.example.yaml）。
"""
from __future__ import annotations

import json
import os
import smtplib
import ssl
from email.message import EmailMessage
from email.utils import formatdate
from pathlib import Path

import yaml
from pydantic import BaseModel, Field

_ENV_PREFIX = "APW_SMTP_"
_DEFAULT_SECRETS = "configs/secrets.local.yaml"


class MailConfig(BaseModel):
    """SMTP 发信配置（真实值仅存本地，入库文件用占位符）。"""

    host: str = ""
    port: int = 587
    security: str = "starttls"  # starttls | ssl | none
    auth: str = "basic"  # basic | xoauth2（MFA 租户用 xoauth2）
    transport: str = "smtp"  # smtp | ews | foxmail（foxmail=本机客户端代发，免微软登录）
    ews_url: str = ""  # ews 端点（缺省 Exchange Online 公共端点）
    foxmail_path: str = ""  # Foxmail.exe 路径（缺省从 mailto 关联注册表发现）
    timeout: float = 30.0
    username: str = ""
    password: str = ""
    from_addr: str = ""
    client_id: str = ""  # xoauth2 用（缺省公共客户端，可换自注册应用）
    to: list[str] = Field(default_factory=list)


def repo_root() -> Path:
    """运行时资产锚定仓库根（同 pytest_plugin 口径，任意目录调用行为一致）。"""
    for parent in Path(__file__).resolve().parents:
        if (parent / "pyproject.toml").exists():
            return parent
    return Path.cwd()


def load_mail_config(secrets_file: str | Path | None = None) -> MailConfig:
    """环境变量优先，其次 secrets 文件的 smtp: 段；均缺失则留空（调用方校验）。"""
    data: dict = {}
    path = Path(secrets_file) if secrets_file else repo_root() / _DEFAULT_SECRETS
    if path.exists():
        section = (yaml.safe_load(path.read_text(encoding="utf-8")) or {}).get("smtp") or {}
        data.update(section)

    env_map = {
        "host": f"{_ENV_PREFIX}HOST",
        "port": f"{_ENV_PREFIX}PORT",
        "security": f"{_ENV_PREFIX}SECURITY",
        "auth": f"{_ENV_PREFIX}AUTH",
        "transport": "APW_MAIL_TRANSPORT",
        "ews_url": "APW_EWS_URL",
        "foxmail_path": "APW_FOXMAIL_PATH",
        "timeout": f"{_ENV_PREFIX}TIMEOUT",
        "username": f"{_ENV_PREFIX}USER",
        "password": f"{_ENV_PREFIX}PASSWORD",
        "from_addr": "APW_NOTIFY_FROM",
        "client_id": "APW_OAUTH_CLIENT_ID",
    }
    for field, env_name in env_map.items():
        value = os.environ.get(env_name, "").strip()
        if value:
            data[field] = value
    to_env = os.environ.get("APW_NOTIFY_TO", "").strip()
    if to_env:
        data["to"] = [addr.strip() for addr in to_env.split(",") if addr.strip()]

    data.setdefault("from_addr", data.get("username", ""))
    if "to" in data and isinstance(data["to"], str):
        data["to"] = [data["to"]]
    return MailConfig(**data)


def should_send(policy: str, failed: int, prev_failed: int | None = None) -> bool:
    """发信策略：off/always/on-fail/on-change（绿翻红或红翻绿才发）。"""
    policy = (policy or "off").strip().lower()
    if policy in ("off", "never", ""):
        return False
    if policy == "always":
        return True
    if policy == "on-fail":
        return failed > 0
    if policy == "on-change":
        return prev_failed is not None and (failed > 0) != (prev_failed > 0)
    raise ValueError(f"未知发信策略: {policy!r}（可用 off|always|on-fail|on-change）")


def build_message(
    cfg: MailConfig,
    *,
    subject: str,
    body: str,
    to: list[str] | None = None,
    html: str | None = None,
    attachments: list[str | Path] | None = None,
) -> tuple[EmailMessage, list[str]]:
    """纯组装（不发信，便于离线自测）。返回 (消息, 收件人)。"""
    recipients = list(to or cfg.to)
    if not recipients:
        raise ValueError("收件人为空：配置 smtp.to / APW_NOTIFY_TO / --to 至少其一")
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = cfg.from_addr or cfg.username
    msg["To"] = ", ".join(recipients)
    msg["Date"] = formatdate(localtime=True)
    msg.set_content(body)
    if html:
        msg.add_alternative(html, subtype="html")
    for item in attachments or []:
        path = Path(item)
        msg.add_attachment(
            path.read_bytes(),
            maintype="application",
            subtype="octet-stream",
            filename=path.name,
        )
    return msg, recipients


def send_mail(
    cfg: MailConfig,
    *,
    subject: str,
    body: str,
    to: list[str] | None = None,
    html: str | None = None,
    attachments: list[str | Path] | None = None,
) -> str:
    """按 transport 分发（smtp/ews/foxmail），返回消息标识。"""
    transport = (cfg.transport or "smtp").strip().lower()
    if transport == "ews":
        from apw.notify import ews  # 惰性导入避免循环依赖

        return ews.send_ews(
            cfg, subject=subject, body=body, to=to, html=html, attachments=attachments
        )
    if transport == "foxmail":
        from apw.notify import foxmail  # 惰性导入避免循环依赖

        return foxmail.send_foxmail(
            cfg, subject=subject, body=body, to=to, html=html, attachments=attachments
        )
    if not cfg.host:
        raise ValueError("SMTP host 未配置（smtp.host / APW_SMTP_HOST）")
    msg, recipients = build_message(
        cfg, subject=subject, body=body, to=to, html=html, attachments=attachments
    )
    security = (cfg.security or "starttls").strip().lower()
    if security == "ssl":
        smtp: smtplib.SMTP = smtplib.SMTP_SSL(
            cfg.host, cfg.port, timeout=cfg.timeout, context=ssl.create_default_context()
        )
    else:
        smtp = smtplib.SMTP(cfg.host, cfg.port, timeout=cfg.timeout)
    with smtp:
        smtp.ehlo()
        if security == "starttls":
            smtp.starttls(context=ssl.create_default_context())
            smtp.ehlo()
        if (cfg.auth or "basic").strip().lower() == "xoauth2":
            from apw.notify import oauth  # 惰性导入避免循环依赖

            token = oauth.get_token(cfg)
            smtp.auth(
                "XOAUTH2",
                lambda challenge=None: oauth.xoauth2_initial_response(
                    cfg.username or cfg.from_addr, token
                ),
            )
        elif cfg.username:
            smtp.login(cfg.username, cfg.password)
        smtp.send_message(msg, from_addr=msg["From"], to_addrs=recipients)
    return str(msg["Message-ID"] or msg["Date"])


def build_summary_mail(summary: dict) -> tuple[str, str]:
    """run-summary.json → (主题, 纯文本正文)。"""
    run_id = summary.get("run_id", "unknown")
    total = int(summary.get("total", 0))
    passed = int(summary.get("passed", 0))
    failed = int(summary.get("failed", 0))
    skipped = int(summary.get("skipped", 0))
    subject = f"[APW] 测试摘要 {run_id}：{passed}/{total} 通过"
    if failed:
        subject += f"，{failed} 失败"
    lines = [
        f"run_id: {run_id}",
        f"结果: {passed} 通过 / {failed} 失败 / {skipped} 跳过（共 {total}）",
        "",
        "明细:",
    ]
    for item in summary.get("flows", []):
        line = (
            f"[{item.get('status')}] {item.get('flow_id')} "
            f"{item.get('name')} ({item.get('duration_ms')}ms)"
        )
        if item.get("skip_reason"):
            line += f" — {item['skip_reason']}"
        lines.append(line)
    return subject, "\n".join(lines)


def notify_from_summary(
    summary_path: str | Path,
    *,
    policy: str = "on-fail",
    cfg: MailConfig | None = None,
    to: list[str] | None = None,
) -> bool:
    """按策略发送 run 摘要邮件；未命中策略返回 False（不发信）。"""
    summary = json.loads(Path(summary_path).read_text(encoding="utf-8"))
    if not should_send(policy, int(summary.get("failed", 0))):
        return False
    cfg = cfg or load_mail_config()
    subject, body = build_summary_mail(summary)
    send_mail(cfg, subject=subject, body=body, to=to)
    return True
