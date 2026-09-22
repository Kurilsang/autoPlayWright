# SPEC：内部 Agent 产品 UI 自动化测试框架（autoPlayWright）

> 状态：ready-for-agent（待同步至 issue tracker）
> 来源：2026-09 需求探讨（grilling 决策记录见文末附录）

## Problem Statement

公司内部 Agent 产品有 Web 端和 Electron 客户端，页面多、业务链路多。核心流程链路（会话创建、对话、工具调用结果展示、文档处理等）目前完全没有自动化覆盖，全靠手工回归，成本高且不可持续。逐条手写 UI 自动化用例不现实：页面数量大、链路数量多，且 Agent 回复由 LLM 生成、内容非确定，传统"断言固定文本"的用例写法会大量假失败。

## Solution

搭建一个分层 UI 自动化测试框架：业务链路用 YAML DSL 描述，由引擎在 pytest 内解释执行；Web 端与 Electron 客户端经由统一驱动抽象共享同一套 Page Object 与用例；断言聚焦确定性部分（组件渲染、状态流转、结构化内容）；提供 AI 半自动生成流水线——爬虫抓取页面结构产出快照，LLM 基于快照生成 DSL 草稿，人工评审后固化入库，CI 稳定回放；执行结果输出步骤级结构化 JSON（机器消费）并映射 Allure 报告（人类消费）。

核心生产闭环：**新增用例 ≈ 写/审一个 YAML 文件**，pytest 只是无感知的执行壳。

## User Stories

1. 作为测试工程师，我想用 YAML 描述一条业务链路（导航→输入→发送→断言），这样不写 Python 代码就能新增用例。
2. 作为测试工程师，我想让同一条 flow 同时在 Web 端和 Electron 客户端上执行，这样一次编写覆盖两端。
3. 作为测试工程师，我想通过 `platforms` 字段把客户端独有功能的链路标记为仅桌面端执行，这样共享链路与独有链路互不干扰。
4. 作为测试工程师，我想在 DSL 里引用集中的命名定位器而不是写裸 selector，这样页面改版只需修改定位器仓库。
5. 作为测试工程师，我想用确定性断言类型（元素可见/文本包含/正则/元素数量/自定义钩子）校验 Agent 回复的结构性行为，这样断言不因 LLM 措辞变化而抖动。
6. 作为测试工程师，我想在 flow 中调用自定义 Python 钩子（如上传文件、复杂校验），这样 DSL 表达不了的场景也能覆盖。
7. 作为测试工程师，我想让引擎自动等待 Agent 流式输出结束后再断言，这样不会因回复未生成完而误报。
8. 作为测试工程师，我想用 marker（平台/优先级/模块）筛选执行子集，这样冒烟和全量可以分开跑。
9. 作为测试工程师，我想让 AI 爬虫遍历页面并产出结构化快照（路由、交互元素、定位器候选），这样生成的 DSL 有事实依据而非猜测。
10. 作为测试工程师，我想让 LLM 基于页面快照和业务描述生成 flow 草稿，这样把"逐条编写"的成本压缩为"审核+微调"。
11. 作为测试负责人，我想以 diff/PR 形式评审 AI 生成的草稿并人工确认后才入库，这样 AI 产出不会未经把关污染用例库。
12. 作为框架维护者，我想让 pytest 自动收集 flows 目录并把每条 flow 转成一个测试用例，这样新增 YAML 无需注册任何代码。
13. 作为框架维护者，我想用 xdist 并行执行、worker 数默认 3 且上限 5，这样不会触发后端 LLM 服务限流。
14. 作为框架维护者，我想在遇到限流（429）时自动退避重试，这样偶发限流不产生假失败。
15. 作为框架维护者，我想让每条 flow 在独立新会话中执行，这样用例之间无数据依赖、可乱序并行。
16. 作为框架维护者，我想通过环境配置切换测试环境 URL 与账号，这样同一套用例可跑多套环境。
17. 作为框架维护者，我想定期重爬页面并与上次快照 diff，输出受影响的定位器/页面/链路清单，这样页面改版时能快速圈定要修的范围。
18. 作为框架维护者，我想让 Electron 支持本地 launch 安装包和 CDP attach 已运行客户端两种连接方式，这样本地调试和 CI 都能跑。
19. 作为框架维护者，我想让失败用例自动保留 trace、截图与页面快照，这样离线也能复盘失败现场。
20. 作为开发工程师，我想看到每一步的结构化结果（输入/实际输出/断言明细/耗时/截图），这样失败时能直接定位到步。
21. 作为测试平台（机器消费者），我想消费每次运行的 JSON 汇总（用例/步骤/断言三级），这样结果能接入内部看板与趋势统计。
22. 作为任何人，我想通过 Allure 看到人类可读的报告（含对话内容与截图附件），这样不懂框架也能看懂结果。
23. 作为新人，我想有一份可直接运行的示例 flow 和使用文档，这样半天内能上手写用例。
24. 作为框架维护者，我想让 flow schema 中预留 `judge` 字段且 v1 执行时标记 skip，这样后续接入 LLM-as-Judge 不需要改 DSL 结构和存量用例。

