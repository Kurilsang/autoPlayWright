"""报告样式库页面对象（/templates 列表 + 预览弹层 + 做同款跳转后的工作流编辑器）。

由 report_style_probe{,2} 与 workspace 探查产物生成（2026-09-29）。产品事实：
- 入口 = 侧边栏「更多场景」→ 场景卡「报告样式库」；8 类 28 套样式，标签 pill 激活态 bg-gray-900，
  分组 h2 标题与标签文案严格一致（筛选生效的确定性锚）；
- 卡片「预览」与「做同款」打开同一预览弹层（头部：做同款/新标签打开/关闭 + 全页样式 iframe）；
- 弹层「做同款」= 一键复制官方示例工作流并跳转 /workflows/<uuid>（2026-09-29 实测为同页跳转，
  弹窗形态由本页对象注意力转移兜底——工作窗口记入 flow_state，后续步骤自动切过去）；
  副本名含「官方模板」与「(Fork)」，参数面板默认预填（jira_id 有默认测试单）；
- 运行面板 = 编辑参数 +「运行」+「工作流产物」（产物行标「· 产物」）+「运行日志」。

硬红线（用例约定）：
- 运行参数绝不填 recipients（留空 = 只生成报告不发邮件，改填即真实外发）；
- 不动「分享 / ⑂ Fork / 🔓锁定 / 用户视图」等无关控件；不做任何公开性变更。
"""
from __future__ import annotations

import time

from apw.pages.base import BasePage

_DISMISS_TEXTS = ("稍后再看", "我已熟悉", "关闭提示", "我已知晓")


def _norm(text: str) -> str:
    """归一化标识文本（丢掉中点/多余空白），跨文案差异比对变体标识。"""
    return " ".join(text.replace("·", " ").split())


def classify_run_failure(signals: dict) -> tuple[str, str]:
    """归因「运行未达成」：(分类, 说明)。"""
    if not signals.get("cancel_cleared", True):
        return "run_stuck", "「取消运行」持续在场：运行未结束（执行挂起或超长）"
    return "run_incomplete", "运行结束但完成信号未齐（无完成行/产物未落位/状态非 completed）"


