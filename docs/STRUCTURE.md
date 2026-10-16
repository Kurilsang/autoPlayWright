# 目录结构

项目各目录/文件的职责与归属。用例清单与进度见 `docs/CASE_PROGRESS.md`，规格与决策见 `docs/SPEC.md`。

## 顶层

```text
autoPlayWright/
├─ flows/                  业务链路用例（YAML DSL，一链路一文件）
├─ examples/               DSL 示例（fixture 夹具站点演示，不计业务链路）
├─ locators/               命名定位器仓库（一页一文件，禁止散落裸 selector）
├─ src/apw/                框架源码（分层见下）
├─ tests/                  框架自测（含浏览器端到端，走 tests/fixture_site/ 本地夹具站点）
├─ configs/                环境/爬取/本地配置（敏感项 gitignored，见下）
├─ scripts/                生成侧工具脚本（AI 复用）
├─ docs/                   规格、用例进度、目录结构、项目报告页
├─ reports/                运行产物（gitignored；report.html 会话结束自动渲染）
├─ workspace/              生成侧临时探查脚本（gitignored，不入库）
├─ .scratch/               任务票、评审批次、页面快照产物（快照不入库）
├─ run_debug.bat           一键调试：单条/筛选链路，窗口可见 + 250ms 慢动作
├─ run_full_debug.bat      全量调试：跑全部用例；桌面端自动带 --remote-debugging-port=9333 拉起客户端
├─ run_slides.bat          打开 docs/banner-light.html 项目报告页
├─ pyproject.toml          包定义 + pytest11 插件入口
├─ README.md               使用入口（安装、配置、常用命令）
└─ AGENTS.md               Agent 规则：硬约束、新页面五步走、已知产品行为/缺陷
```

## src/apw 分层

执行链路：`dsl`（schema 校验）→ `engine`（FlowRunner 产 StepEvent）→ `pages` + `locators` →
`driver`（Web/Electron 统一输出 Page）→ `reporter`（JSON 第一公民）→ `pytest_plugin`（下游消费者）。
引擎不 import pytest/allure。

| 模块 | 职责 |
|------|------|
| `config.py` | 环境配置加载（`configs/envs/<env>.yaml`） |
| `sanitize.py` | 脱敏：敏感串→占位符，快照/探查产物落盘前自动执行 |
| `pytest_plugin.py` | pytest11 插件：收集 flows、`--apw-*` 选项、跳过留痕、报告接线 |
| `dsl/` | flow schema（meta/steps：do·assert·judge）与加载校验 |
| `engine/` | FlowRunner、StepEvent、页面动作注册表（`registry.py`） |
| `pages/` | 页面对象：动作 = 语义原语（链路级完成判定 + 失败取证） |
| `locators/` | 定位器仓库解析（候选优先级 testid > role+name > placeholder/label > text > css/xpath） |
| `driver/` | Web / Electron 统一驱动（Electron 当前仅 CDP attach） |
| `auth/` | 登录（form 表单自动登录；凭据解析：显式配置 → 环境变量 → secrets_file） |
| `crawler/` | 生成侧状态化爬虫（`python -m apw.crawler`）+ `page: probe` 探查原语 |
| `reporter/` | JSON 报告、run 汇总合并、单文件 HTML 渲染 |

## 用例资产（一链路的四件套）

| 资产 | 位置 | 说明 |
|------|------|------|
| 链路 | `flows/<case>.yaml` | meta（platforms/envs/tags）+ steps |
| 定位器 | `locators/<page>.yaml` | 命名定位器，来源标 manual/ai |
| 页面对象 | `src/apw/pages/<page>.py` | 语义原语，注册进 `engine/registry.py` |
| 探查/爬取配置 | `configs/crawl/<page>*.yaml` | 生成侧快照与 probe，喂生成器 |

## configs

| 路径 | 入库 | 说明 |
|------|------|------|
| `configs/envs/fixture.yaml` | 是 | 本地夹具站点，开箱即用 |
| `configs/envs/test.example.yaml` → `test.yaml` | 模板入库，`test.yaml` gitignored | 真实测试环境（URL/登录选择器），真实值仅存本地 |
| `configs/envs/desktop.yaml` | 是 | 桌面端 CDP attach（`http://127.0.0.1:9333`） |
| `configs/secrets.local.yaml` | 否 | 登录凭据（`username`/`password`）；或环境变量 `APW_USERNAME`/`APW_PASSWORD` |
| `configs/sanitize.example.yaml` → `sanitize.local.yaml` | 模板入库 | 脱敏映射（真实串→占位符） |
| `configs/desktop.local.example.bat` → `desktop.local.bat` | 模板入库 | 桌面客户端 exe 路径（`APW_DESKTOP_EXE`） |
| `configs/auth-state.json` | 否 | 登录态回写，后续运行免登录 |
| `configs/crawl/*.yaml` | 是 | 爬取/探查配置（状态路径 + 完成信号探针） |

## 其他

| 路径 | 说明 |
|------|------|
| `scripts/snapshot_summary.py` | 快照摘要（结构核对） |
| `tests/fixture_site/` | 本地夹具站点（框架自测 + 示例链路的被测对象） |
| `reports/<run_id>/` | `<flow_id>.json` + `run-summary.json` + `report.html`（run_id = 时间戳+熵后缀） |
| `.scratch/autoPlayWright/issues/` | 主线任务票 01~08（依赖序） |
| `.scratch/review-p0/` | 评审修复批（spec + 票 + P1/P2 backlog） |
| `.scratch/autoPlayWright/snapshots/` | 页面快照产物（JSON/HTML/PNG/TXT 均不入库） |
| `workspace/` | 一次性探查脚本（不入库） |
| `video/`、`run_video.bat` | 本地演示资产（Remotion 汇报动画出片），gitignored 不入库 |
| `docs/banner-light.html` | 项目报告页（banner 轮播） |

## 文档地图

| 文档 | 受众/内容 |
|------|-----------|
| `README.md` | 安装、环境配置、常用命令、写一条用例 |
| `AGENTS.md` | Agent 硬约束、新页面五步走、已知产品行为/缺陷、当前状态 |
| `docs/SPEC.md` | 规格与决策记录（含 grilling 结论附录） |
| `docs/CASE_PROGRESS.md` | 用例清单与进度 |
| `docs/STRUCTURE.md` | 本文 |
