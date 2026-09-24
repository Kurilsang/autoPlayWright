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
- `src/apw/` — 分层：dsl（schema 校验）→ engine（FlowRunner 产 StepEvent）→ pages → locators → driver（Web/Electron 统一输出 Page）→ reporter（JSON 第一公民）→ pytest_plugin；`apw.crawler` 生成侧快照爬虫（含 `page: probe` 探查原语）
- `configs/envs/*.yaml` — 环境配置（`--apw-env` 选择；fixture=本地夹具站点）
- `configs/crawl/*.yaml` — 爬取配置（状态路径 + 完成信号探针，喂生成器）
- `scripts/` — 生成侧工具脚本（快照摘要等，AI 复用）
- `reports/` — 运行产物（gitignored；`report.html` 会话结束自动渲染）；`docs/SPEC.md` — 规格与决策记录
- `.scratch/autoPlayWright/issues/` — 主建任务票（01~08，依赖序）；`.scratch/review-p0/` — 评审修复批（spec + 票 + P1/P2 backlog）；完成即勾验收框并标 done
- commit 格式：`feat/fix: 一句话` + `- 要点`，极简

## 硬约束

- 并行执行 worker 上限 5（后端 LLM 限流，3~5 并发即限流）
- 只断言确定性内容（组件/状态/结构），不断言 LLM 措辞
- **失败即取证，禁止自愈**：卡死/半截渲染判 fail 并冻结现场（归因/复现/信号时间线/冻结截图随 EvidenceError 入报告），不做自动重载/重试把偶发缺陷跑绿
- 引擎不 import pytest/allure；报告与 pytest 只是引擎下游消费者
- 页面元素一律走定位器仓库，禁止散落裸 selector
- **凭据与内部信息永不入库**：账号密码走 `configs/secrets.local.yaml`（gitignored）或 CI 环境变量 `APW_USERNAME`/`APW_PASSWORD`；内网 URL/域名/IP/API/产品名/个人信息在提交内容与快照产物中一律以占位符呈现（环境真实值只在本地 `configs/envs/test.yaml`）；快照/探查产物落盘自动脱敏（`apw.sanitize`，映射 `configs/sanitize.local.yaml` 真实串仅存本地 + 通用模式兜底）

## 当前状态（2026-09-24）

- 票 01/02 已交付；T07 预演产物已产品化：`locators/aml_chat.yaml` + `AmlChatPage` + `flows/aml_chat_smoke.yaml`（真实环境冒烟持续绿灯）
- 票 06 爬虫快照器已交付：`python -m apw.crawler` 状态化爬取（D20 快照骨架），产物入 `.scratch/autoPlayWright/snapshots/`；另有 `page: probe` 探查原语（生成侧保留名，goto/click/type/insert/dump_dom，未知页面首轮探查用，流程用例禁用）与 `scripts/snapshot_summary.py` 快照摘要工具
- 工作流功能（`/workflows` 编辑器）资产已入库：`locators/aml_workflow.yaml` + `AmlWorkflowPage` + `configs/crawl/workflow{,_probe}.yaml` + 4 条 flows——手动写码保存运行（非 AI 编码）/ AI 编写生成运行 / 并发 2 个 AI 生成任务 / 并发 2 个 AI 运行任务（并发 UI 校验：逐标签身份核对，串台/卡死判 fail 冻结取证）
- 回复判定 = **完整回答六信号**（停止消失/推理步骤/最终答案/操作行/稳定/加载清除）；`capture_context` 把对话上下文（输入/推理步骤/思考过程/最终答案）写入报告证据
- 失败取证：EvidenceError 带归因分类（hang_loading/streaming_stuck/reply_incomplete/content_unstable + gen_stuck/gen_incomplete/run_stuck/run_incomplete/identity_mismatch）+ 复现 + 信号时间线 + 冻结截图
- 测试环境地址在本地 `configs/envs/test.yaml`（gitignored，模板 `test.example.yaml`）；正式环境**勿跑测试/爬取**；测试环境免登录直达会话页
- 已知产品缺陷：「加载对话历史中」偶发卡死（前端），复现线索=新建会话→确认 Agent 类型弹窗→随即发送；测试判 fail 取证待产品侧修复
- 已知产品行为：工作流编辑器为 React 受控输入，`fill` 不触发 onChange（会静默空提交）——输入一律真实键入（type/insert_text）；运行跑的是服务端已保存版本，手动改动必须先「保存工作流」
- 测试基线：`pytest tests` 全绿（框架自测，含证据链路/失败取证/三态报告/脱敏用例）；工作流 4 条链路真实环境 3 次绿跑
- 评审修复批次 P0 已交付（`.scratch/review-p0/`，6 票全 done）：prepare 失败与空步骤终态留痕、报告三态 + 跳过原因、run 目录唯一化 + 汇总合并、快照脱敏管道、定位器计数与解析同链
- 留空待输入：仅 Electron 安装包 launch（T03，CDP attach 可用）
- 下一步：评审 P1/P2（见 `.scratch/review-p0/backlog.md`）→ 04 原语库（两档制 + 收口规则）→ 07 生成器（opencode skill）→ 08；业务用例扩量（v1 目标 20~50 条）
