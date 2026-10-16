"""Skills 广场页面对象（skill 下载/上传）。

由 skill_probe{,2,3} 探查产物生成（2026-09-29）。产品事实：
- 「Skill 套组」是默认页签（广场列表），「我的」页签带计数徽标；官方/社区是徽标图例非筛选控件；
- 排序标签 热度/最新/最近更新 有激活态（bg-white shadow）可作确定性断言；
- 上传表单 = .zip（必须含 SKILL.md）+ 名称* + 描述 + 可见性 radio（scope=private|public）。

硬红线（用例约定）：只允许上传 🔒私人（scope=private），🌐公共会污染公开库；
「设为公开」按钮绝不触碰。上传动作自带可见性核对，误选公共即判 fail 取证。
"""
from __future__ import annotations

import tempfile
import time
import zipfile
from pathlib import Path

from apw.pages.base import BasePage, EvidenceError


class SkillMarketPage(BasePage):
    page_name = "skill_market"

    # ---- 入口与页签 ----

    def open_plaza(self) -> dict:
        """从会话页进入 Skills 广场（侧边栏入口），等页签渲染完成。"""
        self.loc("nav_skill_plaza").click()
        deadline = time.time() + 10
        while self.count("tab_suites") == 0 and time.time() < deadline:
            time.sleep(0.4)
        if self.count("tab_suites") == 0:
            shot = self.snap("plaza-not-loaded")
            raise EvidenceError(
                "Skills 广场未进入［归因: run_stuck］页签未渲染（10s）\n"
                f"  复现: url={self.page.url}\n  冻结截图: {shot or '（未捕获）'}",
                {
                    "classification": "run_stuck",
                    "cause": "Skills 广场页签未渲染",
                    "repro": {"url": self.page.url},
                    "screenshots": [shot] if shot else [],
                },
            )
        return {"surface": "skill_plaza", "mine_count": self._mine_count(), "url": self.page.url}

    def open_tab(self, tab: str = "suites") -> dict:
        """切换页签：suites=Skill 套组（默认公开列表）/ mine=我的。"""
        mapping = {"suites": "tab_suites", "mine": "tab_mine"}
        if tab not in mapping:
            raise ValueError(f"未知页签 {tab!r}，可选 {sorted(mapping)}")
        self.loc(mapping[tab]).click()
        time.sleep(1.0)  # 页签切换后列表异步渲染
        return {"tab": tab, "mine_count": self._mine_count(), "cards": self.count("skill_card")}

    def _mine_count(self) -> str:
        try:
            return self.loc("tab_mine_count").first.inner_text(timeout=1500).strip()
        except Exception:  # noqa: BLE001 - 计数徽标仅作观察证据
            return ""

    def _card(self, name: str):
        return self.loc_all("skill_card").filter(has_text=name)

    # ---- 上传私人 skill ----

    @staticmethod
    def _build_zip(name: str, description: str) -> str:
        """生成最小 skill 包（上传要求 zip 必须包含 SKILL.md），落临时目录不入库。"""
        tmp = Path(tempfile.mkdtemp(prefix="apw-skill-"))
        zip_path = tmp / "apw-skill-case.zip"
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
            z.writestr("SKILL.md", f"# {name}\n\n{description}\n")
        return str(zip_path)

    def upload_private_skill(
        self, name: str, description: str, timeout_ms: int = 20_000
    ) -> dict:
        """上传私人 skill（硬红线：仅 scope=private）。

        生成最小 zip → 填名称/描述（受控输入真实键入）→ 核对可见性 🔒私人选中
        且 🌐公共未选 → 提交。成功信号=上传弹层关闭；未生效/可见性异常即
        EvidenceError 冻结取证（不自愈）。
        """
        self.loc("upload_entry").click()
        deadline = time.time() + 10
        while self.count("upload_modal") == 0 and time.time() < deadline:
            time.sleep(0.3)
        if self.count("upload_modal") == 0:
            shot = self.snap("upload-form-missing")
            raise EvidenceError(
                "上传表单未打开［归因: run_stuck］（10s）\n"
                f"  复现: url={self.page.url}\n  冻结截图: {shot or '（未捕获）'}",
                {
                    "classification": "run_stuck",
                    "cause": "上传 Skill 表单未弹出",
                    "repro": {"url": self.page.url},
                    "screenshots": [shot] if shot else [],
                },
            )
        zip_path = self._build_zip(name, description)
        self.loc("upload_file_input").set_input_files(zip_path)
        # 受控输入一律真实键入（已知产品行为：fill 不触发 onChange）
        self.loc("upload_name_input").first.click()
        self.page.keyboard.type(name, delay=25)
        self.loc("upload_desc_input").first.click()
        self.page.keyboard.type(description, delay=25)
        # ---- 可见性硬红线：private 选中且 public 未选 ----
        private = self.loc("scope_private_radio")
        if not private.is_checked():
            private.check()
        public = self.loc("scope_public_radio")
        scope = {
            "private_checked": private.is_checked(),
            "public_checked": public.is_checked(),
        }
        if not scope["private_checked"] or scope["public_checked"]:
            shot = self.snap("scope-guard")
            raise EvidenceError(
                f"可见性硬红线未过［归因: run_incomplete］{scope}：用例只允许上传私人 skill\n"
                f"  复现: 上传表单可见性核对 @ {self.page.url}\n  冻结截图: {shot or '（未捕获）'}",
                {
                    "classification": "run_incomplete",
                    "cause": "上传可见性非 private（禁止污染公开库）",
                    "scope": scope,
                    "repro": {"url": self.page.url},
                    "screenshots": [shot] if shot else [],
                },
            )
        self.loc("upload_submit").click()
        deadline = time.time() + timeout_ms / 1000
        while self.count("upload_modal") and time.time() < deadline:
            time.sleep(0.4)
        if self.count("upload_modal"):
            shot = self.snap("upload-not-applied")
            raise EvidenceError(
                f"上传未生效［归因: run_stuck］提交后 {timeout_ms}ms 表单未关闭\n"
                f"  复现: url={self.page.url}\n  冻结截图: {shot or '（未捕获）'}",
                {
                    "classification": "run_stuck",
                    "cause": "点击上传后表单未关闭（提交未生效或服务端拒绝）",
                    "repro": {"url": self.page.url, "name": name},
                    "screenshots": [shot] if shot else [],
                },
            )
        return {
            "uploaded_name": name,
            "scope": "private",
            "package": "apw-skill-case.zip（含 SKILL.md）",
            "url": self.page.url,
        }

    # ---- 回显 / 预览 / 公开库污染核对 ----

    def verify_mine_echo(self, name: str, description: str) -> dict:
        """上传回显核对：我的页签出现该 skill，名称/描述回显且带 🔒私人 徽标。"""
        self.open_tab("mine")
        card = self._card(name)
        deadline = time.time() + 10
        while card.count() == 0 and time.time() < deadline:
            time.sleep(0.5)
            card = self._card(name)
        body = card.first.inner_text() if card.count() else ""
        checks = {
            "name_echo": name in body,
            "desc_echo": description in body,
            "private_badge": "私人" in body,
        }
        evidence = {
            "mine_count": self._mine_count(),
            "card_excerpt": body[:160],
            **checks,
        }
        if not all(checks.values()):
            shot = self.snap("echo-mismatch")
            evidence["screenshots"] = [shot] if shot else []
            raise EvidenceError(
                f"上传回显缺失/不符［归因: run_incomplete］{checks}\n"
                f"  复现: 我的页签核对 {name!r} @ {self.page.url}\n"
                f"  冻结截图: {shot or '（未捕获）'}",
                evidence,
            )
        return evidence

    def verify_not_public(self, name: str) -> dict:
        """公开库不被污染核对：套组（公开）列表不得出现本用例的私人 skill。"""
        self.open_tab("suites")
        hits = self._card(name).count()
        evidence = {
            "name": name,
            "public_leak": hits > 0,
            "leak_hits": hits,
            "public_cards": self.count("skill_card"),
        }
        if hits:
            shot = self.snap("public-leak")
            evidence["screenshots"] = [shot] if shot else []
            raise EvidenceError(
                f"私人 skill 泄漏进公开列表［归因: run_incomplete］{name!r} 命中 {hits} 张公开卡\n"
                f"  复现: 套组页签核对 @ {self.page.url}\n  冻结截图: {shot or '（未捕获）'}",
                evidence,
            )
        return evidence

    def preview_skill(self, name: str, description: str = "") -> dict:
        """预览 skill：卡片「预览」→ 弹层出现且名称（与可选描述）回显。"""
        card = self._card(name)
        if not card.count():
            shot = self.snap("preview-card-missing")
            raise EvidenceError(
                f"预览未执行［归因: run_incomplete］未找到 skill 卡片 {name!r}\n"
                f"  复现: url={self.page.url}\n  冻结截图: {shot or '（未捕获）'}",
                {
                    "classification": "run_incomplete",
                    "cause": "目标 skill 卡片不存在",
                    "repro": {"url": self.page.url, "name": name},
                    "screenshots": [shot] if shot else [],
                },
            )
        card.first.get_by_text("预览", exact=True).click()
        deadline = time.time() + 10
        while self.count("preview_modal") == 0 and time.time() < deadline:
            time.sleep(0.4)
        modal_text = (
            self.loc("preview_modal").first.inner_text() if self.count("preview_modal") else ""
        )
        checks = {
            "name_echo": name in modal_text,
            "desc_echo": (description in modal_text) if description else True,
        }
        evidence = {
            "preview_name": name,
            "modal_excerpt": modal_text[:200],
            "skill_md_in_list": "SKILL.md" in modal_text,
            **checks,
        }
        if self.count("preview_modal") == 0 or not all(checks.values()):
            shot = self.snap("preview-mismatch")
            evidence["screenshots"] = [shot] if shot else []
            raise EvidenceError(
                f"预览未正常回显［归因: run_incomplete］{checks}\n"
                f"  复现: 预览 {name!r} @ {self.page.url}\n  冻结截图: {shot or '（未捕获）'}",
                evidence,
            )
        return evidence

    def close_preview(self) -> dict:
        """关闭预览弹层：点头部 X 关闭键（Esc 不关闭是产品实现），等弹层消失。"""
        self.loc("preview_close_button").first.click()
        deadline = time.time() + 8
        while self.count("preview_modal") and time.time() < deadline:
            time.sleep(0.3)
        if self.count("preview_modal"):
            shot = self.snap("preview-not-closed")
            raise EvidenceError(
                "预览弹层未关闭［归因: run_stuck］点击 X 关闭键后 8s 弹层仍在\n"
                f"  复现: url={self.page.url}\n  冻结截图: {shot or '（未捕获）'}",
                {
                    "classification": "run_stuck",
                    "cause": "预览弹层关闭失败",
                    "repro": {"url": self.page.url},
                    "screenshots": [shot] if shot else [],
                },
            )
        return {"preview_closed": True, "closed_by": "x_button"}

    # ---- 筛选标签 / 下载 ----

    def check_sort(self, label: str) -> dict:
        """排序标签核对：激活态迁移到目标标签 + 列表非空（首卡名与卡数记证据）。"""
        self.loc("sort_bar").get_by_text(label, exact=True).click()
        time.sleep(1.2)  # 列表重排渲染
        active = ""
        try:
            active = self.loc("sort_chip_active").first.inner_text(timeout=2000).strip()
        except Exception:  # noqa: BLE001 - 未取到按失败处理
            active = ""
        cards = self.count("skill_card")
        first_card = ""
        if cards:
            try:
                first_card = (
                    self.loc("skill_card").first.inner_text(timeout=1500).splitlines()[0][:40]
                )
            except Exception:  # noqa: BLE001 - 观察字段
                first_card = ""
        evidence = {
            "sort": label,
            "active_chip": active,
            "cards": cards,
            "first_card": first_card,
        }
        if active != label or cards == 0:
            shot = self.snap("sort-mismatch")
            evidence["screenshots"] = [shot] if shot else []
            raise EvidenceError(
                f"排序标签未生效［归因: run_incomplete］"
                f"期望激活 {label!r}，实际 {active!r}，cards={cards}\n"
                f"  复现: 排序切换 @ {self.page.url}\n  冻结截图: {shot or '（未捕获）'}",
                evidence,
            )
        return evidence

    def download_skill(self, name: str = "", max_attempts: int = 3) -> dict:
        """广场下载 skill：成功信号 = GET /api/skills/<id>/download 返回 2xx + 包字节数。

        产品事实（2026-09-29 探查）：下载为 JS 存盘，无浏览器下载事件、无 UI 反馈；
        个别 skill 包缺失会 404 且界面静默失败。故无 name 时逐卡尝试（最多 max_attempts
        张）取一次成功，每次尝试（含点击异常与状态码）都进证据（404 留痕不掩盖）；
        全部失败即 EvidenceError（run_stuck）冻结取证。
        """
        self.open_tab("suites")
        events: list = []

        def _on_response(response) -> None:
            if "/api/skills/" in response.url and response.url.endswith("/download"):
                events.append(response)

        self.page.on("response", _on_response)
        try:
            indexes = [0] if name else list(
                range(min(max_attempts, self.count("skill_card")))
            )
            attempts: list[dict] = []
            for idx in indexes:
                target = self._card(name).first if name else self.loc_all("skill_card").nth(idx)
                before = len(events)
                click_error = ""
                try:
                    target.get_by_text("下载", exact=True).first.click(timeout=8000)
                except Exception as exc:  # noqa: BLE001 - 点击异常如实进证据
                    click_error = f"{type(exc).__name__}: {str(exc)[:120]}"
                deadline = time.time() + 12
                while len(events) == before and time.time() < deadline:
                    time.sleep(0.3)
                status, size = 0, 0
                if len(events) > before:
                    response = events[-1]
                    status = response.status
                    try:
                        size = len(response.body())
                    except Exception:  # noqa: BLE001 - 响应体已消费仅记状态
                        size = 0
                attempts.append(
                    {"card_index": idx, "status": status, "bytes": size, "click_error": click_error}
                )
                if 200 <= status < 300:
                    return {"downloaded_ok": True, "attempts": attempts, "url": self.page.url}
        finally:
            try:
                self.page.remove_listener("response", _on_response)
            except Exception:  # noqa: BLE001 - 监听清理尽力而为
                pass
        shot = self.snap("download-no-signal")
        evidence = {
            "downloaded_ok": False,
            "attempts": attempts,
            "url": self.page.url,
            "screenshots": [shot] if shot else [],
        }
        raise EvidenceError(
            f"下载未见成功信号［归因: run_stuck］{len(attempts)} 次尝试无一 2xx：{attempts}\n"
            f"  复现: 广场下载 @ {self.page.url}\n  冻结截图: {shot or '（未捕获）'}",
            evidence,
        )
