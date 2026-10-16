# 04: 断言体系补全与 Python 钩子逃生舱

**What to build:** 测试工程师能用正则/元素数量断言校验更复杂的回复结构，能在 flow 中按名调用自定义 Python 钩子处理 DSL 表达不了的场景（如上传文件后校验解析结果），等待策略可按页面实际 UI 信号配置；LLM-as-Judge 的接缝在本票中预留到位。

**Blocked by:** 02（DSL schema 与引擎骨架）。

**Status:** ready-for-agent

- [ ] text_regex、element_count、hook 断言类型实现，明细写入 StepEvent
- [ ] 钩子注册表：Python 函数按名注册，DSL 引用执行，签名与报告集成约定明确
- [ ] 流式输出结束等待信号可配置（发送/停止按钮状态等 UI 信号 + 超时兜底）
- [ ] flow 级 vars 支持（测试数据与用例解耦）
- [x] judge 字段在 schema 中合法、执行时标记 skip 并在报告中呈现为 planned（2026-09-23 随票 02 后续演进交付）
- [ ] 动作原语两档制落地：语义原语 6 个 + 基础原语 6 个（SPEC D16/D19，清单见 07）
- [ ] 收口规则 schema 静态检查：flow 用到任一基础原语必须以 assert 收口，收集期报错（SPEC D19）
- [ ] 验收 flow：含文件上传钩子 + 正则断言完整跑通
