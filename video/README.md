# autoPlayWright 项目报告动画（Remotion）

用 Remotion（React 写视频帧）生成的项目汇报片：为什么做、解决/不解决什么、
为什么不做全量、后续计划、团队怎么协作、交付成果。文案口径与
`docs/SPEC.md`、`AGENTS.md`、`.scratch/autoPlayWright/issues/` 保持一致，
改口径时记得同步这里的场景文案（`src/scenes/`）。

## 怎么跑

```powershell
# 一键（推荐）：装依赖 + 渲染 + 出片后自动打开播放器
run_video.bat                # 仓库根目录；首次运行会装 node_modules
run_video.bat preview        # 打开 Remotion Studio 实时预览（逐帧可拖）
run_video.bat --codec=h264   # 额外参数透传给 remotion render

# 或手动：
cd video
npm install
npm run dev        # 打开 Remotion Studio 实时预览（可逐帧拖）
npm run render     # 出片：out/apw-report.mp4（1920x1080 @30fps，约 2 分 9 秒）
```

首次渲染会自动下载 Chrome Headless Shell（约 100MB）。

## 结构

| 文件 | 内容 |
|------|------|
| `src/timing.ts` | 场景时长表（帧）——改停留时间、增删章节改这里 |
| `src/Main.tsx` | 场景装配：Background + 各章 Sequence + 全局进度条 |
| `src/scenes/*.tsx` | 9 个场景（00 开场 ~ 08 收尾），文案即汇报口径 |
| `src/components/` | Reveal（浮入）/ Card / BulletList / CodeCard / StepPipeline / RailTimeline 等复用件 |
| `src/theme.ts` | 配色与字体（微软雅黑 / Segoe UI） |

## 章节与内容来源

| 章 | 问题 | 事实依据 |
|----|------|----------|
| 01 | 为什么要做 | SPEC Problem Statement |
| 02 | 能解决什么 | SPEC Solution、README「写一条用例 = 写一个 YAML」 |
| 03 | 不能解决什么 | SPEC Out of Scope、决策 D2/D10 |
| 04 | 为什么不做全量 | 决策 D11、限流硬约束、测试策略「只测外部行为」 |
| 05 | 之后的打算 | 票 04/07/08、`.scratch/review-p0/backlog.md`、里程碑 M0~M3 |
| 06 | 如何协作 | AGENTS.md「怎么加用例」五步走、硬约束、决策 D10/D12/D15 |
| 07 | 交付成果 | AGENTS.md 当前状态、reports/ 产物形态、tests 门禁 |
