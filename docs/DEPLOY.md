# 部署规范（DEPLOY）

本项目的部署口径。**唯一权威版本**，其他文档只放指针。

## 部署形态

- 部署目标：Linux 服务器上的一个目录（真实路径见本地 `configs/deploy.local.yaml`，gitignored）
- 该目录经 SMB 挂载到开发机（Windows 上是某个盘符），因此**本机打包后可直接写文件过去，无需 scp/ssh 密码**
- 部署机 SSH：密码登录（无免密 key），日常部署走挂载盘即可

## 包规格

- 包名：`apw-deploy-YYYYMMDD.tar.gz`
- **平铺结构**：包根直接是 `src/`、`flows/`、`pyproject.toml`…（无顶层目录，解压即覆盖部署目录）
- 含 `.git`：服务器上可 `git log --oneline -3` 核对实际落地版本

## 一键部署（本机执行）

```powershell
# 打包 + 直接部署到挂载盘（覆盖代码，保留 .venv/reports/configs）
.venv\Scripts\python scripts\pack_release.py --deploy

# 只打包（产出 dist/apw-deploy-<日期>.tar.gz，不部署）
.venv\Scripts\python scripts\pack_release.py --verify

# 附带本地真实配置（内网直传场景；默认不带，凭据不入包）
.venv\Scripts\python scripts\pack_release.py --deploy --with-secrets

# 部署到其他目录
.venv\Scripts\python scripts\pack_release.py --deploy --target <盘符>:\<目录>
```

部署目标从 `configs/deploy.local.yaml` 读取（见下），未配置时用 `--target` 显式指定。

## 服务器上执行（SSH 登录后）

```bash
cd <部署目录>

tar -xzf apw-deploy-<日期>.tar.gz      # 解压覆盖（保留 .venv/reports/configs）

# 首次部署才需要；已有 .venv 可跳过
bash setup_linux.sh --with-deps

# 首次配置真实环境
cp configs/envs/test.example.yaml configs/envs/test.yaml
cp configs/notify.example.yaml configs/secrets.local.yaml

# 跑起来
bash run_flows.sh
bash run_scheduler.sh

# 回归触发 API（外部服务调用；端口约定 18787）
bash run_api.sh --host 0.0.0.0 --port 18787
```

### 回归触发 API 的部署要点

- **端口约定 18787**：避开常见服务占用的 8787；被占用时 `ss -lntp | grep 18787` 查占用者后换端口
- **必须配 token**（绑非本机地址时）：写进 `configs/secrets.local.yaml` 的 `api.token`，
  或启动时 `APW_API_TOKEN=xxx`；生成：`python -m apw.api --gen-token`
- **后台常驻**（推荐）：

  ```bash
  nohup bash run_api.sh --host 0.0.0.0 --port 18787 > reports/api.log 2>&1 &
  curl http://127.0.0.1:18787/health        # {"status": "ok", ...}
  ```

- **启动失败先看 `reports/api.log`**：`Errno 98 Address already in use` = 端口被占（服务其实没起来）
- 调用方连不上时按 `docs/API.md` 的「连通性排查」区分：`Errno 111` = 没监听、
  `Errno 113` = 调用方网络层不通（沙箱出网策略/防火墙，与 API 无关）
- systemd 常驻示例（与 scheduler 并列，按需启用）：

  ```ini
  # /etc/systemd/system/apw-api.service
  [Unit]
  Description=apw 回归触发 API
  After=network-online.target

  [Service]
  WorkingDirectory=<部署目录>
  Environment=PYTHONIOENCODING=utf-8
  Environment=APW_API_TOKEN=<token>
  ExecStart=<部署目录>/.venv/bin/python -m apw.api --host 0.0.0.0 --port 18787
  Restart=always

  [Install]
  WantedBy=multi-user.target
  ```

容器/root 跑 Chromium：

```bash
APW_CHROMIUM_ARGS="--no-sandbox --disable-dev-shm-usage" bash run_flows.sh
```

## 部署语义（重要）

| 项 | 行为 |
|---|---|
| 覆盖 | 源码、用例、定位器、脚本、文档、`*.example.yaml` 模板 |
| **保留** | `.venv/`（服务器既有 Python 环境）、`reports/`（历史产物）、`configs/`（真实配置）、`.git/` |
| 不入包 | `.venv`、`reports`、`.scratch`、`video`、`__pycache__`、`dist`、`*.local.*` 真实凭据 |
| 校验 | `--verify` 检查凭据泄漏（应恒为 0）与顶层结构 |

## 本地部署配置（gitignored）

`configs/deploy.local.yaml`：

```yaml
target: "Z:\\web_agent_test"                          # 开发机上的挂载盘路径
remote_path: "/mnt/fileroot/<user>/web_agent_test"    # 服务器上的真实路径（文档展示用）
host: "<部署机 IP 或主机名>"
user: "<部署机账号>"
```

模板见 `configs/deploy.example.yaml`。**真实值不入库**（AGENTS 红线）。

## 变更记录

- 2026-10-13 首次部署
- 2026-10-14 二次部署（新增 `apw.api` 回归触发 API + `apw.notify` 通知邮件）
