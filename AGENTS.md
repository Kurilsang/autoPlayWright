# AGENTS.md

内部 Agent 产品（Web + Electron 客户端）的 UI 自动化测试框架：业务链路用 YAML DSL 编排（判定语义沉淀为页面对象原语），pytest 插件自动收集执行，输出结构化 JSON + Allure 报告。

## 怎么跑

```powershell
python -m venv .venv
.venv\Scripts\pip install -e ".[dev]"
.venv\Scripts\playwright install chromium

.venv\Scripts\pytest tests          # 框架自测（含浏览器端到端，走本地夹具站点；须 --apw-env fixture，别与 flows 混跑）
.venv\Scripts\pytest flows          # 业务链路（默认 --apw-env fixture）
.venv\Scripts\pytest tests flows    # 仅限同环境自测；真实环境混跑会假红（见「已知框架陷阱」）
.venv\Scripts\pytest flows --apw-headed --apw-slowmo 250  # 调试：窗口可见 + 放慢动作
.\run_debug.bat                                          # 同上一键调试（可透传 pytest 参数）
.\run_and_mail.bat                                       # 一键：跑 flows + 发带附件的报告邮件（--no-mail 只跑）
bash scripts/run_and_mail.sh                                     # 同上（Linux/服务器）
.venv\Scripts\python -m apw.crawler --env test --config configs/crawl/aml_chat.yaml   # 页面状态快照（票 06）
$env:APW_API_TOKEN='xxx'; .venv\Scripts\python -m apw.api --port 18787   # 回归触发 API（外部服务触发+取 zip 产物）
.venv\Scripts\pytest flows/desktop_chat_smoke.yaml --apw-env desktop  # 桌面端（客户端先带 --remote-debugging-port=9333 启动；端口被占可 set APW_CDP_ENDPOINT=http://127.0.0.1:<port>）
.venv\Scripts\ruff check src tests  # lint（提交前必须过）
```

部署到服务器（部署规范见 `docs/DEPLOY.md`；**每次部署都要把命令给用户，且必须含三件套：启动命令、停止命令、能发信的冒烟命令——标准命令唯一权威 = `docs/DEPLOY.md`「服务启停与冒烟」**）：

```powershell
.venv\Scripts\python scripts\pack_release.py --deploy      # 打包 + 部署（目标读 configs/deploy.local.yaml）
```

服务器上：`tar -xzf apw-deploy-<日期>.tar.gz` → `bash scripts/run_flows.sh`（真实路径见本地 `configs/deploy.local.yaml`）。

Linux / 服务器（网页端）：

```bash
bash scripts/setup_linux.sh --with-deps   # 一次性：venv + 依赖 + Playwright chromium（--with-deps 装系统库，需 root）
bash scripts/run_flows.sh                 # 无头跑业务链路（--debug=窗口可见+慢动作；其余参数透传 pytest）
bash scripts/run_and_mail.sh              # 一键：跑 flows + 发带附件的报告邮件（--no-mail 只跑）
bash scripts/run_scheduler.sh             # 定时执行：--cron "0 21 * * *"（可给多次=并集，如 --cron "0 18 * * 5" 每周五 18:00）；默认 30 分钟（--once 单跑；-- 后透传 pytest 参数）
bash scripts/run_api.sh                   # 回归触发 API（跨机需 APW_API_TOKEN=xxx + --host 0.0.0.0）
APW_CHROMIUM_ARGS="--no-sandbox --disable-dev-shm-usage" bash scripts/run_flows.sh   # 容器 root 跑 Chromium 必加
```

- 运行时资产路径锚定仓库根（`configs/envs`/`locators`/`reports`/夹具 base_url），任意目录调用行为一致

## 怎么加用例

新页面五步走（同页面新链路从第 4 步起）：

1. **探页面**：写 `configs/crawl/<page>_probe.yaml`，用 `page: probe` 探查原语推进状态并 dump_dom（仅生成侧探查用，流程用例禁用）→ `python -m apw.crawler --env test --config …` → `python scripts/snapshot_summary.py` 过结构
2. **补定位器**：`locators/<page>.yaml`（候选优先级见下，来源标 manual/ai）
3. **补页面对象**：`src/apw/pages/<page>.py`（动作=语义原语：链路级完成判定 + 失败取证），注册进 `engine/registry.py::default_registry()`
4. **写 flow**：`flows/<case>.yaml`（do/assert/judge）——只断言确定性内容，LLM 产出只进 `capture_context` 证据
5. **过验收门（D15）**：收集期 schema 校验 + `ruff check src tests` + 真实环境绿跑 **2 次**（`pytest flows/<case>.yaml --apw-env test`）

## 技术栈

Python 3.11+ / Playwright（同步 API）/ pytest 9（pytest11 插件入口）/ pydantic v2 / PyYAML / allure-pytest。

## 目录与约定

