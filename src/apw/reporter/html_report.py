"""内置 HTML 渲染层：把 run 目录（run-summary.json + flow 明细）渲染成单文件报告。

零第三方依赖；报告与 flow 明细同目录，截图用相对路径引用。
命令行重渲染：python -m apw.reporter.html_report reports/<run_id>
"""
from __future__ import annotations

import html
import json
import sys
from datetime import datetime
from pathlib import Path

_STATUS_BADGE = {
    "passed": ('✓', "#0a7d32", "#e6f6ec"),
    "failed": ('✗', "#c62828", "#fdeaea"),
    "planned": ('○', "#8a6d00", "#fff7dc"),
    "skipped": ('-', "#5f6368", "#eceff1"),
}

_CSS = """
:root { --bg:#f6f8fa; --card:#fff; --line:#e4e7eb; --text:#1f2328; --muted:#5f6368; }
* { box-sizing: border-box; }
body { font-family: "Segoe UI", "Microsoft YaHei", sans-serif; background: var(--bg);
       color: var(--text); margin: 0; padding: 24px; }
.wrap { max-width: 1080px; margin: 0 auto; }
h1 { font-size: 20px; } h2 { font-size: 16px; margin: 8px 0; }
.meta { color: var(--muted); font-size: 13px; margin-bottom: 16px; }
.totals { display: flex; gap: 12px; margin-bottom: 20px; }
.total { background: var(--card); border: 1px solid var(--line); border-radius: 8px;
         padding: 12px 20px; font-size: 22px; font-weight: 600; }
.total span { display: block; font-size: 12px; color: var(--muted); font-weight: 400; }
.card { background: var(--card); border: 1px solid var(--line); border-radius: 8px;
        margin-bottom: 16px; overflow: hidden; }
.head { display: flex; align-items: center; gap: 10px; padding: 12px 16px;
        border-bottom: 1px solid var(--line); }
.badge { padding: 2px 10px; border-radius: 99px; font-size: 12px; font-weight: 600; }
.dur { color: var(--muted); font-size: 12px; margin-left: auto; }
table { width: 100%; border-collapse: collapse; font-size: 13px; }
th, td { text-align: left; padding: 8px 16px; border-bottom: 1px solid var(--line);
         vertical-align: top; }
th { color: var(--muted); font-weight: 500; background: #fafbfc; }
td.i { color: var(--muted); width: 40px; }
pre { background: #f6f8fa; border: 1px solid var(--line); border-radius: 6px;
      padding: 8px 12px; white-space: pre-wrap; word-break: break-word;
      font-size: 12px; margin: 6px 0 0; }
img.shot { max-width: 480px; border: 1px solid var(--line); border-radius: 6px;
           margin: 8px 0 0; display: block; }
.ctx { margin: 8px 0 0; border: 1px dashed var(--line); border-radius: 6px;
       padding: 8px 12px; }
.ctx .role { font-size: 11px; color: var(--muted); font-weight: 600; margin: 8px 0 0; }
.ctx .role:first-child { margin-top: 0; }
"""

_TEMPLATE = """<!doctype html>
<html lang="zh"><head><meta charset="utf-8">
<title>apw 测试报告 {run_id}</title><style>{css}</style></head>
<body><div class="wrap">
<h1>apw 测试报告</h1>
<div class="meta">run_id: {run_id} · 生成时间: {generated}</div>
<div class="totals">
  <div class="total">{total}<span>总数</span></div>
  <div class="total" style="color:#0a7d32">{passed}<span>通过</span></div>
  <div class="total" style="color:#c62828">{failed}<span>失败</span></div>
</div>
{flow_sections}
</div></body></html>"""

_FLOW_SECTION = """
<div class="card" id="{flow_id}">
  <div class="head">
    <span class="badge" style="color:{c};background:{bg}">{icon} {status}</span>
    <h2>{name}</h2>
    <span class="meta">{flow_id} · platforms: {platforms}</span>
    <span class="dur">{duration_ms} ms</span>
  </div>
  <table>
    <tr><th>#</th><th>类型</th><th>步骤</th><th>耗时</th><th>结果</th></tr>
    {rows}
  </table>
</div>"""

_ROW = """<tr>
  <td class="i">{index}</td><td>{kind}</td><td>{detail}</td><td>{duration_ms} ms</td>
  <td><span class="badge" style="color:{c};background:{bg}">{icon} {status}</span>
      {extra}</td>
</tr>"""


def _esc(text: str) -> str:
    return html.escape(str(text), quote=True)


def _badge(status: str) -> tuple[str, str, str]:
    icon, color, bg = _STATUS_BADGE.get(status, ('?', "#5f6368", "#eceff1"))
    return icon, color, bg


