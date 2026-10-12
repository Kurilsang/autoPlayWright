"""桌面客户端工作流面板（Electron 打包 Web 界面，CDP attach 驱动）。

由爬虫快照探查生成（2026-10-12，configs/crawl/desktop_workflow_probe{,2,3,4,5}.yaml）。
与 web 版 AmlWorkflowPage 语义对齐但结构不同：
- 工作流区是 view slot 栈（div.wf-view-slot）：列表为底座，详情/运行依次叠放，
  「← 返回」回上一槽（详情槽返回后保活、运行槽返回即销毁），同时仅一槽 is-active；
- 脚本编辑器 = CodeMirror（整体 insert_text 避免逐键自动缩进），保存后「保存」按钮
  转 disabled（干净态，探查事实）；流程结构节点保存后解析渲染；
- 运行 = 详情「运行」开运行视图（运行输入/历史运行）→ 再点「运行」执行；运行后台
  执行、视图切走不中断（卡片「进行中」+「最近运行：运行中」在场）——并行工作切换的载体；
- 身份锚点 = 详情标题 h3 / 运行视图标题 / 运行日志「工作流开始：<名>」行。
判定语义沉淀在此；失败即取证，不自愈。
"""
from __future__ import annotations

import time
from datetime import datetime

from apw.pages.base import BasePage, SignalWatch

# 非 AI 编码用例的固定脚本：最小 wf 契约（step/log/set_output），输出完全确定
MANUAL_SCRIPT = (
    "def main(wf):\n"
    '    with wf.step("n1", "打印 hello"):\n'
    '        wf.log("hello")\n'
    '        wf.set_output("greeting", "hello")\n'
)

# 结构采集 DOM 内省：活动 view slot 的身份/脚本/流程摘要/运行日志 + 后台运行卡片（证据，不断言）
_CAPTURE_JS = """
() => {
  const active = document.querySelector('div.wf-view-slot.is-active') || document.body;
  const titleEl = active.querySelector('div.wf-subheader-identity h3')
    || active.querySelector('h3.wf-subheader-title');
  const code = active.querySelector('section.wf-detail-script .cm-content');
  const summary = active.querySelector('span.wf-run-flow-summary');
  const logs = [...active.querySelectorAll('div.wf-log-body div.wf-log-line')]
    .map(el => (el.textContent || '').trim());
  const running = [...document.querySelectorAll('li.wf-card')]
    .filter(card => card.querySelector('span.wf-run-state.is-running, span.wf-badge-running'))
    .map(card => {
      const name = card.querySelector('span.wf-card-name');
      return name ? (name.textContent || '').trim() : '';
    });
  return {
    active_title: titleEl ? (titleEl.textContent || '').trim() : '',
    script: code ? (code.innerText || '') : '',
    flow_summary: summary ? (summary.textContent || '').trim() : '',
    run_log: logs.slice(-40).join('\\n'),
    cards_running: running,
  };
}
"""


def classify_run_failure(signals: dict) -> tuple[str, str]:
    """归因「运行未完成」：(分类, 说明)。"""
    if not signals.get("cancel_cleared", True):
        return "run_stuck", "「取消运行」持续在场：运行未结束（执行挂起或超长）"
    if not signals.get("run_status_present", True):
        return "run_no_record", "运行状态区缺失：运行记录未挂载（启动失败或记录丢失）"
    return "run_incomplete", "完成信号未达成（无「工作流完成」完成行或完成徽标，半截/失败结束）"


