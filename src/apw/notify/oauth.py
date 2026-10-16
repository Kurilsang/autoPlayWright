"""OAuth2（设备码 + 刷新）：MFA 租户下 SMTP XOAUTH2 的令牌来源。

一次性交互登录（`python -m apw.notify --login`，浏览器/设备码 + MFA）换
refresh_token 落本地缓存（gitignored），之后静默刷新，发信免人工干预。
token 缓存=凭据，与 secrets 同口径：只存本地，绝不入库。
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from apw.notify.mail import MailConfig, repo_root

# 公共客户端 ID（非密钥；可换自注册应用或 IT 下发的 client_id）
DEFAULT_CLIENT_ID = "04b07795-8ddb-461a-bbee-02f9e1bf7b46"
DEFAULT_SCOPE = "offline_access https://outlook.office365.com/SMTP.Send"
_TOKEN_CACHE = "configs/.mail-token.local.json"
_OIDC_URL = "https://login.microsoftonline.com/{domain}/v2.0/.well-known/openid-configuration"
_DEVICE_CODE_URL = "https://login.microsoftonline.com/{tenant}/oauth2/v2.0/devicecode"
_TOKEN_URL = "https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token"


def discover_tenant(email_addr: str) -> str:
    """按邮箱域名发现租户 ID（OIDC 配置）；失败回退 common。"""
    domain = email_addr.rsplit("@", 1)[-1]
    try:
        with urllib.request.urlopen(_OIDC_URL.format(domain=domain), timeout=15) as resp:
            issuer = json.load(resp).get("issuer", "")
        parts = issuer.rstrip("/").split("/")
        tenant = parts[-2] if parts[-1] == "v2.0" else parts[-1]
        return tenant or "common"
    except (urllib.error.URLError, OSError, ValueError, KeyError):
        return "common"


def cache_path() -> Path:
    return repo_root() / _TOKEN_CACHE


def load_cached(username: str) -> dict | None:
    path = cache_path()
    if not path.exists():
        return None
    try:
        entries = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    return entries.get(username)


def save_cached(username: str, token: dict) -> None:
    path = cache_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    entries = {}
    if path.exists():
        try:
            entries = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            entries = {}
    entries[username] = token
    path.write_text(json.dumps(entries, ensure_ascii=False, indent=2), encoding="utf-8")
    try:
        path.chmod(0o600)
    except OSError:
        pass


def _post(url: str, payload: dict) -> tuple[int, dict]:
    data = urllib.parse.urlencode(payload).encode()
    request = urllib.request.Request(url, data=data)
    try:
        with urllib.request.urlopen(request, timeout=30) as resp:
            return resp.status, json.load(resp)
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read().decode("utf-8", "ignore") or "{}")


def device_code_login(
    cfg: MailConfig, *, client_id: str = "", scope: str = DEFAULT_SCOPE
) -> dict:
    """设备码登录（一次性交互）：打印验证地址+代码，轮询至登录完成。"""
    client_id = client_id or cfg.client_id or DEFAULT_CLIENT_ID
    username = cfg.username or cfg.from_addr
    tenant = discover_tenant(username)
    status, dc = _post(
        _DEVICE_CODE_URL.format(tenant=tenant),
        {"client_id": client_id, "scope": scope},
    )
    if status != 200:
        raise RuntimeError(
            f"设备码申请失败: {dc.get('error')} {dc.get('error_description', '')[:200]}"
        )
    print(f"[notify] 请在浏览器打开: {dc['verification_uri']}  输入代码: {dc['user_code']}")
    print(f"[notify] {dc.get('message', '')}")

    interval = int(dc.get("interval", 5))
    deadline = time.monotonic() + int(dc.get("expires_in", 900))
    while time.monotonic() < deadline:
        time.sleep(interval)
        status, token = _post(
            _TOKEN_URL.format(tenant=tenant),
            {
                "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
                "client_id": client_id,
                "device_code": dc["device_code"],
            },
        )
        if status == 200 and "refresh_token" in token:
            token["_obtained_at"] = int(time.time())
            token["_client_id"] = client_id
            token["_scope"] = scope
            save_cached(username, token)
            return token
        error = token.get("error", "")
        if error in ("authorization_pending", "slow_down"):
            if error == "slow_down":
                interval += 5
            continue
        raise RuntimeError(f"设备码登录失败: {error} {token.get('error_description', '')[:200]}")
    raise RuntimeError("设备码登录超时（请重跑 --login）")


def get_token(cfg: MailConfig, *, client_id: str = "", scope: str = "") -> str:
    """取可用 access_token：缓存有效直接用，过期用 refresh_token 静默续。

    scope 缺省沿用登录时的 scope（缓存 _scope），保证刷新不触发新的授权评估。
    """
    username = cfg.username or cfg.from_addr
    cached = load_cached(username)
    client_id = (
        client_id or cfg.client_id or (cached or {}).get("_client_id") or DEFAULT_CLIENT_ID
    )
    scope = scope or (cached or {}).get("_scope") or DEFAULT_SCOPE
    if not cached:
        raise RuntimeError("无 OAuth token 缓存，请先运行: python -m apw.notify --login")
    expires_at = int(
        cached.get("expires_at", cached.get("_obtained_at", 0) + int(cached.get("expires_in", 0)))
    )
    if expires_at > time.time() + 120:
        return cached["access_token"]

    tenant = discover_tenant(username)
    status, token = _post(
        _TOKEN_URL.format(tenant=tenant),
        {
            "grant_type": "refresh_token",
            "client_id": client_id,
            "refresh_token": cached.get("refresh_token", ""),
            "scope": scope,
        },
    )
    if status != 200 or "access_token" not in token:
        raise RuntimeError(
            f"token 刷新失败: {token.get('error')} {token.get('error_description', '')[:200]}；"
            "请重跑 python -m apw.notify --login"
        )
    token.setdefault("refresh_token", cached.get("refresh_token", ""))
    token["_obtained_at"] = int(time.time())
    save_cached(username, token)
    return token["access_token"]


def xoauth2_initial_response(username: str, access_token: str) -> str:
    """SMTP AUTH XOAUTH2 初始响应（base64）。"""
    raw = f"user={username}\x01auth=Bearer {access_token}\x01\x01".encode()
    return base64.b64encode(raw).decode("ascii")


# ---- 授权码流（PKCE + 本地回调）：设备码被条件访问封时的替代登录流 ----


def _pkce_pair() -> tuple[str, str]:
    verifier = base64.urlsafe_b64encode(os.urandom(48)).decode().rstrip("=")
    digest = hashlib.sha256(verifier.encode()).digest()
    challenge = base64.urlsafe_b64encode(digest).decode().rstrip("=")
    return verifier, challenge


def auth_code_login(
    cfg: MailConfig, *, client_id: str = "", scope: str = DEFAULT_SCOPE, port: int = 8400
) -> dict:
    """浏览器交互式登录（PKCE + localhost 回调）：MFA 在浏览器完成，本地收 code。"""
    client_id = client_id or cfg.client_id or DEFAULT_CLIENT_ID
    username = cfg.username or cfg.from_addr
    tenant = discover_tenant(username)
    verifier, challenge = _pkce_pair()
    state = base64.urlsafe_b64encode(os.urandom(16)).decode().rstrip("=")
    redirect_uri = f"http://localhost:{port}"
    authorize_url = (
        f"https://login.microsoftonline.com/{tenant}/oauth2/v2.0/authorize?"
        + urllib.parse.urlencode(
            {
                "client_id": client_id,
                "response_type": "code",
                "redirect_uri": redirect_uri,
                "response_mode": "query",
                "scope": scope,
                "code_challenge": challenge,
                "code_challenge_method": "S256",
                "state": state,
            }
        )
    )

    result: dict = {}
    done = threading.Event()

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802 - http.server 命名约定
            query = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            result.update({k: v[0] for k, v in query.items()})
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write("登录完成，可关闭此页回到终端。".encode())
            done.set()

        def log_message(self, *args) -> None:  # noqa: ARG002 - 静默访问日志
            pass

    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    server.timeout = 1
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        print(f"[notify] 请在浏览器完成登录（若未自动打开请手动访问）:\n{authorize_url}")
        webbrowser.open(authorize_url)
        if not done.wait(timeout=1800):
            raise RuntimeError("授权码登录超时（浏览器未完成回调）")
    finally:
        server.shutdown()
        thread.join(timeout=5)

    if result.get("error"):
        raise RuntimeError(
            f"授权码登录失败: {result['error']} {result.get('error_description', '')[:200]}"
        )
    if result.get("state") != state:
        raise RuntimeError("授权码登录失败: state 不匹配（回调被篡改或端口冲突）")

    status, token = _post(
        _TOKEN_URL.format(tenant=tenant),
        {
            "grant_type": "authorization_code",
            "client_id": client_id,
            "code": result["code"],
            "redirect_uri": redirect_uri,
            "code_verifier": verifier,
        },
    )
    if status != 200 or "refresh_token" not in token:
        raise RuntimeError(
            f"授权码换 token 失败: {token.get('error')} {token.get('error_description', '')[:200]}"
        )
    token["_obtained_at"] = int(time.time())
    token["_client_id"] = client_id
    token["_scope"] = scope
    save_cached(username, token)
    return token
