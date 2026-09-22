# 03: Electron 驱动模式与双平台矩阵

**What to build:** 同一条 YAML 用例不加修改即可在 Electron 客户端执行；客户端独有链路仅在桌面端运行、Web 运行时正确 skip 且报告可见。桌面端支持 launch 安装包与 CDP attach 已运行客户端两种连接方式，驱动差异被完全吸收在 driver 层。

**Blocked by:** 01（驱动抽象）、02（DSL platforms 字段与示例 flow）。

**Status:** ready-for-agent

- [ ] 桌面端两种连接方式可用，统一输出 Playwright Page，上层零改动
- [ ] platforms 字段生效矩阵：共享 flow 两端各执行一遍；desktop-only 在 web 运行时 skip 并在报告中标注原因
- [ ] 示例 flow 在客户端上执行通过（含会话页到达与发送消息）
- [ ] Electron 可执行文件获取方式确定并写入环境配置（固定安装路径 / CI 构建产物下载，对应 spec 开放项 2）
- [ ] 版本兼容性风险记录：客户端 Electron 版本与 Playwright 的适配验证结论
