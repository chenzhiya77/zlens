# T12 — 价格表管理页 + 单位标注

**Blocked by:** None — can start immediately（v1/v2 数据展示已稳定）
**Status:** ready-for-agent

## User story

作为 zlens 用户，我想在页面里直接维护每个模型的价格（input / output / cache_read / cache_write，
USD 每 1M tokens），并看到所有 token 统计与成本明确标注单位——不再需要手改 JSON，也不再
因为"不知道单位"而误读数字。

## What to build

前端新增「价格表」页面（主导航之一）：以表单呈现当前 pricing.json 的全部条目，支持
逐行编辑四档价格、新增模型行、删除行、保存（写回定价文件）；页面顶部提示基准单位为
USD/1M tokens，并列出当前尚未计价（价格表缺失）的模型。同时做全局单位标注：总览 KPI
与表格列头/说明明确标注 tokens 与 USD。

后端新增价格表的读取/写入端点：

- GET /api/pricing — 返回当前完整价格表（供表单装载）
- PUT /api/pricing — 接收完整价格表，校验后写回定价文件；热生效（已有每次请求重载机制）

## Acceptance criteria

- [ ] 价格表页可装载、增删改、保存；保存后总览成本立即按新价格重算（切回总览可见）
- [ ] 校验：模型名非空、四项价格非负；非法输入拒绝保存并提示
- [ ] 未计价模型清单在价格表页顶部展示（与总览一致）
- [ ] 单位标注上线：总览「累计 Token」与表格 token 列注明 tokens；成本注明 USD；
      价格表单注明 USD/1M tokens
- [ ] PUT 写文件使用 gitignored 定价文件路径，不触碰模板文件
- [ ] 后端离线测试覆盖读写与校验；前端 `make check` 全绿

## Architectural decisions

- **写定价文件是唯一可写端点**：语义是"用户显式保存配置"，沿用 pricing.json /
  pricing.example.json 的 gitignored 真值模式。
- **单位标注用"页面说明 + 列头"而非每格重复**：保持表格可读性，单位信息出现在表头
  与区域说明里（延续 ZCode 面板 KPI 大数字的克制风格）。