## Implementation Decisions

### 分层与模块

- `driver`：AppDriver 抽象。两种模式——Web：Playwright 直接 launch 浏览器访问测试环境 URL；桌面端：`_electron.launch` 启动安装包，或 CDP attach（`connect_over_cdp`）已运行的客户端实例。两种模式统一输出标准 Playwright `Page`。
- `locators`：定位器仓库，按页面组织的 YAML 文件。每个命名定位器含主定位器与备选定位器，选择器优先级：testid > role+name > text > css。AI 生成的候选定位器带来源标记。
- `pages`：Page Object 层。BasePage 提供通用操作（导航、发送消息、等待流式输出结束、截图），每类页面一个子类组合定位器仓库。Page Object 平台无关——共享页面两端复用，客户端独有功能单独建类，由 flow 的 `platforms` 控制生效矩阵。
- `flows`：业务链路 DSL（YAML）。schema 用 pydantic 定义与校验，非法 DSL 在 pytest 收集期即报错。核心形态（决策压缩版，源自讨论稿）：

```yaml
meta:   { id, name, platforms: [web|desktop], tags: [P0|...], owner }
vars:   { ... }                      # flow 级变量与测试数据
steps:
  - do: { page: <PageObject>, action: <方法名>, args: {...} }
  - do: { hook: <注册的 Python 函数名>, args: {...} }   # 逃生舱
  - assert: { type: visible|text_contains|text_regex|element_count|hook,
              target: ..., expected: ..., timeout: ... }
  - judge:  { ... }                  # v1 预留：校验通过但执行时标记 skip
```

- `engine`：DSL 解释器。加载 → 校验 → 顺序执行 steps（通过 Page Object 与钩子注册表）→ 持续产出 StepEvent 事件流。内置"流式输出完成"等待策略（基于可配置的 UI 信号：发送/停止按钮状态等，加超时兜底）。
- `crawler`（AI 生成侧）：Playwright 驱动的遍历器，产出页面快照 JSON（路由、语义化交互元素：role/name/testid/placeholder）+ 截图。生成器将快照 + 业务描述交给 LLM 产出 flow 草稿与定位器候选，输出为可评审的 diff。快照对比器支持重爬 diff，输出受影响的定位器/页面/链路影响清单。
- `judge`：v1 仅定义接口形状（判定上下文入参 → 评分/结论/理由的结构化出参），不实现判定逻辑；引擎遇到 `judge` 步骤标记 skip 并写入报告。
- `reporter`：StepEvent JSON 是第一公民——flow 级明细（每步的输入/实际输出/断言明细/耗时/截图引用）+ run 级汇总。Allure 为渲染层：flow=测试用例，step=allure step，JSON 与截图作为附件。
- `runner`/配置：pytest 自动收集 flows 目录并按 `platforms × tags` 参数化为测试项；环境配置（URL、账号、驱动模式）独立于用例。

### 执行与并发

- pytest-xdist 并行，默认 3 个 worker、硬上限 5（后端 LLM 服务限流约束）。
- 限流感知重试：429 类错误按退避策略重试，重试计入报告。
- 会话隔离：每条 flow 执行时新建会话，用例间无数据依赖。
- 失败时自动留存 Playwright trace、截图，路径写入 StepEvent。

### 技术栈

Python 3.11+、Playwright（同步 API）、pytest、pytest-xdist、allure-pytest、pydantic v2、PyYAML、tenacity（退避重试）。

