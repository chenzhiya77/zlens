# T14 — 买断支出 null / 0 可区分

**Blocked by:** None — 可立即开工
**Status:** ready-for-agent

## User story

作为用户,我在价格表里没填任何买断金额时,总览页应该老实告诉我"没填"——而不是显示
`¥0.00` 让我以为自己一分钱没花。这两件事必须一眼分得开。

## What to build

修一个**存量正确性 bug**,与本次改版无关,但违反 AGENTS.md 的硬规矩,建议第一个做。

现状:`sources/models.py:56` 里 `Overview.buyout_total: float = 0.0`。
`PriceTable.buyout_total()` 对"价格表里一条买断行都没有"和"买了但花 0 元"都返回 `0.0`,
两者在界面上长得一模一样。前端 `Overview.tsx:80` 现在靠 `o.buyout_total === 0 ? "未填" : "已付清"`
猜,这只是巧合——一旦有人真填了 0,就会显示成"已付清"。

改动:

- `Overview.buyout_total` 改为 `float | None`。
- `PriceTable.buyout_total()`(**`core/cost.py`**):在**没有任何非 null `buyout_amount` 行**时
  返回 `None`;只要有一行填了(包括填 0)就返回数值求和。
- 展示:null → 「未填」;`0.0` → 「¥0.00 · 免费套餐」。
- 同步更新 `frontend/src/lib/api.ts` 的 `Overview` 类型与 `Overview.tsx` 的 KPI5 渲染。

## Acceptance criteria

- [ ] 价格表无任何买断行 → `buyout_total` 为 `null`,界面显示「未填」
- [ ] 价格表有一行 `buyout_amount: 0` → `buyout_total` 为 `0.0`,界面显示「¥0.00 · 免费套餐」
- [ ] 两者并存(一行 null 省略、一行填 0)→ `0.0`
- [ ] 多行买断 → 正确求和,且跳过值为 null 的行(空值不参与求和,不按 0 处理)
- [ ] 新增 `tests/test_buyout_null_vs_zero.py` 覆盖上述四种组合
- [ ] 前端 `api.ts` 类型同步;`Overview.tsx` 不再用 `=== 0` 猜语义
- [ ] `estimated_cost` 与 `buyout_total` **永不相加**,两者在界面上分列展示
- [ ] `make check` 全绿

## Out of scope

- 买断的结清日期(规格 G9b):`ModelPrice` 没有付款日期字段,设计稿「已结清 · 2026-08-20」
  无数据来源,已从设计稿删除。确需时再单独立票加 `buyout_paid_on`。
- 买断价摊成每百万等效单价:摊出来的是假精确,不做。

## Architectural decisions

- **null 与 0 必须可区分**,这条来自 AGENTS.md「把『没填』显示成 ¥0.00 就是撒谎」。
  本票是这条规矩在买断字段上的落地,后面 T16/T20/T21 都会依赖同样的判定习惯。
- `buyout_total` 不受"未计价规则"约束:它是**已经付出去的钱**,缺单价不会让它变得未知,
  所以只有 `estimated_cost` 会因为有模型未计价而变 null,`buyout_total` 不会。
