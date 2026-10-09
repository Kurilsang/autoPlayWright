# 用例进度总览

业务链路（`flows/*.yaml`）与框架自测（`tests/`）的清单与状态。新增/改动用例后同步本页；
链路数量以收集结果为准：`pytest flows --collect-only -q`、`pytest tests --collect-only -q`。

> 判定口径、失败取证规则、已知产品缺陷的完整叙述以 `AGENTS.md` 为准，本页只做清单与进度映射。

**统计（2026-10-09）**：业务链路 13 条（真实/桌面环境 12 条 + fixture 示例 1 条）；
框架自测 13 个文件 84 个用例。测试基线：`pytest tests` 全绿；真实环境链路均已 3 次绿跑。

## 一、业务链路清单

### 对话与会话

| flow | id | 平台/环境 | 步数 | 覆盖场景 | 状态 |
|------|----|-----------|------|----------|------|
| `aml_chat_smoke.yaml` | aml-chat-smoke | web / test | 14 | 新建对话 → 发送 → 完整回答判定 → `capture_context` 证据 | 真实环境持续绿灯（2026-09-22 交付） |
| `chat_concurrent_switch.yaml` | chat-concurrent-switch | web / test | 21 | 双会话并行生成 + 来回切换逐会话身份核对（URL 锚点 / 输入回显 / 对方标记零混入） | 3 次绿跑（2026-09-28） |
| `desktop_chat_smoke.yaml` | desktop-chat-smoke | desktop / desktop | 13 | 桌面客户端：新建任务 → 发送 → 完整回答判定 → Thought 展开核对 | 3 次绿跑（2026-10-08） |
| `example_chat.yaml` | example-chat | web / fixture | 7 | 示例链路（本地夹具站点，DSL 范例 + 引擎端到端素材） | 随 `pytest tests` 端到端覆盖 |

### 工作流（/workflows 编辑器）

| flow | id | 平台/环境 | 步数 | 覆盖场景 | 状态 |
|------|----|-----------|------|----------|------|
| `workflow_manual.yaml` | workflow-manual | web / test | 11 | 手动写码保存并运行（非 AI 编码） | 3 次绿跑（2026-09-24 交付） |
| `workflow_ai_coding.yaml` | workflow-ai-coding | web / test | 10 | AI 编写生成工作流并运行 | 3 次绿跑（2026-09-24 交付） |
| `workflow_ai_concurrent_publish.yaml` | workflow-ai-concurrent-publish | web / test | 5 | 并发 2 个 AI 生成任务，逐标签身份核对（串台/卡死判 fail 冻结取证） | 3 次绿跑（2026-09-24 交付） |
| `workflow_ai_concurrent_run.yaml` | workflow-ai-concurrent-run | web / test | 5 | 并发 2 个 AI 运行任务，逐标签身份核对 | 3 次绿跑（2026-09-24 交付） |

### 广场与场景

| flow | id | 平台/环境 | 步数 | 覆盖场景 | 状态 |
|------|----|-----------|------|----------|------|
| `skill_market_upload_download.yaml` | skill-market-upload-download | web / test | 17 | Skills 广场：私人 skill 上传回显/预览 + 广场下载 + 筛选标签核对 | 3 次绿跑（2026-09-29） |
| `suite_plaza_create.yaml` | suite-plaza-create | web / test | 32 | 套组新建 2 入口 × 2 模式 + 回显刷新 + 单击预览 + 公开库无泄漏（仅私有） | 3 次绿跑（2026-09-29） |
| `report_style_browse.yaml` | report-style-browse | web / test | 28 | 报告样式库：进入/预览/8 类标签切换逐一核对筛选收敛 | 3 次绿跑（2026-09-29） |
| `report_style_copy_run.yaml` | report-style-copy-run | web / test | 16 | 做同款跳转 → 运行 → 工作区产物落位（recipients 恒留空） | 3 次绿跑（2026-09-29） |
| `playground_suite_debug.yaml` | playground-suite-debug | web / test | 14 | 操练场：建私有套组 → 绑定套组新建会话（身份锚三连）→ 测试套组模式对话调试 | 3 次绿跑（2026-09-30） |

