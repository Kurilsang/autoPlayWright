# 用例进度总览

业务链路（`flows/*.yaml`）与框架自测（`tests/`）的清单与状态。新增/改动用例后同步本页；
链路数量以收集结果为准：`pytest flows --collect-only -q`、`pytest tests --collect-only -q`。
DSL 示例（`examples/`，fixture 夹具站点演示）不计业务链路。

> 判定口径、失败取证规则、已知产品缺陷的完整叙述以 `AGENTS.md` 为准，本页只做清单与进度映射。

**统计（2026-10-16）**：业务链路 19 条（`flows/`，真实/桌面环境）；DSL 示例 1 条（`examples/`）；
框架自测 17 个文件。测试基线：`pytest tests` 全绿；真实环境链路均达验收门绿跑要求。

> **验收门绿跑次数：≥2 次**（2026-10-13 由 ≥3 调整，见 `docs/SPEC.md` D15）。
> 下表「3 次绿跑」为历史交付时的实际记录（3 ≥ 2，仍满足现行门槛），非现行要求。

## 一、业务链路清单

### 对话与会话

| flow | id | 平台/环境 | 步数 | 覆盖场景 | 状态 |
|------|----|-----------|------|----------|------|
| `aml_chat_smoke.yaml` | aml-chat-smoke | web / test | 14 | 新建对话 → 发送 → 完整回答判定 → `capture_context` 证据 | 真实环境持续绿灯（2026-09-22 交付） |
| `chat_concurrent_switch.yaml` | chat-concurrent-switch | web / test | 21 | 双会话并行生成 + 来回切换逐会话身份核对（URL 锚点 / 输入回显 / 对方标记零混入） | 3 次绿跑（2026-09-28） |
| `desktop_chat_smoke.yaml` | desktop-chat-smoke | desktop / desktop | 13 | 桌面客户端：新建任务 → 发送 → 完整回答判定 → Thought 展开核对 | 3 次绿跑（2026-10-08） |

> DSL 示例：`examples/example_chat.yaml`（id=example-chat，fixture 夹具站点，7 步）——DSL 范例 + 引擎端到端素材，随 `pytest tests` 覆盖，不计业务链路。

### 工作流（/workflows 编辑器）

| flow | id | 平台/环境 | 步数 | 覆盖场景 | 状态 |
|------|----|-----------|------|----------|------|
| `workflow_manual.yaml` | workflow-manual | web / test | 11 | 手动写码保存并运行（非 AI 编码） | 3 次绿跑（2026-09-24 交付） |
| `workflow_ai_coding.yaml` | workflow-ai-coding | web / test | 10 | AI 编写生成工作流并运行 | 3 次绿跑（2026-09-24 交付） |
| `workflow_ai_concurrent_publish.yaml` | workflow-ai-concurrent-publish | web / test | 5 | 并发 2 个 AI 生成任务，逐标签身份核对（串台/卡死判 fail 冻结取证） | 3 次绿跑（2026-09-24 交付） |
| `workflow_ai_concurrent_run.yaml` | workflow-ai-concurrent-run | web / test | 5 | 并发 2 个 AI 运行任务，逐标签身份核对 | 3 次绿跑（2026-09-24 交付） |

### 工作流（桌面客户端工作流面板）

| flow | id | 平台/环境 | 步数 | 覆盖场景 | 状态 |
|------|----|-----------|------|----------|------|
| `desktop_workflow_manual.yaml` | desktop-workflow-manual | desktop / desktop | 15 | 打开运行：新建 → CodeMirror 写码保存 → 运行视图 → 运行完成（非 AI 编码） | 3 次绿跑（2026-10-12 交付） |
| `desktop_workflow_concurrent_switch.yaml` | desktop-workflow-concurrent-switch | desktop / desktop | 28 | 并行工作切换：双工作流并行运行 + 来回切换逐工作流身份核对（标题/脚本节点/日志名行，对方标记零混入） | 3 次绿跑（2026-10-12 交付） |
| `desktop_workflow_ai_coding.yaml` | desktop-workflow-ai-coding | desktop / desktop | 16 | AI 编写生成工作流并运行（需求回显/助手轮/结构落盘 + 运行完成） | 3 次绿跑（2026-10-12 交付） |
| `desktop_workflow_ai_concurrent_switch.yaml` | desktop-workflow-ai-concurrent-switch | desktop / desktop | 26 | 并行 AI 生成切换：双工作流后台并行生成 + 来回切换逐工作流身份核对（需求回显 + 对方标记零混入） | 3 次绿跑（2026-10-12 交付；1 次踩中空壳轮缺陷判 fail 取证，见已知表） |

