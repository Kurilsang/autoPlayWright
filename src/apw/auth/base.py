"""认证提供者：向 BrowserContext 注入登录态。

T01 spike 落地前，storage_state 方案为留空占位；本地夹具站点用 NoAuth。
"""
from __future__ import annotations

from typing import Protocol

from apw.config import AuthConfig


class AuthProvider(Protocol):
    def context_kwargs(self) -> dict:
        """合并进 browser.new_context(**kwargs) 的登录态参数。"""
        ...


class NoAuth:
    """无需登录（本地夹具站点、免登录测试环境）。"""

    def context_kwargs(self) -> dict:
        return {}


class StorageStateAuth:
    """基于 storage_state 的会话复用。

    登录方案（SSO 处理、state_file 产出方式）待 T01 spike，当前留空。
    """

    def __init__(self, state_file: str) -> None:
        self.state_file = state_file

    def context_kwargs(self) -> dict:
        if not self.state_file:
            raise NotImplementedError(
                "登录方案留空：storage_state 的 state_file 未配置（待 T01 spike 落地）"
            )
        return {"storage_state": self.state_file}


def build_auth(cfg: AuthConfig) -> AuthProvider:
    if cfg.type == "none":
        return NoAuth()
    if cfg.type == "storage_state":
        return StorageStateAuth(cfg.state_file)
    raise ValueError(f"未知认证类型: {cfg.type}")
