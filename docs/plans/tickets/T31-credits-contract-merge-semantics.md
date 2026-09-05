# T31 — 契约扩展:credits/tokens_reported 与三笔账合计语义

**Blocked by:** None — v3 首票
**Status:** draft (2026-09-05)
**Spec:** docs/specs/v3-credit-sources-spec.md §D1/D2/D3(成本层部分)

## User story

作为同时使用 token 计费 agent(ZCode 等)和积分计费 agent(Qoder CN/WorkBuddy)的用户,
我希望两类来源进同一份视图:积分来源显示积分与标价值,token 来源显示 token;「上游没给」
和「给了 0」在数据模型里可区分,谁都不被谁冒充。

## What to build

1. **行级契约四字段**(spec D1,落在 `ModelUsageSummary`、`DailyModelUsage`、`ProjectModelUsage`、
   `DailyUsage`、`ProjectUsage`、`Overview`):
   - `credits: float | None = None` —— 实扣积分;None = 该来源不上报(与 0.0 严格区分,
     沿用 buyout_amount 的 null-vs-0 纪律);
   - `original_credits: float | None = None` —— 折扣前原价积分;
   - `tokens_reported: bool = True` —— False 表示该来源 token 恒为 0 且**不代表零消耗**;
   - `credits_reported: bool = False` —— 适配器声明;`credits` 非 None 的行必须为 True。
2. **恒等式纪律**:`input + output + cache_creation + cache_read == total_tokens` 仅在
   `tokens_reported=True` 时校验;False 时四档 0 是占位值,**禁止参与任何逐档乘价**
   (`cost.py` 的 estimate 路径按行标记跳过)。
3. **合并语义**(spec D2,`sources/multi.py`):
   - credits 采用「忽略 null 求和」:某来源不报积分是"它没有这本账",不是数据缺失;
     参与集合里无任何来源上报 → 合计为 null(不是 0);上报来源集合随合计透出供界面标注;
   - token 合计保持可加,但 `tokens_reported=False` 的来源必须出现在「未计入 token 口径」
     的提示数据里,**禁止静默相加**;
   - 金额规则**以现状为准**(9d9bab8):未计价渠道按 ¥0 计入、聚合永不阻断——spec D2 里
     「任一参与计价的渠道未定价 → estimated_cost = null」一句写于 2026-09-02 决策之前,
     **不采纳**,行级 null cost 保留不变。
4. **MetaInfo** 新增 `credit_reporting_sources`、`token_reporting_sources`、`unpriced_credits`
   (已上报积分但未录积分单价的来源)。
5. **成本层派生量**(spec D3 的 cost 部分):`PriceTable.version` 升 2、新增顶层 `credit_prices`
   (键 `source|basis`,`basis ∈ {plan, pack}`,值 `{cny_per_credit, note?}`,解析失败降级空表);
   `enrich_overview` 新增 `credit_total`、`credit_original_total`、`discount_credits`(纯派生,
   禁写回 pricing.json、禁止前端另算)、`credit_value_cny`(Σ credits × cny_per_credit,
   **按 basis 计算**:某上报来源缺该 basis 单价 → 该 basis 总额 null;只填 plan 不填 pack
   不得让 plan 的标价值变 null)。`credit_value_cny` 是**标价折算**,不是实付——文案纪律见 T36。
6. `tests/test_credits.py` + `tests/test_multi_credits.py`(spec Testing Decisions):
   三笔账两两不相加回归;null-vs-0;version 1 老价格表零改动加载;混合四象限来源的
   合计与 `*_reporting_sources` 标注。

## Acceptance criteria

- [ ] 积分行 fixture:`credits` 有值、token 四档为 0 且 `tokens_reported=False`,不进任何乘价
- [ ] credit 合计忽略 null;纯 token 范围合计为 null;上报来源集合正确透出
- [ ] `credit_prices` 只填 `workbuddy|plan` 时 plan 标价值正常、pack 为 null(互不拖累)
- [ ] `discount_credits` 是派生值,任何写回路径不存在(测试断言)
- [ ] 旧 pricing.json(version 1)加载结果与改动前逐字段一致
- [ ] AGENTS.md 架构红线新增两条:「三笔账两两不相加」「凭据字段禁读」(spec Further Notes)
- [ ] 既有全部离线测试零语义改动通过;`make check` 全绿

## Architectural decisions

- 三笔账(按量消耗 / 买断支出 / 积分标价)**两两永不相加**,缺的那笔是 null 不是 0。
- `reasoning_tokens` 继续是 output 的 breakdown,不另立加数(WorkBuddy 实测 reasoning ⊂ completion,
  research §6.3)。
- fixture 必须覆盖 credit=0(WorkBuddy 混元免费行,research §9.2)与 credit 缺失两种形状。