### 广场与场景

| flow | id | 平台/环境 | 步数 | 覆盖场景 | 状态 |
|------|----|-----------|------|----------|------|
| `skill_market_upload_download.yaml` | skill-market-upload-download | web / test | 17 | Skills 广场：私人 skill 上传回显/预览 + 广场下载 + 筛选标签核对 | 3 次绿跑（2026-09-29） |
| `suite_plaza_create.yaml` | suite-plaza-create | web / test | 32 | 套组新建 2 入口 × 2 模式 + 回显刷新 + 单击预览 + 公开库无泄漏（仅私有） | 3 次绿跑（2026-09-29） |
| `report_style_browse.yaml` | report-style-browse | web / test | 28 | 报告样式库：进入/预览/8 类标签切换逐一核对筛选收敛 | 3 次绿跑（2026-09-29） |
| `report_style_copy_run.yaml` | report-style-copy-run | web / test | 16 | 做同款跳转 → 运行 → 工作区产物落位（recipients 恒留空） | 3 次绿跑（2026-09-29） |
| `playground_suite_debug.yaml` | playground-suite-debug | web / test | 14 | 操练场：建私有套组 → 绑定套组新建会话（身份锚三连）→ 测试套组模式对话调试 | 3 次绿跑（2026-09-30） |

### MCP（Web 端）

| flow | id | 平台/环境 | 步数 | 覆盖场景 | 状态 |
|------|----|-----------|------|----------|------|
| `mcp_config_manage.yaml` | mcp-config-manage | web / test | 29 | Web 端 MCP 配置管理：入口（更多场景→MCP 配置）→ 两区块结构红线 → 表单校验红字 → 新增（headers + 暂时禁用）→ 卡片回显 → 详情（编辑弹层回显）→ 编辑更新 → 删除自清理 → 新开对话完整回答 | 3 次绿跑（2026-10-13） |
| `mcp_invoke_tool.yaml` | mcp-invoke-tool | web / test | 17 | Web 端 MCP **真实调用**：自配服务器（POST /api/mcp-servers）→ 进阶套组勾「MCP（外部工具）」+ 按名引用自配服务器 → 新开对话绑定套组 → 真实工具调用（判据取服务端 `tool-confirm/pending`）→ 放行执行 → 自清理 | 3 次绿跑（2026-10-13） |

> **`mcp_invoke_tool` 的确定性判据（不依赖 LLM 措辞）**：把写权限设为 `ask` 后，
> 外部工具调用会挂起并在服务端留下记录，`GET /api/chat/<id>/tool-confirm/pending` 返回
> `tool_name` / `args_summary` / `tool_call_id`。其中
> **`tool_name` = `<自配服务器名>__<远端工具名>`**（实测 `apw-mcp-invoke 甲甲甲__get_page`）
> —— 该前缀直接证明「这个自配服务器真的被挂载、这个工具真的被调用」。
> 这是本仓库里 Web 端 MCP 唯一可用的强确定性信号；LLM 产出只进 `capture_context` 证据。

