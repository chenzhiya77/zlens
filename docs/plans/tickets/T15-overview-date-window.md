# T15 — 日期窗口参数下推

**Blocked by:** None — 但建议 T14 之后做
**Status:** ready-for-agent

## User story

作为用户,我在总览页选「近 30 天」,所有卡片、趋势图、表格都应该只统计这 30 天的数据——
而不是把装工具以来的全部历史一股脑摊给我。

## What to build

**这是整个后端改版的前置票**,T16 / T17 / T20 / T22 全部挂在它上面。

现状:全站只有 `source` 一个查询参数(`grep -n "Query(" src/zlens` 仅 6 处,全是 source),
`SourceAdapter` 协议没有窗口概念,适配器 SQL 直接扫全表。

改动:

- `overview` / `trends/daily` / `models` / `meta` 四个端点新增 `start` / `end`
  (`date | None`,ISO `YYYY-MM-DD`,**闭区间**,按本地日切)。缺省 = 全量,行为与今天完全一致。
- **窗口必须下推到适配器**,不允许在 API 层拿全量行再过滤:
  - `SourceAdapter` 协议增加窗口入参,三个适配器各自实现——
    zcode 用 `started_at`、minimax 用事件毫秒时间戳、opencode 用 `time.created`,都有日切依据。
  - **原因**:`daily_by_model()` 是按日聚合的,外层过滤会破坏"某天未计价则该天成本为 null"
    的判定,进而算出错误的成本。
- `meta` 同步接受窗口,让首末请求时间反映窗口而非全库。

周期选择器选项(已定稿):`近 7 天` / `近 30 天` / `近 90 天` / `全部` / `自定义区间`。
「全部」= 不带 `start` / `end`。**后端只认绝对日期,不认「近 N 天」这种相对表达式**——
相对窗口的锚点(今天 vs 最后一条请求时间)是产品决定,不该由 API 猜,由前端翻译。

## Acceptance criteria

- [ ] `?start=2026-07-30&end=2026-08-28` 返回的 `total_tokens` 等于该区间各日之和
- [ ] 不带参数时行为与改动前**完全一致**(既有测试零改动通过)
- [ ] 窗口内无数据 → 各计数为 0、`by_model` 为空数组,**不是 500**
- [ ] `start > end` → 422 参数校验错误,错误信息说明区间非法
- [ ] 窗口边界:首日、末日、单日区间、完全落在数据范围之外的区间
- [ ] `meta` 的 `first/last_request_at` 在带窗口时反映窗口,不带时反映全库
- [ ] 三个适配器**都在 SQL 层下推**,不是取全量后过滤(可审查 SQL 或加执行断言)
- [ ] 新增 `tests/test_overview_window.py`
- [ ] 只读约束不变:连接串仍带 `mode=ro`
- [ ] `make check` 全绿;live 冒烟:真实库上窗口统计与全量的差异符合日期跨度

## Out of scope

- 环比(上期窗口)= T16
- 月度聚合 = T17
- 前端的周期选择器 UI = T24

## Architectural decisions

- **窗口下推而非外层过滤**:这不是性能问题,是正确性问题。成本判定发生在按日聚合的那一层,
  在更外层过滤会让"某天未计价 → 该天 null"的规则失效,从而输出一个偏低的假成本。
- **闭区间 + 本地日切**:与 `daily_by_model()` 里 `date(started_at/1000,'unixepoch','localtime')`
  的口径保持一致,否则窗口和会与日序列和对不上。
- **缺省即全量**:保证本票合并时既有行为零回退,也让"全部"这个选项不需要特殊分支。
