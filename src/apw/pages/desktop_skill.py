"""桌面客户端技能页 / 技能市场（Electron 打包 Web 界面，CDP attach 驱动）。

由 CDP 实测探查生成（2026-10-12，<product> 0.2.2）。产品事实：
- 侧栏「技能」进入技能页；页签「本地技能」（默认）/「技能市场」，激活态 .active；
- 市场：搜索框（按名称/描述过滤，实时收敛）+ 刷新 + 计数「技能市场 · N[ · 已安装 M]」+ 卡片列表；
- 卡片：名称 / 徽标（官方·已安装）/ 描述 / 元信息 + 「详情」「安装」；
  已安装卡片 = 徽标「已安装」+ 安装键 .is-installed 且 disabled（文案「已安装」）；
- 本地：计数「本地技能 · N」；无技能时空态「还没有安装任何技能」+「去技能市场看看」；
- 详情 = 右侧抽屉（标题 / 文件树 / 文件内容），关闭键是头部「返回」，**Esc 不关闭**。

硬红线（用例约定）：本地卡「上传到广场」= 公开提交审核，页面对象不提供该动作，
流程用例也绝不允许点击（仅留取证用定位器）。

失败即取证，不自愈。
"""
from __future__ import annotations

import re
import time

from apw.pages.base import BasePage


def _first_int(text: str) -> int:
    m = re.search(r"(\d+)", text or "")
    return int(m.group(1)) if m else -1