> **`mcp_invoke_tool` 的环境约束（必须知道）**：自配服务器的 URL 必须**能被测试后端访问**
> （连接由服务端发起，浏览器侧零请求）。开发机入站被防火墙 GPO `BlockInbound` 拦截、
> 当前账号非管理员 —— 后端 `curl` 开发机端口实测 **15s 超时**
> （`curl: (28) Connection timed out`，2026-10-13 用产品自带 bash 工具实证）。
> 故用例的「自配服务器」指向**内网可达的 MCP 服务**，走完整自配路径
> （POST /api/mcp-servers → 进阶套组按名引用 → 会话挂载 → 真实调用）。
>
> **内网地址不入库**（硬约束）：目标 URL 由环境变量 **`APW_MCP_PROBE_URL`** 提供，
> 未设置时用例 fail 取证并给出提示（不静默用默认值）。运行前设置：
> `$env:APW_MCP_PROBE_URL = "http://<内网MCP主机>:<端口>/mcp"`。
> 自建零依赖夹具 `tests/fixture_mcp/apw_http_mcp.py`（含请求/调用流水账）
> **在有入站放行时可直接替换该变量**（`http://<开发机IP>:8765/mcp`），
> 即可得到完全本地化的确定性证据。

> **Web 端 MCP 挂载机制（2026-10-13 逆向实证）**：套组绑定靠
> `POST /api/chats {preset_id}`；等价稳定的 UI 路径 = 写 `sessionStorage.pending_preset_id`
> 后重载 `/chat`（点套组卡会因轮播动画 `element is not stable`）。
> MCP 是否挂载读回 `GET /api/presets/<id>` 的
> `advanced_config.single = {tools:[...,'mcp'], mcpServerNames:[名]}`。
> 「MCP 服务器（按名引用…）」选择器**只列出当前用户已注册的服务器** ——
> 记录被删时会看不到自配项（早期探查即因此误判「看不到自配服务器」）。

> **Web 端 MCP 仅支持 URL 型（streamableHttp），不支持 stdio**：新增弹层只有
> 服务器名/URL/描述/请求头/暂时禁用，无 transport 选择器、无启动命令/参数/环境变量；
> API 侧带 `transport/command/args` 提交会返回 201 但字段被**静默丢弃**（2026-10-12 实证）。
> 故本用例覆盖的是 Web 端真实存在的 MCP 能力面（URL 型配置管理 + 新对话调用），不含 stdio 步骤。

> Web 端 MCP 的产品事实（写用例的依据）：保存成功**无 toast**（`div[role='status']` 常驻但为空）
> → 成功判据 = 弹层关闭 + 卡片出现；**无独立详情视图**（点卡片 = 静默 no-op）→ 详情断言落在
> 「编辑」弹层字段回显上；删除走原生 `window.confirm`（须注册 `page.on("dialog", accept)`，
> 否则 Playwright 默认 dismiss 永远删不掉）；每卡同名 `button[title='删除']` → 动作按钮一律
> 限定在目标卡片内；编辑弹层 headers **只回显 key、不回显 value** → 只断言 key；
> 普通新对话（专家模式）**不挂载 MCP 工具** → 绝不新增「新对话能看到 MCP 工具」这类断言。

### MCP（桌面端）

| flow | id | 平台/环境 | 步数 | 覆盖场景 | 状态 |
|------|----|-----------|------|----------|------|
| `desktop_mcp_stdio.yaml` | desktop-mcp-stdio | desktop / desktop | 66 | 桌面端 stdio MCP 全链路：设置→MCP 添加服务器（stdio 默认传输）→ 重连 → 卡片回显 + 浏览详情（Resources 查看正文 / Prompts 条目）→ 新开对话调用工具（判定取调用流水账）；**外部真实 MCP 接入**：@modelcontextprotocol/server-everything（官方参考，7 资源/4 提示词/15 工具）+ @mcpcn/12306-ticket-search-mcp（12306 票务，5 工具）→ 连接 → 浏览能力面 → 新开对话调用；**P0 补充入口**：从 mcp.json 导入（写文件→预览→确认→落盘核对）+ 编辑已有服务器（改参数→回显生效）+ 删除（卡片消失 + 落盘配置真移除） | 3 次连续绿跑（2026-10-13，达验收门 ≥2） |

