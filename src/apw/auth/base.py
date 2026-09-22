"""认证提供者：向 BrowserContext 注入登录态。

三种方案：NoAuth（本地夹具）、StorageStateAuth（现成会话文件）、
FormAuth（账号密码表单登录 + storage_state 回写复用，T01）。
凭据解析顺序：显式配置 → 环境变量 APW_USERNAME/APW_PASSWORD → secrets_file。
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import TYPE_CHECKING

import yaml

from apw.config import AuthConfig

if TYPE_CHECKING:
    from playwright.sync_api import Page


class AuthProvider:
    """context_kwargs 合并进 new_context；ensure 在驱动启动后保证已登录。"""

    def context_kwargs(self) -> dict:
        return {}

    def ensure(self, page: Page, base_url: str) -> None:  # noqa: ARG002
        return None


class NoAuth(AuthProvider):
    """无需登录（本地夹具站点、免登录测试环境）。"""


class StorageStateAuth(AuthProvider):
    """基于已有 storage_state 文件的会话复用。"""

    def __init__(self, state_file: str) -> None:
        self.state_file = state_file

    def context_kwargs(self) -> dict:
        if not self.state_file:
            raise NotImplementedError(
                "storage_state 的 state_file 未配置（需要先提供会话文件）"
            )
        return {"storage_state": self.state_file}


class FormAuth(AuthProvider):
    """表单登录。首次登录成功后把 storage_state 回写 state_file 供后续复用。"""

    def __init__(self, cfg: AuthConfig) -> None:
        self.cfg = cfg
        self._credentials: tuple[str, str] | None = None

    # ---- 凭据 ----
    def _load_credentials(self) -> tuple[str, str]:
        if self._credentials:
            return self._credentials
        cfg = self.cfg
        sources: list[str] = []
        if cfg.username and cfg.password:
            self._credentials = (cfg.username, cfg.password)
            return self._credentials
        sources.append("显式配置")
        env_user, env_pwd = os.environ.get("APW_USERNAME"), os.environ.get("APW_PASSWORD")
        if env_user and env_pwd:
            self._credentials = (env_user, env_pwd)
            return self._credentials
        sources.append("环境变量 APW_USERNAME/APW_PASSWORD")
        if cfg.secrets_file:
            path = Path(cfg.secrets_file)
            if path.exists():
                data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
                if data.get("username") and data.get("password"):
                    self._credentials = (str(data["username"]), str(data["password"]))
                    return self._credentials
        sources.append(f"secrets_file={cfg.secrets_file or '未配置'}")
        raise RuntimeError(
            "form 登录缺少凭据，以下来源均未提供：\n  - " + "\n  - ".join(sources)
        )

    # ---- 登录流程 ----
    def context_kwargs(self) -> dict:
        state = self.cfg.state_file
        if state and Path(state).exists():
            return {"storage_state": state}
        return {}

    def ensure(self, page: Page, base_url: str) -> None:
        cfg = self.cfg
        page.goto(base_url, wait_until="load")
        page.wait_for_timeout(1500)  # SPA 路由守卫跳转需要时间
        if not self._on_login_page(page):
            return  # storage_state 复用成功
        self._login(page)
        if cfg.state_file:
            Path(cfg.state_file).parent.mkdir(parents=True, exist_ok=True)
            page.context.storage_state(path=cfg.state_file)

    def _on_login_page(self, page: Page) -> bool:
        if self.cfg.login_path_hint in page.url:
            return True
        return page.locator(self.cfg.username_selector).count() > 0

    def _login(self, page: Page) -> None:
        cfg = self.cfg
        username, password = self._load_credentials()
        page.goto(cfg.login_url, wait_until="load")
        page.locator(cfg.username_selector).first.wait_for(state="visible", timeout=15_000)
        page.fill(cfg.username_selector, username)
        page.fill(cfg.password_selector, password)
        page.click(cfg.submit_selector)
        page.wait_for_url(
            lambda url: cfg.login_path_hint not in url, timeout=30_000
        )
        page.wait_for_load_state("load")


def build_auth(cfg: AuthConfig) -> AuthProvider:
    if cfg.type == "none":
        return NoAuth()
    if cfg.type == "storage_state":
        return StorageStateAuth(cfg.state_file)
    if cfg.type == "form":
        return FormAuth(cfg)
    raise ValueError(f"未知认证类型: {cfg.type}")
