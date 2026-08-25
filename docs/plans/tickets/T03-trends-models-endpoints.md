# T03 — 日趋势 + 按模型端点

**Blocked by:** T01 — 最小数据通路:meta + 总览(token 口径)
**Status:** ready-for-agent

## User story

作为多模型用户,我想看到按日聚合的用量曲线数据和按模型的排行榜数据,以发现异常放量的一天、并知道哪个模型消耗最大。

## What to build

两组只读查询端点:日趋势(按本地时区聚日:每日请求次数与五类 token,含成本字段接入)与按模型(provider+model 维度的请求次数、token、成本排行)。复用 T01 的适配器与 fixture 设施,新增对应的边界合成数据(跨多日、多模型、同模型多 provider)。

## Acceptance criteria

- [ ] 日趋势按本地时区正确归日,跨日合成数据逐日断言通过
- [ ] 按模型端点的排序与聚合口径和 overview 明细一致(同源不同视图不打架)
- [ ] 成本字段遵循 T02 同一套价格规则(未知模型未计价)
- [ ] 新增端点均有离线测试;`make check` 全绿
