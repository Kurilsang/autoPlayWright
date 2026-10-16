"""桌面客户端搜索面板（Electron 打包的 Web 界面，CDP attach 驱动）。

由 CDP 实测探查生成（2026-10-12，<product> 0.2.2）。与 web 版无对应页面：
侧栏「搜索」打开右侧搜索面板，面板含关键词输入 + 四个过滤页签，
结果按会话分组（组头会话标题/路径 + 每条命中 角色/预览/时间）。
选中命中后打开该会话继续对话（继续对话由 desktop_chat 页动作承接）。

失败即取证，不自愈。
"""
from __future__ import annotations

from apw.pages.base import BasePage


class DesktopSearchPage(BasePage):
    page_name = "desktop_search"

    def open_panel(self, timeout_ms: int = 8_000) -> dict:
        """点侧栏「搜索」打开搜索面板，等输入框就位。

        面板未出现即取证（侧栏导航链路异常）。
        """
        self.loc("nav_search_button").click()
        if not self.wait_until(
            lambda: self.count("search_input") > 0,
            timeout_ms=timeout_ms,
            interval_ms=250,
        ):
            self.fail_evidence(
                "搜索面板未打开",
                classification="nav_failed",
                cause="点击侧栏「搜索」后搜索面板输入框未出现",
                repro={"observed": "open_panel 后 search_input 计数为 0"},
                detail=f"点击侧栏「搜索」后 {timeout_ms}ms 内未渲染 input.search-panel-input",
                shot_name="search-panel-missing",
            )
        return {"search_panel": "open"}

    def search(self, keyword: str, timeout_ms: int = 30_000) -> dict:
        """键入关键词并等结果分组出现。

        结果按会话分组渲染（div.search-result-group）；命中数 0 即判失败取证
        （断言要求「搜得到」，搜索链路失效时不留空转）。
        """
        box = self.loc("search_input")
        box.click()
        box.fill("")
        box.type(keyword, delay=60)
        settled = self.wait_until(
            lambda: self.count("result_group") > 0,
            timeout_ms=timeout_ms,
            interval_ms=400,
        )
        groups = self.count("result_group")
        if not settled:
            self.fail_evidence(
                "搜索无命中结果",
                classification="search_miss",
                cause="键入关键词后未渲染任何结果分组",
                repro={
                    "keyword": keyword,
                    "observed": f"search 后 {timeout_ms}ms 内 result_group 计数为 0",
                },
                detail=(
                    f"关键词 {keyword!r} 键入后 {timeout_ms}ms 内 "
                    "div.search-result-group 未出现"
                ),
                shot_name="search-no-hit",
            )
        return {
            "keyword": keyword,
            "result_groups": groups,
            "result_titles": [
                t.strip()
                for t in self.loc_all("result_conv_title").all_inner_texts()[:5]
            ],
        }

    def open_first_result(self, timeout_ms: int = 12_000) -> dict:
        """点首个结果组头打开该会话，等搜索面板收起（面板消失 = 已切入会话）。

        面板未收起即判失败取证（点击未生效或会话未加载）。
        """
        groups = self.count("result_group")
        if groups == 0:
            self.fail_evidence(
                "无结果可打开",
                classification="search_miss",
                cause="open_first_result 前置检查：结果分组为 0",
                repro={"observed": "open_first_result 前 result_group 计数为 0"},
                detail="搜索面板内无结果分组，无法打开会话",
                shot_name="no-result-to-open",
            )
        self.loc_all("result_conv").first.click()
        if not self.wait_until(
            lambda: self.count("panel") == 0,
            timeout_ms=timeout_ms,
            interval_ms=250,
        ):
            self.fail_evidence(
                "打开搜索结果未生效",
                classification="open_result_failed",
                cause="点击结果组头后搜索面板未收起（未切入会话）",
                repro={
                    "observed": f"open_first_result 后 {timeout_ms}ms 内 search-panel 仍在场"
                },
                detail=(
                    f"点击首个结果组头后 {timeout_ms}ms 内 div.search-panel 未消失，"
                    "无法确认已切入会话"
                ),
                shot_name="open-result-failed",
            )
        return {"opened_first_result": True, "result_groups_before": groups}
