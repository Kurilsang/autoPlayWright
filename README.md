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

Linux / 服务器（网页端）：`bash setup_linux.sh --with-deps` 一键装好（venv + 依赖 + Playwright chromium），
`bash run_flows.sh` 无头跑业务链路（`--debug` 转窗口可见 + 慢动作，其余参数透传 pytest）。
容器以 root 跑 Chromium 需加启动参数：`APW_CHROMIUM_ARGS="--no-sandbox --disable-dev-shm-usage" bash run_flows.sh`。

## 启动方式（全部入口）

**Windows（开发机）**

| 入口 | 用途 |
|------|------|
| `run_debug.bat` | 一键调试：`pytest flows --apw-env test --apw-headed --apw-slowmo 250`，额外参数透传 pytest（如 `-k smoke`、`--apw-env fixture`） |
| `run_and_mail.bat` | 一键：跑 `flows` + 发带附件（run 目录 zip）的报告邮件；`--no-mail` 只跑、`--to/--cc` 覆盖收件人、`--env` 换环境，其余透传 pytest（见「报告邮件」） |
| `run_full_debug.bat` | 全量调试跑全部用例（P1 框架自测 → P2 登录冒烟 → P3 夹具样例 → P4 网页端链路 → P5 桌面端链路）；桌面端自动带 `--remote-debugging-port=9333` 拉起客户端并等 CDP 就绪；`APW_SLOWMO` 调慢动作 |
| `run_slides.bat` | 打开 `docs/banner-light.html` 项目报告页 |
| `run_video.bat` | Remotion 演示动画出片（`video/` 本地资产，gitignored，可选） |
| `.venv\Scripts\pytest ...` | 直接调 pytest（配方见「常用命令」） |

**Linux / 服务器（网页端）**

| 入口 | 用途 |
|------|------|
| `bash setup_linux.sh` | 一次性安装：venv + pip 依赖 + Playwright chromium；`--with-deps` 另装 Chromium 系统库（需 root） |
| `bash run_flows.sh` | 无头跑业务链路（默认 `flows --apw-env test`）；`--debug` 转窗口可见 + 250ms 慢动作；`--debug`/`--apw-env` 之外参数透传 pytest |
| `bash run_and_mail.sh` | 一键：跑业务链路 + 发带附件报告邮件（同 `run_and_mail.bat`） |
| `bash run_scheduler.sh` | 定时执行常驻（默认 30 分钟一轮）；`--once` 单跑一轮退出；`--` 后透传 pytest 参数（见「定时执行」） |

**模块入口（跨平台，Python 直调）**

| 入口 | 用途 |
|------|------|
| `python -m apw.scheduler` | 定时调度内核（`run_scheduler.sh` 即其包装；Windows 定时用它） |
| `python -m apw.notify` | 通知邮件直发（`--test` 冒烟 / `--summary <run-summary.json> --report-zip` 发报告；见「报告邮件」） |
| `python -m apw.crawler` | 页面状态快照（AI 生成事实依据 / 改版 diff 基线；`--env`/`--config` 见「常用命令」） |
| `python -m apw.reporter.html_report reports/<run_id>` | HTML 报告重渲染（会话结束已自动渲染一次） |

## 配置

### 配置文件（configs/）

| 文件 | 入库 | 说明 |
|------|------|------|
| `configs/envs/fixture.yaml` | 是 | fixture 本地夹具站点，零配置开箱即用 |
| `configs/envs/test.example.yaml` → `test.yaml` | 模板入库，真实配置 gitignored | 真实测试环境（地址/登录选择器），真实值仅存本地/服务器 |
| `configs/envs/desktop.yaml` | 是 | 桌面端环境（CDP attach 端点） |
| `configs/secrets.local.yaml` | 否 | 测试环境表单登录凭据 `username`/`password`（或环境变量 `APW_USERNAME`/`APW_PASSWORD`，见下）+ 发信 `smtp:` 段 + API `api.token` |
| `configs/notify.local.yaml` | 否 | **报告邮件收件人集中配置**（`notify:` 段：`report_to` 主收件人 / `cc` 抄送）；模板 `configs/notify.example.yaml` |
| `configs/sanitize.example.yaml` → `sanitize.local.yaml` | 模板入库 | 脱敏映射（敏感串→占位符，快照/探查产物落盘前自动执行） |
| `configs/desktop.local.example.bat` → `desktop.local.bat` | 模板入库 | 桌面客户端 exe 路径（`APW_DESKTOP_EXE`） |
| `configs/auth-state.json` | 否 | 登录态回写（首次表单登录成功后生成，后续运行免登录） |
| `configs/crawl/*.yaml` | 是 | 爬取/探查配置（状态路径 + 完成信号探针） |

