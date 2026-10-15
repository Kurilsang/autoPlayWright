"""SMTP 发信实现与 run 摘要邮件组装。

凭据解析顺序：环境变量 APW_SMTP_* / APW_NOTIFY_* → secrets 文件
（默认 configs/secrets.local.yaml 的 smtp: 段，模板 configs/notify.example.yaml）。

收件人集中配置（配置文件里改一处，不用动命令行）。加载顺序，后者覆盖前者：

1. `configs/secrets.local.yaml` 的 `smtp:` 段（与凭据同文件，历史口径）
2. `configs/notify.local.yaml` 的 `notify:` 段（**收件人专用集中配置**，便于单独改名单）
3. 环境变量 `APW_NOTIFY_TO`（逗号分隔，覆盖 `to`）
4. 命令行 `--to/--cc`（最高优先，仅单次生效）

`smtp.report_to` / `notify.report_to` 非空时**整体取代** `to`：报告含内网截图/真实 URL，
常需要「测试组全量 + 管理层摘要」的不同名单。`cc` 抄送进 SMTP 信封收件人（缺省不出现在 To 头）。
（report_to 与 cc 只认配置文件：环境变量按 RFC 只带信封收件人，express 到 To 头会失真。）

附件口径与回归触发 API 完全一致：`attach_run_zip` 调 `apw.api.build_report_zip`，
外部服务从 `GET /runs/<id>/report.zip` 拿到的包与本模块发出的附件是同一个函数产物。
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
_DEFAULT_RECIPIENTS = "configs/notify.local.yaml"
_RECIPIENT_FIELDS = ("to", "cc", "report_to")


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
    cc: list[str] = Field(default_factory=list)
    report_to: list[str] = Field(default_factory=list)  # 非空则整体取代 to


def repo_root() -> Path:
    """运行时资产锚定仓库根（同 pytest_plugin 口径，任意目录调用行为一致）。"""
    for parent in Path(__file__).resolve().parents:
        if (parent / "pyproject.toml").exists():
            return parent
    return Path.cwd()


def _load_yaml_section(path: Path, section: str) -> dict:
    if not path.exists():
        return {}
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except (yaml.YAMLError, OSError):
        return {}
    section_data = data.get(section)
    return section_data if isinstance(section_data, dict) else {}


def _normalize_addresses(data: dict) -> None:
    """收件人字段允许 `a@x` 单串写法（列表/逗号串都收）。"""
    for field in _RECIPIENT_FIELDS:
        value = data.get(field)
        if isinstance(value, str):
            data[field] = [a.strip() for a in value.split(",") if a.strip()]
        elif isinstance(value, (list, tuple)):
            data[field] = [str(a).strip() for a in value if str(a).strip()]


def load_mail_config(secrets_file: str | Path | None = None) -> MailConfig:
    """凭据：环境变量优先，其次 secrets 文件的 smtp: 段；均缺失则留空（调用方校验）。

    收件人另有专用集中配置文件 `configs/notify.local.yaml`（`notify:` 段），
    覆盖 secrets 同名字段——改名单不必碰凭据文件。
    """
    data: dict = {}
    root = repo_root()
    # 专用收件人文件先展开（可能只给收件人），secrets 凭据段在其上合并；
    # 随后逐字段用收件人文件的非空值覆盖——顺序反了会把专用名单顶掉。
    data.update(_load_yaml_section(root / _DEFAULT_RECIPIENTS, "notify"))
    path = Path(secrets_file) if secrets_file else root / _DEFAULT_SECRETS
    data.update(_load_yaml_section(path, "smtp"))
    recipients = _load_yaml_section(root / _DEFAULT_RECIPIENTS, "notify")
    for field in _RECIPIENT_FIELDS:
        if recipients.get(field):
            data[field] = recipients[field]

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
    _normalize_addresses(data)
    cfg = MailConfig(**data)
    if cfg.report_to and not to_env:
        # 报告专用名单在场即整体取代默认收件人（不会被 to 稀释）；
        # 但显式给的 --to / APW_NOTIFY_TO 优先级更高，按点对点投递理解。
        cfg.to = list(cfg.report_to)
    return cfg


def _has_oauth_token(cfg: MailConfig) -> bool:
    """是否已有可用的 OAuth token 缓存（没有就得先 --login）。"""
    try:
        from apw.notify import oauth

        return oauth.load_cached(cfg.username or cfg.from_addr) is not None
    except Exception:  # noqa: BLE001 - 探测失败按「无缓存」处理
        return False


def _foxmail_available(cfg: MailConfig) -> bool:
    """本机是否有可用的 Foxmail 代发通道（有则给用户指一条能走通的路）。"""
    try:
        from apw.notify.foxmail import find_foxmail_exe

        return bool((cfg.foxmail_path or "").strip() or find_foxmail_exe())
    except Exception:  # noqa: BLE001 - 非 Windows / 未安装
        return False


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
    attachments_blob: list[tuple[str, bytes]] | None = None,
) -> tuple[EmailMessage, list[str]]:
    """纯组装（不发信，便于离线自测）。返回 (消息, 收件人)。

    收件人 = `to`（缺省 cfg.to）∪ cfg.cc；返回值为 SMTP 信封收件人全集。
    `attachments_blob` 用于内存产物（如 report.zip）：[(文件名, 字节)]，
    与 `attachments`（磁盘路径）可同时给。
    """
    recipients = list(dict.fromkeys(list(to or cfg.to) + list(cfg.cc)))
    if not recipients:
        raise ValueError(
            "收件人为空：配置 smtp.to（或 smtp.report_to）/ notify.local.yaml / "
            "APW_NOTIFY_TO / --to 至少其一"
        )
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = cfg.from_addr or cfg.username
    msg["To"] = ", ".join(list(to or cfg.to))
    if cfg.cc:
        msg["Cc"] = ", ".join(cfg.cc)
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
    for filename, blob in attachments_blob or []:
        msg.add_attachment(
            blob,
            maintype="application",
            subtype="zip" if filename.lower().endswith(".zip") else "octet-stream",
            filename=filename,
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
    attachments_blob: list[tuple[str, bytes]] | None = None,
) -> str:
    """按 transport 分发（smtp/ews/foxmail），返回消息标识。"""
    transport = (cfg.transport or "smtp").strip().lower()
    if transport == "ews":
        from apw.notify import ews  # 惰性导入避免循环依赖

        return ews.send_ews(
            cfg,
            subject=subject,
            body=body,
            to=to,
            html=html,
            attachments=attachments,
            attachments_blob=attachments_blob,
        )
    if transport == "foxmail":
        from apw.notify import foxmail  # 惰性导入避免循环依赖

        return foxmail.send_foxmail(
            cfg,
            subject=subject,
            body=body,
            to=to,
            html=html,
            attachments=attachments,
            attachments_blob=attachments_blob,
        )
    if not cfg.host:
        raise ValueError("SMTP host 未配置（smtp.host / APW_SMTP_HOST）")
    msg, recipients = build_message(
        cfg,
        subject=subject,
        body=body,
        to=to,
        html=html,
        attachments=attachments,
        attachments_blob=attachments_blob,
    )
    security = (cfg.security or "starttls").strip().lower()
    xoauth2 = (cfg.auth or "basic").strip().lower() == "xoauth2"
    if xoauth2 and not _has_oauth_token(cfg):
        # 本机常见形态：token 只在 Foxmail 自己的凭据库里（我们读不到）。
        # 硬报错会让人以为「发不了信」，其实 foxmail 通道能代发——失败前显式指路。
        if (cfg.transport or "").strip().lower() != "foxmail" and _foxmail_available(cfg):
            raise ValueError(
                "无 OAuth token 缓存：本机装了 Foxmail，请改用代发通道 "
                "APW_MAIL_TRANSPORT=foxmail（免登录，但不支持附件），"
                "或先跑 python -m apw.notify --login 获取 SMTP 令牌"
            )
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
        if xoauth2:
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


def _ordered_flows(summary: dict) -> list[dict]:
    """明细稳定排序（flow_id 字典序）：worker 完成顺序不定，邮件读起来要一致。"""
    return sorted(summary.get("flows", []), key=lambda f: str(f.get("flow_id") or ""))


def build_summary_mail(
    summary: dict,
    *,
    env: str = "",
    targets: list[str] | None = None,
    report_zip_name: str = "",
) -> tuple[str, str]:
    """run-summary.json → (主题, 纯文本正文)。"""
    run_id = summary.get("run_id", "unknown")
    total = int(summary.get("total", 0))
    passed = int(summary.get("passed", 0))
    failed = int(summary.get("failed", 0))
    skipped = int(summary.get("skipped", 0))
    subject = f"[APW] 测试摘要 {run_id}：{passed}/{total} 通过"
    if failed:
        subject += f"，{failed} 失败"
    lines = [f"run_id: {run_id}"]
    if env:
        lines.append(f"环境: {env}")
    if targets:
        lines.append(f"目标: {', '.join(targets)}")
    lines += [
        f"结果: {passed} 通过 / {failed} 失败 / {skipped} 跳过（共 {total}）",
    ]
    if report_zip_name:
        lines.append(f"附件: {report_zip_name}（run 目录全量：report.html + JSON + 失败截图）")
    lines += ["", "明细:"]
    flows = _ordered_flows(summary)
    for item in flows:
        line = (
            f"[{item.get('status')}] {item.get('flow_id')} "
            f"{item.get('name')} ({item.get('duration_ms')}ms)"
        )
        if item.get("skip_reason"):
            line += f" — {item['skip_reason']}"
        lines.append(line)
    failing = [f for f in flows if f.get("status") == "failed"]
    if failing:
        lines += ["", f"失败 {len(failing)} 条（详见附件 JSON 取证：归因/复现/信号时间线）:"]
        lines += [f"- {f.get('flow_id')} {f.get('name')}" for f in failing]
    return subject, "\n".join(lines)


def attach_run_zip(
    run_dir: str | Path,
    *,
    sanitize: bool = False,
    filename: str = "",
) -> list[tuple[str, bytes]]:
    """run 目录 → 内存 zip 附件，**与回归触发 API 的 report.zip 同一产物**。

    实现直接调 `apw.api.build_report_zip`（单一口径：外部服务 GET /runs/<id>/report.zip
    拿到的包 = 本模块邮件附件的字节），避免两条路径各自打包导致内容漂移。
    sanitize=True 时同口径过 `apw.sanitize`（发到项目外部的通道建议开）。
    """
    from apw.api import build_report_zip  # 惰性导入：mail 是 API 的下游，避免循环

    name = filename or f"{Path(run_dir).name}-report.zip"
    return [(name, build_report_zip(run_dir, sanitize=sanitize))]


def notify_from_summary(
    summary_path: str | Path,
    *,
    policy: str = "on-fail",
    cfg: MailConfig | None = None,
    to: list[str] | None = None,
    report_zip: bool = False,
    attach: list[str | Path] | None = None,
    sanitize: bool = False,
    env: str = "",
    targets: list[str] | None = None,
) -> bool:
    """按策略发送 run 摘要邮件；未命中策略返回 False（不发信）。

    report_zip=True 时把该 run 目录打成 zip 作附件（口径同 `apw.api`
    的 `GET /runs/<id>/report.zip`，见 `attach_run_zip`）。
    """
    path = Path(summary_path)
    summary = json.loads(path.read_text(encoding="utf-8"))
    if not should_send(policy, int(summary.get("failed", 0))):
        return False
    cfg = cfg or load_mail_config()
    blobs = attach_run_zip(path.parent, sanitize=sanitize) if report_zip else []
    subject, body = build_summary_mail(
        summary,
        env=env,
        targets=targets,
        report_zip_name=blobs[0][0] if blobs else "",
    )
    send_mail(
        cfg,
        subject=subject,
        body=body,
        to=to,
        attachments=list(attach or []),
        attachments_blob=blobs,
    )
    return True
