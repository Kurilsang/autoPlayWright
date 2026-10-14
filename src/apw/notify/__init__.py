"""通知邮件模块（SMTP 直发）：测试结果摘要外发的下游消费者。

不依赖任何邮件客户端（Foxmail 等底层即同一 SMTP 通道）；引擎与 pytest
不反向依赖本模块，通知失败不影响测试结果。凭据/主机/收件人等真实值
只存本地（configs/secrets.local.yaml 或 APW_SMTP_* 环境变量），入库
文件一律占位符（AGENTS 红线）。
"""
from apw.notify.mail import (
    MailConfig,
    build_message,
    build_summary_mail,
    load_mail_config,
    notify_from_summary,
    send_mail,
    should_send,
)

__all__ = [
    "MailConfig",
    "build_message",
    "build_summary_mail",
    "load_mail_config",
    "notify_from_summary",
    "send_mail",
    "should_send",
]