### 环境配置字段（configs/envs/<env>.yaml）

```yaml
base_url: ""            # http(s)://、file:// 或相对仓库根路径；desktop 留空 = 不导航（客户端启动即其 UI）
driver:
  mode: web             # web | electron
  channel: ""           # 如 "msedge" 用系统浏览器；空 = Playwright 内置 chromium
  headless: true        # --apw-headed 可覆盖
  slow_mo: 0            # 动作间隔 ms；--apw-slowmo 可覆盖
  args: []              # chromium 启动参数（Linux 容器 root 需 --no-sandbox）；APW_CHROMIUM_ARGS 可追加
  electron:
    cdp_endpoint: ""    # CDP attach 端点（如 http://127.0.0.1:9333）；APW_CDP_ENDPOINT 可覆盖
auth:
  type: none            # none（夹具免登录）| storage_state | form（表单登录）
  login_url: ""         # form：登录页地址
  login_path_hint: /login  # URL 含此片段视为未登录
  username_selector: "#username"
  password_selector: "#password"
  submit_selector: 'button[type="submit"]'
  username: ""          # 不推荐入库；解析顺序：显式配置 → 环境变量 → secrets_file
  password: ""
  secrets_file: ""      # 如 configs/secrets.local.yaml
  state_file: ""        # 登录态回写路径（如 configs/auth-state.json），登录成功后生成
```

### 环境变量（服务器/CI 推荐，不落盘）

| 变量 | 作用 |
|------|------|
| `APW_USERNAME` / `APW_PASSWORD` | form 登录凭据（优先于 `secrets.local.yaml`） |
| `APW_CHROMIUM_ARGS` | 追加 chromium 启动参数（shell 风格分词）；容器 root 必加 `"--no-sandbox --disable-dev-shm-usage"` |
| `APW_CDP_ENDPOINT` | 覆盖桌面端 `cdp_endpoint`（默认调试端口被占时换端口） |
| `APW_DESKTOP_EXE` | 桌面客户端 exe 路径（`run_full_debug.bat` 拉起用，优先于 `desktop.local.bat`） |
| `APW_SLOWMO` | `run_full_debug.bat` 慢动作毫秒数（默认 250） |
| `PYTHON` | `setup_linux.sh` 指定 Python 解释器（如 `PYTHON=python3.12`） |
| `PYTHONIOENCODING` | 控制台/子进程输出编码（各脚本内已默认 utf-8） |

### 命令行选项

pytest 插件（`--apw-*`）：

| 选项 | 默认 | 说明 |
|------|------|------|
| `--apw-env` | `fixture` | 执行环境名 → `configs/envs/<env>.yaml` |
| `--apw-flows-dir` | `flows` | 链路目录（相对仓库根；`examples` 可跑 DSL 示例） |
| `--apw-reports-dir` | `reports` | 报告输出目录（相对仓库根） |
| `--apw-headed` | 关 | 浏览器窗口可见（覆盖 `headless: true`） |
| `--apw-slowmo` | `0` | 每个动作间延迟 ms（配合 `--apw-headed` 调试） |

pytest 原生照常可用：`-k` 关键词、`-m` marker 筛选、`--alluredir` Allure 结果目录等。

调度器选项（`python -m apw.scheduler`）见「定时执行」。

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

真实环境链路可参考 `flows/aml_chat_smoke.yaml`（`--apw-env test` 执行；已入库 16 条业务链路见 `flows/*.yaml`，含桌面端 5 条 `flows/desktop_*.yaml`；另有 DSL 示例 `examples/example_chat.yaml` 不计业务链路；清单与进度见 `docs/CASE_PROGRESS.md`）。
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

## 报告邮件（跑完自动发摘要 + 附件）

跑完业务链路后把本轮 run 目录打成 zip 附上，发摘要给收件人。

