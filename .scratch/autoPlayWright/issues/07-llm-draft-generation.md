# 07: LLM 草稿生成与人工评审流程

> **2026-09-22 人工预演完成**：本会话 AI 已按本票工作流手工走通一遍——爬取真实 Aml Agent 页面（含新手引导弹窗发现与处理）、生成 `locators/aml_chat.yaml`（source: ai）与 `AmlChatPage`（双信号流式等待）、产出 `flows/aml_chat_smoke.yaml` 并在真实环境绿灯。产品化（爬虫器 + 生成器 + 评审 diff 工具）仍按本票验收标准实施，预演产物可直接作为生成器的黄金样本。

**What to build:** 维护者提供页面快照与业务描述，LLM 生成 flow YAML 草稿与带 AI 标记的定位器候选，以可评审 diff 形式输出；人工审核修正确认后入库，即可被引擎直接执行。AI 与人写同一种 DSL，评审是把关点，AI 产出永不绕过人直接污染用例库。

**Blocked by:** 04（DSL 完整形态与钩子）、06（页面快照输入）。

**Status:** ready-for-agent

- [ ] 内部 LLM 网关选型与配额确认（对应 spec 开放项 3）
- [ ] 生成器：快照 + 业务描述 → flow 草稿，产出必过 schema 校验
- [ ] 动作原语库落地（两档制）+ 收口规则 schema 静态检查（见下）
- [ ] AI 定位器候选带来源标记并入定位器仓库，遵循既有选择器优先级
- [ ] 草稿以 diff/PR 形式输出供评审，评审通过后入库即可执行
- [ ] 生成器以 opencode skill 形式固化（prompt 资产入库）
- [ ] 失败修复 diff 流：取证（归因/复现/冻结截图/上下文）→ 修复 diff → 人审合入
- [ ] 草稿入库过验收门（D15 分期：v1 = schema + ruff + 真实环境绿跑 ≥3 次）
- [ ] 生成器测试用固定快照 + 录制响应回放，不真实调用 LLM
- [ ] 端到端验收：一条 AI 草稿经人工微调后在 CI 绿灯

## 已定设计（2026-09-23 grilling，SPEC D10/D12/D14/D15/D16/D19）

- **载体**（D14）：生成侧以 opencode skill/命令承载（prompt 资产沉淀为 skill），稳定后升级无人值守 CLI/SDK；pi agent 不引入（避免双生成方 prompt 漂移）
- **动作原语两档制**（D16/D19）：
  - 语义原语（含链路级完成判定/取证，生成器优先产）：`new_session` / `dismiss_popups` / `confirm_dialog` / `send_message` / `wait_reply_done` / `capture_context`
  - 基础原语（元素级，成功=locator 状态）：`click` / `fill` / `press` / `select` / `upload` / `wait_visible`
  - **收口规则**：flow 用到任一基础原语必须以 `assert` 收口（schema 收集期静态检查）；「点了就算成功」不得成为 pass 依据
- **AI 权限边界**（D10）：AI 只修资产、不改现场——失败取证 → 产出修复 diff → 人工审合入；禁止运行时自适应/自愈
- **工作区脚本**（D12）：`workspace/` 临时产，跑通产物归档 `.scratch/` 当黄金样本/素材；升格 `scripts/` 需人工判定
- **入库验收门分期**（D15）：v1 = schema + ruff + 真实环境绿跑 ≥3 次（防偶发卡死污染）；生成器稳定后加固定快照回放测试
