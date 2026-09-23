# autoPlayWright（apw）

公司内部 Agent 产品的 UI 自动化测试框架：业务链路用 YAML DSL 描述，pytest 解释执行，
Web 端与 Electron 客户端共用一套用例，报告输出结构化 JSON + HTML（Allure 可选）。

- 规格：`docs/SPEC.md`（决策记录见附录）
- 任务票：`.scratch/autoPlayWright/issues/`

## 快速开始

```powershell
python -m venv .venv
.venv\Scripts\pip install -e ".[dev]"
.venv\Scripts\playwright install chromium

# 框架自测（含浏览器端到端，走本地夹具站点）
.venv\Scripts\pytest tests
# 业务链路（默认 fixture 本地夹具环境）
.venv\Scripts\pytest flows
# 全部
.venv\Scripts\pytest tests flows
```

## 写一条用例 = 写一个 YAML

`flows/example_chat.yaml`：

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

真实环境已有首条 AI 生成的链路可参考：`flows/aml_chat_smoke.yaml`（`--apw-env test` 执行）。

配套要素：

| 内容 | 位置 |
|------|------|
| 业务链路 DSL | `flows/*.yaml` |
| 命名定位器 | `locators/<page>.yaml`（testid > role+name > placeholder/label > text > css/xpath 候选优先级） |
| 页面动作 | `src/apw/pages/`（Page Object，平台无关） |
| 环境配置 | `configs/envs/<env>.yaml`（`--apw-env` 选择） |
| 页面状态快照 | `configs/crawl/*.yaml`（爬取配置）→ `.scratch/autoPlayWright/snapshots/<env>/`（AI 生成事实依据 + 改版 diff 基线） |
| JSON 报告 | `reports/<run_id>/<flow_id>.json` + `run-summary.json`（含 `capture_context` 采集的完整对话上下文证据：用户输入 / 推理步骤 / 思考过程 / 最终答案） |
| HTML 报告 | `reports/<run_id>/report.html`（会话结束自动渲染，单文件、零依赖；也可 `python -m apw.reporter.html_report reports/<run_id>` 重渲染） |

Allure 集成（可选）：默认无需 Allure 工具链；需要 Allure 平台消费时加 `--alluredir=allure-results`，用 Allure CLI/平台读取结果数据。

## 常用命令

```powershell
pytest flows --apw-env fixture -k example   # 按环境/关键字过滤
pytest flows --apw-env test                 # 真实测试环境（表单登录自动完成）

# 调试模式：窗口可见 + 放慢动作，实时观察执行过程
pytest flows --apw-env test --apw-headed --apw-slowmo 250
# 或直接双击 / 运行 run_debug.bat（等价于上面这条，可追加 pytest 参数）

# 页面状态快照（AI 生成的事实依据 / 页面改版 diff 基线）
python -m apw.crawler --env test --config configs/crawl/aml_chat.yaml
```

## 当前留空（接缝已就位，等输入）

- **Electron launch**：`driver.mode=electron` 当前仅支持 CDP attach，
  安装包 launch 待 T03（`--apw-env` 环境里配 `cdp_endpoint` 即可先试 attach）。

## 开发

```powershell
.venv\Scripts\ruff check src tests     # lint
.venv\Scripts\pytest tests             # 框架自测（含浏览器端到端，走夹具站点）
```
