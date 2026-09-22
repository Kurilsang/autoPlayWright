# AGENTS.md

内部 Agent 产品（Web + Electron 客户端）的 UI 自动化测试框架：业务链路用 YAML DSL 描述，pytest 插件自动收集执行，输出结构化 JSON + Allure 报告。

## 怎么跑

```powershell
python -m venv .venv
.venv\Scripts\pip install -e ".[dev]"
.venv\Scripts\playwright install chromium

.venv\Scripts\pytest tests          # 框架自测（含浏览器端到端，走本地夹具站点）
.venv\Scripts\pytest flows          # 业务链路（默认 --apw-env fixture）
.venv\Scripts\pytest tests flows    # 全部
.venv\Scripts\ruff check src tests  # lint（提交前必须过）
```

## 技术栈

Python 3.11+ / Playwright（同步 API）/ pytest 9（pytest11 插件入口）/ pydantic v2 / PyYAML / allure-pytest。

## 目录与约定

- `flows/*.yaml` — 业务链路用例（meta/steps：do·assert·judge，judge 为 v1 预留标记 planned）
- `locators/*.yaml` — 命名定位器仓库，候选优先级 testid > role+name > text > css/xpath
- `src/apw/` — 分层：dsl（schema 校验）→ engine（FlowRunner 产 StepEvent）→ pages → locators → driver（Web/Electron 统一输出 Page）→ reporter（JSON 第一公民）→ pytest_plugin
- `configs/envs/*.yaml` — 环境配置（`--apw-env` 选择；fixture=本地夹具站点）
- `reports/` — 运行产物（gitignored）；`docs/SPEC.md` — 规格与决策记录
- `.scratch/autoPlayWright/issues/` — 任务票（01~08，依赖序），完成即勾验收框并标 done
- commit 格式：`feat/fix: 一句话` + `- 要点`，极简

## 硬约束

- 并行执行 worker 上限 5（后端 LLM 限流，3~5 并发即限流）
- 只断言确定性内容（组件/状态/结构），不断言 LLM 措辞
- 引擎不 import pytest/allure；报告与 pytest 只是引擎下游消费者
- 页面元素一律走定位器仓库，禁止散落裸 selector

## 当前状态（2026-09-22）

- 票 02（DSL→pytest→JSON tracer bullet）已交付；25 测试全绿
- 留空待输入：登录方案（T01，SSO/账号）、Electron 安装包 launch（T03，CDP attach 可用）
- 下一步：T01（当前唯一前沿票）→ T03/T04/T05/T06 并行 → T07/T08