> **P0 补充三段（2026-10-13）**——覆盖用户实际会用的另两个入口与删除路径：
>
> **① 从 mcp.json 导入**：按钮读**固定路径**（全局 `~/.<产品目录>/mcp.json` +
> 项目级 `<workspace>/.<ProductDir>/mcp.json`，项目优先），**无文件选择器、无粘贴框**；
> 点后弹 `.mcp-import-preview` 预览（`li.mcp-import-item` 列「名称 (transport)」）→「确认导入」。
> 用例自带清理：写入前**备份全局 mcp.json，末步还原**，不污染本机真实配置。
> 固化三条易踩坑行为为断言：**同名覆盖不重复**（`verify_config_state` 内置「重复名恒为缺陷」）、
> **`disabled:true` → `enabled:false`**（反义映射）、**只增改从不删除**。
> ⚠️ 预览条目断言必须读 `.mcp-import-item`，**不能读 `.workspace-overlay` 整块文本**——
> 后者是整页包裹层，会把既存卡片名也算进来，导致误判「预览泄露」（实测踩坑）。
>
> **② 编辑**：卡片**原地变表单**（加 `.is-editing`，字段与添加表单同构，动作按钮位变「取消」）；
> 只改启动命令/参数（名字是身份锚，不改名以免后续按名定位失效）；
> 保存判据 = 退出编辑态 + 命令行回显含新值（产品无 toast）。
>
> **③ 删除**：**无确认弹层**（无 `window.confirm` / 无 `.modal`），点红色按钮即生效（<0.4s）。
> 故用例只删**自己建的 `apw-json-*` 条目**，绝不碰夹具与外部 MCP；
> 页面对象仍注册 `page.on("dialog", accept)` 并留痕，防产品后续加确认弹层时
> 因 Playwright 默认 dismiss 导致「永远删不掉」（Web 端 MCP 删除即此坑）。
> 关键判据：**UI 卡片消失 ≠ 配置真移除** → 删除判据取 `app.sqlite` 落盘值
> （`delete_server` 内部轮询 DB 直到条目消失，`verify_config_state` 再独立复核）。

> **⚠️ 关键产品行为：`new_task` 会断开全部 MCP 服务器**（2026-10-13 实测）
> ——新建会话切换工作区 → 客户端发出 `notifyRootsChanged` → **断开所有 MCP**，
> 之后按需**懒重连且不保证及时**。若紧接着发消息，目标服务器可能仍未连上
> → 模型拿不到该工具 → 用例误判 `tool_not_invoked`（实测：12306 被断开后始终
> 未自动重连，而会话已在生成）。故用例在**每次发消息前**调 `ensure_server_connected`
> 显式确认/修复连接（已连接则不点重连，避免无谓断开）；证据里 `reconnected`
> 字段直接反映本次是否发生过重连。该动作完成后**退回会话页**——否则设置面板的
> `.workspace-overlay` 会拦截组合器点击（实测 `Locator.click: Timeout`）。

> **幂等可重跑设计**（用例需反复跑，失败中断也不污染下次）：
> 导入段准备节依次 ①`purge_temp_servers`（删 DB 里 `apw-json-*` 残留；带 `reload`，
> 因为 UI 卡片列表会**陈旧渲染**——实测 UI 显示 3 张而 DB 实为 4 条，按 UI 清理会漏删）、
> ②`reset_mcp_json`（回收侧车备份/测试污染文件，回到「文件不存在」干净起点；含非测试
> 条目时**不动**，宁可跳过也不误删用户配置）、③兜底 `purge`。
> 收尾 `restore_mcp_json` 优先读**侧车备份**（跨运行持久），纠正「上次失败留下的污染
> 被这次当成原始状态」的固化问题——实测踩坑。


> 桌面端与 Web 端的 MCP 能力面**不同**：Web 端 `/mcp-config` 仅 streamableHttp（无 transport 字段）；
> 桌面端设置→MCP 支持 `stdio / HTTP / SSE` 三选一。本用例只覆盖 stdio，`platforms: [desktop]`。
> 夹具：`tests/fixture_mcp/apw_test_mcp.py`（零依赖 stdio MCP server，工具名 `apwfix_*` 前缀防与他服务器同名歧义）。

