"""专家套组广场页面对象（套组新建/预览）。

由 suite_probe{,2,3,4} 探查产物生成（2026-09-29）。产品事实：
- 新建入口两个：广场右上角 header「新建套组」/ 我的套组页尾虚线「新建套组」卡；
- 入口后先选模式：「⚡ 简易模式」（用户口径=普通模式）/「🔬 进阶模式」，两模式共用同一表单壳；
- 表单分区：基本信息 / 智能体配置 / 发布设置；可见范围 radio scope=private|public
  （🔒私人空间 默认选中 / 🌐公共套组广场 需管理员审核）；
- 套组卡片单击=预览（详情面板：名称 + Agent 配置 + ✦应用此套组/⏳发起长任务），双击=套用。

硬红线（用例约定）：只允许 🔒私人（scope=private），🌐公共与「应用此套组」绝不触碰；
卡片只单击不双击。创建动作自带可见性核对，误选公共即判 fail 取证。
"""
from __future__ import annotations

import time
from datetime import datetime

from apw.pages.base import BasePage, EvidenceError


def _ascii_name(text: str) -> str:
    """英文字段填充（双语字段为静默必填）：取 ASCII 部分，缺省给固定兜底（确定性）。"""
    ascii_part = "".join(ch for ch in text if ch.isascii() and ch.strip())
    return " ".join(ascii_part.split())[:60] or "apw-suite-en"


