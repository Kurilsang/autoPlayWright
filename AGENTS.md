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
.venv\Scripts\pytest flows --apw-headed --apw-slowmo 250  # 调试：窗口可见 + 放慢动作
.\run_debug.bat                                          # 同上一键调试（可透传 pytest 参数）
.venv\Scripts\python -m apw.crawler --env test --config configs/crawl/aml_chat.yaml   # 页面状态快照（票 06）
.venv\Scripts\ruff check src tests  # lint（提交前必须过）
```

## 技术栈

Python 3.11+ / Playwright（同步 API）/ pytest 9（pytest11 插件入口）/ pydantic v2 / PyYAML / allure-pytest。

## 目录与约定

- `flows/*.yaml` — 业务链路用例（meta：platforms/envs/tags，steps：do·assert·judge，judge 为 v1 预留标记 planned）
- `locators/*.yaml` — 命名定位器仓库，候选优先级 testid > role+name > placeholder/label > text > css/xpath
- `src/apw/` — 分层：dsl（schema 校验）→ engine（FlowRunner 产 StepEvent）→ pages → locators → driver（Web/Electron 统一输出 Page）→ reporter（JSON 第一公民）→ pytest_plugin
- `configs/envs/*.yaml` — 环境配置（`--apw-env` 选择；fixture=本地夹具站点）
- `reports/` — 运行产物（gitignored；`report.html` 会话结束自动渲染）；`docs/SPEC.md` — 规格与决策记录
- `.scratch/autoPlayWright/issues/` — 任务票（01~08，依赖序），完成即勾验收框并标 done
- commit 格式：`feat/fix: 一句话` + `- 要点`，极简

## 硬约束

- 并行执行 worker 上限 5（后端 LLM 限流，3~5 并发即限流）
- 只断言确定性内容（组件/状态/结构），不断言 LLM 措辞
- **失败即取证，禁止自愈**：卡死/半截渲染判 fail 并冻结现场（归因/复现/信号时间线/冻结截图随 EvidenceError 入报告），不做自动重载/重试把偶发缺陷跑绿
- 引擎不 import pytest/allure；报告与 pytest 只是引擎下游消费者
- 页面元素一律走定位器仓库，禁止散落裸 selector
- **凭据永不入库**：本地 `configs/secrets.local.yaml`（gitignored）或 CI 环境变量 `APW_USERNAME`/`APW_PASSWORD`

## 当前状态（2026-09-23）

- 票 01/02 已交付；T07 预演产物已产品化：`locators/aml_chat.yaml` + `AmlChatPage` + `flows/aml_chat_smoke.yaml`（真实环境冒烟持续绿灯）
- 票 06 爬虫快照器已交付：`python -m apw.crawler` 状态化爬取（D20 快照骨架），产物入 `.scratch/autoPlayWright/snapshots/`；真实环境 4 状态快照**待人工检查**（票面唯一未勾项）
- 回复判定 = **完整回答六信号**（停止消失/推理步骤/最终答案/操作行/稳定/加载清除）；`capture_context` 把对话上下文（输入/推理步骤/思考过程/最终答案）写入报告证据
- 失败取证：EvidenceError 带归因分类（hang_loading/streaming_stuck/reply_incomplete/content_unstable）+ 复现 + 信号时间线 + 冻结截图
- 测试环境 `http://10.28.28.134:3000/`（免登录）；`aml-agent.amlogic.com` 是正式环境，**勿跑测试**
- 已知产品缺陷：「加载对话历史中」偶发卡死（前端），复现线索=新建会话→确认 Agent 类型弹窗→随即发送；测试判 fail 取证待产品侧修复
- 测试基线：`pytest tests` 全绿（框架自测，含证据链路与失败取证用例）；真实环境冒烟通过
- 留空待输入：仅 Electron 安装包 launch（T03，CDP attach 可用）
- 下一步：04 原语库（两档制 + 收口规则）→ 07 生成器（opencode skill）→ 08；业务用例扩量（v1 目标 20~50 条）