### 关键架构决策（讨论结论）

1. 被测客户端为 Electron；Web 端与客户端共享部分前端代码，客户端有独有功能——驱动层吸收差异，之上全部平台无关。
2. AI 生成采用"半自动 + 人工固化"：爬取→生成草稿→人工评审入库→CI 回放；不做全自动探索。
3. 断言 v1 只做确定性断言；LLM-as-Judge 为既定后续计划，本框架仅预留接缝。
4. 用例载体为混合形态：DSL 描述常规链路，复杂逻辑下沉为 Python 钩子，DSL 引用钩子。
5. 报告双轨：结构化 JSON（机器）+ Allure（人类），JSON 优先。

## Testing Decisions

- **好的测试只测外部行为**：对框架自身而言，外部行为是"给定 DSL 与页面，产出确定的事件流与执行结果"。引擎测试不依赖真实内网环境，用本地静态样例站点（fixture 页面）作为夹具，验证步骤编排、等待策略、断言判定、事件流产出。
- **单测范围**：DSL schema 校验（收集期报错）、StepEvent 结构、定位器仓库解析与优先级回退、快照 schema、快照 diff 逻辑。
- **生成器测试**：爬虫快照与 LLM 草稿生成用固定快照 + 录制响应回放验证，不真实调用 LLM；真实调用仅在人工验收生成质量时进行。
- **驱动层测试**：AppDriver 双模式各需一条连通性冒烟（Web 打开样例页 / Electron 启动测试用最小壳或 attach 开发环境客户端）。
- **Prior art**：无。这是本产品的首个自动化测试资产，框架自身的测试体系随 M0 一并建立。
- **被测系统的测试策略**（框架的目标产物）：核心链路 DSL 化，v1 首期 20~50 条，按 P0/P1 分级；用例只断言页面可见行为与结构化输出，不断言 LLM 措辞。

## Out of Scope

- LLM-as-Judge 的实现（仅预留 schema 字段与接口）。
- 全自动探索式测试（AI 自主漫游页面）。
- 后端 API 造数与接口测试、性能/压测、视觉像素级回归、移动端。
- mock LLM 后端（Agent 产品必须测真实链路）。
- 测试平台/看板本体的开发（框架只负责输出标准 JSON）。
- 手工用例与自动化用例的管理映射系统。

## Further Notes

- **限流是硬约束**：所有执行侧设计（并行度、重试、排队）以"后端 LLM 服务 3~5 并发即限流"为前提。
- **风险与前置开放项**（进入 M0 前需确认）：
  - 登录方式：SSO/验证码如何自动化登录，测试账号从哪来。
  - Electron 可执行文件在 CI 上的获取方式（固定安装路径？构建产物下载？）与版本管理和 Playwright 兼容性。
  - 内部 LLM 网关用于草稿生成的选型与配额。
- 里程碑建议：M0 骨架（驱动双模式 + BasePage + 引擎 + JSON/Allure 报告 + 1 条手写 flow 跑通）→ M1 核心链路覆盖（20~50 条）→ M2 AI 生成流水线（爬虫 + 草稿 + 评审流程）→ M3 快照 diff/影响分析 + Judge 接入。
- 本 spec 按用户选择落盘于仓库内 `docs/`，后续如接入 issue tracker 应迁移并打 `ready-for-agent` 标签。

---

## 附录：决策记录（grilling 结论）

| # | 决策点 | 结论 |
|---|--------|------|
| D1 | 客户端技术栈 | Electron；与 Web 共享部分前端代码，客户端有独有功能 |
| D2 | AI 生成模式 | 半自动生成 + 人工固化（b） |
| D3 | 断言策略 | v1 仅确定性断言；LLM-as-Judge 列入后续计划 |
| D4 | 用例载体 | 混合：YAML DSL 为主 + Python 钩子逃生舱（c） |
| D5 | 分层结构 | cases / flows / pages / locators / driver / judge / reporter 七层 |
| D6 | 报告 | JSON 第一公民 + Allure 渲染（c） |
| D7 | 环境与并发 | 独立测试环境；xdist 默认 3、上限 5（限流约束） |
| D8 | spec 去向 | 本地 `docs/SPEC.md`（b） |
