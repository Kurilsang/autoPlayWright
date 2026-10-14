# 回归触发 API（契约）

给**外部服务**用的接口：外部服务定时触发回归 → 拿到 zip 产物 → 用**它自己的**邮件通道外发。

这样发信能力与测试侧解耦：本项目只需能跑测试、能产出报告，**跨平台可用**（Linux 无任何邮件通道也能跑），
邮件认证/租户策略问题全部归外部服务。

- 实现：`src/apw/api.py`（标准库，零新增依赖）
- 启动：`python -m apw.api --host 127.0.0.1 --port 18787`（Linux：`bash run_api.sh`）
- 自测：`pytest tests/test_api.py`
- **端口约定：默认 18787**（避开常见服务占用的 8787）

## 启动

```bash
# 本机自测（只绑 127.0.0.1，无需 token）
bash run_api.sh

# 跨机给外部服务调（必须配 token；端口按需改）
nohup bash run_api.sh --host 0.0.0.0 --port 18787 > reports/api.log 2>&1 &

# 验证活着（免鉴权）
curl http://127.0.0.1:18787/health      # {"status": "ok", "runs": 0}
```

### 启动失败排查

| 现象 | 原因 | 处理 |
|---|---|---|
| `OSError: [Errno 98] Address already in use` | 端口被别的服务占用（**日志里能看到，服务实际没起来**） | `ss -lntp \| grep 18787` 看占用者，换端口 `--port <空闲端口>` |
| 绑定非本机地址但无 token | 安全兜底（拒绝启动，退出码 2） | 配 token：`APW_API_TOKEN=xxx` 或 `configs/secrets.local.yaml` 的 `api.token` |
| 外部机器连不上 | 见下「连通性排查」 | — |

### 连通性排查

```bash
# 1) 服务真在监听吗（服务器上执行）
ss -lntp | grep 18787

# 2) 本机自连通（排除防火墙）
curl -sS http://127.0.0.1:18787/health

# 3) 从调用方机器连通
curl -sS http://<服务器IP>:18787/health
```

- `Connection refused`（Errno 111）= 端口没在监听 → 服务没起来或端口不对
- `No route to host`（Errno 113）= **调用方网络层不通**（沙箱出网策略/防火墙 REJECT/网段隔离），
  与 API 自身无关；需让调用方放行该 IP:端口，或换一个调用方能到达的地址

## 鉴权

除 `/health` 外全部需要：

```
Authorization: Bearer <token>
```

token 解析顺序（与框架其余凭据同口径，真实值只存本地）：

1. `--token <t>`（命令行，最高优先）
2. 环境变量 `APW_API_TOKEN`
3. `configs/secrets.local.yaml` 的 `api.token`（gitignored）

```powershell
.venv\Scripts\python -m apw.api --gen-token      # 生成随机 token，粘进 secrets 的 api.token
```

**未配置 token 时**：仅允许绑定 `127.0.0.1`（启动时打印提示，接口无鉴权）；
**绑定非本机地址（如 `0.0.0.0`）且无 token → 拒绝启动**（退出码 2）。

生成后可自测：

```powershell
# 无 token → 401；正确 token → 200
curl.exe -H "Authorization: Bearer <token>" http://127.0.0.1:18787/runs
```

## 端点

### `POST /runs` — 触发一轮（异步）

请求体（字段全部可选，宽松解析：多传字段不报错）：

| 字段 | 类型 | 默认 | 说明 |
|---|---|---|---|
| `env` | string | `fixture` | 执行环境，对应 `configs/envs/<env>.yaml` |
| `targets` | string \| string[] | `["flows"]` | pytest 目标（目录/文件/用例 id） |
| `flows_dir` | string | `flows` | DSL 目录（`--apw-flows-dir`） |
| `tags` | string \| string[] | `[]` | pytest `-m` 标记过滤（多值以 `or` 连接） |
| `headed` | bool | `false` | 窗口可见（调试；服务器上无效） |
| `slowmo` | int | `0` | 动作间隔毫秒 |
| `extra_args` | string[] | `[]` | 追加透传给 pytest |
| `callback_url` | string | `""` | 跑完回调地址；留空则自行轮询 |
| `callback_token` | string | `""` | 回调时带的 `Authorization: Bearer` |

响应 `202`：

