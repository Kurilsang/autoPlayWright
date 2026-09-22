# 02: DSL→pytest→JSON 报告最小全链路（核心 tracer bullet）

**What to build:** 测试工程师新增一个 YAML 文件，即能让一条手写业务链路（新建会话→发送消息→等待流式输出结束→断言回复区出现）在 Web 端被 pytest 自动收集执行，并在报告中看到步骤级结构化结果。从此「新增用例 ≈ 写 YAML」成立，pytest 是无感知执行壳。

**Blocked by:** 01（登录与 Web 驱动）。

**Status:** ready-for-agent

- [ ] flow DSL 最小 schema（meta/vars/steps）定义并用 pydantic 校验，非法 DSL 在 pytest 收集期即报错
- [ ] 定位器仓库：DSL 只引用命名定位器，选择器优先级 testid > role+name > text > css
- [ ] 引擎执行 do/assert 步骤，内置流式输出结束等待的最小策略（超时兜底）
- [ ] pytest 自动收集 flows 目录并按 web 平台参数化为测试项，无需注册代码
- [ ] StepEvent JSON（flow 级明细 + run 级汇总）与 Allure 报告（步骤划分、附件）产出
- [ ] 示例 flow 与新人上手文档可完整跑通

schema 决策压缩版（源自 spec 讨论）：

```yaml
meta:   { id, name, platforms: [web|desktop], tags: [P0|...], owner }
vars:   { ... }
steps:
  - do: { page: <PageObject>, action: <方法名>, args: {...} }
  - assert: { type: visible|text_contains, target: ..., expected: ..., timeout: ... }
```