> **外部真实 MCP 接入**（2026-10-13 交付，与手工添加的夹具服务器**并存**，同一链路内覆盖）：
> 落地方式 = `scripts/setup_external_mcp.py` 把 npm 包装到 `.scratch/mcp_servers`（gitignored，幂等 + 握手自检）。
> **为什么不用 npx**：实测客户端 `StdioClientTransport` 以 `shell:false` spawn，Node 24 下
> `npx` 裸命令 ENOENT、`npx.cmd` EINVAL（安全策略拒绝 .cmd）→ 都起不来；故用 `node <entry>` 直接执行（实测可跑通）。
> **为什么经代理**：真实第三方 MCP 不写调用流水账 → 「工具真被调用」无确定性判据。代理
> `tests/fixture_mcp/mcp_proxy.py` 逐帧**透明转发** JSON-RPC 并顺带记账（与夹具**同一份**流水账），
> 判定手段统一且完全不改变真实服务器行为与返回。
> **判定口径**（按需求：只测「能连上 + 可调用」，返回值内容供人工查看）：
> 连接 = 卡片「已连接 + N 工具（N>0）」；调用 = 代理流水账命中 `tool`（外部服务器再限定 `server`）。
> **具体返回值只进证据、绝不断言**（真实数据会变：余票/日期/外部服务状态）——
> 实测 `get-sum(17,25) → 42`、`get-station-code-of-citys(上海) → SHH` 均入报告供人工核对。
> 12306 仅提供 tools 能力（无 resources/prompts）→ 不浏览，符合能力面。


## 二、框架自测清单（`pytest tests`）

| 文件 | 覆盖面 | 用例数 |
|------|--------|--------|
| `test_schema.py` | DSL schema：合法/非法 flow 解析、assert 动作 | 14 |
| `test_engine_fixture_site.py` | 引擎端到端（DSL→引擎→事件流）、失败路径、证据采集、prepare 失败、三态汇总 | 14 |
| `test_locator_repo.py` | 定位器仓库：加载、候选优先级、软计数同链、多元素解析 | 11 |
| `test_sanitize.py` | 脱敏器：敏感串→占位符、结构保留、映射加载 | 11 |
| `test_probe_page.py` | 探查原语（生成侧）+ 爬虫 probe 通道 | 9 |
| `test_base_page.py` | BasePage 纯函数：未达成归因分类、标记段拆分 | 8 |
| `test_signal_watch.py` | SignalWatch 多信号收敛判定：gate/稳定采样/提前收场、失败取证形制 | 6 |
| `test_crawler_schema.py` | 爬虫配置与快照 schema | 5 |
| `test_crawler_fixture_site.py` | 爬虫端到端：状态推进→逐状态快照（票 06） | 3 |
| `test_json_report.py` | run 目录唯一化 + 汇总合并语义 | 3 |
| `test_html_report.py` | HTML 单文件报告渲染 | 3 |
| `test_plugin_skip_report.py` | 插件跳过留痕贯通到 run 汇总 | 1 |
| `test_real_login.py` | T01 真实环境登录连通冒烟（仅 `--apw-env test` 执行，其余环境 skip 留痕） | 1 |
| `test_no_secrets.py` | 入库红线门禁：无内网 IP / 凭据值 / 产品名 | 1 |
| **合计** | | **90** |

## 三、判定与取证口径（摘要）

- 回复判定：web 端 = 完整回答六信号；桌面端 = 停止生成消失 / 回答气泡 / Thought 块在场 / 操作行 / 稳定 + `expand_thinking` 展开核对。
- 工作流运行判定（桌面端）：运行记录挂载 + 「取消运行」清除 + 完成徽标 + 「✅ 工作流完成」完成行 + 日志稳定收敛。
- AI 生成判定（桌面端）：「停止」消失 + 「发送」回归 + 助手消息轮渲染完整（空壳轮不算）+ 脚本落盘解析 + 面板内容稳定；生成后台执行切走不中断，需求回显气泡 = 确定性身份锚点。
- 只断言确定性内容（组件/状态/结构）；LLM 产出只进 `capture_context` 证据。
- 失败即取证、禁止自愈：EvidenceError 带归因分类 + 复现 + 信号时间线 + 冻结截图。
- 平台矩阵：`platforms: [desktop]` 的链路在 web 环境自动 skip 并留痕。