class ReportStylePage(BasePage):
    page_name = "report_style"

    def __init__(self, *, page, repo) -> None:  # noqa: ANN001 - 与 BasePage 同型
        super().__init__(page=page, repo=repo)
        # 做同款可能弹出新窗口：工作窗口记入流程级状态，后续步骤注意力自动切换过去
        store = self.flow_state
        work = store.get("work_page")
        if work is not None and not work.is_closed():
            work._apw_flow_state = store  # 同一流程状态随工作窗口延续
            self.page = work

    # ---- 内部 ----
    def _card(self, variant: str, card_index: int = 0):
        cards = self.loc_all("style_card")
        if variant:
            hit = cards.filter(has_text=variant)
            if hit.count() == 0:
                self.fail_evidence(
                    "样式卡未找到",
                    classification="run_incomplete",
                    cause="目标样式卡不存在（筛选结果里没有该变体）",
                    repro={"url": self.page.url, "variant": variant},
                    detail=f"变体 {variant!r} 不在当前列表",
                    shot_name="card-missing",
                )
            return hit
        return cards.nth(card_index)

    def _title_value(self) -> str:
        try:
            return self.loc("wf_name_input").input_value(timeout=3_000)
        except Exception:  # noqa: BLE001 - 编辑器未就绪按空处理
            return ""

    def _dismiss_popups(self) -> None:
        """关闭工作流编辑器新手提示（幂等）。"""
        for _ in range(2):
            for label in _DISMISS_TEXTS:
                btn = self.page.get_by_text(label, exact=True)
                if btn.count():
                    try:
                        btn.first.click(timeout=1_500)
                        self.page.wait_for_timeout(300)
                        break
                    except Exception:  # noqa: BLE001 - 单个按钮失效尝试下一个
                        continue
            else:
                return

    def _artifact_names(self) -> list[str]:
        """产物行（标「· 产物」，中间文件不算最终结果）的文件名列表。"""
        rows = self.loc_all("artifact_row").filter(has_text="· 产物")
        names: list[str] = []
        for i in range(rows.count()):
            try:
                names.append(rows.nth(i).inner_text(timeout=1_500).splitlines()[0].strip())
            except Exception:  # noqa: BLE001 - 单行读取失败不影响整体判定
                continue
        return names

    def _log_length(self) -> int:
        try:
            return len(self.loc("run_log").inner_text(timeout=1_500))
        except Exception:  # noqa: BLE001 - 日志区缺席按 0（稳定性判据会兜住）
            return 0

    # ---- 列表页：进入 / 标签筛选 / 预览 ----

    def open_library(self, timeout_ms: int = 15_000) -> dict:
        """侧边栏「更多场景」→ 场景卡「报告样式库」进入列表页，等样式卡渲染。"""
        self.loc("nav_more_scenes").click()
        self.page.wait_for_timeout(600)
        self.loc("nav_report_style").click()
        self.wait_until(
            lambda: self.count("style_card") > 0, timeout_ms=timeout_ms, interval_ms=400
        )
        if self.count("style_card") == 0:
            self.fail_evidence(
                "报告样式库未进入",
                classification="run_stuck",
                cause="报告样式库列表未渲染",
                repro={"url": self.page.url},
                detail=f"样式卡未渲染（{timeout_ms}ms）",
                shot_name="library-not-loaded",
            )
        return {
            "surface": "report_style_library",
            "url": self.page.url,
            "cards": self.count("style_card"),
            "tags": [
                t.strip()
                for t in self.loc_all("tag_chip").all_inner_texts()
                if t.strip()
            ],
        }

    def switch_tag(self, label: str, timeout_ms: int = 8_000) -> dict:
        """标签切换筛选核对：激活态迁移到目标标签 + 只剩该类分组（确定性结构信号）。

        分组 h2 标题与标签文案严格一致（产品事实）：非「全部」时全部分组标题必须等于标签；
        「全部」时分组数 > 1。不符即 EvidenceError（run_incomplete）冻结取证。
        """
        chips = self.loc("tag_bar").get_by_text(label, exact=True)
        if chips.count() != 1:
            self.fail_evidence(
                "标签筛选未执行",
                classification="run_incomplete",
                cause="目标筛选标签不存在或有歧义",
                repro={"url": self.page.url, "label": label},
                detail=f"标签 {label!r} 命中 {chips.count()} 处",
                shot_name="tag-missing",
            )
        chips.first.click()
        active = ""

        def active_is_label() -> bool:
            nonlocal active
            try:
                active = self.loc("tag_chip_active").first.inner_text(timeout=1_000).strip()
            except Exception:  # noqa: BLE001 - 激活态读取失败继续等
                active = ""
            return active == label

        self.wait_until(active_is_label, timeout_ms=timeout_ms, interval_ms=300)
        sections = [
            t.strip() for t in self.loc_all("style_section_title").all_inner_texts() if t.strip()
        ]
        cards = self.count("style_card")
        if label == "全部":
            filtered_ok = len(sections) > 1
        else:
            filtered_ok = bool(sections) and all(s == label for s in sections)
        evidence = {
            "label": label,
            "active_chip": active,
            "sections": sections,
            "cards": cards,
        }
        if active != label or not filtered_ok or cards == 0:
            self.fail_evidence(
                "标签筛选未生效",
                classification="run_incomplete",
                cause="期望激活标签且分组收敛，实际不符",
                repro={"url": self.page.url, "observed": "标签切换"},
                detail=f"期望激活 {label!r}，实际 active={active!r} "
                f"sections={sections} cards={cards}",
                shot_name="tag-filter-mismatch",
                extra=evidence,
            )
        return evidence

    def open_preview(
        self, variant: str = "", card_index: int = 0, timeout_ms: int = 10_000
    ) -> dict:
        """卡片「预览」→ 预览弹层打开且头部回显变体标识（弹层含全页样式 iframe）。"""
        card = self._card(variant, card_index)
        card.first.get_by_text("预览", exact=True).first.click()
        self.wait_until(
            lambda: self.count("preview_modal") > 0, timeout_ms=timeout_ms, interval_ms=300
        )
        modal_text = (
            self.loc("preview_modal").first.inner_text(timeout=1_500)
            if self.count("preview_modal")
            else ""
        )
        header = modal_text.splitlines()[0].strip() if modal_text else ""
        try:
            iframe_title = self.loc("preview_iframe").first.get_attribute("title") or ""
        except Exception:  # noqa: BLE001 - 观察字段
            iframe_title = ""
        checks = {
            "modal_open": self.count("preview_modal") > 0,
            # 徽标「A · Editorial」与弹层头部「… · A Editorial」分隔符不同，归一化后比对
            "variant_echo": (
                _norm(variant) in _norm(header) if variant else True
            ),
            "iframe_in_modal": self.count("preview_iframe") > 0,
        }
        evidence = {
            "variant": variant,
            "modal_header": header,
            "iframe_title": iframe_title,
            **checks,
        }
        if not all(checks.values()):
            self.fail_evidence(
                "预览弹层未正常打开",
                classification="run_incomplete",
                cause="弹层/头部回显/iframe 核对未全过",
                repro={
                    "url": self.page.url,
                    "observed": f"预览 {variant or f'card[{card_index}]'}",
                },
                detail=f"checks={checks}",
                shot_name="preview-mismatch",
                extra=evidence,
            )
        return evidence

    def close_preview(self, timeout_ms: int = 8_000) -> dict:
        """关闭预览弹层（弹层头部「关闭」按钮），等弹层消失。"""
        self.loc("preview_close_button").first.click()
        self.wait_until(lambda: self.count("preview_modal") == 0, timeout_ms=timeout_ms)
        if self.count("preview_modal"):
            self.fail_evidence(
                "预览弹层未关闭",
                classification="run_stuck",
                cause="预览弹层关闭失败",
                repro={"url": self.page.url},
                detail="点击「关闭」后弹层仍在",
                shot_name="preview-not-closed",
            )
        return {"preview_closed": True, "closed_by": "close_button"}

    # ---- 做同款：复制官方示例工作流并跳转 ----

    def copy_template(
        self, variant: str = "", card_index: int = 0, timeout_ms: int = 20_000
    ) -> dict:
        """弹层「做同款」= 一键复制官方示例工作流并跳转 /workflows/<uuid>。

        跳转形态双兜底（产品实测同页跳转，弹窗形态亦接管）：新窗口记入 flow_state，
        后续步骤的页面对象自动把注意力切到工作窗口。跳转后校验编辑器就绪 + 副本名回显
        （含「官方模板」/「(Fork)」锚），不符即 identity_mismatch 冻结取证。
        """
        preview = self.open_preview(variant, card_index)
        popped: list = []
        self.page.context.on("page", lambda p: popped.append(p))
        self.loc("preview_copy_button").first.click()
        work, jump = self._wait_work_window(popped, timeout_ms)
        self.flow_state["work_page"] = work
        self.page = work  # 本动作后续操作也作用于工作窗口
        self._dismiss_popups()
        self.wait_until(lambda: self._title_value() != "", timeout_ms=10_000, interval_ms=400)
        name = self._title_value()
        url = self.page.url
        checks = {
            "jumped": "/workflows/" in url,
            "editor_ready": name != "",
            "template_anchor": ("官方模板" in name) or ("(Fork)" in name),
        }
        evidence = {
            "jump_mode": jump,
            "workflow_name": name,
            "work_url_path": url.split("?")[0].split("/", 3)[-1],
            "preview": preview,
            **checks,
        }
        if not all(checks.values()):
            category = "identity_mismatch" if checks["jumped"] else "run_stuck"
            self.fail_evidence(
                "做同款跳转未达成",
                classification=category,
                cause="跳转后编辑器/副本名校验未全过",
                repro={"url": url, "observed": "弹层做同款 → 编辑器"},
                detail=f"checks={checks}",
                shot_name="copy-jump-mismatch",
                extra=evidence,
            )
        return evidence

    def _wait_work_window(self, popped: list, timeout_ms: int):
        """等待跳转落点：弹窗形态取新页，同页形态等 URL 进 /workflows/。

        注意：轮询必须走 Playwright API（wait_for_timeout）泵事件循环——纯 time.sleep
        不派发事件，page.url 会停在跳转前的旧值（2026-09-29 实测踩坑）。
        """
        deadline = time.time() + timeout_ms / 1000
        while time.time() < deadline:
            if popped:
                work = popped[0]
                try:
                    work.wait_for_load_state("load", timeout=5_000)
                except Exception:  # noqa: BLE001 - 加载未完成也接管，后续就绪校验兜底
                    pass
                return work, "popup"
            self.settle(300)  # 泵事件，URL/弹窗事件才会推进
            if "/workflows/" in self.page.url:
                return self.page, "same_tab"
        self.fail_evidence(
            "做同款未跳转",
            classification="run_stuck",
            cause="「做同款」未产生跳转（无弹窗且同页未导航）",
            repro={"url": self.page.url},
            detail=f"{timeout_ms}ms 内无新窗口且 URL 未进工作流编辑器",
            shot_name="copy-no-jump",
        )

    # ---- 运行：AI 长任务，完成判定六信号 + 工作区最终结果 ----

    def run_workflow(self, timeout_ms: int = 300_000) -> dict:
        """运行官方示例副本（参数面板默认预填；硬红线：绝不填 recipients）。

        完成判定 = 六信号（全部确定性）：
        ① 取消运行消失 ② 日志「✅ 工作流完成」完成行 ③ 输出键行在场
        ④ 状态徽标 completed ⑤ 工作流产物落位（「· 产物」≥1 且占位清除）⑥ 日志文本稳定。
        未达成即判失败冻结现场（run_stuck / run_incomplete），绝不自愈重试。
        """
        try:
            self.loc("run_button").click(timeout=5_000)
        except Exception as exc:  # noqa: BLE001 - 运行未启动即取证
            self.fail_evidence(
                "运行未启动",
                classification="not_ready",
                cause="「运行」按钮不可用",
                repro={"url": self.page.url, "steps": "run_workflow"},
                shot_name="run-not-started",
                from_exc=exc,
            )
        watch = self.watch_signals(
            signals=lambda: {
                "cancel_cleared": self.count("cancel_run_button") == 0,
                "done_line": self.count("run_done_marker") > 0,
                "output_keys": self.count("run_output_keys_marker") > 0,
                "status_completed": self.count("run_status_badge") > 0,
                "artifacts_landed": (
                    self.count("artifacts_placeholder") == 0
                    and len(self._artifact_names()) > 0
                ),
            },
            size=self._log_length,
            timeout_ms=timeout_ms,
            size_field="log_len",
        )
        if watch.settled:  # ⑥ 日志稳定（watch 内已多信号收敛）
            return self._run_evidence(watch.signals, watch.timeline)
        self.fail_incomplete(
            "运行未达成",
            classify=classify_run_failure,
            watch=watch,
            steps="copy_template → run_workflow",
            observed=f"运行启动后 {timeout_ms}ms 内完成信号未达成",
            shot_name="run-timeout",
            extra=self._run_facts(),
        )

    def _run_facts(self) -> dict:
        """运行现场事实（日志尾/产物/名称/URL）：成功证据与失败取证共用。"""
        log_tail = ""
        try:
            log_tail = self.loc("run_log").inner_text(timeout=1_500)[-600:]
        except Exception:  # noqa: BLE001 - 证据尽力而为
            pass
        return {
            "log_tail": log_tail,
            "artifacts": self._artifact_names(),
            "workflow_name": self._title_value(),
            "url": self.page.url.split("?")[0],
        }

    def _run_evidence(self, signals: dict, timeline: list[dict]) -> dict:
        return {"run_signals": signals, "timeline": timeline[-5:], **self._run_facts()}

    def verify_artifacts(self, min_count: int = 1) -> dict:
        """工作区最终结果核对：「工作流产物」区「· 产物」行 ≥ min_count。

        产物缺失 = 最终结果未在工作区落位（run_incomplete），冻结取证。
        """
        artifacts = self._artifact_names()
        evidence = {
            "artifacts": artifacts,
            "placeholder_count": self.count("artifacts_placeholder"),
            "rows_total": self.count("artifact_row"),
        }
        if len(artifacts) < min_count:
            self.fail_evidence(
                "工作区最终结果缺失",
                classification="run_incomplete",
                cause="「· 产物」行不足，最终结果未在工作区落位",
                repro={"url": self.page.url, "observed": "verify_artifacts"},
                detail=f"「· 产物」行 {len(artifacts)} < {min_count}",
                shot_name="artifacts-missing",
                extra=evidence,
            )
        return evidence