- `flows/*.yaml` — 业务链路用例（meta：platforms/envs/tags，steps：do·assert·judge，judge 为 v1 预留标记 planned）
- `examples/` — DSL 示例（fixture 夹具站点演示 + 引擎端到端素材，不计业务链路；`pytest --apw-flows-dir examples examples` 可跑）
- `locators/*.yaml` — 命名定位器仓库，候选优先级 testid > role+name > placeholder/label > text > css/xpath
- `src/apw/` — 分层：dsl（schema 校验）→ engine（FlowRunner 产 StepEvent）→ pages → locators → driver（Web/Electron 统一输出 Page）→ reporter（JSON 第一公民）→ pytest_plugin；`apw.crawler` 生成侧快照爬虫（含 `page: probe` 探查原语）；`apw.notify` 通知邮件（下游消费者，`python -m apw.notify --test/--summary [--report-zip]`，pytest 侧 `APW_NOTIFY=always|on-fail|on-change` + `APW_NOTIFY_ATTACH=1` 门控默认关闭；三通道 smtp/ews/foxmail，凭据只存 `configs/secrets.local.yaml`，模板 `configs/notify.example.yaml`；**收件人集中配置** `configs/notify.local.yaml` 的 `notify:` 段，或 secrets 的 `smtp.to`/`report_to`/`cc`，优先级 文件 < `APW_NOTIFY_TO` < `--to/--cc`；**邮件附件与 API 的 report.zip 同口径**——`attach_run_zip` 直接调 `apw.api.build_report_zip`，两个入口一个产物）；`apw.api` 回归触发 API（下游消费者，`python -m apw.api`／`scripts/run_api.sh`，契约见 `docs/API.md`：POST /runs 触发 + GET /runs/<id> 查状态 + GET /runs/<id>/report.zip 取产物包 + 完成回调，单飞队列、Bearer 鉴权、默认仅绑本机）
- `configs/envs/*.yaml` — 环境配置（`--apw-env` 选择；fixture=本地夹具站点）
- `configs/crawl/*.yaml` — 爬取配置（状态路径 + 完成信号探针，喂生成器）
- `scripts/` — 生成侧工具脚本（快照摘要等，AI 复用）
- `reports/` — 运行产物（gitignored；`report.html` 会话结束自动渲染）；`docs/SPEC.md` — 规格与决策记录；`docs/CASE_PROGRESS.md` — 用例清单与进度（新增/改动链路后同步）；`docs/STRUCTURE.md` — 目录结构；`docs/DEPLOY.md` — **部署规范（唯一权威）**；`docs/banner-light.html` — 项目报告页（banner 轮播，`scripts/run_slides.bat` 打开）；`video/`+`run_video.bat` — Remotion 汇报动画本地资产（gitignored 不入库）
- `.scratch/auto_playwright/issues/` — 主建任务票（01~08，依赖序）；`.scratch/review-p0/` — 评审修复批（spec + 票 + P1/P2 backlog）；完成即勾验收框并标 done
- commit 格式：`feat/fix: 一句话` + `- 要点`，极简

## 硬约束

- 并行执行 worker 上限 5（后端 LLM 限流，3~5 并发即限流）
- 只断言确定性内容（组件/状态/结构），不断言 LLM 措辞
- **失败即取证，禁止自愈**：卡死/半截渲染判 fail 并冻结现场（归因/复现/信号时间线/冻结截图随 EvidenceError 入报告），不做自动重载/重试把偶发缺陷跑绿
- 引擎不 import pytest/allure；报告与 pytest 只是引擎下游消费者
- 页面元素一律走定位器仓库，禁止散落裸 selector
- 页面对象的等待/判定/取证一律走 BasePage 基建（`settle`/`wait_until`/`SignalWatch` + `fail_evidence`/`fail_incomplete`，D27），不裸写 time.sleep/裸循环/裸拼 EvidenceError
- **凭据与内部信息永不入库**：账号密码走 `configs/secrets.local.yaml`（gitignored）或 CI 环境变量 `APW_USERNAME`/`APW_PASSWORD`；内网 URL/域名/IP/API/产品名/个人信息在提交内容与快照产物中一律以占位符呈现（环境真实值只在本地 `configs/envs/test.yaml`）；快照/探查产物落盘自动脱敏（`apw.sanitize`，映射 `configs/sanitize.local.yaml` 真实串仅存本地 + 通用模式兜底）；入库红线有机器门禁 `tests/test_no_secrets.py`（内网 IP/凭据值/产品名扫描）

## 当前状态（2026-10-16）