## 四、已知产品缺陷/行为 → 受影响用例

| 已知项（详见 AGENTS.md） | 受影响用例 | 用例侧处理 |
|--------------------------|------------|------------|
| 「加载对话历史中」偶发卡死（前端） | aml_chat_smoke、chat_concurrent_switch、mcp_config_manage | 判 fail 冻结取证，不重试跑绿 |
| Skills 广场缺失包下载 404 静默失败 | skill_market_upload_download | 逐卡尝试取一次成功，404 尝试随证据留痕 |
| 套组英文名/英文描述静默必填 + 提交须停在「基本信息」 | suite_plaza_create、playground_suite_debug | 按产品现状写步骤，不触发静默 no-op |
| React 受控输入 `fill` 不触发 onChange | workflow_manual、workflow_ai_coding | 输入一律真实键入（type/insert_text） |
| 桌面端工作流为 view slot 栈 + 运行后台执行（切走不中断） | desktop_workflow_manual、desktop_workflow_concurrent_switch | 切换 = 弹回列表 + 卡片「打开」；身份锚点 = 详情标题 + 脚本节点 + 日志「工作流开始：<名>」 |
| 桌面端常驻「服务连接异常」toast 拦截点击（关闭钮为图标钮 aria-label=关闭） | desktop_workflow_manual、desktop_workflow_concurrent_switch | 交互前 `dismiss_toasts` 幂等清理 |
| CodeMirror 编辑器逐键插入触发自动缩进 | desktop_workflow_manual、desktop_workflow_concurrent_switch | 脚本整体 insert_text 插入 |
| 会话标题异步生效（分钟级滞后） | chat_concurrent_switch | 会话 URL 作身份锚点，标题仅辅助 |
| 桌面端纯寒暄偶发缺 Thought 块 | desktop_chat_smoke | 用推理型消息保证思考块渲染（待产品侧确认） |
| Web 端 MCP **不支持 stdio**（无 transport 字段；API 静默丢弃 `transport/command/args`） | mcp_config_manage | 只覆盖 URL 型配置管理；stdio 场景由桌面端用例承担 |
| Web 端 MCP 保存成功**无 toast**、**无独立详情视图** | mcp_config_manage | 成功判据=弹层关闭+卡片出现；详情断言落在编辑弹层回显 |
| Web 端普通新对话**不挂载 MCP 工具** | mcp_config_manage | 只判「新开对话→发送→完成判定」，不断言工具可见 |
| 工具清单类回复结构不稳定（表格行数/个数波动） | mcp_config_manage | 不新增表格结构断言，LLM 产出只进 `capture_context` |
| 桌面端 AI 编写助手轮偶发空壳渲染（Thought/工具/正文全缺、脚本照常落盘；竞态窗口≈生成完成边界附近打开面板） | desktop_workflow_ai_concurrent_switch | 判 fail 冻结取证（空壳轮不算渲染完整），不重试跑绿（2026-10-12 实测，待产品侧修复） |
| 桌面端 AI 生成后台执行、会话按工作流各归各 | desktop_workflow_ai_coding、desktop_workflow_ai_concurrent_switch | 发完即走 + 切换接力 `wait_gen_done`；需求回显气泡作身份锚点，对方标记零混入 |

## 五、待办与下一步

- **扩量**：v1 目标 20~50 条业务链路（优先方向：多轮上下文漂移用例）。
- **评审 P1/P2**：`.scratch/review-p0/backlog.md`（auth 加固、裸 selector 收口、票 05 三件套等）。
- **任务票**：`.scratch/auto_playwright/issues/` 01/02/06 已交付；03（Electron launch）留空待输入；04/05/07/08 待做。
- **票 06 收尾**：快照语义人工检查（票面验收项）仍 pending。