```powershell
# 一键：跑 flows 并发送（Windows / Linux）
.\run_and_mail.bat
bash run_and_mail.sh

# 只跑不发 / 换环境 / 临时改收件人（其余参数透传 pytest）
.\run_and_mail.bat --no-mail
.\run_and_mail.bat --env fixture
.\run_and_mail.bat --to a@x.com,b@y.com --cc lead@x.com

# 等价模块入口（额外做「附件 = API report.zip」逐字节核对）
.venv\Scripts\python scripts\console_summary.py --targets flows --env test --mail
```

**收件人集中配置** —— 改名单只动 `configs/notify.local.yaml`（gitignored），不用碰凭据文件、不用动命令行：

```yaml
notify:
  report_to:                    # 主收件人（加一行 = 加一个收件人）
    - <user>@<domain>
  cc:                           # 可选：抄送（只进 SMTP 信封，不出现在 To 头）
    - <lead>@<domain>
```

优先级：`smtp.to`（secrets）< `notify.local.yaml` < 环境变量 `APW_NOTIFY_TO` < 命令行 `--to/--cc`。
`report_to` **非空即整体取代** `to`（可给报告单独一份名单）。

**发信通道**（`smtp.transport`）：

| 通道 | 认证要求 | 附件 |
|---|---|---|
| `smtp` + **私人邮箱授权码** | 只需自己的邮箱授权码 | ✅ **推荐**（无需任何内网权限，可无人值守） |
| `smtp` + `xoauth2` | M365 交互式 `--login` | ✅ |
| `ews` / `foxmail` | 无（foxmail 复用本机客户端登录态） | ❌ |

**附件与回归触发 API 同口径**：邮件附件直接调 `apw.api.build_report_zip`，
与外部服务 `GET /runs/<id>/report.zip` 下载到的包**逐字节一致**（同一函数产物）。

一键脚本**只跑 `flows`**：`tests` 是框架自测，需要 `--apw-env fixture`，与真实环境混跑会出假红。

## 定时执行（固定间隔 / cron 钟点锚定）

调度器 `python -m apw.scheduler`（Linux 用 `run_scheduler.sh` 等价包装），排期在服务内自管：

```bash
bash run_scheduler.sh                      # 常驻：每 30 分钟跑 flows --apw-env test
APW_NOTIFY=always APW_NOTIFY_ATTACH=1 bash run_scheduler.sh   # 同上（每 30 分钟）+ 每轮自动发完整报告邮件
bash run_scheduler.sh --interval-minutes 60  # 调整间隔
bash run_scheduler.sh --cron "0 21 * * *"    # 每天 21:00（cron 钟点锚定，首轮到点才跑）
bash run_scheduler.sh --cron "0 18 * * 5"    # 每周五 18:00（周频率）
bash run_scheduler.sh --cron "0 21 * * *" --cron "0 18 * * 5"   # 多档并集：每天 21:00 + 每周五 18:00
bash run_scheduler.sh --cron "0 21 * * 1"    # 每周一 21:00（周频率）
bash run_scheduler.sh --cron "0 21 1 * *"    # 每月 1 日 21:00（月频率）
bash run_scheduler.sh --once               # 单跑一轮就退出（联调/冒烟；立即执行）
bash run_scheduler.sh -- --apw-env fixture   # `--` 后透传 pytest 参数（替换默认）
# 停止：pkill -f apw.scheduler（SIGTERM 优雅停，当前轮子进程一并终止）
# Windows：.venv\Scripts\python -m apw.scheduler（同一模块）
```

`--cron` 为标准 5 字段（分 时 日 月 周，周 0/7=周日）：支持 `*`、`n`、`a-b`、`*/s`、
`a-b/s`、`n/s`、逗号列表、跨区间（`22-2`）；日与周同时限定时取「或」（经典 cron 语义）。
**`--cron` 可给多次 = 多档排期并集**（单服务承载，如每天 21:00 + 每周五 18:00）。
`--cron` 与 `--interval-minutes` 互斥。

- 固定节奏排期：一轮超时不叠跑、不补跑错过的槽位；每轮输出落 `reports/scheduler/run-<ts>.log`，
  测试报告照常落 `reports/<run_id>/`；Ctrl+C / SIGTERM 优雅停（当前轮子进程一并终止）
