# 03: 准备失败留痕

**What to build:** 测试工程师复盘时不再看到「凭空消失」的 flow：准备阶段（导航）失败也产出失败步骤事件（错误文本 + 失败截图 + 证据字段），flow 结果必被构建、报告器必被调用，明细 JSON 落入 run 目录。失败事件与步骤失败一样携带截图与证据字段，既有取证能力不回退。

**Blocked by:** None (can start immediately)

**Status:** done

- [x] 主缝：准备回调抛错 → 产生失败事件（status=failed、error 非空）且明细 JSON 存在于 run 目录
- [x] 失败事件带截图（尽力而为）与证据字段，结构与步骤失败一致
- [x] 准备失败的 flow 状态为 failed 并计入 run 汇总 failed
- [x] 既有取证能力回归全绿（归因分类/复现信息/信号时间线/冻结截图/对话上下文）

## Comments
- 2026-09-24 交付：prepare 纳入事件模型（StepEvent kind 增补 `prepare`），失败即留痕；`FlowResult.from_spec` 统一三处终态装配。
- code-review 复核修正：原证据断言恒真（isinstance dict），已加强为双用例——普通异常 evidence == {}，prepare 抛 EvidenceError 时结构化证据原样入事件（与步骤失败同构）。
