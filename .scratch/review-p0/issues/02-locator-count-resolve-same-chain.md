# 02: 定位器计数与解析同链

**What to build:** 排障者拿到定位失败时能直接看出哪个候选为什么没命中：软计数（预期缺席的探测，如完成信号）与硬解析走同一条候选回退链——主候选未命中自动试后续候选；未知定位器名抛定位器未找到异常（不再是内部 KeyError）；全候选未命中时异常携带逐条候选失败原因。

**Blocked by:** None (can start immediately)

**Status:** done

- [x] FakePage：主候选命中 0 次 → 软计数回退到下一候选并返回其计数
- [x] FakePage：未知定位器名 → 软计数抛定位器未找到
- [x] FakePage：全候选未命中 → 异常信息含每个候选的失败原因
- [x] 硬解析既有候选回退行为回归全绿
- [x] 完成信号探测经由同链，无旁路直取单候选

## Comments
- 2026-09-24 交付：`BasePage.count` 收口到 `LocatorRepo.count`（与 `resolve` 共用 `_first_hit` 候选回退链，NamedTuple `_Hit` 自释）；未找到异常携带逐候选「选择器 + 异常类型 + 原因」明细。
- code-review 复核修正：错误明细由仅记异常类型改为附原因文本（截断 80 字符），测试断言到原因层。
