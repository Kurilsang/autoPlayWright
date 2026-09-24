"""工作流编辑页（真实环境，/workflows 与 /workflows/<id>）。

由 AI 探查页面结构生成（T07 流程）。核心语义：
- 非 AI 编码 = 「编辑」态手动写脚本（整体插入避免逐键自动缩进）→ 保存 → 运行
  （产品约定：运行的是服务端已保存版本，未保存改动必须先保存）；
- AI 编码 = 「AI 编写」提交需求生成/更新工作流（生成中拦截运行与 AI 编辑）；
- 并发 UI 校验 = 多标签同时「发布 AI 任务」（生成提交 / 运行触发），逐标签核对
  身份与状态，串台/卡死即 EvidenceError 冻结取证（不自愈）。
"""
from __future__ import annotations

import time
from datetime import datetime
from typing import TYPE_CHECKING
from urllib.parse import urljoin

from apw.pages.base import BasePage, EvidenceError

if TYPE_CHECKING:
    from playwright.sync_api import Page

_DISMISS_TEXTS = ("稍后再看", "我已熟悉", "关闭提示", "关闭", "我已知晓")

# 可见性按钮名 → 定位器仓库条目
_VISIBILITY_LOCATORS = {
    "公开": "wf_visibility_public",
    "私有": "wf_visibility_private",
}

# 非 AI 编码用例的固定脚本：最小 wf 契约（step/log/set_output），输出完全确定
MANUAL_SCRIPT = (
    "def main(wf):\n"
    '    with wf.step("n1", "打印 hello"):\n'
    '        wf.log("hello")\n'
    '        wf.set_output("greeting", "hello")\n'
)

# 结构采集 DOM 内省：名称/脚本/流程节点/运行日志（证据，尽力而为不断言）
_CAPTURE_JS = """
() => {
  const nameInput = document.querySelector('input.font-semibold');
  const codeEl = document.querySelector('textarea[spellcheck="false"]')
    || document.querySelector('pre');
  const nodes = [...document.querySelectorAll('span.text-sm.font-medium.truncate')]
    .map(el => (el.textContent || '').trim()).filter(Boolean).slice(0, 20);
  const log = [...document.querySelectorAll('div.break-all.leading-relaxed')]
    .map(el => (el.textContent || '').trim());
  return {
    workflow_name: nameInput ? nameInput.value : '',
    script: codeEl ? (codeEl.value || codeEl.textContent || '') : '',
    flow_nodes: nodes,
    run_log: log.slice(-40).join('\\n'),
  };
}
"""


def classify_gen_failure(signals: dict) -> tuple[str, str]:
    """归因「生成未达成」：(分类, 说明)。"""
    if not signals.get("gen_cleared", True):
        return (
            "gen_stuck",
            "「AI 正在生成工作流」标志持续在场：生成会话卡死（后端生成挂起）",
        )
    if not signals.get("script_applied", True):
        return (
            "gen_incomplete",
            "生成会话已结束但脚本未落盘（编辑器仍空态）：静默失败",
        )
    return "content_unstable", "生成内容持续变化未稳定（页面文本长度未收敛）"


def classify_run_failure(signals: dict) -> tuple[str, str]:
    """归因「运行未完成」：(分类, 说明)。"""
    if not signals.get("cancel_cleared", True):
        return "run_stuck", "「取消运行」持续在场：运行未结束（执行挂起或超长）"
    return "run_incomplete", "运行日志无「工作流完成」完成行（半截/失败结束）"