- 票 01/02 已交付；T07 预演产物已产品化：`locators/aml_chat.yaml` + `AmlChatPage` + `flows/aml_chat_smoke.yaml`（真实环境冒烟持续绿灯）
- 票 06 爬虫快照器已交付：`python -m apw.crawler` 状态化爬取（D20 快照骨架），产物入 `.scratch/auto_playwright/snapshots/`；另有 `page: probe` 探查原语（生成侧保留名，goto/click/type/insert/dump_dom，未知页面首轮探查用，流程用例禁用）与 `scripts/snapshot_summary.py` 快照摘要工具；**pending**：票面「快照语义人工检查」未勾
- 工作流功能（`/workflows` 编辑器）资产已入库：`locators/aml_workflow.yaml` + `AmlWorkflowPage` + `configs/crawl/workflow{,_probe}.yaml` + 4 条 flows——手动写码保存运行（非 AI 编码）/ AI 编写生成运行 / 并发 2 个 AI 生成任务 / 并发 2 个 AI 运行任务（并发 UI 校验：逐标签身份核对，串台/卡死判 fail 冻结取证）
- 对话并行切换链路已交付（2026-09-28）：`flows/chat_concurrent_switch.yaml` 双会话并行生成 + 来回切换逐会话身份核对（URL 锚点对号 + 输入回显 + 对方标记零混入），真实环境 3 次绿跑；`AmlChatPage.switch_session` 语义原语 + `BasePage.flow_state` 流程级共享状态
- Skills 广场链路已交付（2026-09-29）：`flows/skill_market_upload_download.yaml` 私人 skill 上传回显/预览 + 广场下载 + 筛选标签核对，真实环境 3 次绿跑；`SkillMarketPage`（上传硬红线仅 private）+ `locators/skill_market.yaml` + `LocatorRepo.resolve_multi` 多元素解析出口（修复 resolve 单元素上 .filter/.nth 静默落空）
- 套组广场链路已交付（2026-09-29）：`flows/suite_plaza_create.yaml` 新建套组 2×2（广场右上角/我的页虚线卡入口 × 简易/进阶模式）+ 回显刷新 + 单击预览 + 公开库无泄漏，真实环境 3 次绿跑；`SuitePlazaPage`（仅私有硬红线）+ `locators/suite_plaza.yaml`
- 报告样式库链路已交付（2026-09-29）：`flows/report_style_browse.yaml`（进入/预览/标签切换 8 类逐一核对筛选收敛）+ `flows/report_style_copy_run.yaml`（做同款跳转 → 运行 → 工作区产物落位），真实环境 3 次绿跑；`ReportStylePage` + `locators/report_style.yaml`
- 操练场链路已交付（2026-09-30）：`flows/playground_suite_debug.yaml` 创建私有套组 → 操练场新建会话绑定刚建套组（身份锚三连：unique 名/选择器/「已加载」徽标）→ 测试套组模式简单对话调试（六信号判完成），真实环境 3 次绿跑；`PlaygroundPage` + `locators/playground.yaml`；`SuitePlazaPage.create_suite` 增 `unique` 命名 + `flow_state["suite_name"]` 跨步锚
- 桌面客户端对话链路已交付（2026-10-08）：`flows/desktop_chat_smoke.yaml` 新建任务 → 发送消息 → 完整回答判定 → Thought 展开核对，真实客户端 3 次绿跑；`DesktopChatPage` + `locators/desktop_chat.yaml` + `configs/envs/desktop.yaml`（CDP attach：客户端带 `--remote-debugging-port=9333` 启动）+ 探查配置 `configs/crawl/desktop_chat_probe{,2,3,4}.yaml`（3/4=Thought 块与展开交互）；平台矩阵生效（`platforms: [desktop]` 在 web 环境自动 skip 留痕）
- Web 端 MCP 配置管理链路已交付（2026-10-13）：`flows/mcp_config_manage.yaml`（29 步）入口「更多场景」→「MCP 配置」→ 两区块结构红线 → 表单校验红字 → 新增（请求头 + 暂时禁用）→ 卡片回显 → 详情（编辑弹层回显）→ 编辑更新 → 删除自清理 → 新开对话完整回答，真实环境 3 次绿跑；`McpConfigPage`（10 个语义原语）+ `locators/mcp_config.yaml`（43 条）+ 探查配置 `configs/crawl/mcp_probe{,2..13}.yaml`（13 个，均过 crawler schema）；用例自清理（`apw-*` 前缀条目链路内删除，收尾核对 UI 空态 + `GET /api/mcp-servers` = `[]`）
- 桌面客户端工作流链路已交付（2026-10-12）：`flows/desktop_workflow_manual.yaml` 打开运行（新建 → CodeMirror 写码保存 → 运行视图 → 运行完成，非 AI 编码）+ `flows/desktop_workflow_concurrent_switch.yaml` 并行工作切换（双工作流并行运行 + 来回切换逐工作流身份核对）+ `flows/desktop_workflow_ai_coding.yaml` AI 编写生成并运行 + `flows/desktop_workflow_ai_concurrent_switch.yaml` 并行 AI 生成切换（双工作流后台并行生成 + 逐工作流身份核对），真实客户端各 3 次绿跑；`DesktopWorkflowPage` + `locators/desktop_workflow.yaml` + 探查配置 `configs/crawl/desktop_workflow_probe{,2,3,4,5,6,7,8,9}.yaml`（5=后台运行与切换语义，7=AI 编写生成旅程，9=AI 并行生成切换）
- 回复判定：web 端 = **完整回答六信号**（停止消失/推理步骤/最终答案/操作行/稳定/加载清除）；桌面端 = 停止生成消失/回答气泡/Thought 块在场/操作行/稳定 + `expand_thinking` 展开核对；`capture_context` 把对话上下文（输入/推理步骤/思考过程/最终答案）写入报告证据
- Web 端 MCP **真实调用**链路已交付（2026-10-13）：`flows/mcp_invoke_tool.yaml`（17 步）自配服务器 → 进阶套组勾「MCP（外部工具）」+ 按名引用自配服务器 → 新开对话绑定套组 → **真实工具调用** → 放行执行 → 自清理，真实环境 3 次绿跑；`McpInvokePage`（12 个语义原语）+ `locators/mcp_invoke.yaml`（12 条）+ 零依赖夹具 `tests/fixture_mcp/apw_http_mcp.py`（手写 streamableHttp JSON-RPC + 请求/调用流水账）。**判据全取服务端真值**：`tool_name` = `<自配服务器名>__<远端工具>`（实测 `apw-mcp-invoke 甲甲甲__get_page`）→ 直接证明该自配服务器真的挂载、工具真的被调用，不依赖 LLM 措辞
- Web 端 MCP 挂载机制（2026-10-13 逆向实证）：套组绑定靠 `POST /api/chats {preset_id}`；稳定 UI 路径 = 写 `sessionStorage.pending_preset_id` 后重载 `/chat`（点套组卡会因轮播 `element is not stable`）；挂载配置读回 `GET /api/presets/<id>` 的 `advanced_config.single = {tools:[...,'mcp'], mcpServerNames:[名]}`；「MCP 服务器（按名引用…）」选择器**只列出当前用户已注册的服务器**（记录被删时看不到自配项，早期探查即因此误判）
- 已知产品行为（Web 端 MCP 真实调用）：外部工具调用受**写权限门**控制 —— 默认 `mode=ask` 时调用**挂起等确认**，服务端记录于 `GET /api/chat/<id>/tool-confirm/pending`（含 `tool_name`/`args_summary`/`tool_call_id`）；`PUT /api/chat/<id>/tool-confirm/mode {mode:"conversation"}` 全部放行，`POST /api/chat/tool-confirm {chat_id,tool_call_id,approved:true,scope:"once"}` 单次放行。**未放行时工具调用被拒**（模型只能说「未被授权」）——这是排查「工具没被调用」的第一现场
- ⚠️ 已知环境约束（Web 端 MCP 真实调用）：自配服务器的 URL 必须**能被测试后端访问**（连接由服务端发起，浏览器侧零请求）。开发机入站被防火墙 GPO `BlockInbound` 拦截且当前账号非管理员 —— 后端 `curl` 开发机端口实测 **15s 超时**（`curl: (28) Connection timed out`，2026-10-13 用产品自带 bash 工具实证）。故 `mcp_invoke_tool` 的目标指向内网可达的 MCP 服务；**内网地址不入库**，URL 由环境变量 **`APW_MCP_PROBE_URL`** 提供（未设置即 fail 取证，不静默用默认值）；自建夹具在有入站放行时可直接替换该变量
- 失败取证：EvidenceError 带归因分类（hang_loading/streaming_stuck/reply_incomplete/content_unstable/thinking_expand_failed + gen_stuck/gen_incomplete/run_stuck/run_incomplete/identity_mismatch）+ 复现 + 信号时间线 + 冻结截图
- 测试环境地址在本地 `configs/envs/test.yaml`（gitignored，模板 `test.example.yaml`）；正式环境**勿跑测试/爬取**；测试环境免登录直达会话页
- 已知产品缺陷：「加载对话历史中」偶发卡死（前端），复现线索=新建会话→确认 Agent 类型弹窗→随即发送；切换回仍在生成的会话时该占位亦会挂起（2026-09-28 实测）；测试判 fail 取证待产品侧修复
- 已知产品缺陷：Skills 广场个别 skill 包缺失时 `/api/skills/<id>/download` 返回 404 且界面无任何提示（静默失败，2026-09-29 实测）；下载链路用例逐卡尝试取一次成功，404 尝试随证据留痕
- 已知产品行为：工作流编辑器为 React 受控输入，`fill` 不触发 onChange（会静默空提交）——输入一律真实键入（type/insert_text）；运行跑的是服务端已保存版本，手动改动必须先「保存工作流」
- 已知产品行为：会话标题异步生效（首条消息/LLM 生成，繁忙时滞后分钟级）——多会话定位一律用会话 URL（`/chat/<uuid>`）作身份锚点，标题仅作辅助
- 已知产品行为：Skills 广场下载为 JS 存盘——无浏览器下载事件、无 UI 反馈，成功信号 = `GET /api/skills/<id>/download` 2xx + 包字节数；预览弹层靠头部 X 关闭（Esc 不关闭）；可见性 radio `scope=private|public`（🔒私人/🌐公共）
- 已知产品缺陷：套组新建表单的英文名/英文描述为**静默必填**——缺失时「创建套组」点击静默 no-op（零网络零校验提示，2026-09-29 实测）；且提交需停在「基本信息」分区（停留「发布设置」提交同样静默 no-op）
- 已知产品行为：套组卡片单击=预览模态（右上 X 或 Esc 关闭）、双击=套用；自有套组预览仅「✦应用此套组」，公开套组另有「⏳发起长任务」与「Agent 配置」区；卡片徽标=Agent 类型（快速/专家模式）非创建模式
- 已知产品行为：报告样式库（侧边栏「更多场景」→ 场景卡）8 类 28 套样式；卡片「预览/做同款」开同一弹层（头部：做同款/新标签打开/关闭），弹层「做同款」=一键复制官方示例工作流跳转 `/workflows/<uuid>`（副本名含「官方模板」「(Fork)」；实测同页跳转，页面对象兼容弹窗形态）；运行面板参数默认预填，**recipients 留空=不发邮件（用例绝不填）**；「工作流产物」区「· 产物」行 = 工作区最终结果
- 已知框架陷阱：Playwright 同步 API 纯 `time.sleep` 轮询不泵事件循环，`page.url` 会停在旧值（做同款跳转等待曾误判未跳转）——轮询一律走 API 调用（`wait_for_timeout`/`count`/`inner_text`）
- 已知框架陷阱：定位器裸 text 候选（`exact: true`）会错配同名结构——工作流面板开着时 `<h2>工作流</h2>` 抢在侧边栏按钮前命中（2026-10-12 实测）；结构候选（css）必须排在裸 text 候选前
- 已知框架陷阱（Foxmail 代发通道，2026-10-14 实测）：Foxmail=Delphi 程序 UIA 全盲，发信=mailto 拉写信窗 + 前台 Ctrl+Enter；①窗口句柄会被 Windows 复用，新旧写信窗辨别必须 `{hwnd: 标题}` 映射比标题（裸句柄集合会把新窗当旧窗屏蔽）；②前台锁下 AttachThreadInput+SetForegroundWindow 无效，有效序列=SW_RESTORE→空敲 ALT→SetForegroundWindow 循环重试；③窗太新就发键会被吞（等 TCEFWindowParent 子窗出现，**冷启动实测可超 15s，就绪超时已放宽到 60s**）；④新邮件弹窗（TMailViewerForm）会瞬时偷焦点，每轮键击前重验前台（`APW_NOTIFY_DEBUG=1` 留证）；⑤**失败会留下残留写信窗**，而 Foxmail 对后续 mailto 复用旧窗（不再新建），于是"未在 N 秒内出现"的报错会自我延续——重试前必须先清空写信箱；⑥启动第二个 Foxmail 实例会触发 `CefBrowserProcessHandler::OnAlreadyRunningAppRelaunch` 未实现告警（见 `Global/Log/cef.log`），正文回落到旧版 `TFoxHTMLEditor`、CEF 子窗永不出现
- 已知框架局限（通知邮件通道能力，2026-10-15）：**附件只有 smtp 通道能给**（ews/foxmail 显式报错，不静默丢）；foxmail 通道已按用户决定降级为兜底（`transport` 默认 `smtp`），其三个真 bug 已修（`/` 未编码、超长 URL 被静默丢弃、不可见僵尸窗污染探测）但不推荐生产；`auth=xoauth2` 需一次性交互 `--login`（无法无人值守），故推荐私人邮箱 `auth: basic` + 授权码
- 已知产品行为：操练场（更多场景→「创作与调试」组）= 套组调试沙箱，会话卡绑一个套组；「新建会话」弹窗（会话名称 + 原生 select 从套组加载）确定后**直接进 IDE**（列表恢复才走「进入调试」）；IDE 两种模式=Agent 助手（读写工作区文件）/▶测试套组（输入用户消息 Enter 运行一次完整推理）；运行日志=「▶ 操练场运行开始」→「Prompt: 回显」→「│」输出行→「✅ 运行完成，用时 Ns，Token: N」，顶栏状态 空闲→已完成
- 已知产品行为（桌面客户端）：组合器为 contenteditable 富输入（Enter 发送/Shift+Enter 换行，同工作流编辑器陷阱一律真实键入）；生成中发送键变「停止生成」（`button.btn-send.btn-stop`）= 流式信号；Thought 折叠块（`details.msg-thinking`）**正文展开才渲染**（折叠态仅 summary，`expand_thinking` 测展开：summary 点击 → `details[open]` + `.msg-thinking-body`）；完成态=回答气泡 + 完成态操作行；「新任务」清空会话区（未清空判 fail）；无会话 URL，身份锚点=消息 `data-message-id`；会话标题异步生效（生成中带 `.is-generating`）
- 已知产品行为（桌面客户端工作流）：工作流区是 **view slot 栈**（列表底座 + 详情/运行叠放，「← 返回」回上一槽：详情槽保活、运行槽销毁，同时仅一槽 `is-active`）；**运行后台执行、视图切走不中断**（卡片「进行中」角标 +「最近运行：运行中」）；脚本编辑器=CodeMirror（整体 insert_text，同逐键自动缩进陷阱），保存落定=「保存」按钮转 disabled，流程节点保存后解析；运行=详情「运行」开运行视图（运行输入/历史运行）→ 再点「运行」执行，完成行=「✅ 工作流完成。…」；身份锚点=详情标题 h3 / 运行视图标题 / 日志「工作流开始：<名>」行；常驻「服务连接异常」toast 会拦截下方点击（关闭钮是 `aria-label=关闭` 的图标钮，无文本，`dismiss_toasts` 幂等清）
- 已知产品行为（桌面客户端 AI 编写）：「AI 编写」=脚本面板开关，展开 `aside.wf-author` 助手面板（模型选择/清除对话/收起 + 需求 textarea + 发送钮）；生成态状态机=状态点 `is-streaming`+「停止」钮 → `is-done`+「发送」回归（状态点仅采证）；**AI 生成后台执行、视图切走/详情槽替换不中断**，会话按工作流各归各（需求回显气泡=确定性身份锚点，对方标记零混入）；助手改写后直接保存并校验（`Save script` 工具卡 + 流程结构解析，自动保存成功提示为瞬态）；面板在生成完成边界附近打开时偶发助手消息轮**空壳渲染**（见已知缺陷）
- 已知产品缺陷（桌面客户端 AI 编写，2026-10-12 实测）：助手消息轮偶发**空壳渲染**——竞态窗口≈生成完成边界附近打开面板，Thought/工具卡/正文全缺（零高度空 div），脚本却照常落盘解析、状态点 `is-done`；判 fail 冻结取证（`_assistant_turn_ready` 空壳不算渲染完整，同型时序不必然复现），待产品侧修复
- 已知产品缺陷观察（桌面客户端）：纯寒暄偶发走 ~2s 无思考快速路径，回复整条缺 Thought 块（2026-10-08 实测 8 轮中 2 轮，判 fail 取证见 reports/20261008-110107、reports/20261008-112123）；对话用例一律用**推理型消息**保证思考块渲染，该不一致待产品侧确认
- 已知产品行为（Web 端 MCP `/mcp-config`）：入口=首页「更多场景」→ 场景卡「MCP 配置」（直连 `/mcp-config` 亦可）；两块=「官方 MCP 服务器 (N)」（只有「复制配置」，用例绝不触碰）与「我的 MCP 服务器 (N)」（空态=虚线框 +「新增第一个」）；**保存成功无 toast**（`div[role='status']` 常驻但为空）→ 成功判据=弹层关闭 + 卡片出现；**无独立详情视图**（点卡片/空白=静默 no-op）→ 详情唯一载体是「编辑」弹层字段回显；编辑弹层 headers **只回显 key、不回显 value**（提示「出于安全，已保存的 header 值不回显」）→ 只断言 key
- 已知产品缺陷（Web 端 MCP）：**不支持 stdio**——新增弹层仅 服务器名\*/URL\*/描述/请求头/暂时禁用（0 个 select，无 transport、无启动命令/参数/环境变量）；API 侧带 `transport/command/args` 提交返回 201 但字段被**静默丢弃**（2026-10-12 实证）。故 Web 端 MCP 用例只覆盖 URL 型（streamableHttp）配置管理；stdio 场景由桌面端 `desktop_mcp_stdio.yaml` 承担
- 已知产品行为（Web 端 MCP）：删除走原生 `window.confirm`（文案「删除 MCP 服务器「<名>」？」）——页面对象必须先注册 `page.on("dialog", accept)`，否则 Playwright 默认 dismiss 永远删不掉；每张卡都有同名 `button[title='删除']`/`button[title='编辑']` → 动作按钮一律经 `_card(name)` 限定在目标卡片内，禁用全局 `.first`（会误删他条）
- 已知产品行为（Web 端 MCP）：普通新对话（专家模式）**不挂载 MCP 工具**（工具清单无 `mcp__` 前缀，2026-10-12 实证）→ 用例绝不新增「新对话能看到 MCP 工具」这类断言；「工具清单」类回复结构不稳定（表格行数 7~10、表格个数 1~3 波动，LLM 每次分组不同）→ 判定只用 `wait_reply_done` 六信号，LLM 产出只经 `capture_context` 进证据
- 仓库与基建口径（2026-10-09）：DSL=编排层、判定语义在页面原语（宣传口径同步修正，D26）；等待/判定/取证收编 BasePage 基建（D27，SignalWatch 多信号收敛 + fail_evidence/fail_incomplete 统一取证，自测 `tests/test_signal_watch.py`）；示例链路移居 `examples/`（业务链路口径 = 19 条）；`video/`+`run_video.bat` 演示资产出库为本地（gitignored）
- Linux 网页端可跑（2026-10-12）：`DriverConfig.args` + `APW_CHROMIUM_ARGS` 环境变量追加（容器 root 跑 `--no-sandbox`）+ 运行时路径锚定仓库根（`pytest_plugin.get_runtime` 不再吃 CWD）+ `scripts/setup_linux.sh`/`scripts/run_flows.sh`；桌面端链路仍需 Windows 客户端
- 定时执行模块已交付（2026-10-13）：`python -m apw.scheduler`（+`scripts/run_scheduler.sh`）固定节奏循环跑 pytest（默认 30 分钟一轮，测试阶段口径），常驻/cron（`--once`）两用，超长跑跳槽不叠跑、每轮日志落 `reports/scheduler/`，SIGINT/SIGTERM 优雅停（含子进程终止）；2026-10-15 增 `--cron`（标准 5 字段自包含解析，支持日/周/月频率，日与周同限取「或」，跨区间 `22-2`；**可给多次=多档并集**；与 `--interval-minutes` 互斥；`--once` 立即跑不受其影响；当前排期口径=每天 21:00 + 每周五 18:00）
- 回归触发 API 已交付（2026-10-14）：`src/apw/api.py`（+`scripts/run_api.sh`）供外部服务定时触发跑测、取 zip 产物、由其自建邮件通道外发——**发信能力与测试侧解耦，跨平台**（Linux 无邮件通道亦可跑）；单飞队列（同时只跑一轮，避免叠加触发 LLM 限流）、Bearer 鉴权（`APW_API_TOKEN`，非本机绑定强制要求）、默认只绑 127.0.0.1、完成回调（POST callback_url，失败不影响结果可补拉）、zip = run 目录全量（report.html + run-summary.json + 明细 JSON + 失败冻结截图）；`build_report_zip(sanitize=True)` 预留外发脱敏开关（复用 `apw.sanitize`，默认关=内网可信调用）；契约见 `docs/API.md`，自测 `tests/test_api.py`
- 通知邮件模块增强（2026-10-14/15）：**收件人集中配置**（`configs/notify.local.yaml` 的 `notify:` 段，改名单不碰凭据；或 secrets 的 `smtp.to`/`report_to`/`cc`；`report_to` 非空整体取代 `to`，`cc` 只进 SMTP 信封不进 To 头）+ **邮件附件与回归触发 API 的 report.zip 同口径**（`apw.notify.mail.attach_run_zip` 直接调 `apw.api.build_report_zip`，外部服务 GET 到的包 = 邮件附件字节，同一函数一个产物；CLI `--report-zip` / `--zip-sanitize`，pytest 侧 `APW_NOTIFY_ATTACH=1` / `APW_NOTIFY_ZIP_SANITIZE=1`）+ `APW_NOTIFY=on-change` 策略（配 `APW_NOTIFY_PREV_FAILED` 基线）+ 摘要正文按 flow_id 稳定排序并单列失败清单；自测 `tests/test_notify.py`（含 attach 与 API zip 逐字节一致性断言）
- 一键跑测+发报告已交付（2026-10-15）：`scripts/run_and_mail.bat`（Windows）/`scripts/run_and_mail.sh`（Linux）= 跑 `flows --apw-env <env>` → 定位本轮 run 目录（取**最新且含 run-summary.json** 的一份，免疫并发 writer 的中间态）→ `python -m apw.notify --report-zip` 发带附件摘要；`--no-mail` / `--env` / `--to` / `--cc` 自有开关，其余透传 pytest；跨平台等价物 `scripts/console_summary.py --targets flows --env test --mail`（额外做「附件 = API report.zip」逐字节核对，用于验收该不变量）。**只跑 flows**：`tests` 是夹具自测，与真实环境混跑必假红
- 发信通道现状（2026-10-15，**实发验证**）：本机改走**私人邮箱 SMTP + 授权码**（`smtp.qq.com:465` SSL + `auth: basic`），绕开微软 xoauth2 交互登录（无需 M365 任何权限）；已成功投递（私人邮箱 → 目标邮箱），带 2,152,044 字节附件，且**附件与 `apw.api` 的 report.zip 逐字节一致**。具体账号/授权码只在本地 `configs/secrets.local.yaml`。前提事实：目标邮箱域收信走 M365，**外部未认证直投（自建 SMTP/MX 直连）不可行**——本机出口 IP 无 PTR 反向解析，M365 会判 550/丢弃
- 服务器部署现状（2026-10-15）：定时任务 + 每轮自动发信已部署服务器并实测发信成功（收件人只留 zepeng.huang，名单在服务器 `configs/notify.local.yaml`，SMTP 凭据并入服务器 `secrets.local.yaml` 且其 `api.token` 保留）；服务器起测前置 = `.venv/bin/playwright install chromium`（缺浏览器时 16 条全红，见下条连锁假错陷阱）
- 本机全量跑测基线（2026-10-14，`tests + flows --apw-env test` 混跑，**跑法有误**，仅存档）：`19 failed, 136 passed, 5 skipped`。其中框架自测 14 条假红（`--apw-env test` 下夹具站点未起）+ 门禁 1 条（已于 2026-10-15 修复）；业务链路 4 failed / 7 passed / 5 skipped（skip=desktop 在 web 环境留痕）。**正确跑法**见下条「tests 与 flows 必须分开跑」——分开后 `pytest tests` 全绿。4 条业务失败均带完整取证：`aml-chat-smoke`（`reply_incomplete`，缺 reasoning_steps/final_answer_card/reply_actions）、`playground-suite-debug` 与 `suite-plaza-create`（`run_incomplete` 私有套组命中公开列表）、`skill-market-upload-download`（`run_stuck` 3 次下载无 2xx）
- 门禁缺陷已修（`tests/test_no_secrets.py`，2026-10-15）：此前恒误报 5 条（改动前即失败），噪音会把真违规淹掉。两处根因：①`_SELF` 只跳过自身、没跳过 `scripts/redline_check.py`——该脚本是扫描规则的**载体**，正文必然含产品名模式串；②「凭据值」正则命中**赋值语句**而非配置值（`token = oauth.get_token(cfg)` 之类）。已修：跳过两个规则载体文件 + 「凭据值」只匹配配置取值语境并排除函数调用/占位符/变量引用。修后 `pytest tests` 全绿，且反向验证过仍能抓到硬编码 token/密码/内网 IP/产品名
- 已知框架陷阱（本机跑全量的正确姿势，2026-10-14）：`tests` 与 `flows` 必须**分开跑或按环境跑**——夹具类自测（`test_crawler_fixture_site`/`test_engine_fixture_site`/`test_probe_page`/`test_crawler_schema`）走 `--apw-env fixture` 的本地夹具站点，业务链路走 `--apw-env test`；一条命令混跑（`pytest tests flows --apw-env test`）会把夹具自测按真实环境起浏览器，14 条因找不到 `[data-testid=new-chat]` 等夹具元素而红，属**运行方式导致的假红**，不代表回归
- 已知框架陷阱（通知邮件凭据落位，2026-10-14）：新增真实收件人配置后，`load_mail_config` 会从 `repo_root()` 读 `configs/notify.local.yaml`，**未做 repo_root 隔离的离线自测会被真实名单污染**（`tests/test_notify.py` 已统一 `monkeypatch.setattr(mail, "repo_root", lambda: tmp_path)` + 按 `<tmp>/configs/notify.local.yaml` 相对路径落盘夹具）
- 已知框架陷阱（Playwright 启动失败连锁假错，2026-10-15）：驱动启动失败（如服务器缺浏览器）泄漏 sync 上下文后，后续所有用例连锁报 `Sync API inside the asyncio loop` 假错、把真因淹没——**排查只认第一条报错**；且平台/环境跳过判定发生在起驱动之后（`ApwFlowItem.runtest` 先 `get_runtime`），驱动一炸连本该 skip 的用例也 fail
- 测试基线：`pytest tests`（**fixture 环境、独立跑**）**全绿 = 156 passed, 1 skipped**（2026-10-15 门禁修复后达成，含证据链路/失败取证/三态报告/脱敏用例/红线门禁）；工作流 4 条链路 + 对话并行切换 + Skills 广场 + 套组广场 + 报告样式库 2 条 + 操练场真实环境 3 次绿跑 + 桌面端对话冒烟真实客户端 3 次绿跑 + 桌面端工作流 4 条链路（打开运行/并行切换/AI 编写/AI 编写并行）真实客户端 3 次绿跑 + 桌面端 MCP 全链路（2026-10-15）+ 桌面端搜索/技能市场链路（2026-10-16）；真实环境均达验收门（**绿跑 ≥2 次**，2026-10-13 由 ≥3 调整）
- 评审修复批次 P0 已交付（`.scratch/review-p0/`，6 票全 done）：prepare 失败与空步骤终态留痕、报告三态 + 跳过原因、run 目录唯一化 + 汇总合并、快照脱敏管道、定位器计数与解析同链
- 留空待输入：仅 Electron 安装包 launch（T03；CDP attach 已有真实用例跑通=桌面端对话冒烟）
- 下一步：评审 P1/P2（见 `.scratch/review-p0/backlog.md`）→ 04 原语库（两档制 + 收口规则）→ 07 生成器（opencode skill）→ 08；业务用例扩量（v1 目标 20~50 条）
