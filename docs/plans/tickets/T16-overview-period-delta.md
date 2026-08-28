# T16 — 环比 delta 与上期完整性判定

**Blocked by:** T15 — 日期窗口参数
**Status:** ready-for-agent

## User story

作为用户,我选「近 30 天」时想一眼看出比上一个 30 天涨了还是跌了。但如果上期那段
我还没装这个工具,我希望页面**干脆不显示环比**,而不是显示一个"暴涨 300%"来骗我。

## What to build

`Overview` 新增 `delta: PeriodDelta | None`。

- **上期窗口 = 当期窗口向前平移等长天数**(等长前移)。选 30 天,上期就是紧挨着的前 30 天。
  这样两期天数相同,总量可直接相除,不需要做日均归一化。
  (对照:自然月对齐会让两期天数不同,28 天 vs 31 天直接比总量会得出**相反**的结论——
  详见规格 §7 的 Q5。)
- `PeriodDelta` 只带两个字段:`request_count`、`estimated_cost`,
  形如 `{ previous: number | null, change_rate: number | null }`。
- **上期完整性判定**:上期窗口必须完整落在数据范围内,否则 `delta = null`。
  判定依据 `meta.first_request_at <= 上期窗口起点`(按本地日切比较)。

## Acceptance criteria

- [ ] 上期有完整数据 → `delta` 给出 `previous` 与 `change_rate`
- [ ] **上期部分有数据(窗口起点早于 `first_request_at`)→ `delta = null`**
      (例:总共 40 天数据却选「近 30 天」,上期有 20 天是空的。缺的那些天不是没用量,
      是那会儿还没装工具——显示它就是撒谎)
- [ ] 上期窗口内完全无数据 → `delta = null`
- [ ] **当期或上期任一侧 `estimated_cost` 为 null → 该字段 `change_rate = null`**,
      但 `previous` 仍可给出(未计价就是不知道,不是"没涨")
- [ ] `change_rate` 为 null 时前端**不渲染**该处环比,不允许显示 "—%" 或 0%
- [ ] `previous` 为 0 时的除零保护(`change_rate = null`,不是 Infinity)
- [ ] 「全部」窗口下不做环比(上期无从定义),`delta = null`
- [ ] 新增 `tests/test_overview_delta.py` 覆盖上述全部分支
- [ ] `make check` 全绿

## Out of scope

- 前端环比 UI(红涨绿跌的渲染)= T24
- 自然月对齐:已否决,不实现

## Architectural decisions

- **禁止前端拿 `/api/trends/daily` 自行切片算环比**。分母口径(未计价 null、四档归一、
  窗口边界)只有后端知道,前端重算必然算出另一个数。
- **宁可不显示,也不显示假数字**。这条与"未计价即 null"是同一条原则。
  上期不完整时缺的不是用量,是数据本身;把缺失当 0 会得出必然上涨的荒谬结论。
- 环比只对 `request_count` 与 `estimated_cost` 两个字段做,不做全字段——
  token 各档的环比没有独立解读价值,反而会让卡片变得臃肿。
