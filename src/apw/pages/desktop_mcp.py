"""桌面客户端「设置 → MCP」页面对象：stdio 服务器添加 / 连接 / 详情浏览 / 会话调用核对。

链路级语义（本类的判定与取证口径）：
  open_settings_mcp     进设置 → MCP（并记流水账基线）
  add_stdio_server      添加 stdio 服务器（表单回读校验）
  add_external_mcp_server  接入外部真实 MCP（npm 包，经透明代理挂在本地）
  verify_card_echo      卡片回显核对（名称 / stdio 徽标 / 命令行）
  connect_server        点「重新连接」并等「已连接 + N 工具」（产品保存后不自动连接）
  browse_resources      浏览面板 Resources：条目在场 + 点「查看」得资源正文
  browse_prompts        浏览面板 Prompts：条目在场
  import_from_mcp_json  「从 mcp.json 导入」：预览 → 确认（按名合并）
  edit_server           编辑已有服务器（卡片原地变表单，改命令/参数后回显生效）
  delete_server         删除服务器（**无确认弹层**，危险动作，仅删自建临时条目）
  write_mcp_json / restore_mcp_json  写入/还原全局 mcp.json（导入功能的读取路径）
  verify_config_state   直读落盘配置核对（谁在/谁不在/开关；UI 只是渲染层）
  purge_temp_servers    兜底清理自建临时条目（幂等）
  verify_tool_called    会话里工具被真实调用的**确定性**核对（读调用流水账）
  back_to_chat          退出设置回到会话页

产品事实（实测 2026-10-12/13，客户端 0.2.2 / Electron 39.8.10）：
- 「添加服务器」表单默认折叠，需点 .btn-primary.mcp-panel-add 展开；
- 传输方式 stdio/HTTP/SSE，**stdio 默认选中**；
- **保存后不自动连接**：新卡「0 工具 / 未连接」，须点「重新连接」才「N 工具 / 已连接」；
- 「浏览」为内联面板，Resources 用「查看」、Prompts 用「获取」；
  点浏览可能触发一次**重连**（面板先显示「正在连接…」）→ 必须等它消失再读条目；
- 会话里工具调用块仅显示 `mcp` + 名称前缀（实测被截断），
  **拿不到工具全名** → 工具是否真被调用由调用流水账判定，UI 只作在场性证据；
- **删除无确认弹层**（点红按钮即生效）；**编辑为卡片原地变表单**（加 .is-editing）；
- **导入读固定路径**（全局 + 项目级，项目优先），按名覆盖且**只增改不删**。

失败即取证、禁止自愈：判据未达即 fail_evidence / fail_incomplete 冻结现场。
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path

from apw.pages.base import BasePage

# 调用流水账（夹具 apw_test_mcp.py 与外部 MCP 代理 mcp_proxy.py 追加写同一份）
CALL_LOG = Path(".scratch/auto_playwright/mcp_calls.jsonl")

# 外部真实 MCP 的本地安装目录（scripts/setup_external_mcp.py 落地，gitignored）
EXTERNAL_MCP_ROOT = Path(".scratch/mcp_servers/node_modules")

# 仓库内解释器与代理（相对路径，_abs 解析为绝对；客户端在别的 CWD 拉起进程）
PROXY_PYTHON = ".venv/Scripts/python.exe"
PROXY_SCRIPT = "tests/fixture_mcp/mcp_proxy.py"

# 客户端 userData 目录名：**真实产品名不入库**（AGENTS 硬约束 + 门禁 tests/test_no_secrets.py）。
# 默认值由本地 gitignored 的 configs/desktop.local.bat 或环境变量提供；
# 未配置时 verify_config_state 走「判据不可用」分支（明确 skipped，不误判失败）。
CLIENT_USERDATA_ENV = "APW_CLIENT_USERDATA"
CLIENT_USERDATA_SUBDIR = ".config"  # userData 位于 ~/.config/<产品目录名>/

# 工具调用块判定：UI 侧只能看到分组标题「Called N tool(s)」与「mcp」前缀
_CALLED_RE = re.compile(r"Called\s+(\d+)\s+tool", re.I)
_TOOLS_BADGE_RE = re.compile(r"(\d+)\s*工具")

# 卡片/面板状态内省（一次 evaluate 拿全，减少往返）
_STATE_JS = r"""
() => {
  const txt = el => (el.innerText || el.textContent || '').trim();
  const vis = el => { const r = el.getBoundingClientRect(); return r.width > 0 && r.height > 0; };
  const cards = [...document.querySelectorAll('.mcp-server-card:not(.mcp-add-card)')].filter(vis);
  return {
    url: location.href,
    settingsNav: document.querySelectorAll('.settings-nav-item').length,
    mcpNavActive: [...document.querySelectorAll('.settings-nav-item.active')]
      .some(b => txt(b) === 'MCP'),
    addCardOpen: [...document.querySelectorAll('.mcp-server-card.mcp-add-card')].filter(vis).length,
    transportActive: (() => {
      const b = document.querySelector('.mcp-add-card .mcp-segmented-btn.is-active');
      return b ? txt(b) : '';
    })(),
    cards: cards.map(c => ({
      name: txt(c.querySelector('.mcp-server-name') || { innerText: '' }),
      transport: txt(c.querySelector('.mcp-badge-transport') || { innerText: '' }),
      tools: txt(c.querySelector('.mcp-badge-tools') || { innerText: '' }),
      status: txt(c.querySelector('.mcp-status-label') || { innerText: '' }),
      command: txt(c.querySelector('.mcp-server-meta code') || { innerText: '' }),
      browseOpen: !!c.querySelector('.mcp-browse'),
      editing: c.classList.contains('is-editing'),
      enabled: (() => {
        const t = c.querySelector('input[type=checkbox]');
        return t ? t.checked : null;
      })(),
    })),
    browse: (() => {
      const b = document.querySelector('.mcp-browse');
      if (!b) return null;
      return {
        tab: txt(b.querySelector('.mcp-segmented-btn.is-active') || { innerText: '' }),
        hint: txt(b.querySelector('.mcp-browse-hint') || { innerText: '' }),
        items: [...b.querySelectorAll('.mcp-browse-item')].map(it => ({
          name: txt(it.querySelector('.mcp-browse-item-name') || { innerText: '' }),
          desc: txt(it.querySelector('.mcp-browse-item-desc') || { innerText: '' }),
          uri: txt(it.querySelector('.mcp-browse-item-uri') || { innerText: '' }),
          action: txt(it.querySelector('button') || { innerText: '' }),
        })),
        text: txt(b).slice(0, 3000),
      };
    })(),
    // 会话侧：工具调用块
    calledGroups: [...document.querySelectorAll('.msg-tool-group-header .msg-tool-title')].map(txt),
    toolTitles: [...document.querySelectorAll('.msg-tool-title')].map(txt),
    toolPreviews: [...document.querySelectorAll('.msg-tool-preview')].map(txt),
  };
}
"""


class DesktopMcpPage(BasePage):
    page_name = "desktop_mcp"

    # ---- 内部 ----

    def _state(self) -> dict:
        return self.page.evaluate(_STATE_JS)

    def _card(self, name: str):
        """按名称把动作限定在目标卡片内（删除/重连等每卡同名按钮，禁止全局 .first）。"""
        return self.loc_all("server_card").filter(has_text=name)

    def _abs(self, value: str) -> str:
        """相对路径按仓库根解析为绝对路径（客户端在别的 CWD 拉起进程，必须绝对）。

        仅当该相对路径**真实存在**时才替换，裸命令名（如 npx）原样透传。
        """
        if not value or Path(value).is_absolute():
            return value
        candidate = Path.cwd() / value
        return str(candidate) if candidate.exists() else value

    def _set_value(self, loc, text: str) -> None:
        """填值并回读校验；不一致时退化为真实键入（React 受控输入保险）。"""
        loc.click()
        loc.fill(text)
        if (loc.input_value() or "") == text:
            return
        loc.fill("")
        loc.type(text, delay=10)

    def _record(self, key: str, value) -> None:
        self.flow_state[key] = value

    def _client_userdata(self) -> Path | None:
        """解析客户端 userData 目录（app.sqlite 所在）。

        **真实产品名不入库**（AGENTS 硬约束 + tests/test_no_secrets.py 门禁），
        故不硬编码目录名，按下列来源解析：
          1. 环境变量 APW_CLIENT_USERDATA（完整路径）
          2. configs/desktop.local.bat 里的 APW_CLIENT_USERDATA（gitignored，本地真实值）
          3. 兜底：~/.config 下唯一含 app.sqlite 的目录
        都拿不到时返回 None → verify_config_state 记 skipped（判据不可用，
        不假装通过也不误判失败）。
        """
        env_path = os.environ.get(CLIENT_USERDATA_ENV, "").strip() or self._local_bat_var(
            CLIENT_USERDATA_ENV
        )
        if env_path:
            p = Path(env_path)
            return p if p.exists() else None
        # 兜底：~/.config 下唯一含 app.sqlite 的目录（客户端 userData 判定特征）
        base = Path.home() / CLIENT_USERDATA_SUBDIR
        if base.is_dir():
            cands = [d for d in base.iterdir() if (d / "app.sqlite").exists()]
            if len(cands) == 1:
                return cands[0]
        return None

    @staticmethod
    def _local_bat_var(name: str) -> str:
        """读 configs/desktop.local.bat 里的 `set "<name>=<value>"`（gitignored 本地配置）。

        真实产品名/路径只存本地该文件，不入库；解析不到返回空串。
        """
        local = Path("configs/desktop.local.bat")
        if not local.exists():
            return ""
        m = re.search(
            rf'set\s+"?{re.escape(name)}=([^"\r\n]+)',
            local.read_text(encoding="utf-8", errors="replace"),
        )
        return m.group(1).strip() if m else ""

    def _app_settings_mcp(self) -> list[dict] | None:
        """直读客户端 DB 的 mcpServers（独立于 UI 的权威核对）。

        UI 卡片消失 ≠ 配置真被移除（可能只是列表没刷新）。删除类断言必须落到
        落盘配置上才有意义——这是本方法存在的理由。
        读的是 app.sqlite 副本（含 WAL），客户端在运行时也能安全读。
        """
        import shutil
        import sqlite3
        import tempfile

        src = self._client_userdata()
        if src is None:
            return None
        db = src / "app.sqlite"
        if not db.exists():
            return None
        try:
            with tempfile.TemporaryDirectory() as td:
                for suffix in ("", "-wal", "-shm"):
                    f = src / f"app.sqlite{suffix}"
                    if f.exists():
                        shutil.copy2(f, Path(td) / f.name)
                con = sqlite3.connect(f"file:{Path(td) / 'app.sqlite'}?mode=ro", uri=True)
                try:
                    row = con.execute("select payload from app_settings").fetchone()
                finally:
                    con.close()
            payload = json.loads(row[0]) if row else {}
            return payload.get("mcpServers", [])
        except Exception:  # noqa: BLE001 - 读不到就不作为判据（返回 None）
            return None

    def verify_config_state(
        self,
        expect_present: list[str] | None = None,
        expect_absent: list[str] | None = None,
        expect_enabled: dict[str, bool] | None = None,
    ) -> dict:
        """核对**落盘配置**（非 UI）：谁在、谁不在、开关状态。

        UI 只是渲染层；删除/导入/编辑是否真生效，以 app.sqlite 的 mcpServers 为准。
        读不到 DB 时明确记 skipped 证据（不假装通过、也不误判失败）。
        """
        servers = self._app_settings_mcp()
        if servers is None:
            return {"skipped": True, "reason": "app.sqlite 不可读（判据不可用）"}
        names = [s.get("name", "") for s in servers]
        by_name = {s.get("name", ""): s for s in servers}

        # 重复名恒为缺陷（导入按名合并，不应产生重复条目）
        dupes = sorted({n for n in names if names.count(n) > 1})
        missing = [n for n in (expect_present or []) if n not in names]
        leaked = [n for n in (expect_absent or []) if n in names]
        wrong = {
            n: {"expect": v, "actual": by_name[n].get("enabled")}
            for n, v in (expect_enabled or {}).items()
            if n in by_name and by_name[n].get("enabled") is not v
        }
        if dupes or missing or leaked or wrong:
            self.fail_evidence(
                "落盘配置与期望不符（UI 可能只是渲染差异）",
                classification="config_state_mismatch",
                cause=(
                    f"重复名={dupes} 缺={missing} 不应有={leaked} 开关不符={wrong}"
                ),
                repro={"url": self.page.url, "observed": names},
                detail="以 app.sqlite 的 mcpServers 为准；期望值见 cause，页面原状冻结",
                shot_name="config-state-mismatch",
            )
        return {
            "names": names,
            "present": expect_present or [],
            "absent": expect_absent or [],
            "enabled": {
                n: by_name[n].get("enabled")
                for n in (expect_enabled or {})
                if n in by_name
            },
        }

    def _global_mcp_json(self) -> Path:
        """全局 mcp.json 路径（导入功能的固定读取路径之一）。

        产品目录名**不入库**（门禁红线），故运行时解析，按优先级：
          1. 环境变量 / desktop.local.bat 的 APW_CLIENT_MCP_JSON（完整路径，最稳）
          2. 由 userData 目录名反推：客户端 userData 在 `~/.config/<名>`，
             而全局 mcp.json 在 `~/.<名小写>`（实测两者**仅大小写不同**）→ 取小写形式
          3. 兜底：~ 下含 mcp.json 的隐藏目录（唯一命中才采用）
        都拿不到则报错提示配置，不静默写错位置。
        """
        direct = (
            os.environ.get("APW_CLIENT_MCP_JSON", "").strip()
            or self._local_bat_var("APW_CLIENT_MCP_JSON")
        )
        if direct:
            return Path(direct)
        named = (
            os.environ.get("APW_CLIENT_DIRNAME", "").strip()
            or self._local_bat_var("APW_CLIENT_DIRNAME")
        )
        if named:
            return Path.home() / f".{named.lstrip('.')}" / "mcp.json"
        ud = self._client_userdata()
        if ud is not None:
            # 实测：userData = ~/.config/<Name>，全局配置目录 = ~/.<name 小写>
            return Path.home() / f".{ud.name.lower()}" / "mcp.json"
        # 兜底：~ 下隐藏目录里含 mcp.json 的唯一候选
        try:
            cands = [
                d / "mcp.json"
                for d in Path.home().iterdir()
                if d.is_dir() and d.name.startswith(".") and (d / "mcp.json").exists()
            ]
        except OSError:
            cands = []
        if len(cands) == 1:
            return cands[0]
        self.fail_evidence(
            "无法解析全局 mcp.json 路径",
            classification="config_unavailable",
            cause=(
                f"候选={[str(c) for c in cands]}；请设 APW_CLIENT_MCP_JSON（完整路径）"
                " 或 APW_CLIENT_DIRNAME（目录名，不含前导点）"
            ),
            repro={"url": self.page.url, "observed": "环境变量未配置且兜底不唯一"},
            detail="为避免把真实产品名写入仓库，路径改为运行时解析；页面原状冻结",
            shot_name="mcp-json-path-unresolved",
        )
        raise AssertionError("unreachable")  # fail_evidence 已抛

    def reset_mcp_json(self) -> dict:
        r"""把全局 mcp.json 重置到「干净起点」，保证用例幂等可重跑。

        处理三种历史残留：
          • 侧车备份 `.json.apw-backup`（上次失败没走到还原步）→ 有则按它还原并清除；
          • 残留文件条目**全是 apw-json- 前缀**（测试污染）→ 判定为残留，删除文件；
          • 含非测试条目（用户真实配置）→ **不动**（宁可跳过也不误删用户数据）。
        """
        try:
            path = self._global_mcp_json()
        except Exception:  # noqa: BLE001 - 路径解析失败即跳过（后续 write 会再报）
            return {"reset": False, "reason": "路径不可解析"}
        side = path.with_suffix(".json.apw-backup")
        actions: list[str] = []
        try:
            if side.exists():
                path.write_text(side.read_text(encoding="utf-8"), encoding="utf-8")
                side.unlink(missing_ok=True)
                actions.append("restored-from-sidecar")
            if path.exists():
                try:
                    existing = json.loads(path.read_text(encoding="utf-8")).get(
                        "mcpServers"
                    ) or {}
                except json.JSONDecodeError:
                    existing = {}
                if existing and all(str(k).startswith("apw-json-") for k in existing):
                    path.unlink()
                    actions.append("removed-test-residue")
                elif not existing:
                    path.unlink()
                    actions.append("removed-empty")
        except OSError as exc:
            return {"reset": False, "reason": str(exc), "actions": actions}
        return {
            "reset": True,
            "path": str(path),
            "actions": actions or ["already-clean"],
            "exists_after": path.exists(),
        }

    def write_mcp_json(self, servers: dict, cleanup_after: bool = True) -> dict:
        """写入全局 mcp.json（`~/.<产品目录名>/mcp.json`，导入功能的固定读取路径之一）。

        备份原文件，返回其内容供收尾还原（flow 末步用 restore_mcp_json 恢复，
        避免污染用户本机的真实配置）。servers = {名字: 配置对象}。

        command/args 里的相对路径一律经 `_abs` 绝对化——客户端在**自己的 CWD**
        拉起进程（工作区目录），相对路径必然解析失败。
        """
        normalized: dict = {}
        for name, cfg in servers.items():
            item = dict(cfg)
            if isinstance(item.get("command"), str):
                item["command"] = self._abs(item["command"])
            if isinstance(item.get("args"), list):
                item["args"] = [self._abs(a) if isinstance(a, str) else a for a in item["args"]]
            normalized[name] = item

        path = self._global_mcp_json()
        # 备份到**独立文件**而非 flow_state：中途失败时下次运行仍能据此还原，
        # 避免「失败的运行留下测试内容 → 后续运行把污染当 original 备份」的固化陷阱
        # （实测踩坑 2026-10-13：一次失败后污染被固化进备份）。
        #
        # 防污染保护：若现存文件的条目**全是本用例的测试条目**（apw-json-*），
        # 说明它是上次失败留下的残留而非用户真实配置 → 不建备份，
        # 收尾时按「原本不存在」处理（删除文件），否则污染会一次次被"还原"回来。
        backup_side = path.with_suffix(".json.apw-backup")
        polluted = False
        if path.exists():
            try:
                existing = json.loads(path.read_text(encoding="utf-8")).get("mcpServers") or {}
                polluted = bool(existing) and all(
                    str(k).startswith("apw-json-") for k in existing
                )
            except (OSError, json.JSONDecodeError):
                polluted = False
        if polluted:
            backup_side.unlink(missing_ok=True)
        elif not backup_side.exists() and path.exists():
            try:
                backup_side.write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
            except OSError:  # noqa: BLE001 - 备份失败不挡主流程（记在证据里）
                pass
        backup = None if polluted else (
            path.read_text(encoding="utf-8") if path.exists() else None
        )
        self._record("mcp_json_backup", backup)
        self._record("mcp_json_path", str(path))
        self._record("mcp_json_backup_side", str(backup_side))
        self._record("mcp_json_polluted_before", polluted)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps({"mcpServers": normalized}, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        return {
            "path": str(path),
            "written": list(normalized.keys()),
            "resolved_servers": normalized,
            "had_backup": backup is not None,
            "polluted_before": polluted,
            "backup_sidecar": str(backup_side) if backup_side.exists() else "",
            "cleanup_after": cleanup_after,
        }

    def restore_mcp_json(self) -> dict:
        """还原全局 mcp.json 到**本用例首次写入前**的状态（无备份则删除文件）。

        优先用侧车备份 `.json.apw-backup`——它跨运行持久，能纠正「上次失败的运行
        留下污染、这次把污染当原始状态」的固化问题（实测踩坑 2026-10-13）。
        侧车不存在时退回本流程内存备份。
        """
        path_s = self.flow_state.get("mcp_json_path") or ""
        path = Path(path_s) if path_s else None
        if path is None or not path.name:
            return {"restored": False, "reason": "无写入记录"}
        side = Path(self.flow_state.get("mcp_json_backup_side") or "")
        try:
            if side and side.exists():
                path.write_text(side.read_text(encoding="utf-8"), encoding="utf-8")
                side.unlink(missing_ok=True)
                return {"restored": True, "action": "restored-from-sidecar", "path": str(path)}
            backup = self.flow_state.get("mcp_json_backup")
            if backup is None:
                path.unlink(missing_ok=True)
                return {"restored": True, "action": "removed", "path": str(path)}
            path.write_text(backup, encoding="utf-8")
            return {"restored": True, "action": "restored-from-memory", "path": str(path)}
        except OSError as exc:
            return {"restored": False, "reason": str(exc)}

    def purge_temp_servers(self, prefix: str = "apw-tmp-", reload_first: bool = True) -> dict:
        """兜底清理：删除所有以 prefix 开头的临时服务器（幂等，找不到就跳过）。

        用途：链路中途失败时，残留的临时条目会影响下次运行（同名复用逻辑）。

        reload_first：先重载页面让 UI 与落盘配置同步。实测踩坑（2026-10-13）：
        DB 里有残留条目时，UI 卡片列表可能是**陈旧渲染**（只显示 3 张，DB 实为 4 条）
        → 按 UI 清理会漏删，残留继续污染后续断言。故默认先 reload。
        """
        if reload_first:
            self.page.reload(wait_until="domcontentloaded")
            self.settle(2500)
            # reload 后可能落到会话页 → 重新进 MCP（open_settings_mcp 自带状态自适应）
            if self.count("server_card") == 0:
                self.open_settings_mcp()
            self.settle(600)

        removed: list[str] = []
        for c in list(self._state()["cards"]):
            if c["name"].startswith(prefix):
                self.loc_all("server_card").filter(has_text=c["name"]).locator(
                    "button.mcp-icon-btn.is-danger[title='删除']"
                ).first.click()
                self.settle(900)
                removed.append(c["name"])

        # 落盘复核：UI 若仍陈旧，以 DB 为准再补一轮（DB 有而 UI 没删掉的，reload 后强删）
        db_names = [s.get("name", "") for s in (self._app_settings_mcp() or [])]
        leftover = [n for n in db_names if n.startswith(prefix) and n not in removed]
        for n in leftover:
            self.page.reload(wait_until="domcontentloaded")
            self.settle(2200)
            if self.count("server_card") == 0:
                self.open_settings_mcp()
            card = self.loc_all("server_card").filter(has_text=n)
            if card.count() > 0:
                card.locator("button.mcp-icon-btn.is-danger[title='删除']").first.click()
                self.settle(900)
                removed.append(n)
        return {
            "purged": removed,
            "remaining": [c["name"] for c in self._state()["cards"]],
            "db_names_after": [
                s.get("name", "") for s in (self._app_settings_mcp() or [])
            ],
        }
    def _name_of(self, name: str) -> str:
        """动作入参留空时取本流程早前生成的动态名称（D23 跨步骤动态身份锚）。"""
        resolved = name or self.flow_state.get("mcp_server_name", "")
        if not resolved:
            self.fail_evidence(
                "缺少服务器名：既未传参也无流程内动态锚",
                classification="identity_mismatch",
                cause="add_stdio_server 未执行或 flow_state 中无 mcp_server_name",
                repro={"url": self.page.url, "observed": f"name={name!r}"},
                detail="后续动作无法定位目标卡片，页面原状冻结",
                shot_name="missing-server-name",
            )
        return resolved

    # ---- 入口 ----

    def open_settings_mcp(self) -> dict:
        """进入 设置 → MCP（状态自适应：面板已开/已在该页时不重复点击）。

        同时记录夹具流水账基线行数，供 verify_tool_called 判定「本次运行新增的调用」。
        """
        st = self._state()
        if not st["settingsNav"]:
            self.loc("settings_button").click()
            self.settle(1200)
            st = self._state()
        if not st["mcpNavActive"]:
            self.loc("nav_mcp").click()
            st = self.wait_until(
                lambda: self._state()["mcpNavActive"], timeout_ms=8_000, interval_ms=300
            )
            if not st:
                self.fail_evidence(
                    "未能进入 MCP 设置页",
                    classification="nav_stuck",
                    cause="点击设置导航「MCP」后 active 态未出现",
                    repro={"url": self.page.url, "observed": "nav_mcp 点击后未激活"},
                    detail="设置面板可能被遮挡或导航项文案变更，页面原状冻结",
                    shot_name="mcp-nav-failed",
                )
        baseline = 0
        if CALL_LOG.exists():
            baseline = sum(1 for _ in CALL_LOG.open(encoding="utf-8"))
        self._record("mcp_call_baseline", baseline)
        return {"entered_mcp": True, "call_log_baseline": baseline}

    def back_to_chat(self) -> dict:
        """退出设置回到会话页（点「返回」）。"""
        if self.loc("sidebar_back").count():
            self.loc("sidebar_back").click()
            self.settle(1200)
        st = self._state()
        return {"settings_nav_visible": st["settingsNav"] > 0}

    # ---- 添加 ----

    def add_stdio_server(
        self,
        name: str = "apw-stdio-mcp",
        command: str = "",
        args: list[str] | None = None,
        env: dict | None = None,
        reuse_existing: bool = True,
    ) -> dict:
        """添加 stdio 服务器：展开表单 → 确认 stdio → 填名称/命令/参数/环境变量 → 保存。

        名称**固定**（默认 `apw-stdio-mcp`）而非随机：会话提示词要按名引用服务器，
        同环境多个服务器提供同名工具时模型可能选错目标（实测踩坑），故必须单实例、
        名字可预期。reuse_existing=True 时同名卡片已存在则复用（幂等，不重复累积，
        也不删除既有配置）；命令不一致会在连接阶段以证据失败暴露。
        名称写入 flow_state["mcp_server_name"] 供后续步骤引用（D23）。
        """
        if not command:
            self.fail_evidence(
                "未提供启动命令",
                classification="config_invalid",
                cause="stdio 服务器的「启动命令」为必填，缺失无法拉起本地进程",
                repro={"url": self.page.url, "observed": "command 为空"},
                detail="用例应提供 .venv python 或 npx 等可执行命令",
                shot_name="missing-command",
            )
        server_name = name or "apw-stdio-mcp"
        resolved_cmd = self._abs(command)
        resolved_args = [self._abs(a) for a in (args or [])]

        # 幂等：同名卡片已在列则直接复用（不重复添加，避免同工具多服务器歧义）
        existing = next(
            (c for c in self._state()["cards"] if server_name in c["name"]), None
        )
        if existing and reuse_existing:
            self._record("mcp_server_name", server_name)
            return {
                "server_name": server_name,
                "command": existing.get("command", ""),
                "transport": existing.get("transport", ""),
                "reused": True,
                "expected_command": resolved_cmd,
                "expected_args": resolved_args,
            }

        # 展开「添加服务器」表单（折叠态才需点）
        if not self._state()["addCardOpen"]:
            self.loc("add_server_button").click()
            if not self.wait_until(
                lambda: self._state()["addCardOpen"], timeout_ms=8_000, interval_ms=300
            ):
                self.fail_evidence(
                    "「添加服务器」表单未展开",
                    classification="form_not_opened",
                    cause="点击添加按钮后 .mcp-add-card 未渲染",
                    repro={"url": self.page.url, "observed": "addCardOpen=False"},
                    detail="表单可能受权限或页面状态限制，页面原状冻结",
                    shot_name="add-form-not-open",
                )

        # 传输方式：stdio 为默认选中；若被改成别的则点回 stdio（硬前提）
        st = self._state()
        if st["transportActive"] != "stdio":
            self.loc("transport_stdio").click()
            self.settle(400)
            st = self._state()
        if st["transportActive"] != "stdio":
            self.fail_evidence(
                "传输方式未选中 stdio",
                classification="transport_mismatch",
                cause="本用例只覆盖 stdio（本地进程）形态，HTTP/SSE 不在范围内",
                repro={"url": self.page.url, "observed": f"active={st['transportActive']!r}"},
                detail="点击 stdio 分段按钮后仍未激活，表单结构可能变更",
                shot_name="transport-not-stdio",
            )

        # 填字段：名称 / 启动命令 / 参数 / 环境变量
        self._set_value(self.loc("field_name"), server_name)
        self._set_value(self.loc("field_command"), resolved_cmd)
        textareas = self.loc_all("field_args")
        args_text = "\n".join(resolved_args)
        if args_text and textareas.count() >= 1:
            self._set_value(textareas.nth(0), args_text)
        if env and textareas.count() >= 2:
            self._set_value(textareas.nth(1), json.dumps(env, ensure_ascii=False))

        # 回读校验：填进去什么，表单里就该是什么（防静默空提交）
        readback = {
            "name": self.loc("field_name").input_value(),
            "command": self.loc("field_command").input_value(),
            "args": textareas.nth(0).input_value() if textareas.count() >= 1 else "",
        }
        if readback["name"] != server_name or readback["command"] != resolved_cmd:
            self.fail_evidence(
                "表单回读与输入不一致（疑似静默空提交）",
                classification="form_silent_noop",
                cause="受控输入未接收键入内容，保存将写入空值",
                repro={
                    "url": self.page.url,
                    "observed": f"name={readback['name']!r} command={readback['command']!r}",
                },
                detail=f"期望 name={server_name!r} command={resolved_cmd!r}，页面原状冻结",
                shot_name="form-readback-mismatch",
            )

        self.loc("save_button").click()
        self.settle(1500)

        # 成功判据 = 表单关闭 + 目标卡片出现（产品保存成功无 toast）
        appeared = self.wait_until(
            lambda: any(
                server_name in c["name"] for c in self._state()["cards"]
            ),
            timeout_ms=15_000,
            interval_ms=500,
        )
        if not appeared:
            self.fail_evidence(
                "保存后卡片未出现",
                classification="save_failed",
                cause="点「保存」后表单未关闭或服务器未落库（产品无 toast，以卡片出现为判据）",
                repro={"url": self.page.url, "observed": f"未找到名为 {server_name!r} 的卡片"},
                detail=f"期望新增卡片 {server_name!r}；页面原状冻结",
                shot_name="save-card-missing",
            )
        self._record("mcp_server_name", server_name)
        return {
            "server_name": server_name,
            "command": resolved_cmd,
            "args": resolved_args,
            "transport": "stdio",
            "readback": readback,
        }

    # ---- 回显 / 连接 ----
    def add_external_mcp_server(
        self,
        name: str,
        package: str,
        entry: str,
        server_label: str = "",
        reuse_existing: bool = True,
        command: str = "node",
    ) -> dict:
        """接入**外部真实 MCP**（npm 包）并挂到本机：走 stdio 表单 + 透明代理。

        为什么经代理：真实第三方 MCP 不会写调用流水账，`verify_tool_called`
        将无据可依。代理（tests/fixture_mcp/mcp_proxy.py）逐帧透明转发 JSON-RPC，
        顺带把 tools/call 记入与夹具**同一份**流水账 → 判定手段统一，
        且完全不改变真实服务器的行为与返回。

        表单填法：
          名称     = name（如 apw-ext-everything）
          启动命令 = .venv/Scripts/python.exe（仓库内解释器）
          参数     = tests/fixture_mcp/mcp_proxy.py
                     --server <server_label>
                     --
                     node <EXTERNAL_MCP_ROOT>/<package>/<entry>

        package/entry 由 scripts/setup_external_mcp.py 安装落地；
        缺文件时 fail_evidence 指出需先跑安装脚本（不静默跳过）。
        """
        entry_path = EXTERNAL_MCP_ROOT / package / entry
        if not entry_path.exists():
            self.fail_evidence(
                "外部 MCP 未安装",
                classification="external_mcp_missing",
                cause=f"找不到 npm 包入口 {entry_path}",
                repro={"url": self.page.url, "observed": str(entry_path)},
                detail=(
                    "外部 MCP 需先落地："
                    ".venv/Scripts/python scripts/setup_external_mcp.py"
                    "（装到 .scratch/mcp_servers，gitignored）"
                ),
                shot_name="external-mcp-missing",
            )
        resolved_entry = str(entry_path.resolve())
        args = [
            PROXY_SCRIPT,
            "--server",
            server_label or name,
            "--",
            command,
            resolved_entry,
        ]
        result = self.add_stdio_server(
            name=name,
            command=PROXY_PYTHON,
            args=args,
            reuse_existing=reuse_existing,
        )
        result.update(
            {
                "external": True,
                "package": package,
                "entry": resolved_entry,
                "proxy": PROXY_SCRIPT,
            }
        )
        return result

    def verify_card_echo(self, name: str = "", expect_transport: str = "stdio") -> dict:
        """卡片回显核对：名称在场 + 传输徽标为 stdio（确定性结构，不看措辞）。"""
        server_name = self._name_of(name)
        st = self._state()
        card = next((c for c in st["cards"] if server_name in c["name"]), None)
        if card is None:
            self.fail_evidence(
                "列表未见目标服务器卡片",
                classification="echo_missing",
                cause="保存后列表未回显该服务器",
                repro={
                    "url": self.page.url,
                    "observed": f"cards={[c['name'] for c in st['cards']]}",
                },
                detail=f"期望卡片含 {server_name!r}，页面原状冻结",
                shot_name="card-echo-missing",
            )
        if card["transport"] != expect_transport:
            self.fail_evidence(
                "传输方式徽标不符",
                classification="echo_mismatch",
                cause=f"期望徽标 {expect_transport!r}，实际 {card['transport']!r}",
                repro={"url": self.page.url, "observed": card},
                detail="卡片传输徽标与添加时所选不一致，页面原状冻结",
                shot_name="transport-badge-mismatch",
            )
        return {"card": card}

    def connect_server(self, name: str = "", timeout_ms: int = 30_000) -> dict:
        """点「重新连接」并等「已连接」且工具数 > 0。

        产品行为：保存后**不会自动连接**（新卡 0 工具/未连接），必须显式重连。
        流式连接未达即判失败取证，不重试刷绿。
        """
        server_name = self._name_of(name)
        before = next(
            (c for c in self._state()["cards"] if server_name in c["name"]), None
        )
        self._card(server_name).locator(
            "button.mcp-icon-btn[title='重新连接']"
        ).first.click()

        target = {"name": server_name, "status": "", "tools": ""}

        def connected() -> bool:
            card = next(
                (c for c in self._state()["cards"] if server_name in c["name"]), None
            )
            if card is None:
                return False
            target.update(card)
            m = _TOOLS_BADGE_RE.search(card["tools"])
            return card["status"] == "已连接" and bool(m) and int(m.group(1)) > 0

        if not self.wait_until(connected, timeout_ms=timeout_ms, interval_ms=1000):
            st = self._state()
            self.fail_evidence(
                "MCP 服务器连接未达成",
                classification="mcp_connect_failed",
                cause="点「重新连接」后未出现「已连接 + N 工具（N>0）」",
                repro={
                    "url": self.page.url,
                    "observed": f"status={target['status']!r} tools={target['tools']!r}",
                },
                detail=(
                    f"服务器 {server_name!r} 连接前状态={before}；"
                    f"等待 {timeout_ms}ms 未达成，页面原状冻结"
                    f"（可能原因：命令/参数路径错误、本地进程启动失败、启动超时）"
                ),
                shot_name="mcp-connect-failed",
                extra={"cards": st["cards"]},
            )
        m = _TOOLS_BADGE_RE.search(target["tools"])
        return {"status": target["status"], "tools": target["tools"], "tool_count": int(m.group(1))}

    # ---- 浏览详情 ----

    def _open_browse(self, server_name: str) -> None:
        """展开目标卡片的「浏览」面板（已展开则跳过）。

        注意（实测 2026-10-13）：卡片显示「已连接」可能是**上一会话的陈旧状态**；
        点「浏览」会触发一次**重新连接**（客户端日志可见 disconnected→connected），
        面板先渲染「正在连接…」。若此时就读条目会误判「Resources 无条目」。
        故展开后额外等「正在连接…」提示消失，再交给调用方读条目。
        """
        card = next(
            (c for c in self._state()["cards"] if server_name in c["name"]), None
        )
        if card is None:
            self.fail_evidence(
                "无法浏览：卡片不存在",
                classification="echo_missing",
                cause="浏览前未找到目标服务器卡片",
                repro={"url": self.page.url, "observed": f"name={server_name!r}"},
                detail="页面原状冻结",
                shot_name="browse-card-missing",
            )
        if card.get("browseOpen"):
            self._settle_browse(server_name)
            return
        self._card(server_name).locator("button.mcp-icon-btn[title='浏览']").first.click()
        if not self.wait_until(
            lambda: bool(self._state()["browse"]), timeout_ms=10_000, interval_ms=400
        ):
            self.fail_evidence(
                "浏览面板未展开",
                classification="browse_not_opened",
                cause="点「浏览」后 .mcp-browse 未渲染",
                repro={"url": self.page.url, "observed": "browse=None"},
                detail="页面原状冻结",
                shot_name="browse-not-open",
            )
        self._settle_browse(server_name)

    def _settle_browse(self, server_name: str, timeout_ms: int = 40_000) -> None:
        """等浏览面板渲染出**条目**（点浏览可能触发一次重连）。

        产品行为（实测 2026-10-13）：面板在连接完成前会显示提示文案，两种形态都含「连接」：
          「正在连接…」/「该服务器未提供此能力，或尚未连接」——
        连接完成后提示消失、条目渲染。故**等 items 出现**是最稳的判据；
        只等「正在连接」消失会漏掉第二种形态（实测导致误判「Resources 无条目」）。
        仍等不到则由调用方按最终状态取证（不在此处吞掉失败）。
        """
        self.wait_until(
            lambda: len((self._state()["browse"] or {}).get("items") or []) > 0,
            timeout_ms=timeout_ms,
            interval_ms=500,
        )

    def browse_resources(
        self, name: str = "", expect_name: str = "", expect_content: str = ""
    ) -> dict:
        """Resources 标签：切标签 → 条目在场 → 点「查看」→ 详情正文含期望内容。

        expect_content 用于确定性核对本地进程真实返回的资源正文（如 APW_STDIO_RESOURCE_OK）。
        """
        server_name = self._name_of(name)
        self._open_browse(server_name)
        self.loc("browse_tab_resources").click()
        self.settle(1200)
        self._settle_browse(server_name)

        st = self._state()
        browse = st["browse"] or {}
        items = browse.get("items", [])
        if not items:
            self.fail_evidence(
                "Resources 无条目",
                classification="resource_missing",
                cause="Resources 标签下条目为空（服务器未提供或列表拉取失败）",
                repro={"url": self.page.url, "observed": browse.get("hint", "")},
                detail=f"服务器 {server_name!r} 的 Resources 列表为空，页面原状冻结",
                shot_name="resources-empty",
            )
        if expect_name and not any(expect_name in it["name"] for it in items):
            self.fail_evidence(
                "Resources 未见期望条目",
                classification="resource_mismatch",
                cause=f"期望含 {expect_name!r} 的资源条目",
                repro={"url": self.page.url, "observed": [it["name"] for it in items]},
                detail="资源名称与夹具声明不一致，页面原状冻结",
                shot_name="resources-mismatch",
            )

        idx = next(
            (i for i, it in enumerate(items) if not expect_name or expect_name in it["name"]),
            0,
        )
        self.loc_all("browse_item_action").nth(idx).click()
        self.settle(1500)

        detail = ""
        if expect_content:
            ok = self.wait_until(
                lambda: expect_content in (self._state()["browse"] or {}).get("text", ""),
                timeout_ms=10_000,
                interval_ms=500,
            )
            detail = (self._state()["browse"] or {}).get("text", "")
            if not ok:
                self.fail_evidence(
                    "资源详情未展示期望内容",
                    classification="resource_detail_missing",
                    cause=f"点「查看」后详情区未出现 {expect_content!r}",
                    repro={
                        "url": self.page.url,
                        "observed": detail[-400:],
                    },
                    detail="本地进程资源正文未回显（可能未真实调用 resources/read），页面原状冻结",
                    shot_name="resource-detail-missing",
                )
        return {"items": items, "detail_tail": detail[-400:]}

    def browse_prompts(self, name: str = "", expect_name: str = "") -> dict:
        """Prompts 标签：切标签 → 条目在场（含动作按钮「获取」）。"""
        server_name = self._name_of(name)
        self._open_browse(server_name)
        self.loc("browse_tab_prompts").click()
        self.settle(1200)
        self._settle_browse(server_name)

        browse = self._state()["browse"] or {}
        items = browse.get("items", [])
        if not items:
            self.fail_evidence(
                "Prompts 无条目",
                classification="prompt_missing",
                cause="Prompts 标签下条目为空（服务器未提供或列表拉取失败）",
                repro={"url": self.page.url, "observed": browse.get("hint", "")},
                detail=f"服务器 {server_name!r} 的 Prompts 列表为空，页面原状冻结",
                shot_name="prompts-empty",
            )
        if expect_name and not any(expect_name in it["name"] for it in items):
            self.fail_evidence(
                "Prompts 未见期望条目",
                classification="prompt_mismatch",
                cause=f"期望含 {expect_name!r} 的提示词条目",
                repro={"url": self.page.url, "observed": [it["name"] for it in items]},
                detail="提示词名称与夹具声明不一致，页面原状冻结",
                shot_name="prompts-mismatch",
            )
        return {"items": items}

    def ensure_server_connected(
        self, name: str = "", timeout_ms: int = 60_000, return_to_chat: bool = True
    ) -> dict:
        """确保目标服务器处于「已连接 + N 工具」态，未连则点「重新连接」修复。

        **为什么需要**（实测 2026-10-13，重要产品行为）：
        `new_task`（新建会话）会切换工作区，客户端随即发出 `notifyRootsChanged`
        并**断开全部 MCP 服务器**，之后按需懒重连。若紧接着发消息，目标服务器可能
        仍未连上 → 模型拿不到该工具 → 用例误判 `tool_not_invoked`（实测一次运行：
        12306 被断开后始终未自动重连，而会话已在生成）。
        故在「发消息调用工具」前显式确认/修复连接，把不确定性收敛到可判定的一步。

        return_to_chat：本动作为了检查状态会进设置页，完成后**必须退回会话页**
        （否则设置面板的 `.workspace-overlay` 会拦截组合器点击，实测踩坑）。
        """
        server_name = self._name_of(name)
        card = next((c for c in self._state()["cards"] if server_name in c["name"]), None)
        if card is None:
            # 不在 MCP 页（如刚 new_task 完在会话页）→ 直接进设置；open_settings_mcp 状态自适应
            self.open_settings_mcp()
            card = next(
                (c for c in self._state()["cards"] if server_name in c["name"]), None
            )
        result: dict
        if card is not None:
            m = _TOOLS_BADGE_RE.search(card.get("tools", ""))
            if card.get("status") == "已连接" and m and int(m.group(1)) > 0:
                result = {
                    "status": card["status"],
                    "tools": card["tools"],
                    "reconnected": False,
                }
            else:
                result = self.connect_server(name=server_name, timeout_ms=timeout_ms)
                result["reconnected"] = True
        else:
            result = self.connect_server(name=server_name, timeout_ms=timeout_ms)
            result["reconnected"] = True
        if return_to_chat:
            self.back_to_chat()
        return result

    # ---- mcp.json 导入（实测 2026-10-13）----

    def import_from_mcp_json(
        self,
        expect_names: list[str] | None = None,
        expect_absent: list[str] | None = None,
        timeout_ms: int = 15_000,
    ) -> dict:
        """「从 mcp.json 导入」：点按钮 → 等预览面板 → 核对预览条目 → 确认导入。

        产品行为（实测）：按钮读**固定路径**——全局 `~/.<产品目录>/mcp.json` 与
        项目级 `<workspace>/.<ProductDir>/mcp.json`（项目优先）；**无文件选择器、无粘贴框**。
        点后弹 `.workspace-overlay` 预览面板列「名称 (transport)」→ 点「确认导入」。

        合并语义（**必须知道**）：按名覆盖，**只增改、从不删除**——
        文件里删掉的条目，导入后旧卡片仍在；且**文件压过界面**，
        UI 上手动关掉的开关会被导入翻回文件里的状态。

        expect_names：预览面板**必须**出现的服务器名（文件已写入的）；
        expect_absent：预览面板**不得**出现的名字（验证预览只反映文件内容）。
        """
        self.loc("import_button").click()
        # 注意：loc() 是硬解析（候选全落空即抛 LocatorNotFound）→ 轮询/软探测必须用 count()
        if not self.wait_until(
            lambda: self.count("import_panel") > 0, timeout_ms=8_000, interval_ms=300
        ):
            # 区分「无文件」与「面板未渲染」：前者是产品正常提示，不是缺陷
            if self.count("import_none_hint") > 0:
                self.fail_evidence(
                    "未找到 mcp.json，导入无从进行",
                    classification="import_source_missing",
                    cause=(
                        "产品提示未找到 mcp.json"
                        "（项目 .<ProductDir>/mcp.json 或 ~/.<产品目录>/mcp.json）"
                    ),
                    repro={"url": self.page.url, "observed": "import_none_hint 在场"},
                    detail="用例需先写入全局 mcp.json 再调本动作，页面原状冻结",
                    shot_name="import-source-missing",
                )
            self.fail_evidence(
                "导入预览面板未出现",
                classification="import_panel_missing",
                cause="点「从 mcp.json 导入」后 .mcp-import-preview 未渲染",
                repro={"url": self.page.url, "observed": "import_panel count=0"},
                detail="页面原状冻结",
                shot_name="import-panel-missing",
            )

        panel_text = self.loc("import_panel").first.inner_text()
        # 只取预览条目文本（`.mcp-import-item`）——面板外层可能含既存卡片名，
        # 用整块文本会误判「泄露」。
        n_items = self.count("import_preview_item")
        items = [
            self.loc_all("import_preview_item").nth(i).inner_text().strip()
            for i in range(n_items)
        ]
        listed = " \n".join(items)
        preview = [n for n in (expect_names or []) if n in listed]
        missing = [n for n in (expect_names or []) if n not in listed]
        leaked = [n for n in (expect_absent or []) if n in listed]
        if missing:
            self.fail_evidence(
                "导入预览未列出期望服务器",
                classification="import_preview_mismatch",
                cause=f"预览条目缺 {missing}（实际条目={items}）",
                repro={"url": self.page.url, "observed": listed[:400]},
                detail="文件已写入但预览未反映，页面原状冻结",
                shot_name="import-preview-missing",
            )
        if leaked:
            self.fail_evidence(
                "导入预览出现不应有的服务器",
                classification="import_preview_mismatch",
                cause=f"预览条目含 {leaked}（该名字不在文件中）",
                repro={"url": self.page.url, "observed": listed[:400]},
                detail="预览应只反映文件内容，页面原状冻结",
                shot_name="import-preview-leak",
            )

        self.loc("import_confirm_button").click()
        # 成功判据 = 预览面板关闭（产品无 toast）
        if not self.wait_until(
            lambda: self.count("import_panel") == 0, timeout_ms=timeout_ms, interval_ms=300
        ):
            self.fail_evidence(
                "点「确认导入」后预览面板未关闭",
                classification="import_confirm_failed",
                cause="确认导入后 .workspace-overlay 仍在场",
                repro={"url": self.page.url, "observed": panel_text[:300]},
                detail="页面原状冻结",
                shot_name="import-confirm-stuck",
            )
        return {
            "preview_items": items,
            "preview_text": panel_text[:600],
            "previewed": preview,
            "confirmed": True,
            "cards_after": [c["name"] for c in self._state()["cards"]],
        }

    # ---- 编辑（卡片原地变表单）----

    def edit_server(
        self,
        name: str = "",
        command: str = "",
        args: list[str] | None = None,
    ) -> dict:
        """点卡片「编辑」→ 改「启动命令/参数」→ 保存 → 等卡片回显新命令。

        产品行为（实测）：编辑态 = 该卡加 `.is-editing`，字段与添加表单同构，
        动作按钮位变「取消」，表单尾有「保存 / 取消」。
        保存成功判据：卡片退出 is-editing 且命令行回显含新值（产品无 toast）。

        只改命令/参数（不改名、不动传输方式）：名字是身份锚，改名会让后续按名定位失效。
        """
        server_name = self._name_of(name)
        card = next((c for c in self._state()["cards"] if server_name in c["name"]), None)
        if card is None:
            self.fail_evidence(
                "编辑目标卡片不存在",
                classification="echo_missing",
                cause=f"未见服务器 {server_name!r} 的卡片",
                repro={
                    "url": self.page.url,
                    "observed": [c["name"] for c in self._state()["cards"]],
                },
                detail="页面原状冻结",
                shot_name="edit-card-missing",
            )
        resolved_cmd = self._abs(command) if command else ""
        resolved_args = [self._abs(a) for a in (args or [])]

        self._card(server_name).locator("button.mcp-icon-btn[title='编辑']").first.click()
        if not self.wait_until(
            lambda: self.count("editing_card") > 0, timeout_ms=8_000, interval_ms=300
        ):
            self.fail_evidence(
                "编辑态未进入",
                classification="edit_not_opened",
                cause="点「编辑」后未见 .mcp-server-card.is-editing",
                repro={"url": self.page.url, "observed": "editing_card count=0"},
                detail="页面原状冻结",
                shot_name="edit-not-opened",
            )

        if resolved_cmd:
            loc = self.loc_all("edit_command").first
            loc.click()
            loc.fill(resolved_cmd)
            if (loc.input_value() or "") != resolved_cmd:
                loc.fill("")
                loc.type(resolved_cmd, delay=10)
        if resolved_args:
            ta = self.loc_all("edit_args").first
            ta.click()
            ta.fill("\n".join(resolved_args))

        self.loc("edit_save_button").first.click()

        def saved() -> bool:
            st = self._state()
            c = next((x for x in st["cards"] if server_name in x["name"]), None)
            if c is None or c.get("editing"):
                return False
            if resolved_cmd:
                return resolved_cmd in c.get("command", "")
            return True

        if not self.wait_until(saved, timeout_ms=15_000, interval_ms=500):
            st = self._state()
            self.fail_evidence(
                "编辑保存未生效",
                classification="edit_save_failed",
                cause="保存后卡片仍在编辑态，或命令行未回显新值",
                repro={
                    "url": self.page.url,
                    "observed": next(
                        (x for x in st["cards"] if server_name in x["name"]), st["cards"]
                    ),
                },
                detail=f"期望 command 含 {resolved_cmd!r}，页面原状冻结",
                shot_name="edit-save-failed",
            )
        after = next((c for c in self._state()["cards"] if server_name in c["name"]), {})
        self._record("mcp_edited_command", resolved_cmd)
        return {"name": server_name, "command": resolved_cmd, "card_after": after}

    # ---- 删除（无确认弹层，危险动作）----

    def delete_server(self, name: str = "", timeout_ms: int = 15_000) -> dict:
        """点卡片「删除」→ 等卡片消失 → 返回剩余卡片。

        **危险动作**：实测**无确认弹层**（无 window.confirm / 无 .modal），
        点红按钮即生效（0.4s 内卡片消失）→ 用例只允许删**自己刚建的临时条目**，
        绝不删他人配置（如夹具 apw-stdio-mcp 或外部 MCP）。

        同时注册 dialog 监听：若产品后续加了确认弹层，自动 accept 并留痕，
        避免 Playwright 默认 dismiss 导致"永远删不掉"（Web 端 MCP 删除即此坑）。
        """
        server_name = self._name_of(name)
        if not any(server_name == c["name"] for c in self._state()["cards"]):
            self.fail_evidence(
                "删除目标卡片不存在",
                classification="echo_missing",
                cause=f"未见服务器 {server_name!r} 的卡片（可能已被删或名字不符）",
                repro={
                    "url": self.page.url,
                    "observed": [c["name"] for c in self._state()["cards"]],
                },
                detail="页面原状冻结（不重试）",
                shot_name="delete-card-missing",
            )

        dialogs: list[str] = []
        handler = lambda d: (dialogs.append(f"{d.type}:{d.message}"), d.accept())  # noqa: E731
        self.page.on("dialog", handler)
        try:
            self._card(server_name).locator(
                "button.mcp-icon-btn.is-danger[title='删除']"
            ).first.click()
            # 判据 = **落盘配置**里该条目消失（UI 消失只是渲染层，可能与 DB 不同步；
            # 实测踩坑 2026-10-13：UI 已消失但 DB 仍有该条目，导致后续断言误判）。
            gone = self.wait_until(
                lambda: server_name
                not in [s.get("name", "") for s in (self._app_settings_mcp() or [])],
                timeout_ms=timeout_ms,
                interval_ms=500,
            )
            if not gone:
                gone = self.wait_until(
                    lambda: not any(
                        server_name == c["name"] for c in self._state()["cards"]
                    ),
                    timeout_ms=5_000,
                    interval_ms=300,
                )
        finally:
            self.page.remove_listener("dialog", handler)

        remaining = [c["name"] for c in self._state()["cards"]]
        db_names = [s.get("name", "") for s in (self._app_settings_mcp() or [])]
        if not gone or server_name in db_names:
            self.fail_evidence(
                "删除后条目仍在落盘配置中",
                classification="delete_failed",
                cause=(
                    f"点红色「删除」后 {server_name!r} 仍在 app.sqlite.mcpServers"
                    f"（UI 卡片={remaining}，落盘={db_names}）"
                ),
                repro={"url": self.page.url, "observed": db_names, "dialogs": dialogs},
                detail="UI 消失 ≠ 配置移除；以落盘配置为准，页面原状冻结",
                shot_name="delete-failed",
            )
        return {
            "deleted": server_name,
            "remaining": remaining,
            "db_names": db_names,
            "dialogs": dialogs,  # 空 = 产品无确认弹层（当前实测）
        }

    # ---- 会话侧：工具真实调用核对 ----
    def verify_tool_called(
        self,
        tool: str = "",
        expect_result: str = "",
        timeout_ms: int = 30_000,
        min_calls: int = 1,
        server: str = "",
    ) -> dict:
        """核对「本地 stdio 进程被真实拉起并执行了工具」。

        判定依据 = 调用流水账（确定性，非 LLM 措辞）：基线之后存在 ≥min_calls 条
        tool == `tool` 的记录；expect_result 非空时还须命中返回值前缀。
        server 非空时进一步限定来源服务器（外部 MCP 经代理记账时带 `server` 字段）。
        同时采集 UI 侧工具调用块（`Called N tool(s)`）作在场性证据。
        """
        baseline = int(self.flow_state.get("mcp_call_baseline", 0))
        deadline_hit = self.wait_until(
            lambda: len(self._matching_calls(baseline, tool, expect_result, server))
            >= min_calls,
            timeout_ms=timeout_ms,
            interval_ms=1000,
        )
        matches = self._matching_calls(baseline, tool, expect_result, server)
        ui = self._state()
        ui_called = [t for t in ui["toolTitles"] if _CALLED_RE.search(t)]

        if not deadline_hit or len(matches) < min_calls:
            self.fail_evidence(
                "工具未被真实调用（调用流水账无记录）",
                classification="tool_not_invoked",
                cause=(
                    f"基线（{baseline} 行）之后无 tool={tool!r}"
                    + (f" server={server!r}" if server else "")
                    + (f" 且返回值含 {expect_result!r}" if expect_result else "")
                    + " 的调用记录"
                ),
                repro={
                    "url": self.page.url,
                    "observed": f"matches={len(matches)} ui_called={ui_called}",
                },
                detail=(
                    "可能原因：服务器未连接 / 工具未被挂载到该会话 / 模型未选择调用该工具；"
                    f"UI 工具调用块={ui_called}，页面原状冻结"
                ),
                shot_name="tool-not-invoked",
                extra={"call_log": str(CALL_LOG), "baseline": baseline},
            )
        return {
            "tool": tool,
            "server": server,
            "call_count": len(matches),
            "last_call": matches[-1],
            "ui_called_groups": ui_called,
            "ui_tool_previews": ui["toolPreviews"],
        }

    def _matching_calls(
        self, baseline: int, tool: str, expect_result: str, server: str = ""
    ) -> list[dict]:
        """读流水账基线之后的记录，按服务器/工具名/返回值过滤。"""
        if not CALL_LOG.exists():
            return []
        out: list[dict] = []
        with CALL_LOG.open(encoding="utf-8") as fh:
            for i, line in enumerate(fh):
                if i < baseline:
                    continue
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if tool and rec.get("tool") != tool:
                    continue
                if server and rec.get("server") != server:
                    continue
                if expect_result and expect_result not in str(rec.get("result", "")):
                    continue
                out.append(rec)
        return out
