# T20 — 合计行 totals

**Blocked by:** T15 — 日期窗口参数
**Status:** done (2026-08-29)

## User story

作为用户,我想在表格底部看到一行合计,并且如果其中任何一个模型还没定价,
合计的成本应该老实显示"未计价",而不是把所有已知的成本加起来给我一个偏低的假数字。

## What to build

`Overview` 新增 `totals: OverviewTotals`,包含 `request_count`、六个 token 档、
`estimated_cost`。

**由后端算,不是让前端把 `by_model` 加一遍。**

合计沿用同一条诚实规则:

- **任一模型未计价 → `totals.estimated_cost = null`**
- token 各档照常求和(它们不依赖价格表)

同时修正设计稿 D3:合计行文案「本页合计 · 前 5 个模型」与副标题「共 14 个模型」自相矛盾
(画布只画了 5 行示意)。**不做分页**,文案改为「全部合计 · 共 N 个模型」。

注意:合计必须是**窗口 + 来源过滤后的全量合计**,不是"当前页"——不分页,所以两者等价,
但命名与实现都要按"全量"来写,免得将来加分页时埋雷。

## Acceptance criteria

- [ ] 全部模型已计价 → `totals.estimated_cost` 等于各模型成本之和
- [ ] **任一模型未计价 → `totals.estimated_cost` 为 `null`**,而 token 各档合计照常给出
- [ ] `totals` 随 `source` 参数与 T15 的窗口参数变化
- [ ] 从 `pricing.json` 删掉某个渠道的价格 → 合计成本变 null,token 合计不变(手工验收项)
- [ ] 新增 `tests/test_overview_totals.py`
- [ ] `make check` 全绿

## Out of scope

- 合计行的 UI 渲染 = T24
- 分页:已决定不做

## Architectural decisions

- **合计由后端返回,不由前端求和**,与排序(T19)、月度聚合(T17)同一条理由:
  未计价判定是业务口径,前端复制一份就会漏。
- **成本合计与 token 合计的诚实标准不同**:成本依赖价格表,有一个不知道就全不知道;
  token 是上游直接上报的事实,不依赖价格表,所以照常给出。这不是双重标准,
  是两类数据的确定性来源本来就不同。
- **不做分页**:模型数量级是十几个,分页带来的复杂度(页码、每页条数、合计语义)
  远大于收益,而且"本页合计"这个概念本身就是误导——用户想看的是总量。
