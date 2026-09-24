# 05: flow 三态与跳过留痕

**What to build:** QA lead 能从报告核对用例矩阵到底执行了什么：平台矩阵或环境过滤不匹配的 flow 以 skipped 状态写入报告明细与 run 汇总并标注原因；flow 结果状态扩为 passed/failed/skipped 三态；汇总分列三态统计，skipped 不计入 passed；HTML 报告渲染三态徽章与跳过原因。旧报告保持可渲染。

**Blocked by:** 03（准备失败留痕——先确立「任何终态必写报告」的事件构造路径，本票的 skip 留痕复用它）

**Status:** done

- [x] 主缝：平台矩阵不匹配的 flow → run 汇总含 skipped 记录与跳过原因
- [x] 主缝：环境过滤不匹配的 flow → 同上
- [x] run 汇总分列 passed/failed/skipped 三态计数，skipped 不计入 passed
- [x] HTML 报告渲染 skipped 徽章与跳过原因
- [x] 插件接线集成用例：夹具站一次会话贯通 skip 留痕到 run 汇总
- [x] 既有报告与渲染用例回归全绿（含旧报告仍可渲染）

## Comments
- 2026-09-24 交付：`FlowResult` 三态 + `skip_reason`；runtest 双闸（平台/环境）先留痕后 `pytest.skip`；汇总三态计数；HTML 三态统计卡 + 跳过原因行；集成用例走一次真实 pytest 会话核对 run-summary（未开 pytester 新缝）。
- code-review 复核修正：HTML 徽章断言由恒真的裸文本改为「图标+状态对」（`- skipped`）；旧格式汇总（无 skipped 键）向后兼容显式断言（三态卡默认 0）。