- **systemd 常驻**（推荐服务器用法；路径填实际部署目录）：

  ```ini
  # /etc/systemd/system/apw-scheduler.service
  [Unit]
  Description=apw 定时执行
  After=network-online.target

  [Service]
  WorkingDirectory=<部署目录>
  Environment=PYTHONIOENCODING=utf-8
  ExecStart=<部署目录>/.venv/bin/python -m apw.scheduler --root <部署目录>
  Restart=always

  [Install]
  WantedBy=multi-user.target
  ```

  ```bash
  systemctl enable --now apw-scheduler
  ```

- **crontab 备选**（一般不需要：每日/每周/每月排期用上面的 `--cron` 服务内自管；
  系统 crontab 只在想让外部调度托管时用 `--once`）：

  ```cron
  */30 * * * * cd <部署目录> && .venv/bin/python -m apw.scheduler --once >> reports/scheduler/cron.log 2>&1
  ```

- 部署（打包 → 上传 → 服务器解压）与**服务启停 / 冒烟（发信）标准命令**见
  [`docs/DEPLOY.md`](docs/DEPLOY.md)（「服务启停与冒烟」为唯一权威，每次部署交付必给）。

## 回归触发 API（外部服务触发跑测、取报告包）

给**外部服务**用的接口：它定时触发回归 → 拿到 zip 产物 → 用它自己的邮件通道外发。
这样发信能力与测试侧解耦，本项目只需能跑测试、能产出报告（跨平台，Linux 无邮件通道也能跑）。
完整契约见 [`docs/API.md`](docs/API.md)。

```bash
# 启动（Linux；默认端口 18787）
bash run_api.sh                                       # 本机自测（只绑 127.0.0.1）
nohup bash run_api.sh --host 0.0.0.0 --port 18787 > reports/api.log 2>&1 &   # 跨机（须配 token）

# Windows
.venv\Scripts\python -m apw.api --port 18787

# 停止
pkill -f apw.api
```

| 方法 | 路径 | 作用 |
|---|---|---|
| `POST` | `/runs` | 触发一轮（异步，返回 `run_id` / `status_url` / `report_zip`） |
| `GET` | `/runs/<run_id>` | 查状态与摘要（`summary` / `flows` / `failed_flows`） |
| `GET` | `/runs/<run_id>/report.zip` | 下载产物包（`report.html` + JSON + 失败冻结截图，可直接当邮件附件） |
| `GET` | `/runs` | 最近 20 轮（对账/补拉） |
| `GET` | `/health` | 存活探针（免鉴权） |

```bash
TOKEN=<token>   # configs/secrets.local.yaml 的 api.token，或 APW_API_TOKEN 环境变量
curl -X POST http://<服务器IP>:18787/runs \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"env":"test","callback_url":"https://mail-svc/hook"}'
curl -H "Authorization: Bearer $TOKEN" -o report.zip \
  http://<服务器IP>:18787/runs/<run_id>/report.zip
```

- 鉴权：除 `/health` 外都要 `Authorization: Bearer <token>`；token 解析顺序
  `--token` → `APW_API_TOKEN` → `configs/secrets.local.yaml` 的 `api.token`；
  生成：`python -m apw.api --gen-token`
- 安全兜底：未配 token 时只允许绑 `127.0.0.1`；绑 `0.0.0.0` 且无 token **拒绝启动**
- 单飞队列：同时只跑一轮，其余排队（避免叠加触发撞后端 LLM 限流）
- 完成回调：跑完 `POST callback_url`（带 `summary` / `failed_flows` / `report_zip` / `stdout_tail`），
  失败不影响本轮结果，可补拉 `GET /runs/<id>`
- 启动失败排查与连通性诊断（`Errno 98` 端口占用 / `Errno 111` 未监听 / `Errno 113` 网络不通）
  见 [`docs/API.md`](docs/API.md) 的「启动」与「连通性排查」两节

## 当前留空（接缝已就位，等输入）

- **Electron launch**：`driver.mode=electron` 当前仅支持 CDP attach
  （已有真实用例跑通：`flows/desktop_chat_smoke.yaml` @ `configs/envs/desktop.yaml`），
  安装包 launch 待 T03。

## 开发

```powershell
.venv\Scripts\ruff check src tests     # lint
.venv\Scripts\pytest tests             # 框架自测（含浏览器端到端，走夹具站点）
```
