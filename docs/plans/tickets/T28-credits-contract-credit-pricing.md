# T28 — [已退役] 积分用量契约与按积分计价

**Status:** retired (2026-09-05) —— 被 **T31**(`docs/plans/tickets/T31-credits-contract-merge-semantics.md`)取代

本票起草于 v3 取证之前,契约(`credits_consumed` + `price_per_credit`)与取数路径
(网页账单导出)均与定稿的 v3 规格不一致,已退役:

- 规格以 **docs/specs/v3-credit-sources-spec.md** 为准(三笔账、tokens_reported、
  `credit_prices` 两段键);
- 本票有价值的实测结论已并入 **docs/research/credit-opaque-agents-usage.md §九**
  (五档模型参考单价、混元免费、逐通道费率差异);
- 网页账单接口(`/api/v1/me/usages/...` histories)与「已获得」配额记录可作为
  **对账导入**的远期素材(规格 Out of Scope 的离线对账另立票),不作为消耗事实源。

原始内容见 git 历史(若已提交)或本会话记录;不要按本票开工。