## 二、框架自测清单（`pytest tests`）

| 文件 | 覆盖面 | 用例数 |
|------|--------|--------|
| `test_schema.py` | DSL schema：合法/非法 flow 解析、assert 动作 | 14 |
| `test_engine_fixture_site.py` | 引擎端到端（DSL→引擎→事件流）、失败路径、证据采集、prepare 失败、三态汇总 | 14 |
| `test_locator_repo.py` | 定位器仓库：加载、候选优先级、软计数同链、多元素解析 | 11 |
| `test_sanitize.py` | 脱敏器：敏感串→占位符、结构保留、映射加载 | 11 |
| `test_probe_page.py` | 探查原语（生成侧）+ 爬虫 probe 通道 | 9 |
| `test_base_page.py` | BasePage 纯函数：未达成归因分类、标记段拆分 | 8 |
| `test_crawler_schema.py` | 爬虫配置与快照 schema | 5 |
| `test_crawler_fixture_site.py` | 爬虫端到端：状态推进→逐状态快照（票 06） | 3 |
| `test_json_report.py` | run 目录唯一化 + 汇总合并语义 | 3 |
| `test_html_report.py` | HTML 单文件报告渲染 | 3 |
| `test_plugin_skip_report.py` | 插件跳过留痕贯通到 run 汇总 | 1 |
| `test_real_login.py` | T01 真实环境登录连通冒烟（仅 `--apw-env test` 执行，其余环境 skip 留痕） | 1 |
| `test_no_secrets.py` | 入库红线门禁：无内网 IP / 凭据值 / 产品名 | 1 |
| **合计** | | **84** |

## 三、判定与取证口径（摘要）

- 回复判定：web 端 = 完整回答六信号；桌面端 = 停止生成消失 / 回答气泡 / Thought 块在场 / 操作行 / 稳定 + `expand_thinking` 展开核对。
- 只断言确定性内容（组件/状态/结构）；LLM 产出只进 `capture_context` 证据。
- 失败即取证、禁止自愈：EvidenceError 带归因分类 + 复现 + 信号时间线 + 冻结截图。
- 平台矩阵：`platforms: [desktop]` 的链路在 web 环境自动 skip 并留痕。

## 四、已知产品缺陷/行为 → 受影响用例

| 已知项（详见 AGENTS.md） | 受影响用例 | 用例侧处理 |
|--------------------------|------------|------------|
| 「加载对话历史中」偶发卡死（前端） | aml_chat_smoke、chat_concurrent_switch | 判 fail 冻结取证，不重试跑绿 |
| Skills 广场缺失包下载 404 静默失败 | skill_market_upload_download | 逐卡尝试取一次成功，404 尝试随证据留痕 |
| 套组英文名/英文描述静默必填 + 提交须停在「基本信息」 | suite_plaza_create、playground_suite_debug | 按产品现状写步骤，不触发静默 no-op |
| React 受控输入 `fill` 不触发 onChange | workflow_manual、workflow_ai_coding | 输入一律真实键入（type/insert_text） |
| 会话标题异步生效（分钟级滞后） | chat_concurrent_switch | 会话 URL 作身份锚点，标题仅辅助 |
| 桌面端纯寒暄偶发缺 Thought 块 | desktop_chat_smoke | 用推理型消息保证思考块渲染（待产品侧确认） |

## 五、待办与下一步

- **扩量**：v1 目标 20~50 条业务链路（优先方向：多轮上下文漂移用例）。
- **评审 P1/P2**：`.scratch/review-p0/backlog.md`（auth 加固、裸 selector 收口、票 05 三件套等）。
- **任务票**：`.scratch/autoPlayWright/issues/` 01/02/06 已交付；03（Electron launch）留空待输入；04/05/07/08 待做。
- **票 06 收尾**：快照语义人工检查（票面验收项）仍 pending。
