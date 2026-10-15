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

# 收件人集中配置（可选）：只改名单、不碰凭据文件；整段覆盖 secrets 的同名字段
cp configs/notify.example.yaml configs/notify.local.yaml   # 只留 notify: 段填真实邮箱

# 跑起来
bash run_flows.sh
bash run_and_mail.sh              # 一键：跑业务链路 + 发带附件的报告邮件
bash run_scheduler.sh

# 回归触发 API（外部服务调用；端口约定 18787）
bash run_api.sh --host 0.0.0.0 --port 18787
```

### 发报告邮件（`run_and_mail.sh` / `run_and_mail.bat`）

跑完 `flows` 后自动把本轮 run 目录打成 zip 附上，发摘要给配置里的收件人。

- **收件人集中配置**：`configs/notify.local.yaml` 的 `notify:` 段（`report_to` 主收件人、`cc` 抄送）。
  改名单只动这个文件；优先级 `notify.local.yaml` < `APW_NOTIFY_TO` < `--to/--cc`
- **一键脚本**：`bash run_and_mail.sh`（Linux）/ `run_and_mail.bat`（Windows）；
  `--no-mail` 只跑不发、`--env fixture` 换环境、其余参数透传 pytest
- **只跑 flows**：`tests` 是框架自测，需要 `--apw-env fixture`，与真实环境混跑会出假红
- **附件 = API 的 report.zip**：同一函数产物（`attach_run_zip` → `apw.api.build_report_zip`），
  外部服务从 `GET /runs/<id>/report.zip` 拿到的包与邮件附件逐字节一致

#### 发信通道怎么选（重要）

| 通道 | 认证要求 | 附件 | 适用 |
|---|---|---|---|
| `smtp` + 私人邮箱授权码 | 只需**你自己**的邮箱授权码 | ✅ | **推荐**：无需任何内网权限 |
| `smtp` + xoauth2 | M365 交互式登录（`--login`，无法无人值守） | ✅ | 有租户权限时 |
| `ews` / `foxmail` | 无（foxmail 复用本机客户端登录态） | ❌ | 兜底；foxmail 时序脆弱，见 AGENTS「已知框架陷阱」 |

**私人邮箱授权码是本项目推荐的发信方式**：`auth: basic` + 授权码即可，
不碰 OAuth、不需要 M365 任何权限、可无人值守（服务器上也能用）。以 QQ/Foxmail 邮箱为例：

```yaml
smtp:
  host: smtp.qq.com
  port: 465
  security: ssl
  auth: basic
  transport: smtp
  username: <你的邮箱>@qq.com
  password: <16位授权码>       # 邮箱设置里生成，只显示一次
  from: <你的邮箱>@qq.com
```

> **注意**：收信方若走 M365（如本项目的目标邮箱域），**自建 SMTP 服务或 MX 直连投递不可行**——
> 需要出口 IP 有 PTR 反向解析，普通办公/家庭宽带没有，M365 会判 550 或静默丢弃。
> 走有信誉的发信服务或已有邮箱账号即可绕开。

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
- 2026-10-14 三次调整：收件人集中配置（`configs/notify.local.yaml`）+ 邮件附件与
  `report.zip` 同口径（`attach_run_zip` → `apw.api.build_report_zip`）
- 2026-10-15 四次调整：一键跑测+发报告脚本（`run_and_mail.sh`/`.bat`）；发信通道
  明确推荐「私人邮箱 SMTP + 授权码」（无需 M365 权限，可无人值守）；记录自建 SMTP/MX
  直投不可行的原因（出口 IP 无 PTR）
