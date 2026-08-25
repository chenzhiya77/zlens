# T06 — 日趋势图 + 模型排行视图

**Blocked by:** T03 — 日趋势 + 按模型端点; T05 — 前端壳 + 总览视图页
**Status:** ready-for-agent

## User story

作为多模型用户,我想在页面直接看到日趋势折线图和模型排行榜,而不是去读 JSON。

## What to build

两个数据视图:日趋势(ECharts 折线/面积,请求次数与主要 token 维度可切换)、按模型排行(provider+model 表格或条形,token 与估算金额列,未计价行特殊标注)。react-query 取数,统一的加载中 / 错误 / 空数据三态。

## Acceptance criteria

- [ ] 两个视图在合成 fixture 场景下渲染正确(数值与端点响应一致)
- [ ] 加载、请求失败(如数据源不兼容降级错误)、空库三种状态均有友好呈现
- [ ] 未计价模型在排行中有明确视觉标识
- [ ] `make check` 全绿
