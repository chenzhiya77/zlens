# T21 — 缓存命中率

**Blocked by:** None — 可独立开工
**Status:** ready-for-agent

## User story

作为用户,我想知道我的 prompt 里有多大比例是命中缓存来的——这个数字直接决定我的
缓存策略值不值,也解释了为什么成本没有随用量线性上涨。

## What to build

新增字段:`Overview.cache_hit_rate: float | None` 与
`ModelUsageSummary.cache_hit_rate: float | None`(行级可选)。

**公式(已定稿:方案 A,分母含缓存写)**:

```
cache_hit_rate = cache_read / (input + cache_read + cache_creation)     分母为 0 → null
```

分母 = 全部 prompt token。语义:**你的 prompt 里有多大比例是白嫖缓存来的**。

## Acceptance criteria

- [ ] `Overview.cache_hit_rate` 与行级 `cache_hit_rate` 均按上式计算
- [ ] 分母为 0 → `null`(不是 0、不是 NaN、不是 100%)
- [ ] 四档归一后的取值正确(fixture **必须按真实形状写**:zcode 的嵌套形状要照写嵌套,
      即 `input_tokens` 里含 `cache_read` 与 `cache_creation`,见 `tests/test_overview.py` 的现有写法)
- [ ] 验算:设计稿 KPI 卡 累计 5.49 亿 / 输出 148.9 万 / 缓存读 5.20 亿 / 缓存写 0
      → 5.20 / 5.475 ≈ 94.97%,与设计稿标注的 94.7% 吻合
- [ ] 与 `source` 参数、T15 的窗口参数组合生效
- [ ] 新增 `tests/test_cache_hit_rate.py`
- [ ] `make check` 全绿

## Out of scope

- KPI 卡上的百分比渲染 = T24(且必须带一句「按 token 计」的说明,
  避免被误读成"请求命中率")
- 请求维度的命中率:没有逐请求命中/未命中的计数,做不出来,也不做近似

## Architectural decisions

**为什么分母含缓存写(方案 A 而非 B)——三条理由,按分量排序:**

1. **B 会输出语义上不可能的数字**。当 `input = 0` 且 `cache_creation > 0` 时,
   B 的分母 = `cache_read`,命中率恒为 **100%**,而此时用户正按最贵的缓存写单价付费。
   "命中率 100% 但仍在付费"自相矛盾。
2. **缓存写比普通输入还贵**。`pricing.example.json` 里 `claude-sonnet-4-5` 的单价是
   `input: 21.6` / `cache_read: 2.16` / `cache_write: 27.0`。B 把它踢出分母,
   等于把 prompt 里最贵的那一档藏起来,而那恰好是最该被看见的部分。
   成本工具不该美化成本指标。
3. **A 的分母 = prompt token 总量**,与"四档相加 = `total_tokens`"的契约天然对齐,
   不引入第二个口径。

**当前数据下 A 与 B 无差别**:2026-08-29 三源实测(zcode 2737 行 / opencode 4 行 /
minimax 5 会话)**缓存写恒为 0**,两种算法给出同一个数。选 A 不付任何代价,
纯粹是给将来买保险(详见规格 D8)。

⚠️ **不要因为"现在看不出区别"就跳过这个决定**:三个源的协议里都有缓存写字段,
只是当前 provider 没触发。一旦某个模型开始写缓存,差别立刻显现。
