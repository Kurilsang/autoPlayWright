"""环境与驱动配置：configs/envs/<env>.yaml → EnvConfig。"""
from __future__ import annotations

from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field


class AuthConfig(BaseModel):
    """认证配置。

    - none: 无登录（本地夹具站点）
    - storage_state: 直接复用已有 storage_state 文件
    - form: 账号密码表单登录（T01）。凭据解析顺序：
      显式配置（不推荐入库）→ 环境变量 APW_USERNAME/APW_PASSWORD → secrets_file
    """

    type: Literal["none", "storage_state", "form"] = "none"
    state_file: str = ""  # storage_state 路径；form 模式下登录成功后回写复用
    # ---- form 专属 ----
    login_url: str = ""
    login_path_hint: str = "/login"  # URL 含此片段视为未登录
    username_selector: str = "#username"
    password_selector: str = "#password"
    submit_selector: str = 'button[type="submit"]'
    username: str = ""
    password: str = ""
    secrets_file: str = ""


class ElectronConfig(BaseModel):
    """Electron 连接配置。T03 落地，当前留空。"""

    executable_path: str = ""
    cdp_endpoint: str = ""
    args: list[str] = Field(default_factory=list)


class DriverConfig(BaseModel):
    mode: Literal["web", "electron"] = "web"
    channel: str = ""  # 例如 "msedge" 使用系统浏览器，空则用 Playwright 内置 chromium
    headless: bool = True
    electron: ElectronConfig = Field(default_factory=ElectronConfig)


class EnvConfig(BaseModel):
    name: str = "default"
    base_url: str = ""
    driver: DriverConfig = Field(default_factory=DriverConfig)
    auth: AuthConfig = Field(default_factory=AuthConfig)


def load_env(env: str, config_dir: str | Path = "configs/envs") -> EnvConfig:
    path = Path(config_dir) / f"{env}.yaml"
    if not path.exists():
        raise FileNotFoundError(f"环境配置不存在: {path}")
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return EnvConfig.model_validate({**data, "name": env})


def resolve_base_url(env: EnvConfig, root: str | Path = ".") -> str:
    """base_url 支持 http(s)://、file:// 与相对路径（本地夹具站点转 file URI）。"""
    url = env.base_url
    if url.startswith(("http://", "https://", "file://")):
        return url
    if not url:
        raise ValueError(f"环境 {env.name} 的 base_url 未配置")
    return (Path(root) / url).resolve().as_uri()