```json
{
  "run_id": "20261014-142924-32476a",
  "status": "queued",
  "status_url": "http://127.0.0.1:18787/runs/20261014-142924-32476a",
  "report_zip": "http://127.0.0.1:18787/runs/20261014-142924-32476a/report.zip"
}
```

**单飞队列**：同时只跑一轮，其余排队（框架 worker 上限 5，叠加触发会撞后端 LLM 限流）。

### `GET /runs/<run_id>` — 查状态与结果

```json
{
  "run_id": "20261014-142924-32476a",
  "status": "finished",
  "exit_code": 0,
  "started_at": "2026-10-14T14:29:24",
  "finished_at": "2026-10-14T14:29:27",
  "request": {"env": "fixture", "targets": ["examples"], "tags": []},
  "summary": {"total": 1, "passed": 1, "failed": 0, "skipped": 0},
  "flows": [
    {"flow_id": "example-chat", "name": "示例：发送消息并等待回复",
     "status": "passed", "skip_reason": "", "duration_ms": 1101}
  ],
  "failed_flows": [],
  "report_zip": "http://127.0.0.1:18787/runs/20261014-142924-32476a/report.zip"
}
```

`status`：`queued` → `running` → `finished`（执行器异常时 `failed`，见 `error`）。
`summary`/`flows`/`failed_flows` 在产出报告后才出现。

### `GET /runs/<run_id>/report.zip` — 下载产物包

`Content-Type: application/zip`，`Content-Disposition: attachment; filename="<run_id>-report.zip"`。

包内为 run 目录全量（可直接当邮件附件发）：

```
<run_id>/report.html          # 自包含报告（截图走包内相对路径，解压即看）
<run_id>/run-summary.json     # 机器可读汇总（写邮件正文用）
<run_id>/<flow_id>.json       # 每条链路明细（含失败取证：归因/复现/信号时间线）
<run_id>/*.png                # 失败冻结截图
```

未跑完时返回 `409`。

### `GET /runs` — 最近 20 轮（对账/补拉）

### `GET /health` — 存活探针（免鉴权）

## 完成回调

跑完向 `callback_url` `POST`（`Content-Type: application/json`，带 `callback_token`）：

```json
{
  "run_id": "20261014-142924-32476a",
  "status": "finished",
  "exit_code": 1,
  "summary": {"total": 16, "passed": 15, "failed": 1, "skipped": 0},
  "failed_flows": [{"flow_id": "aml_chat_smoke", "status": "failed"}],
  "report_zip": "http://<apw-host>:18787/runs/<run_id>/report.zip",
  "stdout_tail": "…最后 2000 字符 pytest 输出…"
}
```

回调失败**不影响**本轮结果（外部服务可补拉 `GET /runs/<run_id>`）。

## 外部服务侧典型流程

```
1. POST /runs  {env:"test", callback_url:"https://mail-svc/hook"}
   （Header: Authorization: Bearer <token>）
2. 收到回调（或轮询 GET /runs/<id> 直到 finished）
3. 失败则 GET /runs/<id>/report.zip 下载
4. 用自有邮件通道外发：正文取 summary/failed_flows，附件=zip
```

curl 示例：

```bash
TOKEN=<token>
# 触发
curl -X POST http://apw-host:18787/runs \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"env":"test","callback_url":"https://mail-svc/hook"}'
# 查状态 / 取包
curl -H "Authorization: Bearer $TOKEN" http://apw-host:18787/runs/<run_id>
curl -H "Authorization: Bearer $TOKEN" -o report.zip \
  http://apw-host:18787/runs/<run_id>/report.zip
```

## 与既有模块的关系

| 模块 | 定位 |
|---|---|
| `apw.scheduler` | 本机定时跑（不取结果外发）；与外部服务调度**二选一**，别并用 |
| `apw.notify` | 本机直接发信（smtp/ews/foxmail）；跨平台受限，保留给本机场景 |
| `apw.api` | 外部服务触发 + 取产物，**发信由外部服务负责**（跨平台推荐） |

## 注意

- **产物含真实内网 URL/产品名/截图**：zip 出到本项目之外即属外发。内网可信服务直接发即可；
  若需过外部通道，把 `build_report_zip(sanitize=True)` 接进接口（复用 `apw.sanitize` 脱敏，默认关闭）。
- 触发接口 = 能跑任意 pytest 参数，**必须配 token**，不要裸奔在公网。