class AmlWorkflowPage(BasePage):
    page_name = "aml_workflow"

    # ---- 导航与弹窗 ----
    def _goto_workflows(self) -> None:
        self.page.goto(urljoin(self.page.url, "/workflows"), wait_until="load")
        self.page.wait_for_timeout(800)
        self.dismiss_popups()

    def open_via_nav(self) -> None:
        """从侧边栏「任务」→「工作流」进入列表（验证导航入口链路）。"""
        self.loc("nav_tasks").click()
        self.page.wait_for_timeout(400)
        self.loc("nav_workflow").click()
        self.page.wait_for_timeout(800)
        self.dismiss_popups()

    def dismiss_popups(self) -> None:
        """关闭新手引导/提示横幅（幂等：不存在时直接返回）。"""
        for _ in range(3):
            for label in _DISMISS_TEXTS:
                btn = self.page.get_by_text(label, exact=True)
                if btn.count():
                    try:
                        btn.first.click(timeout=2000)
                        self.page.wait_for_timeout(500)
                        break
                    except Exception:  # noqa: BLE001 - 单个按钮失效尝试下一个
                        continue
            else:
                return

    # ---- 内部：工作流创建 ----
    def _title_value(self) -> str:
        try:
            return self.loc("wf_title_input").input_value(timeout=3_000)
        except Exception:  # noqa: BLE001 - 编辑器未就绪时按空处理
            return ""

    def _create_workflow(self, base_name: str, visibility: str = "私有") -> str:
        """列表页新建工作流并进入编辑器，返回带时间戳的唯一名。"""
        if visibility not in _VISIBILITY_LOCATORS:
            raise ValueError(f"未知可见性 {visibility!r}，可选 {sorted(_VISIBILITY_LOCATORS)}")
        self._goto_workflows()
        self.loc("new_workflow_button").click()
        full = f"{base_name}-{datetime.now().strftime('%m%d%H%M%S')}"
        name_input = self.loc("wf_dialog_name_input")
        name_input.wait_for(state="visible", timeout=5_000)
        name_input.click()
        self.page.keyboard.type(full, delay=20)  # React 受控输入：真实键入（fill 不触发 onChange）
        self.loc(_VISIBILITY_LOCATORS[visibility]).click()
        self.loc("wf_create_button").click()
        self.loc("wf_title_input").wait_for(state="visible", timeout=15_000)
        deadline = time.time() + 10
        while self._title_value() != full and time.time() < deadline:
            time.sleep(0.3)
        if self._title_value() != full:
            shot = self.snap("create-no-editor")
            raise EvidenceError(
                f"创建后编辑器未就绪［归因: not_ready］标题输入未回显 {full!r}\n"
                f"  冻结截图: {shot or '（未捕获）'}",
                {
                    "classification": "not_ready",
                    "cause": "创建后未进入编辑器（标题输入未回显）",
                    "repro": {"url": self.page.url, "steps": "new_workflow → 创建"},
                    "screenshots": [shot] if shot else [],
                },
            )
        return full

    def new_workflow(self, name: str = "apw-ui-test", visibility: str = "私有") -> dict:
        """新建工作流并进入编辑器（测试数据默认私有可见性，不污染广场）。"""
        full = self._create_workflow(name, visibility)
        return {"workflow_name": full, "visibility": visibility}

    # ---- 内部：AI 生成 ----
    def _fill_prompt(self, prompt: str) -> None:
        box = self.loc("ai_prompt_input")
        box.click()
        self.page.keyboard.type(prompt, delay=20)  # React 受控输入：真实键入

    def _click_generate(self) -> None:
        self.loc("generate_button").click(timeout=5_000)

    def _wait_gen_done(self, timeout_ms: int, context: dict | None = None) -> dict:
        """等待「生成完成」：生成中标志消失 + 面板进迭代态 + 脚本落盘 + 内容稳定。

        未达成即判失败，绝不自愈重载（静默失败/卡死本身就是缺陷，页面原状冻结）。
        """
        deadline = time.time() + timeout_ms / 1000
        stable, last_len, signals, prev, tick = 0, -1, {}, None, 0
        timeline: list[dict] = []
        while time.time() < deadline:
            time.sleep(1)
            tick += 1
            signals = {
                "gen_cleared": self.count("gen_running_marker") == 0,
                "gen_done": self.count("gen_done_marker") > 0,
                "script_applied": self.count("script_empty_marker") == 0,
            }
            length = self.page.evaluate(
                "() => (document.body.innerText || '').length"
            )
            if signals != prev or tick % 10 == 0:
                timeline.append({"t_s": tick, "text_len": length, **signals})
                prev = dict(signals)
            if all(signals.values()) and length == last_len and length > 0:
                stable += 1
                if stable >= 3:
                    return {"gen_signals": signals, "timeline": timeline[-5:]}
            else:
                stable = 0
            last_len = length
        category, cause = classify_gen_failure(signals)
        shot = self.snap("gen-timeout")
        evidence: dict = {
            "classification": category,
            "cause": cause,
            "signals": signals,
            "timeline": timeline,
            "repro": {
                "url": self.page.url,
                "observed": f"生成提交后 {timeout_ms}ms 内未达成完成信号",
                "steps": "fill_prompt → 生成工作流 → wait_gen_done",
            },
            "screenshots": [shot] if shot else [],
        }
        if context:
            evidence.update(context)
        try:
            evidence.update(self.capture_context())  # 半截现场一并取证
        except Exception:  # noqa: BLE001 - 取证尽力而为
            pass
        raise EvidenceError(
            f"AI 生成未达成［归因: {category}］{cause}\n"
            f"  信号: {signals}\n  冻结截图: {shot or '（未捕获）'}",
            evidence,
        )

    def generate_ai(self, prompt: str, timeout_ms: int = 180_000) -> dict:
        """AI 编码：描述需求生成/更新工作流（语义原语：链路级完成判定 + 取证）。

        React 受控输入必须真实键入（fill 不触发 onChange，会静默空提交）。
        """
        self.dismiss_popups()
        self._fill_prompt(prompt)
        self._click_generate()
        result = self._wait_gen_done(timeout_ms, {"prompt": prompt})
        try:
            result.update(self.capture_context())
        except Exception:  # noqa: BLE001
            pass
        return result

    # ---- 非 AI 编码：手动写脚本 ----
    def type_script(self, script: str = MANUAL_SCRIPT) -> dict:
        """「编辑」态手动写脚本并保存（整体插入避免逐键自动缩进）。

        产品约定：运行的是服务端已保存版本，改动必须先「保存工作流」。
        """
        self.loc("code_edit_toggle").click()
        code = self.loc("code_input")
        code.wait_for(state="visible", timeout=5_000)
        code.click()
        self.page.keyboard.press("Control+a")
        self.page.keyboard.insert_text(script)  # 整体插入：不触发逐键自动缩进
        self.page.wait_for_timeout(500)
        self.loc("save_button").click()
        try:
            self.loc("saved_badge").wait_for(state="visible", timeout=10_000)
        except Exception as exc:  # noqa: BLE001 - 保存失败即取证
            shot = self.snap("save-failed")
            raise EvidenceError(
                f"脚本保存未生效［归因: save_failed］顶栏未回「已保存」\n"
                f"  冻结截图: {shot or '（未捕获）'}",
                {
                    "classification": "save_failed",
                    "cause": "点击「保存工作流」后未出现「已保存」",
                    "repro": {"url": self.page.url, "steps": "type_script → 保存工作流"},
                    "screenshots": [shot] if shot else [],
                },
            ) from exc
        return {"script": script, "saved": True}

    # ---- 运行 ----
    def start_run(self) -> dict:
        """点击「运行」发布一次工作流运行（就绪校验失败即取证，不静默重试）。"""
        self.dismiss_popups()
        try:
            self.loc("run_button").click(timeout=5_000)
        except Exception as exc:  # noqa: BLE001
            shot = self.snap("run-not-started")
            raise EvidenceError(
                "运行未启动［归因: not_ready］「运行」不可用"
                "（常见：脚本未保存 / 生成中 / 无脚本）\n"
                f"  冻结截图: {shot or '（未捕获）'}",
                {
                    "classification": "not_ready",
                    "cause": "「运行」按钮不可用",
                    "repro": {"url": self.page.url, "steps": "start_run"},
                    "screenshots": [shot] if shot else [],
                },
            ) from exc
        return {"run_started": True}

    def wait_run_done(self, timeout_ms: int = 180_000) -> dict:
        """等待「运行完成」：日志完成行在场 + 「取消运行」消失 + 日志稳定。

        未达成即判失败冻结现场（运行卡死/半截结束本身就是缺陷）。
        """
        deadline = time.time() + timeout_ms / 1000
        stable, last_len, signals, prev, tick = 0, -1, {}, None, 0
        timeline: list[dict] = []
        while time.time() < deadline:
            time.sleep(1)
            tick += 1
            signals = {
                "run_done": self.count("run_done_marker") > 0,
                "cancel_cleared": self.count("cancel_run_button") == 0,
            }
            length = self.page.evaluate(
                "() => [...document.querySelectorAll('div.break-all.leading-relaxed')]"
                ".map(el => (el.textContent || '').length).reduce((a, b) => a + b, 0)"
            )
            if signals != prev or tick % 10 == 0:
                timeline.append({"t_s": tick, "log_len": length, **signals})
                prev = dict(signals)
            if all(signals.values()) and length == last_len and length > 0:
                stable += 1
                if stable >= 3:
                    evidence = {"run_signals": signals, "timeline": timeline[-5:]}
                    try:
                        evidence.update(self.capture_context())
                    except Exception:  # noqa: BLE001
                        pass
                    return evidence
            else:
                stable = 0
            last_len = length
        category, cause = classify_run_failure(signals)
        shot = self.snap("run-timeout")
        evidence: dict = {
            "classification": category,
            "cause": cause,
            "signals": signals,
            "timeline": timeline,
            "repro": {
                "url": self.page.url,
                "observed": f"运行启动后 {timeout_ms}ms 内完成信号未达成",
                "steps": "start_run → wait_run_done",
            },
            "screenshots": [shot] if shot else [],
        }
        try:
            evidence.update(self.capture_context())
        except Exception:  # noqa: BLE001
            pass
        raise EvidenceError(
            f"运行未完成［归因: {category}］{cause}\n"
            f"  信号: {signals}\n  冻结截图: {shot or '（未捕获）'}",
            evidence,
        )

    # ---- 并发：多标签同时发布 AI 任务 ----
    def _spawn_actors(
        self, names: list[str], visibility: str = "私有"
    ) -> tuple[list[AmlWorkflowPage], list[str], list[Page]]:
        """每任务一个标签页：主标签保序第一（后续 assert 作用于主标签）。"""
        tabs: list[Page] = [self.page]
        for _ in names[1:]:
            tab = self.page.context.new_page()
            tab.goto(urljoin(self.page.url, "/workflows"), wait_until="load")
            tabs.append(tab)
        actors: list[AmlWorkflowPage] = []
        full_names: list[str] = []
        for tab, base in zip(tabs, names, strict=True):
            actor = AmlWorkflowPage(page=tab, repo=self.repo)
            actor.screenshot_dir = self.screenshot_dir
            actors.append(actor)
            full_names.append(actor._create_workflow(base, visibility))
        return actors, full_names, tabs

    @staticmethod
    def _close_extra_tabs(tabs: list[Page]) -> None:
        for tab in tabs[1:]:
            try:
                tab.close()
            except Exception:  # noqa: BLE001 - 清理尽力而为
                pass

    def _assert_identity(self, actors: list[AmlWorkflowPage], full_names: list[str]) -> None:
        """并发串台检查：各标签顶栏名称输入必须回显自己的工作流名。"""
        for actor, full in zip(actors, full_names, strict=True):
            actual = actor._title_value()
            if actual == full:
                continue
            shot = actor.snap("identity-mismatch")
            raise EvidenceError(
                f"并发串台［归因: identity_mismatch］标签身份错位：期望 {full!r}，实际 {actual!r}\n"
                f"  冻结截图: {shot or '（未捕获）'}",
                {
                    "classification": "identity_mismatch",
                    "cause": "并发任务标签页身份错位（UI 串台）",
                    "repro": {"expected": full, "actual": actual, "url": actor.page.url},
                    "screenshots": [shot] if shot else [],
                },
            )

    @staticmethod
    def _tab_evidence(actor: AmlWorkflowPage, full: str, extra: dict) -> dict:
        evidence = {"workflow_name": full, "title_value": actor._title_value()}
        try:
            context = actor.capture_context()
            evidence["script_excerpt"] = str(context.get("script", ""))[:200]
            evidence["run_log"] = str(context.get("run_log", ""))[-500:]
        except Exception:  # noqa: BLE001
            pass
        shot = actor.snap("tab-evidence")
        if shot:
            evidence["screenshot"] = shot
        evidence.update(extra)
        return evidence

    @staticmethod
    def _observe_concurrent(
        actors: list[AmlWorkflowPage], marker: str, samples: int = 20, interval: float = 0.5
    ) -> tuple[bool, list[bool]]:
        """轮询捕捉「全部标签同处 marker 态」的瞬时并发证据。

        返回 (并发瞬时是否出现, 各标签是否出现过 marker 态)。UI 状态切换有渲染延迟，
        立即采样会误判无并发，故轮询至多 samples*interval 秒。
        """
        ever = [False] * len(actors)
        for _ in range(samples):
            flags = [a.count(marker) > 0 for a in actors]
            ever = [e or f for e, f in zip(ever, flags, strict=True)]
            if all(flags):
                return True, ever
            time.sleep(interval)
        return False, ever

    def publish_ai_tasks_concurrently(
        self,
        names: list[str],
        prompt: str,
        timeout_ms: int = 240_000,
        visibility: str = "私有",
    ) -> dict:
        """并发发布 AI 生成任务：多标签背靠背提交「AI 编写」，逐标签核对 UI 与身份。

        校验点：各标签都进入生成中态（并发确实发生）→ 各自完成且脚本各归各 →
        标签身份无错位。任一异常即 EvidenceError 冻结现场（不自愈）。
        """
        if len(names) < 2:
            raise ValueError("并发发布至少需要 2 个任务名（names）")
        actors, full_names, tabs = self._spawn_actors(names, visibility)
        try:
            for actor in actors:
                actor._fill_prompt(prompt)
            for actor in actors:  # 背靠背提交 = 并发发布
                actor._click_generate()
            concurrent_seen, generating = self._observe_concurrent(actors, "gen_running_marker")
            per_tab: list[dict] = []
            for actor, full, marker_seen in zip(actors, full_names, generating, strict=True):
                actor._wait_gen_done(timeout_ms, {"prompt": prompt})
                per_tab.append(
                    self._tab_evidence(
                        actor,
                        full,
                        {
                            "generating_seen": marker_seen,
                            "concurrent_observed": concurrent_seen,
                        },
                    )
                )
            self._assert_identity(actors, full_names)
            return {
                "concurrency": len(names),
                "prompt": prompt,
                "concurrent_observed": concurrent_seen,
                "tabs": per_tab,
            }
        finally:
            self._close_extra_tabs(tabs)

    def run_tasks_concurrently(
        self,
        names: list[str],
        prompt: str,
        timeout_ms: int = 300_000,
        visibility: str = "私有",
    ) -> dict:
        """并发发布 AI 运行任务：多标签各自生成脚本后背靠背点「运行」，逐标签核对。

        校验点：点击后各标签同处「取消运行」运行态（并发确实发生）→ 各自跑到
        「工作流完成」→ 标签身份无错位。任一异常即 EvidenceError 冻结现场（不自愈）。
        """
        if len(names) < 2:
            raise ValueError("并发运行至少需要 2 个任务名（names）")
        actors, full_names, tabs = self._spawn_actors(names, visibility)
        try:
            for actor in actors:  # 脚本生成顺序执行（并发点在运行发布）
                actor.generate_ai(prompt, timeout_ms)
            for actor in actors:  # 背靠背发布运行 = 并发 AI 任务
                actor.start_run()
            concurrent_seen, running = self._observe_concurrent(actors, "cancel_run_button")
            per_tab: list[dict] = []
            for actor, full, marker_seen in zip(actors, full_names, running, strict=True):
                actor.wait_run_done(timeout_ms)
                per_tab.append(
                    self._tab_evidence(
                        actor,
                        full,
                        {
                            "running_seen": marker_seen,
                            "concurrent_observed": concurrent_seen,
                        },
                    )
                )
            self._assert_identity(actors, full_names)
            return {
                "concurrency": len(names),
                "prompt": prompt,
                "concurrent_observed": concurrent_seen,
                "tabs": per_tab,
            }
        finally:
            self._close_extra_tabs(tabs)

    # ---- 证据采集 ----
    def capture_context(self) -> dict:
        """采集工作流上下文证据：名称/脚本/流程节点/运行日志（供人工核对，不作断言）。"""
        data = self.page.evaluate(_CAPTURE_JS)
        return {
            "url": self.page.url,
            "captured_at": datetime.now().isoformat(timespec="seconds"),
            **data,
        }
