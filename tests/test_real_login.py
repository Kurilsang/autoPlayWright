"""T01 真实环境连通冒烟：自动登录并到达 Agent 会话页。

仅 --apw-env test 时执行（凭据就绪的前提下），其余环境跳过。
"""
from __future__ import annotations

import pytest


def test_login_reaches_chat_page(apw_env, apw_driver):
    if apw_env.name != "test":
        pytest.skip("真实环境冒烟仅 --apw-env test 执行")
    page = apw_driver.page
    assert "/login" not in page.url, f"仍在登录页: {page.url}"
    # 应用壳核心元素：新建对话入口（登录成功即渲染）
    assert page.get_by_text("新建对话").first.is_visible(), "会话页核心入口不可见"