class DesktopSkillPage(BasePage):
    page_name = "desktop_skill"

    _TAB_LABELS = {"local": "本地技能", "market": "技能市场"}

    # ---- 内部读取 ----

    def _text(self, name: str, wait_ms: int = 2_000) -> str:
        """读取定位器文本；元素晚渲染时轮询等待（缺失/超时返回空串，仅作观察字段）。

        市场计数与本地计数均随数据异步渲染（计数先于/晚于卡片出现），故一律带等待轮询，
        避免「卡片已渲染但计数为空」的假不一致。
        """
        deadline = time.time() + wait_ms / 1000
        while True:
            try:
                text = self.loc(name).first.inner_text(timeout=800).strip()
                if text:
                    return text
            except Exception:  # noqa: BLE001 - 观察字段，缺失/超时返回空串
                pass
            if time.time() >= deadline:
                return ""
            self.settle(250)

    def _market_ready(self) -> bool:
        """市场列表就绪判据：计数文案「技能市场 · N」已渲染且非空。"""
        try:
            return bool(self.loc("market_count").first.inner_text(timeout=300).strip())
        except Exception:  # noqa: BLE001 - 未就绪即假，交给 wait_until 重试
            return False

    def _active_tab(self) -> str:
        return self._text("tab_active")

    def _names(self) -> list[str]:
        try:
            return [t.strip() for t in self.loc_all("card_name").all_inner_texts()]
        except Exception:  # noqa: BLE001 - 观察字段
            return []

    # ---- 入口 / 页签 ----

    def dismiss_drawer(self, timeout_ms: int = 6_000) -> dict:
        """前置清理：若详情抽屉仍在场（如上次运行中断遗留），点「返回」收起。

        这是**用例前置条件**而非失败自愈——抽屉在场会遮挡侧栏/卡片点击，导致后续步骤无法执行；
        本动作不掩盖本次运行内的任何失败（开关抽屉仍由 open_detail/close_detail 严格判定）。
        """
        if self.count("drawer_backdrop") == 0:
            return {"dismissed": False, "reason": "无遗留抽屉"}
        self.loc("drawer_back_button").click()
        closed = self.wait_until(
            lambda: self.count("drawer_backdrop") == 0,
            timeout_ms=timeout_ms,
            interval_ms=250,
        )
        return {"dismissed": True, "closed": closed}

    def open_panel(self, timeout_ms: int = 10_000) -> dict:
        """侧栏点「技能」进入技能页，等容器渲染。

        未出现即取证（侧栏导航链路异常）。
        """
        self.loc("nav_skill_button").click()
        if not self.wait_until(
            lambda: self.count("panel") > 0, timeout_ms=timeout_ms, interval_ms=250
        ):
            self.fail_evidence(
                "技能页未打开",
                classification="nav_failed",
                cause="点击侧栏「技能」后技能页容器 div.skills-panel 未渲染",
                repro={"observed": f"open_panel 后 {timeout_ms}ms 内 panel 计数为 0"},
                detail=f"点击侧栏「技能」后 {timeout_ms}ms 内未渲染 div.skills-panel",
                shot_name="skill-panel-missing",
            )
        return {"skill_panel": "open", "active_tab": self._active_tab()}

    def open_tab(self, tab: str, timeout_ms: int = 8_000) -> dict:
        """切换页签：local=本地技能 / market=技能市场。

        等待激活态迁移到目标页签且对应容器渲染完成；未生效即取证。
        """
        if tab not in self._TAB_LABELS:
            raise ValueError(f"未知页签 {tab!r}，可选 {sorted(self._TAB_LABELS)}")
        label = self._TAB_LABELS[tab]
        container = "local" if tab == "local" else "market"
        self.loc("tab_local" if tab == "local" else "tab_market").click()
        ok = self.wait_until(
            lambda: self._active_tab() == label
            and self.count(container) > 0
            and (tab != "market" or self._market_ready()),
            timeout_ms=timeout_ms,
            interval_ms=250,
        )
        if not ok:
            self.fail_evidence(
                f"页签切换未生效：{label}",
                classification="tab_switch_failed",
                cause=f"点击「{label}」后激活态未迁移或容器 {container} 未渲染",
                repro={
                    "expected_tab": label,
                    "observed_active_tab": self._active_tab(),
                    "container_count": self.count(container),
                },
                detail=f"点击「{label}」后 {timeout_ms}ms 内未完成切换",
                shot_name="tab-switch-failed",
            )
        return {"tab": tab, "active_tab": label}

    # ---- 市场快照 / 搜索 ----

    def market_snapshot(self) -> dict:
        """市场页签当前状态：计数文案/总数/卡片数/卡片名/首卡。

        卡片数与计数文案里的总数不一致即取证（列表渲染不完整）。
        """
        count_text = self._text("market_count", wait_ms=3_000)
        names = self._names()
        total = _first_int(count_text)
        evidence = {
            "count_text": count_text,
            "total": total,
            "cards": len(names),
            "installed": self.count("card_action_installed"),
            "first_card": names[0] if names else "",
            "names": names[:8],
        }
        if total <= 0 or len(names) == 0 or len(names) != total:
            self.fail_evidence(
                "技能市场列表渲染不一致",
                classification="market_render_mismatch",
                cause="计数文案缺失，或计数总数与已渲染卡片数不一致（或列表为空）",
                repro={"count_text": count_text, "cards": len(names)},
                detail=f"计数 {count_text!r} 解析总数 {total}，实际渲染 {len(names)} 张卡片",
                extra={"names": names[:8]},
                shot_name="market-render-mismatch",
            )
        # 记基线：供 filter_by_first_card / restore_search 做前后对照（同流程共享）
        self.flow_state["desktop_skill.market_count_text"] = count_text
        self.flow_state["desktop_skill.market_total"] = total
        return evidence

    def filter_by_first_card(self, timeout_ms: int = 10_000) -> dict:
        """按首卡名搜索，核对列表收敛且目标卡片仍在（自包含，不依赖固定技能名）。

        判据：结果含被搜索的卡名；总数严格小于过滤前（市场仅 1 条时退化为相等）。
        """
        names = self._names()
        if not names:
            self.fail_evidence(
                "无卡片可搜索",
                classification="card_missing",
                cause="市场列表无卡片，无法取首卡名做过滤",
                repro={"observed": "market_snapshot 后 card_name 为空"},
                detail="技能市场卡片列表为空",
                shot_name="no-card-to-filter",
            )
        keyword = names[0]
        before = int(
            self.flow_state.get(
                "desktop_skill.market_total", _first_int(self._text("market_count"))
            )
        )
        res = self.set_search(keyword, timeout_ms=timeout_ms)
        checks = {
            "keyword_present": keyword in res["names"],
            "converged": (res["total"] < before) if before > 1 else (res["total"] == before),
        }
        if not all(checks.values()):
            self.fail_evidence(
                "搜索过滤结果不符",
                classification="search_filter_mismatch",
                cause="按首卡名搜索后目标卡片缺失，或列表未收敛",
                repro={
                    "keyword": keyword,
                    "before_total": before,
                    "after_total": res["total"],
                    "after_names": res["names"],
                },
                detail=f"搜索 {keyword!r} 后应仅保留相关卡片且总数收敛",
                extra={"checks": checks},
                shot_name="search-filter-mismatch",
            )
        return {
            "keyword": keyword,
            "before_total": before,
            "after_total": res["total"],
            "checks": checks,
        }

    def restore_search(self, timeout_ms: int = 10_000) -> dict:
        """清空搜索框，核对市场列表复原到过滤前的计数文案（基线取自 flow_state）。"""
        expect = str(self.flow_state.get("desktop_skill.market_count_text", ""))
        if not expect:
            expect = self._text("market_count")
        return self.clear_search(expect, timeout_ms=timeout_ms)

    def set_search(self, keyword: str, timeout_ms: int = 10_000) -> dict:
        """在搜索框键入关键词，等计数文案变化（= 列表已按关键词收敛）。

        计数未变化即取证（搜索过滤未生效）。
        """
        before = self._text("market_count")
        box = self.loc("market_search_input")
        box.click()
        box.fill("")
        box.type(keyword, delay=60)
        ok = self.wait_until(
            lambda: self._text("market_count") not in ("", before),
            timeout_ms=timeout_ms,
            interval_ms=300,
        )
        if not ok:
            self.fail_evidence(
                "搜索过滤未生效",
                classification="search_no_effect",
                cause="键入关键词后市场计数文案未变化（列表未收敛）",
                repro={
                    "keyword": keyword,
                    "count_before": before,
                    "count_now": self._text("market_count"),
                },
                detail=f"关键词 {keyword!r} 键入后 {timeout_ms}ms 内 market_count 未变化",
                shot_name="search-no-effect",
            )
        count_text = self._text("market_count")
        return {
            "keyword": keyword,
            "count_text": count_text,
            "total": _first_int(count_text),
            "names": self._names()[:8],
        }

    def clear_search(self, expect_count_text: str, timeout_ms: int = 10_000) -> dict:
        """清空搜索框，等计数文案恢复到期望值（= 列表复原）。

        未恢复即取证（过滤未撤销）。
        """
        box = self.loc("market_search_input")
        box.click()
        box.fill("")
        ok = self.wait_until(
            lambda: self._text("market_count") == expect_count_text,
            timeout_ms=timeout_ms,
            interval_ms=300,
        )
        if not ok:
            self.fail_evidence(
                "清空搜索后列表未复原",
                classification="search_clear_failed",
                cause="清空关键词后计数文案未回到清空前的值",
                repro={"expect": expect_count_text, "observed": self._text("market_count")},
                detail=f"清空搜索框后 {timeout_ms}ms 内计数文案未恢复为 {expect_count_text!r}",
                shot_name="search-clear-failed",
            )
        return {"count_text": self._text("market_count"), "cards": self.count("skill_card")}

    # ---- 详情抽屉 ----

    def open_detail(self, index: int = 0, timeout_ms: int = 12_000) -> dict:
        """点第 index 张卡片的「详情」，等抽屉出现并回显标题与文件树。

        抽屉未出现 / 标题不回显 / 文件树为空（三者任一）即取证。
        """
        cards = self.count("skill_card")
        if cards <= index:
            self.fail_evidence(
                "无可查看详情的卡片",
                classification="card_missing",
                cause=f"卡片数 {cards} 不足，无法取第 {index} 张",
                repro={"cards": cards, "index": index},
                detail="市场列表卡片数不足",
                shot_name="no-card-for-detail",
            )
        expect_name = self._names()[index] if index < len(self._names()) else ""
        self.loc_all("card_action_detail").nth(index).click()
        # 抽屉与文件树均为异步渲染：等「抽屉在场 + 标题回显 + 文件树非空」三者齐备
        ok = self.wait_until(
            lambda: self.count("drawer") > 0 and self.count("drawer_file_item") > 0,
            timeout_ms=timeout_ms,
            interval_ms=300,
        )
        title = self._text("drawer_title", wait_ms=1_500)
        files = self.count("drawer_file_item")
        if not ok or not title or files == 0:
            self.fail_evidence(
                "详情抽屉未正常打开",
                classification="detail_drawer_failed",
                cause="点击「详情」后抽屉未出现 / 标题未回显 / 文件树为空",
                repro={
                    "expect_name": expect_name,
                    "drawer_title": title,
                    "file_items": files,
                },
                detail=f"点击第 {index} 张卡「详情」后 {timeout_ms}ms 内抽屉未就绪",
                shot_name="detail-drawer-failed",
            )
        return {
            "index": index,
            "card_name": expect_name,
            "drawer_title": title,
            "file_items": files,
        }

    def close_detail(self, timeout_ms: int = 8_000) -> dict:
        """点抽屉头部「返回」关闭，等遮罩消失（Esc 不关闭是产品实现）。

        未关闭即取证。
        """
        self.loc("drawer_back_button").click()
        if not self.wait_until(
            lambda: self.count("drawer_backdrop") == 0,
            timeout_ms=timeout_ms,
            interval_ms=250,
        ):
            self.fail_evidence(
                "详情抽屉未关闭",
                classification="detail_close_failed",
                cause="点击「返回」后抽屉遮罩仍在场",
                repro={"observed": f"close_detail 后 {timeout_ms}ms 内 drawer_backdrop 仍在"},
                detail=f"点击抽屉「返回」后 {timeout_ms}ms 内 div.skills-drawer-backdrop 未消失",
                shot_name="detail-close-failed",
            )
        return {"drawer_closed": True, "closed_by": "back_button"}

    # ---- 安装（幂等）----

    def ensure_installed(self, index: int = 0, timeout_ms: int = 20_000) -> dict:
        """确保第 index 张卡片已安装（幂等）：已安装则跳过，未安装则点击并等状态落定。

        安装落定判据 = 该卡片安装键获得 .is-installed（disabled + 文案「已安装」），
        且市场计数文案出现「已安装 N」。
        """
        before_installed = self.count("card_action_installed")
        btn = self.loc_all("card_action_install").nth(index)
        text = btn.inner_text(timeout=2000).strip()
        if btn.is_disabled() or "已安装" in text:
            return {"newly_installed": False, "already_installed": True, "button_text": text}
        btn.click()
        ok = self.wait_until(
            lambda: self.count("card_action_installed") == before_installed + 1,
            timeout_ms=timeout_ms,
            interval_ms=400,
        )
        if not ok:
            self.fail_evidence(
                "技能安装未落定",
                classification="install_not_applied",
                cause="点击「安装」后卡片未进入已安装态（.is-installed）",
                repro={
                    "index": index,
                    "installed_before": before_installed,
                    "installed_now": self.count("card_action_installed"),
                    "count_text": self._text("market_count"),
                },
                detail=f"点击第 {index} 张卡「安装」后 {timeout_ms}ms 内未出现安装完成态",
                shot_name="install-not-applied",
            )
        return {
            "newly_installed": True,
            "already_installed": False,
            "installed_total": self.count("card_action_installed"),
            "count_text": self._text("market_count"),
        }

    # ---- 本地技能快照 ----

    def local_snapshot(self) -> dict:
        """本地技能页签状态：计数文案/数量/卡片名/是否空态。

        空态（还没有安装任何技能）下产品不渲染计数元素——此时计数按 0 记，不算缺失。
        """
        empty = self.count("local_empty_title") > 0
        count_text = "" if empty else self._text("local_count", wait_ms=2_000)
        names = self._names()
        evidence = {
            "count_text": count_text,
            "total": 0 if empty else _first_int(count_text),
            "cards": len(names),
            "names": names[:8],
            "empty": empty,
            "empty_title": self._text("local_empty_title", wait_ms=0),
        }
        self.flow_state["desktop_skill.local_total"] = evidence["total"]
        return evidence
