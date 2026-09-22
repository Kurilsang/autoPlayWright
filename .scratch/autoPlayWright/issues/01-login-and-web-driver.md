# 01: 打通测试环境登录与 Web 端驱动连接

**What to build:** 测试工程师在本地执行 pytest，框架自动完成测试环境登录（方案由 spike 确定：SSO / 账号密码 / 会话复用），并通过 Web 驱动产出已认证的统一 Page。这是一切用例可执行的前置能力，也是全框架风险最高的侦察战。

**Blocked by:** None (can start immediately).

**Status:** ready-for-agent

- [ ] 登录方案 spike 完成并记录决策：SSO 处理方式、测试账号来源、会话保持与复用策略（对应 spec 开放项 1）
- [ ] AppDriver Web 模式封装完成，对外统一输出 Playwright Page，上层不感知连接细节
- [ ] pytest 连通性冒烟：自动登录并到达 Agent 会话页，核心界面元素可见断言通过
- [ ] 登录态复用策略明确（避免每条用例重复完整登录流程的开销）
