# autoPlayWright（apw）

公司内部 Agent 产品的 UI 自动化测试框架：业务链路用 YAML DSL 描述，pytest 解释执行，
Web 端与 Electron 客户端共用一套用例，报告输出结构化 JSON + Allure。

- 规格：`docs/SPEC.md`（决策记录见附录）
- 任务票：`.scratch/autoPlayWright/issues/`

## 快速开始

```powershell
python -m venv .venv
.venv\Scripts\pip install -e ".[dev]"
.venv\Scripts\playwright install chromium

# 跑全部框架自测 + flows/ 下的业务链路
.venv\Scripts\pytest
# 只跑业务链路（默认 fixture 本地夹具环境）
.venv\Scripts\pytest flows
```

## 写一条用例 = 写一个 YAML

`flows/example_chat.yaml`：

```yaml
meta:
  id: example-chat
  name: 示例：发送消息并等待回复
  platforms: [web]          # web | desktop，双端各跑一遍
  tags: [P0, example]
steps:
  - do: { page: agent_chat, action: new_session, args: {} }
  - do: { page: agent_chat, action: send_message, args: { text: "你好，夹具" } }
  - do: { page: agent_chat, action: wait_reply_done, args: { timeout_ms: 15000 } }
  - assert: { type: visible, target: message_list }
  - assert: { type: text_contains, target: message_list, expected: "你好，夹具" }
  - judge: { note: "v1 预留：LLM-as-Judge 后续接入" }
```

配套要素：

| 内容 | 位置 |
|------|------|
| 业务链路 DSL | `flows/*.yaml` |
| 命名定位器 | `locators/<page>.yaml`（testid > role > text > css/xpath 候选优先级） |
| 页面动作 | `src/apw/pages/`（Page Object，平台无关） |
| 环境配置 | `configs/envs/<env>.yaml`（`--apw-env` 选择） |
| JSON 报告 | `reports/<run_id>/<flow_id>.json` + `run-summary.json` |

## 常用命令

```powershell
pytest flows --apw-env fixture -k example   # 按环境/关键字过滤
pytest flows --apw-env test                 # 真实测试环境（登录留空，待 T01）
```

## 当前留空（接缝已就位，等输入）

- **登录**：`auth.type=storage_state` 的 `state_file` 产出方式待 T01 spike，
  未配置前对真实环境执行会抛 `NotImplementedError`。
- **Electron launch**：`driver.mode=electron` 当前仅支持 CDP attach，
  安装包 launch 待 T03（`--apw-env` 环境里配 `cdp_endpoint` 即可先试 attach）。

## 开发

```powershell
.venv\Scripts\ruff check src tests     # lint
.venv\Scripts\pytest tests             # 只跑框架自测（不触发浏览器）
```
