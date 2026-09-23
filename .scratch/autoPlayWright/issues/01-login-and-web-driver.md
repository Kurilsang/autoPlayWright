# 01: 打通测试环境登录与 Web 端驱动连接

> **Status: done（2026-09-22 交付）**

**What to build:** 测试工程师在本地执行 pytest，框架自动完成测试环境登录（方案由 spike 确定：SSO / 账号密码 / 会话复用），并通过 Web 驱动产出已认证的统一 Page。这是一切用例可执行的前置能力，也是全框架风险最高的侦察战。

**Blocked by:** None (can start immediately).

- [x] 登录方案 spike 完成并记录决策：被测产品为**账号密码表单登录**（非 SSO）；凭据来源 `configs/secrets.local.yaml`（本地，gitignored）或 `APW_USERNAME`/`APW_PASSWORD` 环境变量（CI）；登录成功后回写 storage_state（`configs/auth-state.json`）供后续运行复用，失效自动重登
- [x] AppDriver Web 模式封装完成，对外统一输出 Playwright Page，上层不感知连接细节
- [x] pytest 连通性冒烟：`tests/test_real_login.py --apw-env test` 自动登录并到达会话页（/chat），「新建对话」入口可见断言通过
- [x] 登录态复用策略明确：storage_state 命中则跳过表单登录，未命中自动重登并回写

 spike 探测结论：登录页 `#username` / `#password` / `button[type=submit]`，成功后跳转 `/chat`；SPA 水合约 1.5s，操作前需等待表单可见。