def _turn_text(turn: dict) -> str:
    """把一轮对话规整为可读文本：用户输入 / 推理步骤 + 思考过程 + 最终答案。"""
    if turn.get("role") == "user":
        return str(turn.get("text", ""))
    blocks = []
    if turn.get("reasoning_steps"):
        blocks.append(f"[推理步骤]\n{turn['reasoning_steps']}")
    if turn.get("thinking"):
        blocks.append(f"[思考过程]\n{turn['thinking']}")
    blocks.append(f"[最终答案]\n{turn.get('final_answer') or turn.get('answer') or ''}")
    return "\n\n".join(blocks)


def _render_evidence(evidence: dict) -> str:
    """渲染动作采集证据：对话上下文按轮展示、归因数据 JSON、冻结截图内嵌。"""
    parts = []
    turns = evidence.get("turns") or []
    if turns:
        parts.append(f'<div class="role">上下文采集 · {len(turns)} 轮</div>')
        for turn in turns:
            role = "用户输入" if turn.get("role") == "user" else "回答"
            ts = turn.get("timestamp") or evidence.get("captured_at", "")
            head = f"{role} · {ts}" if ts else role
            parts.append(
                f'<div class="role">{_esc(head)}</div><pre>{_esc(_turn_text(turn))}</pre>'
            )
    rest = {
        k: v
        for k, v in evidence.items()
        if k not in {"turns", "screenshots", "url", "captured_at", "turn_count"}
    }
    if rest:
        parts.append(
            '<div class="role">归因与复现</div>'
            f'<pre>{_esc(json.dumps(rest, ensure_ascii=False, indent=2))}</pre>'
        )
    if not parts:
        parts.append(
            f'<pre>{_esc(json.dumps(evidence, ensure_ascii=False, indent=2))}</pre>'
        )
    for shot in evidence.get("screenshots") or []:
        name = Path(str(shot)).name
        parts.append(f'<img class="shot" src="{_esc(name)}" alt="冻结截图 {_esc(name)}">')
    return f'<div class="ctx">{"".join(parts)}</div>'


def _render_row(event: dict) -> str:
    icon, color, bg = _badge(event.get("status", ""))
    extra = ""
    if event.get("evidence"):
        extra += _render_evidence(event["evidence"])
    if event.get("error"):
        extra += f'<pre>{_esc(event["error"])}</pre>'
    if event.get("screenshot"):
        shot = Path(event["screenshot"])
        extra += (f'<img class="shot" src="{_esc(shot.name)}" '
                  f'alt="失败截图 {_esc(shot.name)}">')
    return _ROW.format(
        index=event.get("index", ""), kind=_esc(event.get("kind", "")),
        detail=_esc(event.get("detail", "")) or "&mdash;",
        duration_ms=event.get("duration_ms", 0), icon=icon, c=color, bg=bg,
        status=_esc(event.get("status", "")), extra=extra,
    )


def _render_flow(detail_path: Path) -> str:
    flow = json.loads(detail_path.read_text(encoding="utf-8"))
    icon, color, bg = _badge(flow.get("status", ""))
    rows = "\n".join(_render_row(e) for e in flow.get("events", []))
    return _FLOW_SECTION.format(
        flow_id=_esc(flow.get("flow_id", "")), name=_esc(flow.get("name", "")),
        status=_esc(flow.get("status", "")), icon=icon, c=color, bg=bg,
        platforms=_esc(", ".join(flow.get("platforms", []))),
        duration_ms=flow.get("duration_ms", 0), rows=rows,
    )


def render_html(run_dir: str | Path) -> Path:
    """渲染 run 目录为 report.html，返回报告路径。"""
    run_dir = Path(run_dir)
    summary_path = run_dir / "run-summary.json"
    if not summary_path.exists():
        raise FileNotFoundError(f"缺少 run-summary.json: {run_dir}")
    summary = json.loads(summary_path.read_text(encoding="utf-8"))

    sections = []
    for item in summary.get("flows", []):
        detail = run_dir / item.get("detail", "")
        if detail.exists():
            sections.append(_render_flow(detail))

    html_text = _TEMPLATE.format(
        run_id=_esc(summary.get("run_id", "")),
        generated=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        css=_CSS, total=summary.get("total", 0),
        passed=summary.get("passed", 0), failed=summary.get("failed", 0),
        flow_sections="\n".join(sections),
    )
    out = run_dir / "report.html"
    out.write_text(html_text, encoding="utf-8")
    return out


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("用法: python -m apw.reporter.html_report <run_dir>")
        raise SystemExit(2)
    print(render_html(sys.argv[1]))
