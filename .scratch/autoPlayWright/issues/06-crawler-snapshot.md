# 06: 爬虫快照器（AI 生成的地基）

**What to build:** 框架维护者运行爬取命令，框架基于驱动与登录态遍历测试环境页面，产出语义化页面快照 JSON（路由、可交互元素的 role/name/testid/placeholder）与截图存档。快照是后续 AI 生成 flow 草稿的事实依据，也是页面改版 diff 的基线。

**Blocked by:** 01（驱动与登录态，可与 02~05 并行推进）。

**Status:** in-progress（爬取器已交付，待人工检查与 08 基线固化）

> 运行：`python -m apw.crawler --env test --config configs/crawl/aml_chat.yaml [--headed] [--slowmo 250]`；示例配置 `configs/crawl/{fixture_chat,aml_chat}.yaml`；快照产物 `.scratch/autoPlayWright/snapshots/<env>/`（git 版本化）。

- [x] 遍历器复用 AppDriver，遍历入口与范围可配置（爬取配置 YAML：targets × 状态步骤）
- [x] 快照 JSON schema 定义并校验（`src/apw/crawler/schema.py`，pydantic）
- [x] 快照按**状态**采集（`state_path` 标注到达路径，同页面多状态多份快照）
- [x] `elements[].candidates` 按选择器优先级产出，可直接映射 `locators/` 格式
- [x] `signals` 完成信号在场性采集（在场=可见，隐藏元素不计；喂完成判定类原语的生成）
- [x] 每个页面快照附截图存档，路径写入快照文件
- [ ] 对会话链路相关页面实际爬取一次，产出快照并人工检查语义合理性（2026-09-23 已产出 4 状态快照，**待人工检查**）
- [x] 快照文件可版本化管理（`.scratch/autoPlayWright/snapshots/` 入 git，作为 08 的 diff 基线）

## 已定设计（2026-09-23 grilling，SPEC D18/D20）

- 工作区约定：AI 临时脚本跑在 `workspace/`（gitignored），产物归档 `.scratch/` 作生成器素材与 diff 基线原料
- **每页面状态一份快照**，`state_path` 标注到达路径（如 `new_session → agent_mode:专家模式/confirmed → done`）——弹窗/流式/完成态等「状态里的结构」必须分别采集
- 快照 JSON 骨架（schema_version 1）：

```json
{
  "schema_version": 1,
  "env": "test",
  "route": "/chat/:id",
  "url": "…/chat/<id>",
  "state_path": ["new_session", "agent_mode:专家模式/confirmed", "send:…", "done"],
  "captured_at": "2026-09-23T15:30:00",
  "elements": [
    {
      "name_hint": "message_input",
      "region": "composer|message_list|header|dialog|sidebar",
      "role": "textbox", "accessible_name": "", "testid": "", "placeholder": "…",
      "tag": "textarea", "classes": ["…"], "text": "",
      "interactable": true, "visible": true,
      "candidates": [{ "by": "placeholder", "value": "…" }, { "by": "css", "value": "…" }]
    }
  ],
  "signals": { "stop_button": false, "final_answer_card": true, "loading": false },
  "screenshots": ["….png"],
  "dom_excerpt": "…可选状态片段"
}
```

- 字段宁多勿缺：`candidates` 直接落 `locators/` 现成格式；`signals` 喂 `wait_reply_done` 类原语生成；`region` 供语义组装；`dom_excerpt` 可选保留（弹窗类状态光靠 elements 不够直观）
