# T19 — 表格排序参数

**Blocked by:** None — 可独立开工
**Status:** done (2026-08-29)

## User story

作为用户,我想点表头按任意一列排序,默认按「成本(估算)」从高到低——我最关心的是
哪个模型最烧钱。刷新页面后排序要还在,别又跳回默认。

## What to build

`overview` / `models` 端点新增:

- `sort` 参数:`total_tokens` | `estimated_cost` | `request_count`。
  **默认 `total_tokens`**,避免改动既有视图行为。
- `order` 参数:`desc`(默认)| `asc`。

**未计价行(`estimated_cost = null`)恒排最后,与升降序无关**——它们是"不知道",
不该混进排序中间。

排序由后端做,前端只传参。前端(T24)还需:

- 可点列:请求数 / 输入 / 输出 / 缓存写 / 缓存读 / 总计 / 成本(估算)
- 默认 `sort=estimated_cost&order=desc`(对齐设计稿副标题「按成本降序」)
- `sort` / `order` / `source` / 窗口**全部进 URL query**,刷新与前进后退可还原

## Acceptance criteria

- [ ] `sort=estimated_cost` 时按成本排序,**未计价行恒排最后**(升序降序都一样)
- [ ] 其余可排序列同理;不支持的列返回 422 并说明可选值
- [ ] 默认 `sort=total_tokens&order=desc`,既有测试零改动通过
- [ ] 与 `source`、T15 的窗口参数组合生效
- [ ] 新增 `tests/test_overview_sort.py`
- [ ] 前端:`sort`/`order`/`source`/窗口进 URL query,刷新后视图状态保持(在 T24 验收)
- [ ] `make check` 全绿

## Out of scope

- 表头指示器与点击交互的 UI = T24
- 分页:规格 G7 已决定不做(模型数本来就十几个量级)
- 搜索:纯客户端过滤,在 T24

## Architectural decisions

- **排序由后端做,不是前端 `Array.sort`**。理由不只是数据量:
  "未计价行恒排最后"是一条业务规则,前端排就会漏掉它一次,
  让未计价的行混进排序中间,看起来像是成本很低而不是未知。
- **默认保持 `total_tokens`**:`models` 页等既有视图依赖当前顺序,
  改默认值等于静默改变它们的语义。默认值的改动要单独决定,不夹带在本票里。
- **URL 持久化**:总览页的视图状态只有这一份(排序 + 来源 + 窗口),
  全部进 query 就能覆盖刷新、前进后退、链接分享三种场景,不需要额外的状态管理。
