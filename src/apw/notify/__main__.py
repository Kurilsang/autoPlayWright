"""通知邮件 CLI：python -m apw.notify

  --test                    冒烟：发一封测试邮件（验证 SMTP 链路）
  --login                   OAuth2 设备码登录（MFA 租户一次性交互，缓存 token）
  --summary reports/…/run-summary.json   发送 run 摘要（配合 --policy）
  --policy off|always|on-fail|on-change  发信策略（summary 模式生效）
  --to a@x,b@y              覆盖收件人（逗号分隔）
  --attach PATH             附加文件（可多次）
"""
from __future__ import annotations

import argparse
import os
import platform
import sys
from datetime import datetime

from apw.notify.mail import (
    build_message,
    load_mail_config,
    notify_from_summary,
    send_mail,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="apw.notify", description="APW 通知邮件（SMTP 直发）")
    parser.add_argument("--test", action="store_true", help="发送冒烟测试邮件")
    parser.add_argument("--login", action="store_true", help="OAuth2 设备码登录（缓存 token）")
    parser.add_argument(
        "--login-browser",
        action="store_true",
        help="OAuth2 授权码登录（浏览器+PKCE+本地回调；设备码被策略封时用）",
    )
    parser.add_argument("--summary", metavar="PATH", help="run-summary.json 路径")
    parser.add_argument(
        "--policy",
        default="on-fail",
        choices=["off", "always", "on-fail", "on-change"],
        help="发信策略（--summary 模式生效，默认 on-fail）",
    )
    parser.add_argument("--to", metavar="ADDRS", help="收件人覆盖，逗号分隔")
    parser.add_argument("--attach", action="append", default=[], metavar="PATH", help="附件")
    args = parser.parse_args(argv)

    if not args.test and not args.summary and not args.login and not args.login_browser:
        parser.error("需要 --login、--login-browser、--test 或 --summary")

    cfg = load_mail_config()
    to = [a.strip() for a in args.to.split(",") if a.strip()] if args.to else None

    try:
        if args.login or args.login_browser:
            from apw.notify import oauth

            scope = os.environ.get("APW_OAUTH_SCOPE", "").strip() or oauth.DEFAULT_SCOPE
            if args.login_browser:
                oauth.auth_code_login(cfg, scope=scope)
            else:
                oauth.device_code_login(cfg, scope=scope)
            print("[notify] 登录成功，token 已缓存（后续发信自动刷新）")
            return 0

        if args.test:
            stamp = datetime.now().strftime("%H%M%S")
            subject = f"[APW] 通知链路冒烟测试 {stamp}"
            body = (
                "APW 邮件通知链路冒烟测试（SMTP 直发）。\n"
                f"发送时间: {datetime.now().isoformat(timespec='seconds')}\n"
                f"主机: {platform.node()}\n"
                f"SMTP: {cfg.host}:{cfg.port} ({cfg.security})\n"
            )
            msg, recipients = build_message(
                cfg, subject=subject, body=body, to=to, attachments=args.attach or None
            )
            send_mail(
                cfg,
                subject=subject,
                body=body,
                to=to,
                attachments=args.attach or None,
            )
            print(f"[notify] 冒烟邮件已发送 → {', '.join(recipients)} ({msg['Message-ID']})")
            return 0

        sent = notify_from_summary(
            args.summary,
            policy=args.policy,
            cfg=cfg,
            to=to,
        )
        if sent:
            print(f"[notify] 摘要邮件已发送（policy={args.policy}）")
        else:
            print(f"[notify] 未发送（policy={args.policy} 未命中）")
        return 0
    except Exception as exc:  # noqa: BLE001 - CLI 顶层统一报错
        print(f"[notify] 发送失败: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
