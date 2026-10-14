"""EWS 发信后端（Exchange Web Services SOAP）。

SMTP 提交权限（SMTP.Send）受租户预授权限制时的替代通道：拿
EWS.AccessAsUser.All 令牌（Outlook 桌面同款权限，一方应用预授权），
以登录身份（From=登录邮箱）经 Exchange Online 发出，效果等价于 SMTP 发信。
"""
from __future__ import annotations

import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from apw.notify.mail import MailConfig

DEFAULT_EWS_URL = "https://outlook.office365.com/EWS/Exchange.asmx"
EWS_SCOPE = "offline_access https://outlook.office365.com/EWS.AccessAsUser.All"

_NS = {
    "soap": "http://schemas.xmlsoap.org/soap/envelope/",
    "t": "http://schemas.microsoft.com/exchange/services/2006/types",
    "m": "http://schemas.microsoft.com/exchange/services/2006/messages",
}

_ENVELOPE = """<?xml version="1.0" encoding="utf-8"?>
<soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/"
               xmlns:t="http://schemas.microsoft.com/exchange/services/2006/types"
               xmlns:m="http://schemas.microsoft.com/exchange/services/2006/messages">
  <soap:Header>
    <t:RequestServerVersion Version="Exchange2013" />
  </soap:Header>
  <soap:Body>
    <m:CreateItem MessageDisposition="SendAndSaveCopy">
      <m:SavedItemFolderId>
        <t:DistinguishedFolderId Id="sentitems" />
      </m:SavedItemFolderId>
      <m:Items>
        <t:Message>
          <t:Subject>{subject}</t:Subject>
          <t:Body BodyType="Text">{body}</t:Body>
          <t:ToRecipients>{to}</t:ToRecipients>
        </t:Message>
      </m:Items>
    </m:CreateItem>
  </soap:Body>
</soap:Envelope>"""


def _xml_escape(text: str) -> str:
    return (
        text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    )


def build_ews_envelope(*, subject: str, body: str, to: list[str]) -> str:
    """组装 CreateItem/SendAndSaveCopy SOAP 信封（纯函数，便于离线自测）。"""
    mailboxes = "".join(
        f"<t:Mailbox><t:EmailAddress>{_xml_escape(addr)}</t:EmailAddress></t:Mailbox>"
        for addr in to
    )
    return _ENVELOPE.format(
        subject=_xml_escape(subject), body=_xml_escape(body), to=mailboxes
    )


def parse_ews_response(xml_text: str) -> str:
    """校验响应并返回 RootItemId；失败抛 RuntimeError（带响应码/原因）。"""
    root = ET.fromstring(xml_text)
    response = root.find(".//m:CreateItemResponseMessage", _NS)
    if response is None:
        raise RuntimeError("EWS 响应异常：缺少 CreateItemResponseMessage")
    if response.get("ResponseClass") != "Success":
        code = response.findtext("m:ResponseCode", default="?", namespaces=_NS)
        reason = response.findtext("m:MessageText", default="", namespaces=_NS)
        raise RuntimeError(f"EWS 发信失败: {code} {reason}"[:300])
    return response.findtext(".//t:RootItemId", default="", namespaces=_NS) or ""


def send_ews(
    cfg: MailConfig,
    *,
    subject: str,
    body: str,
    to: list[str] | None = None,
    html: str | None = None,  # noqa: ARG001 - EWS 文本正文，HTML 暂不支持
    attachments: list | None = None,
) -> str:
    """EWS 发信，返回 RootItemId。附件暂不支持（显式报错，不静默丢）。"""
    from apw.notify import oauth  # 惰性导入避免循环依赖

    if attachments:
        raise NotImplementedError("EWS 通道暂不支持附件（请用 smtp 通道）")
    recipients = list(to or cfg.to)
    if not recipients:
        raise ValueError("收件人为空：配置 smtp.to / APW_NOTIFY_TO / --to 至少其一")
    token = oauth.get_token(cfg, scope=EWS_SCOPE)
    envelope = build_ews_envelope(subject=subject, body=body, to=recipients)
    request = urllib.request.Request(
        cfg.ews_url or DEFAULT_EWS_URL,
        data=envelope.encode("utf-8"),
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "text/xml; charset=utf-8",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=cfg.timeout) as resp:
            xml_text = resp.read().decode("utf-8", "ignore")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "ignore")[:300]
        raise RuntimeError(f"EWS 调用失败 HTTP {exc.code}: {detail}") from exc
    return parse_ews_response(xml_text)
