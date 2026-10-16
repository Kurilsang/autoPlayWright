# 评审 P1/P2 backlog（code-review 双轴结论，2026-09-24）

P0 六项已随 `review-p0/issues/` 交付。以下为按优先级排列的后续修复面，立项时可直接扩成任务票。

## P1 — 稳定性 / 合规

- **auth 加固**：`type: form` 校验 `login_url` 必填（加载期报错）；`login_path_hint in page.url` 子串匹配改精确判据；去掉 1500ms 固定等待；config 明文凭据加 validator 拒绝
- **裸 selector 收口**：auth 默认 `#username/#password`、`_DISMISS_TEXTS` 的 `get_by_text`、`test_real_login` 的 `get_by_text`、`_CAPTURE_JS` 内嵌 class 选择器——入定位器仓库或文档豁免（该违例已多次复现，建议同步加机械门禁：lint/CI 拦 `page.locator/get_by_*` 出现在 repo/crawler/probe 之外）
- **定位器解析判据**：`resolve` 的 `count()>0` 只判挂 DOM，可能命中隐藏元素——补可见性判据；候选优先级顺序零校验（加载期可校验 testid→role→…趋势）
- **`BasePage.sanitize_mapping` 类级可变默认值**：改实例级或 MappingProxyType
- **logging 体系**：全项目仅 print；截图/取证失败静默返回空串——logger.warning 起步
- **write_summary 状态计数收口**：三态计数与 html_report 徽章映射共享一张状态表

## P2 — 既有票范围 + agent 容错加固

- **票 05 三件套（顺序建议）**：Playwright trace 失败留存（成本最低收益最高）→ xdist 并行（默认 3、硬上限 5，**超限拒绝启动**）→ 429 退避重试（tenacity，重试计入报告不计失败）
- **票 04 范围**：hook 逃生舱（注册表 + DSL `do: {hook}`）、断言扩展 `text_regex|element_count`、`vars` + `{{name}}` 替换
- **judge 语义收口**：接入 LLM-as-Judge 时只评结构化可校验维度（章节/字段/工具调用记录），措辞评分走旁路不进 pass/fail
- **六信号加固**：文本稳定判据改内容哈希（现为长度）；网络层第二通道交叉验证（SSE/请求完成）；跑飞归因 `runaway/loop_repeat`（末尾片段重复检测）；等待信号可配置化
- **会话隔离**：框架级「每 flow 新建会话」保证（现依赖 flow 手写 new_session）
- **多轮上下文漂移用例**：指代上文的多轮链路（v1 扩量优先方向）
- **测试盲区**：FormAuth/AppDriver/pytest_plugin 收集机制/JsonReporter 无单测
- **重复代码收口**：`runner._exec_do` 与 `crawler._exec_do`、三处 `while count(): sleep` 轮询同形、Evidence 字典凝类型

## 已知留待人工

- git 历史中旧快照产物是否清洗（filter-repo/BFG），需人工拍板