class SuitePlazaPage(BasePage):
    page_name = "suite_plaza"

    # ---- 入口与页签 ----

    def open_plaza(self) -> dict:
        """从会话页进入专家套组广场（侧边栏入口），等页签渲染完成。"""
        self.loc("nav_suite_plaza").click()
        deadline = time.time() + 10
        while self.count("tab_plaza") == 0 and time.time() < deadline:
            time.sleep(0.4)
        if self.count("tab_plaza") == 0:
            shot = self.snap("suite-plaza-not-loaded")
            raise EvidenceError(
                "专家套组广场未进入［归因: run_stuck］页签未渲染（10s）\n"
                f"  复现: url={self.page.url}\n  冻结截图: {shot or '（未捕获）'}",
                {
                    "classification": "run_stuck",
                    "cause": "专家套组广场页签未渲染",
                    "repro": {"url": self.page.url},
                    "screenshots": [shot] if shot else [],
                },
            )
        return {
            "surface": "suite_plaza",
            "mine_count": self._mine_count(),
            "url": self.page.url,
        }

    def open_tab(self, tab: str = "plaza") -> dict:
        """切换页签：plaza=套组广场 / mine=我的套组。"""
        mapping = {"plaza": "tab_plaza", "mine": "tab_mine"}
        if tab not in mapping:
            raise ValueError(f"未知页签 {tab!r}，可选 {sorted(mapping)}")
        self.loc(mapping[tab]).click()
        time.sleep(1.0)  # 页签切换后列表异步渲染
        return {"tab": tab, "mine_count": self._mine_count(), "cards": self.count("suite_card")}

    def _mine_count(self) -> str:
        try:
            return self.loc("tab_mine_count").first.inner_text(timeout=1500).strip()
        except Exception:  # noqa: BLE001 - 计数徽标仅作观察证据
            return ""

    def _card(self, name: str):
        return self.loc_all("suite_card").filter(has_text=name)

    # ---- 新建套组（2 入口 × 2 模式）----

    def create_suite(
        self,
        name: str,
        description: str,
        mode: str = "simple",
        entry: str = "plaza",
        timeout_ms: int = 20_000,
        unique: bool = False,
    ) -> dict:
        """新建套组（2x2：entry=plaza|mine × mode=simple|advanced），仅私有。

        流程：入口 → 模式选择卡 → 表单填名称/描述（受控输入真实键入）→
        发布设置核对可见性 🔒私人选中且 🌐公共未选（硬红线）→ 创建套组。
        成功信号=新建表单消失；未生效/可见性异常即 EvidenceError 冻结取证。

        unique=True 时名称追加时间戳（防重复名歧义），并把创建名写入 flow_state
        供跨步骤锚定（如操练场「从套组加载」按名绑定刚创建的套组）。
        """
        if mode not in ("simple", "advanced"):
            raise ValueError(f"未知模式 {mode!r}，可选 simple|advanced")
        if entry not in ("plaza", "mine"):
            raise ValueError(f"未知入口 {entry!r}，可选 plaza|mine")
        if unique:
            name = f"{name}-{datetime.now().strftime('%m%d%H%M%S')}"

        self.open_tab("plaza" if entry == "plaza" else "mine")
        self.loc("create_entry_plaza" if entry == "plaza" else "create_entry_mine").click()
        # 模式选择卡（用户口径：普通模式=简易模式）
        mode_key = "mode_simple" if mode == "simple" else "mode_advanced"
        deadline = time.time() + 10
        while self.count(mode_key) == 0 and time.time() < deadline:
            time.sleep(0.3)
        if self.count(mode_key) == 0:
            shot = self.snap("mode-chooser-missing")
            raise EvidenceError(
                f"模式选择未出现［归因: run_stuck］入口={entry} 找不到模式卡（10s）\n"
                f"  复现: url={self.page.url}\n  冻结截图: {shot or '（未捕获）'}",
                {
                    "classification": "run_stuck",
                    "cause": "新建入口后模式选择卡未渲染",
                    "repro": {"url": self.page.url, "entry": entry, "mode": mode},
                    "screenshots": [shot] if shot else [],
                },
            )
        self.loc(mode_key).click()
        deadline = time.time() + 10
        while self.count("suite_form_title") == 0 and time.time() < deadline:
            time.sleep(0.3)
        if self.count("suite_form_title") == 0:
            shot = self.snap("suite-form-missing")
            raise EvidenceError(
                f"新建表单未打开［归因: run_stuck］模式={mode}（10s）\n"
                f"  复现: url={self.page.url}\n  冻结截图: {shot or '（未捕获）'}",
                {
                    "classification": "run_stuck",
                    "cause": "模式选择后新建表单未渲染",
                    "repro": {"url": self.page.url, "entry": entry, "mode": mode},
                    "screenshots": [shot] if shot else [],
                },
            )
        # 受控输入一律真实键入（已知产品行为）；双语 4 字段全填
        # （英文名/英文描述为静默必填，缺则提交 no-op 且无校验提示——2026-09-29 实测）
        self.loc("suite_name_input").first.click()
        self.page.keyboard.type(name, delay=25)
        self.loc("suite_en_name_input").first.click()
        self.page.keyboard.type(_ascii_name(name), delay=25)
        self.loc("suite_desc_input").first.click()
        self.page.keyboard.type(description, delay=25)
        self.loc("suite_en_desc_input").first.click()
        self.page.keyboard.type(_ascii_name(description), delay=25)
        # 摘要模式徽标核对（UI 使用正常的确定性信号）
        mode_badge = (
            self.count("summary_mode_simple" if mode == "simple" else "summary_mode_advanced")
            > 0
        )
        # ---- 可见性硬红线：发布设置 → 🔒私人选中且 🌐公共未选 ----
        self.loc("tab_publish").click()
        time.sleep(0.5)
        private = self.loc("scope_private_radio")
        if not private.is_checked():
            private.check()
        public = self.loc("scope_public_radio")
        scope = {
            "private_checked": private.is_checked(),
            "public_checked": public.is_checked(),
        }
        summary_private = self.count("summary_private_badge") > 0
        if not scope["private_checked"] or scope["public_checked"]:
            shot = self.snap("scope-guard")
            raise EvidenceError(
                f"可见性硬红线未过［归因: run_incomplete］{scope}：用例只允许私人套组\n"
                f"  复现: 新建表单可见性核对 @ {self.page.url}\n  冻结截图: {shot or '（未捕获）'}",
                {
                    "classification": "run_incomplete",
                    "cause": "套组可见性非 private（禁止进公共套组广场）",
                    "scope": scope,
                    "repro": {"url": self.page.url},
                    "screenshots": [shot] if shot else [],
                },
            )
        if not mode_badge:
            shot = self.snap("mode-badge-mismatch")
            raise EvidenceError(
                f"模式徽标不符［归因: run_incomplete］期望 {mode} 对应摘要徽标未在场\n"
                f"  复现: 新建表单模式核对 @ {self.page.url}\n  冻结截图: {shot or '（未捕获）'}",
                {
                    "classification": "run_incomplete",
                    "cause": "表单摘要模式徽标与所选模式不符（UI 状态异常）",
                    "mode": mode,
                    "repro": {"url": self.page.url},
                    "screenshots": [shot] if shot else [],
                },
            )
        # 切回「基本信息」再提交（实测可过：停留发布设置区提交会静默 no-op）
        self.loc("tab_basic").click()
        time.sleep(0.5)
        self.loc("submit_create").click()
        deadline = time.time() + timeout_ms / 1000
        while self.count("suite_form_title") and time.time() < deadline:
            time.sleep(0.4)
        if self.count("suite_form_title"):
            shot = self.snap("create-not-applied")
            raise EvidenceError(
                f"套组未创建［归因: run_stuck］提交后 {timeout_ms}ms 表单未关闭\n"
                f"  复现: url={self.page.url}\n  冻结截图: {shot or '（未捕获）'}",
                {
                    "classification": "run_stuck",
                    "cause": "点击创建套组后表单未关闭（提交未生效或服务端拒绝）",
                    "repro": {"url": self.page.url, "name": name, "mode": mode},
                    "screenshots": [shot] if shot else [],
                },
            )
        self.flow_state["suite_name"] = name  # 跨步骤锚：下游（如操练场）按名绑定本套组
        return {
            "created_name": name,
            "mode": mode,
            "entry": entry,
            "scope": "private",
            "mode_badge": mode_badge,
            "summary_private_badge": summary_private,
            "url": self.page.url,
        }

    # ---- 回显 / 公开泄漏 / 预览 ----

    def verify_mine_echo(self, name: str, description: str = "") -> dict:
        """创建回显核对：我的套组出现该卡（名称回显 + 私人徽标 + 可选描述）。"""
        self.open_tab("mine")
        card = self._card(name)
        deadline = time.time() + 10
        while card.count() == 0 and time.time() < deadline:
            time.sleep(0.5)
            card = self._card(name)
        body = card.first.inner_text() if card.count() else ""
        # 注：卡片渲染=名称+Agent 类型徽标，无隐私徽标
        # （隐私由 scope 守卫 + verify_not_public 硬保证）
        checks = {"name_echo": name in body}
        evidence = {
            "mine_count": self._mine_count(),
            "card_excerpt": body[:160],
            "private_badge_on_card": "私人" in body or "私有" in body,
            "desc_on_card": (description in body) if description else None,
            **checks,
        }
        if not all(checks.values()):
            shot = self.snap("echo-mismatch")
            evidence["screenshots"] = [shot] if shot else []
            raise EvidenceError(
                f"创建回显缺失/不符［归因: run_incomplete］{checks}\n"
                f"  复现: 我的套组核对 {name!r} @ {self.page.url}\n"
                f"  冻结截图: {shot or '（未捕获）'}",
                evidence,
            )
        return evidence

    def verify_not_public(self, name: str) -> dict:
        """公开库不被污染核对：套组广场公开列表不得出现本用例的私人套组。"""
        self.open_tab("plaza")
        hits = self._card(name).count()
        evidence = {
            "name": name,
            "public_leak": hits > 0,
            "leak_hits": hits,
            "public_cards": self.count("suite_card"),
        }
        if hits:
            shot = self.snap("public-leak")
            evidence["screenshots"] = [shot] if shot else []
            raise EvidenceError(
                f"私人套组泄漏进公开列表［归因: run_incomplete］{name!r} 命中 {hits} 张公开卡\n"
                f"  复现: 套组广场核对 @ {self.page.url}\n  冻结截图: {shot or '（未捕获）'}",
                evidence,
            )
        return evidence

    def preview_suite(self, name: str, description: str = "") -> dict:
        """单击卡片预览（绝不双击=套用）：详情面板出现且名称回显 + Agent 配置结构在场。"""
        self.open_tab("mine")
        face = self.loc_all("suite_card_face").filter(has_text=name)
        if not face.count():
            shot = self.snap("preview-card-missing")
            raise EvidenceError(
                f"预览未执行［归因: run_incomplete］未找到套组卡 {name!r}\n"
                f"  复现: url={self.page.url}\n  冻结截图: {shot or '（未捕获）'}",
                {
                    "classification": "run_incomplete",
                    "cause": "目标套组卡不存在",
                    "repro": {"url": self.page.url, "name": name},
                    "screenshots": [shot] if shot else [],
                },
            )
        face.first.click()  # 单击=预览；双击=套用，绝不用 dblclick
        deadline = time.time() + 10
        while self.count("detail_apply_button") == 0 and time.time() < deadline:
            time.sleep(0.4)
        # 模态内容渲染异步：轮询取终值（标题名称 + 模态壳整文含描述）
        panel, title = "", ""
        checks: dict = {}
        deadline = time.time() + 6
        while True:
            if self.count("detail_panel_root"):
                try:
                    panel = self.loc("detail_panel_root").first.inner_text(timeout=1500)
                except Exception:  # noqa: BLE001 - 模态文本仅作核对
                    panel = ""
            try:
                title = self.loc("detail_title").first.inner_text(timeout=1200)
            except Exception:  # noqa: BLE001 - 标题未就绪继续轮询
                title = ""
            checks = {
                "panel_open": self.count("detail_apply_button") > 0,
                "name_echo": name in title or name in panel,
                "desc_echo": (description in panel) if description else True,
            }
            if all(checks.values()) or time.time() >= deadline:
                break
            time.sleep(0.5)
        evidence = {
            "preview_name": name,
            "panel_title": title.strip()[:60],
            "panel_excerpt": panel[:200],
            "task_button": self.count("detail_task_button") > 0,  # 仅公开套组有（观察）
            "agent_config_section": self.count("detail_agent_config") > 0,
            **checks,
        }
        if not all(checks.values()):
            shot = self.snap("preview-mismatch")
            evidence["screenshots"] = [shot] if shot else []
            raise EvidenceError(
                f"预览未正常回显［归因: run_incomplete］{checks}\n"
                f"  复现: 单击预览 {name!r} @ {self.page.url}\n  冻结截图: {shot or '（未捕获）'}",
                evidence,
            )
        return evidence

    def close_preview(self) -> dict:
        """关闭预览模态（右上 X 按钮），等模态消失。"""
        self.loc("detail_close_button").first.click()
        deadline = time.time() + 8
        while self.count("detail_apply_button") and time.time() < deadline:
            time.sleep(0.3)
        if self.count("detail_apply_button"):
            shot = self.snap("preview-not-closed")
            raise EvidenceError(
                "预览面板未关闭［归因: run_stuck］点击关闭后 8s 面板仍在\n"
                f"  复现: url={self.page.url}\n  冻结截图: {shot or '（未捕获）'}",
                {
                    "classification": "run_stuck",
                    "cause": "预览详情面板关闭失败",
                    "repro": {"url": self.page.url},
                    "screenshots": [shot] if shot else [],
                },
            )
        return {"preview_closed": True}
