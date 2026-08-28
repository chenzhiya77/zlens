# T25 — zcode 逐行 clamp 测试补全

**Blocked by:** None — 可独立开工
**Status:** ready-for-agent

## User story

作为维护者,我希望"一行脏数据不会把其它正常行抵消成负数"这个行为有测试锁住,
这样哪天有人重构 SQL 把它改坏了,测试会立刻报警。

## What to build

**补测试,不改逻辑。**

`src/zlens/sources/zcode.py:62` 的 `_AGGREGATE_SQL` 里,`MAX(..., 0)` 是包在 `SUM` **里面**的:

```sql
COALESCE(SUM(MAX(
    COALESCE(input_tokens, 0) - COALESCE(cache_read_input_tokens, 0)
    - COALESCE(cache_creation_input_tokens, 0), 0)), 0) AS input_tokens,
```

`zcode.py:58` 的注释写明了意图:

> a single malformed record must not be able to offset a good one into a negative

但**现有 fixture 全是合法行**(`tests/test_overview.py` 三行都满足
`cache_read + cache_creation <= input_tokens`),**没有任何测试覆盖这个兜底**。

风险很具体:如果有人把 `MAX` 挪到 `SUM` 外面(看起来是等价的"优化"),
现有测试会全绿,但行为已经变了——一行 `cache_read > input` 的脏数据会抵消掉
其它正常行的未缓存输入,让统计偏低。

新增 `tests/test_zcode_clamp_per_row.py`:

1. 构造混合数据:若干正常行 + 一行 `cache_read + cache_creation > input_tokens` 的脏数据
2. 断言脏数据行贡献的 `input_tokens` 为 **0**(不是负数)
3. 断言其它正常行的 `input_tokens` **不受影响**(等于各自 `input - cache_read - cache_creation`)
4. **反向断言**:证明这条测试真的在守这个行为——即"若把 `MAX` 挪到 `SUM` 外面,
   会得到不同的结果"。可以用一段独立的 SQL 在 fixture 库上直接跑出那个错误结果并断言它 ≠ 正确结果。

## Acceptance criteria

- [ ] 脏数据行(`cache_read + cache_creation > input_tokens`)贡献的 input 为 0
- [ ] 其它正常行的 input 不受脏数据影响
- [ ] 测试中包含"挪到 SUM 外会得到不同结果"的反向断言,证明测试有约束力
- [ ] 全脏数据(所有行都不合法)→ input 为 0,不抛异常
- [ ] 既有测试零改动通过
- [ ] `make check` 全绿

## Out of scope

- 修改 `_AGGREGATE_SQL`:逻辑是对的,只补测试
- 其它适配器的类似兜底:minimax / opencode 的上游是分档独立的,不存在嵌套,无需 clamp

## Architectural decisions

- **测试要能证明自己在守行为**。只断言"结果是 0"是不够的——
  如果 `MAX` 被挪到外面,某些输入下结果碰巧也是 0,测试就形同虚设。
  所以要求第 4 条反向断言:明确展示错误实现会得到不同输出。
- **逐行兜底而非全局兜底**是刻意的:全局兜底会让一行脏数据吃掉其它行的真实用量,
  统计偏低且无从察觉;逐行兜底最多让这一行贡献 0,影响可控且可定位。
- 本票与改版无关,是盘点设计稿时顺带发现的测试缺口(见规格 §5)。
