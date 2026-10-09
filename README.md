# autoPlayWright（apw）

Agent 产品的 UI 自动化测试框架：业务链路用 YAML DSL 编排（步骤/参数/断言），
判定语义沉淀为页面对象原语（Python），pytest 解释执行，
Web 端与 Electron 客户端共用一套用例，报告输出结构化 JSON + HTML（Allure 可选）。

- 规格：`docs/SPEC.md`（决策记录见附录）
- 用例进度：`docs/CASE_PROGRESS.md`；目录结构：`docs/STRUCTURE.md`
- 任务票：`.scratch/autoPlayWright/issues/`

## 快速开始

```powershell
python -m venv .venv
.venv\Scripts\pip install -e ".[dev]"
.venv\Scripts\playwright install chromium

# 框架自测（含浏览器端到端，走本地夹具站点）
.venv\Scripts\pytest tests
# DSL 示例（fixture 本地夹具站点；框架自测亦端到端覆盖）
.venv\Scripts\pytest --apw-flows-dir examples examples
# 业务链路（按 meta.envs/platforms 自动跳过不匹配项；真实环境见「常用命令」）
.venv\Scripts\pytest flows
# 全部
.venv\Scripts\pytest tests flows
```

## 环境配置（跑非 fixture 环境前）

- **fixture（默认）**：零配置，`pytest flows` 走本地夹具站点。
- **test（真实测试环境）**：复制 `configs/envs/test.example.yaml` → `configs/envs/test.yaml`
  填内网地址（gitignored，真实值不入库）；登录凭据放 `configs/secrets.local.yaml`
  （`username`/`password`，gitignored）或 CI 环境变量 `APW_USERNAME`/`APW_PASSWORD`。
  登录成功后 `configs/auth-state.json` 回写会话，后续运行免登录。
- **desktop（Electron 客户端）**：复制 `configs/desktop.local.example.bat` → `configs/desktop.local.bat`
  填客户端路径（或先 `set APW_DESKTOP_EXE=...`）；客户端需带 `--remote-debugging-port=9333` 启动，
  `run_full_debug.bat` 会自动拉起并等 CDP 就绪。
- **脱敏映射**：复制 `configs/sanitize.example.yaml` → `configs/sanitize.local.yaml`
  （快照/探查产物落盘前自动脱敏，映射真实串仅存本地）。

## 一条链路 = 一个 YAML（编排）

`examples/example_chat.yaml`（DSL 示例，fixture 本地夹具站点；业务链路在 `flows/`）：

```yaml
meta:
  id: example-chat
  name: 示例：发送消息并等待回复
  platforms: [web]          # web | desktop
  envs: [fixture]           # 仅在 fixture 环境执行；test=真实环境
  tags: [P0, example]
steps:
  - do: { page: agent_chat, action: new_session, args: {} }
  - do: { page: agent_chat, action: send_message, args: { text: "你好，夹具" } }
  - do: { page: agent_chat, action: wait_reply_done, args: { timeout_ms: 15000 } }
  - do: { page: agent_chat, action: capture_context, args: {} }
  - assert: { type: visible, page: agent_chat, target: message_list }
  - assert: { type: text_contains, page: agent_chat, target: message_list, expected: "你好，夹具" }
  - judge: { note: "v1 预留：LLM-as-Judge 后续接入" }
```

真实环境链路可参考 `flows/aml_chat_smoke.yaml`（`--apw-env test` 执行；已入库 12 条业务链路见 `flows/*.yaml`，含桌面端 `flows/desktop_chat_smoke.yaml`；另有 DSL 示例 `examples/example_chat.yaml` 不计业务链路；清单与进度见 `docs/CASE_PROGRESS.md`）。
新页面「五步走」的完整指引（探查快照 → 定位器 → 页面对象 → flow → 验收门）见 `AGENTS.md`「怎么加用例」；
目录与各层职责见 `docs/STRUCTURE.md`。

配套要素：

| 内容 | 位置 |
|------|------|
| 业务链路 DSL | `flows/*.yaml` |
| DSL 示例 | `examples/example_chat.yaml`（fixture 夹具站点演示，非业务链路） |
| 命名定位器 | `locators/<page>.yaml`（testid > role+name > placeholder/label > text > css/xpath 候选优先级） |
| 页面动作 | `src/apw/pages/`（Page Object，平台无关） |
| 环境配置 | `configs/envs/<env>.yaml`（`--apw-env` 选择） |
| 脱敏映射 | `configs/sanitize.local.yaml`（敏感串→占位符，真实值仅存本地；模板 `configs/sanitize.example.yaml`）——快照/探查产物落盘前自动脱敏 |
| 页面状态快照 | `configs/crawl/*.yaml`（爬取配置）→ `.scratch/autoPlayWright/snapshots/<env>/`（AI 生成事实依据 + 改版 diff 基线；JSON/HTML/PNG 均不入库） |
| JSON 报告 | `reports/<run_id>/<flow_id>.json` + `run-summary.json`（run_id = 时间戳+熵后缀全局唯一，汇总为合并语义；含 `capture_context` 采集的完整对话上下文证据：用户输入 / 推理步骤 / 思考过程 / 最终答案，三态 passed/failed/skipped + 跳过原因） |
| HTML 报告 | `reports/<run_id>/report.html`（会话结束自动渲染，单文件、零依赖；也可 `python -m apw.reporter.html_report reports/<run_id>` 重渲染） |

Allure 集成（可选）：默认无需 Allure 工具链；需要 Allure 平台消费时加 `--alluredir=allure-results`，用 Allure CLI/平台读取结果数据。

## 常用命令

```powershell
pytest flows --apw-env fixture -m "not slow"  # 按 marker 筛选（fixture 环境下不匹配项自动 skip）
pytest --apw-flows-dir examples examples     # DSL 示例（fixture 本地夹具站点）
pytest flows --apw-env test                 # 真实测试环境（表单登录自动完成）
# 桌面端（Electron 客户端先带调试端口启动：<app>.exe --remote-debugging-port=9333）
pytest flows/desktop_chat_smoke.yaml --apw-env desktop

# 调试模式：窗口可见 + 放慢动作，实时观察执行过程
pytest flows --apw-env test --apw-headed --apw-slowmo 250
# 或直接双击 / 运行 run_debug.bat（等价于上面这条，可追加 pytest 参数）
# run_full_debug.bat = 全量调试跑全部用例（桌面端自动带调试端口拉起客户端）

# 页面状态快照（AI 生成的事实依据 / 页面改版 diff 基线）
python -m apw.crawler --env test --config configs/crawl/aml_chat.yaml
```

## 当前留空（接缝已就位，等输入）

- **Electron launch**：`driver.mode=electron` 当前仅支持 CDP attach
  （已有真实用例跑通：`flows/desktop_chat_smoke.yaml` @ `configs/envs/desktop.yaml`），
  安装包 launch 待 T03。

## 开发

```powershell
.venv\Scripts\ruff check src tests     # lint
.venv\Scripts\pytest tests             # 框架自测（含浏览器端到端，走夹具站点）
```
