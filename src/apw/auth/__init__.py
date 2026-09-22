"""认证接缝：登录方案 T01 spike 前留空，仅提供可插拔接口与占位实现。"""
from apw.auth.base import AuthProvider, NoAuth, StorageStateAuth, build_auth

__all__ = ["AuthProvider", "NoAuth", "StorageStateAuth", "build_auth"]
