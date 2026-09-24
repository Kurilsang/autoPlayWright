# 04: 空步骤防御

**What to build:** 空壳用例不能刷绿：空步骤列表在 DSL 加载期即被拒绝（非法用例收集期报错，沿用「非法 DSL 收集期报错」既有决策）；引擎运行层兜底——即使收到空步骤列表也判 failed 并附明确错误信息。

**Blocked by:** None (can start immediately)

**Status:** done

- [x] 空步骤 YAML 在收集期报错，错误信息指向用例
- [x] 直接调用引擎执行空步骤列表 → status=failed 且错误信息明确（不得为 passed）
- [x] 非空用例的收集与执行回归全绿

## Comments
- 2026-09-24 交付：加载期 `steps 不能为空` 拒绝（含缺 steps 键）+ 引擎运行层兜底判 failed（error=「无可执行步骤」）；红灯阶段真实复现过「空 steps 刷绿」缺陷后修复。
