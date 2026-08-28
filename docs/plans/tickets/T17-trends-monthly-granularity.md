# T17 — 趋势月度聚合

**Blocked by:** T15 — 日期窗口参数
**Status:** ready-for-agent

## User story

作为用户,我把周期切到「全部」时,想看到按月汇总的用量柱状图,而不是一根密到看不清的
每日锯齿线——我的数据可能跨好几个月甚至一年。

## What to build

`/api/trends/daily` 增加 `granularity` 参数(`day` 默认 | `month`)。

在 `core/cost.py` 里与 `fold_daily` 并列新增 `fold_monthly`:

- 把聚合 key 从 `day`(`YYYY-MM-DD`)换成 `YYYY-MM`。
- **复用同一条未计价判定**:某月内任一天未计价 → 该月 `estimated_cost = null`。
  token 各档照常求和(它们不依赖价格表)。
- 返回结构沿用 `DailyTrends`,新增一个 `granularity` 回显字段便于前端确认。

前端(T24 内接线):定长窗口(7/30/90 天 + 自定义)走按日折线;「全部」走按月柱状图,
x 轴用 `2026-03` 短月份,月份多时允许横向滚动。

## Acceptance criteria

- [ ] `?granularity=month` 返回按月聚合的序列;缺省 `day` 时行为与改动前完全一致
- [ ] 月内**任一天**未计价 → 该月 `estimated_cost` 为 `null`(不是 0,也不是跳过那天)
- [ ] 月内全部计价 → 该月成本等于各日之和
- [ ] token 各档在两种粒度下求和结果一致(日序列加总 == 月序列加总)
- [ ] 与 T15 的窗口参数组合生效:`?start=&end=&granularity=month`
- [ ] `fold_monthly` 与 `fold_daily` **共用同一段未计价判定**,不复制一份
- [ ] 新增 `tests/test_trends_monthly.py`
- [ ] `make check` 全绿

## Out of scope

- 前端的柱状图渲染 = T24
- 按周聚合:未提需求,不做

## Architectural decisions

- **月度聚合必须走后端**,不是前端拿日序列自己加一遍。表面看"按月加一遍"很轻,
  但它要复用同一条未计价判定;让前端再实现一遍,等于在界面层抄了一份成本口径,
  正是规格 §4「所有聚合仍在后端」明令禁止的。
- **不新增端点**,只加参数:`fold_daily` 与 `fold_monthly` 的输入都是同一个
  `list[DailyModelUsage]`,差异只在分组 key,合在一个端点是自然形状。
- 空月份不补 0:数据里没有的那个月就不出现,不要为了"画满 x 轴"而插入成本为 0 的假月份。