class DesktopWorkflowPage(BasePage):
    page_name = "desktop_workflow"

    # ---- 浮层 ----
    def dismiss_toasts(self) -> None:
        """关闭「服务连接异常」等常驻 toast（幂等：不存在时直接返回）。

        toast 是右下角浮层，会拦截下方按钮点击（2026-10-12 探查实测）；
        单个关闭失败不挡流程，后续点击判定兜底。
        """
        for _ in range(3):
            if self.count("toast_close") == 0:
                return
            try:
                self.loc("toast_close").click(timeout=2_000)
            except Exception:  # noqa: BLE001 - 关不掉由后续点击判定兜底
                return
            self.settle(300)

    # ---- 导航 ----
    def open_section(self) -> dict:
        """从侧边栏「工作流」进入工作流面板（列表为 view slot 栈底座）。"""
        self.dismiss_toasts()
        self.loc("nav_workflow").click()
        if not self.wait_until(
            lambda: self.count("new_workflow_button") > 0, timeout_ms=10_000
        ):
            self.fail_evidence(
                "工作流区未打开",
                classification="not_ready",
                cause="点击侧边栏「工作流」后列表未渲染",
                repro={"url": self.page.url, "steps": "open_section"},
                detail="「新建工作流」入口 10s 内未出现，页面原状冻结",
                shot_name="wf-section-not-open",
            )
        return {"workflow_section": "opened"}

    # ---- 视图栈 ----
    def _detail_title(self) -> str:
        try:
            return self.loc("detail_title").inner_text(timeout=1_500).strip()
        except Exception:  # noqa: BLE001 - 未就绪按空处理
            return ""

    def _active_text(self) -> str:
        """活动 view slot 的可见文本（身份核对采样；隐藏槽不计，防列表串扰）。"""
        try:
            return self.page.evaluate(
                "() => { const s = document.querySelector('div.wf-view-slot.is-active');"
                " return s ? (s.innerText || '') : ''; }"
            )
        except Exception:  # noqa: BLE001 - 采样失败按空处理
            return ""

    def back_to_list(self, max_pops: int = 4) -> dict:
        """逐槽「← 返回」弹回列表底座（运行槽销毁、详情槽保活）。

        未在 max_pops 次内回到列表即视图栈异常，冻结取证（不自愈）。
        """
        pops = 0
        while self.count("list_active") == 0 and pops < max_pops:
            self.loc("active_back_button").click()
            self.settle(600)
            pops += 1
        if self.count("list_active") == 0:
            self.fail_evidence(
                "未回到工作流列表",
                classification="not_ready",
                cause=f"连点 {pops} 次「← 返回」后列表槽仍未激活（视图栈异常）",
                repro={"url": self.page.url, "steps": "back_to_list"},
                detail=f"max_pops={max_pops}，活动槽非列表槽，页面原状冻结",
                shot_name="back-to-list-failed",
            )
        return {"back_pops": pops}

    def switch_workflow(
        self,
        name: str,
        expect_text: str = "",
        forbid_text: str = "",
        timeout_ms: int = 30_000,
    ) -> dict:
        """切到指定工作流详情并做逐工作流身份核对（并行工作切换语义原语）。

        切换路径：弹回列表（后台运行继续）→ 目标卡片「打开」（详情槽复用为目标）。
        核对三点：详情标题含 name、视图含 expect_text、不含 forbid_text（对方标记
        零混入）；串台 / 切换未生效即 EvidenceError 冻结取证（不自愈）。
        name 传基名即可：本流程 new_workflow 记录的唯一名（flow_state）优先，
        防历史同名用例残留卡干扰。
        """
        self.back_to_list()
        self.dismiss_toasts()
        full = self.flow_state.get(f"wf:{name}", "")
        card = self.loc_all("wf_card").filter(has_text=full or name)
        if not self.wait_until(lambda: card.count() > 0, timeout_ms=10_000):
            self.fail_evidence(
                "切换目标不在列表",
                classification="identity_mismatch",
                cause=f"列表中无名称含 {(full or name)!r} 的工作流卡片（目标未创建或列表未刷新）",
                repro={"url": self.page.url, "name": name, "expected_full": full},
                detail="卡片 10s 内未出现，页面原状冻结",
                shot_name="switch-target-missing",
            )
        card.first.get_by_text("打开", exact=True).first.click()
        title = body = ""
        title_ok = expect_ok = forbid_ok = False
        deadline = time.time() + 25
        while True:
            title = self._detail_title()
            body = self._active_text()
            title_ok = (full or name) in title
            expect_ok = (expect_text in body) if expect_text else True
            forbid_ok = (forbid_text not in body) if forbid_text else True
            if title_ok and expect_ok and forbid_ok:
                break
            if time.time() >= deadline:
                break
            self.settle(500)
        evidence = {
            "switched_to": name,
            "expected_full": full,
            "detail_title": title,
            "expect_text": expect_text,
            "expect_found": expect_ok,
            "forbid_found": not forbid_ok,
            "card_running": self._cards_running(),
        }
        if not (title_ok and expect_ok and forbid_ok):
            self.fail_evidence(
                f"工作流切换串台：期望 {name!r}",
                classification="identity_mismatch",
                cause="切换后身份三点核对未过",
                repro={
                    "url": self.page.url,
                    "observed": f"title={title!r}",
                    "steps": "back_to_list → 卡片「打开」→ 身份核对",
                },
                detail=(
                    f"title_ok={title_ok}，expect_found={expect_ok}"
                    f"（{expect_text!r}），forbid_found={not forbid_ok}"
                    f"（{forbid_text!r}）"
                ),
                shot_name="wf-switch-mismatch",
                extra=evidence,
            )
        return evidence

    def _cards_running(self) -> list[str]:
        """列表卡片中「后台运行在跑」的工作流名（并行运行观察证据）。"""
        try:
            return self.page.evaluate(
                "() => [...document.querySelectorAll('li.wf-card')]"
                ".filter(c => c.querySelector("
                "'span.wf-run-state.is-running, span.wf-badge-running'))"
                ".map(c => { const n = c.querySelector('span.wf-card-name');"
                " return n ? (n.textContent || '').trim() : ''; })"
            )
        except Exception:  # noqa: BLE001 - 观察证据尽力而为
            return []

    # ---- 创建 ----
    def new_workflow(self, name: str = "apw-desktop-wf") -> dict:
        """列表新建工作流（唯一名带时间戳）并落定详情视图（默认可见性私有，不污染广场）。"""
        self.back_to_list()
        self.dismiss_toasts()
        full = f"{name}-{datetime.now().strftime('%m%d%H%M%S')}"
        self.loc("new_workflow_button").click()
        name_input = self.loc("wf_dialog_name_input")
        name_input.wait_for(state="visible", timeout=5_000)
        name_input.click()
        self.page.keyboard.type(full, delay=20)  # React 受控输入：真实键入（fill 不触发 onChange）
        self.dismiss_toasts()
        self.loc("wf_dialog_create_button").click()
        if not self.wait_until(
            lambda: full in self._detail_title(), timeout_ms=15_000
        ):
            self.fail_evidence(
                "创建后详情未就绪",
                classification="not_ready",
                cause="「创建」后详情视图标题未回显工作流名",
                repro={"url": self.page.url, "steps": f"new_workflow({name})"},
                detail=f"详情标题 15s 内未回显 {full!r}，页面原状冻结",
                shot_name="create-no-detail",
            )
        self.flow_state[f"wf:{name}"] = full
        return {"workflow_name": full, "visibility": "私有（默认）"}

    # ---- 手动写脚本 ----
    def type_script(self, script: str = MANUAL_SCRIPT) -> dict:
        """CodeMirror 整体插入脚本并保存（整体插入避免逐键自动缩进）。

        产品约定：运行的是服务端已保存版本，改动必须先「保存」；保存落定信号 =
        「保存」按钮转 disabled（干净态，探查事实 2026-10-12）。
        """
        code = self.loc("code_editor")
        code.click()
        self.page.keyboard.press("Control+a")
        self.page.keyboard.insert_text(script)
        self.settle(500)
        self.loc("save_button").click()
        if not self.wait_until(self._save_settled, timeout_ms=10_000):
            self.fail_evidence(
                "脚本保存未生效",
                classification="save_failed",
                cause="点击「保存」后按钮未转 disabled（脏状态未落盘）",
                repro={"url": self.page.url, "steps": "type_script → 保存"},
                detail="保存 10s 内未落定，页面原状冻结",
                shot_name="save-failed",
            )
        return {"script": script, "saved": True}

    def _save_settled(self) -> bool:
        try:
            return self.loc("save_button").is_disabled()
        except Exception:  # noqa: BLE001 - 未就绪继续轮询
            return False

    # ---- 运行 ----
    def open_run_view(self, timeout_ms: int = 10_000) -> dict:
        """详情「运行」打开运行视图（运行输入/历史运行）；已在运行视图则幂等返回。"""
        if self.count("run_input_section") > 0:
            return {"run_view": "already_open"}
        self.dismiss_toasts()
        try:
            self.loc("detail_run_button").click(timeout=5_000)
        except Exception as exc:  # noqa: BLE001 - 失败即取证
            self.fail_evidence(
                "运行视图未打开",
                classification="not_ready",
                cause="详情「运行」按钮不可用",
                repro={"url": self.page.url, "steps": "open_run_view"},
                detail="常见：详情未就绪 / 生成中拦截",
                shot_name="run-view-not-open",
                from_exc=exc,
            )
        if not self.wait_until(
            lambda: self.count("run_input_section") > 0, timeout_ms=timeout_ms
        ):
            self.fail_evidence(
                "运行视图未打开",
                classification="not_ready",
                cause="点击详情「运行」后运行输入区未渲染",
                repro={"url": self.page.url, "steps": "open_run_view"},
                detail=f"{timeout_ms}ms 内运行视图未就绪，页面原状冻结",
                shot_name="run-view-not-ready",
            )
        return {"run_view": "opened"}

    def start_run(self, timeout_ms: int = 30_000) -> dict:
        """运行视图「运行」发布执行：运行记录挂载（状态区出现）才算启动。

        就绪校验失败即取证，不静默重试（未启动本身就是缺陷）。
        """
        self.dismiss_toasts()
        try:
            self.loc("run_execute_button").click(timeout=5_000)
        except Exception as exc:  # noqa: BLE001
            self.fail_evidence(
                "运行未启动",
                classification="not_ready",
                cause="运行视图「运行」按钮不可用",
                repro={"url": self.page.url, "steps": "start_run"},
                detail="常见：脚本未保存 / 上次运行未结束 / 无输入不适用",
                shot_name="run-not-started",
                from_exc=exc,
            )
        if not self.wait_until(
            lambda: self.count("run_status_section") > 0, timeout_ms=timeout_ms
        ):
            self.fail_evidence(
                "运行未挂载",
                classification="run_no_record",
                cause="点击「运行」后运行状态区未出现（运行记录未挂载）",
                repro={"url": self.page.url, "steps": "start_run"},
                detail=f"{timeout_ms}ms 内运行状态区未渲染，页面原状冻结",
                shot_name="run-not-mounted",
            )
        return {"run_started": True}

    def wait_run_done(self, timeout_ms: int = 180_000) -> dict:
        """等待「运行完成」（判定信号缺一不可，日志稳定收敛才算完成）：

        1. 运行状态区在场：运行记录已挂载
        2. 「取消运行」消失（执行结束的 UI 状态）
        3. 完成徽标在场（状态区 is-completed）
        4. 日志「✅ 工作流完成。…」完成行在场
        5. 运行日志文本长度连续 3 次采样不变（内容稳定）

        已稳定 5 采样仍缺结构信号 = 半截结束，立即取证（不空等满超时）。
        未达成即判失败，绝不自愈重载（页面原状冻结）。
        """
        stall_shot = ""

        def on_tick(w: SignalWatch) -> None:
            nonlocal stall_shot
            # 长时间无完成行 = 执行卡死现场，冻结一份快照供归因
            if (
                not stall_shot
                and w.signals.get("run_status_present")
                and not w.signals.get("run_done_line")
                and w.elapsed_s > 60
            ):
                stall_shot = self.snap("run-stall-onset")

        watch = self.watch_signals(
            signals=lambda: {
                "run_status_present": self.count("run_status_section") > 0,
                "cancel_cleared": self.count("cancel_run_button") == 0,
                "completed_badge": self.count("run_completed_badge") > 0,
                "run_done_line": self.count("run_done_marker") > 0,
            },
            size=lambda: self.page.evaluate(
                "() => { const l = document.querySelector("
                "'div.wf-view-slot.is-active div.wf-log-body');"
                " return l ? (l.innerText || '').length : 0; }"
            ),
            timeout_ms=timeout_ms,
            size_field="log_len",
            gate=["run_status_present", "cancel_cleared", "completed_badge", "run_done_line"],
            # 稳定计数只认「执行已结束」：结构信号长期缺失时由 give_up 提前收场
            stability_gate=lambda s: s.get("cancel_cleared", False),
            on_tick=on_tick,
            give_up=lambda w: w.stable >= 5,  # 已稳定仍缺结构 = 半截结束，立即取证
        )
        if watch.settled:
            evidence = {"run_signals": watch.signals, "timeline": watch.timeline[-5:]}
            try:
                evidence.update(self.capture_context())
            except Exception:  # noqa: BLE001
                pass
            return evidence
        self.fail_incomplete(
            "运行未完成",
            classify=classify_run_failure,
            watch=watch,
            steps="open_run_view → start_run → wait_run_done",
            observed=f"运行启动后 {timeout_ms}ms 内完成信号未达成",
            freeze_shots=[stall_shot],
        )

    # ---- 证据采集 ----
    def capture_context(self) -> dict:
        """采集工作流上下文证据：视图身份/脚本/流程摘要/运行日志/后台运行卡片（不作断言）。"""
        return {
            "url": self.page.url,
            "captured_at": datetime.now().isoformat(timespec="seconds"),
            **self.page.evaluate(_CAPTURE_JS),
        }
