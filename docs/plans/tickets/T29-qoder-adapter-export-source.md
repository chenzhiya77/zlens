# T29 — [已退役] Qoder 适配器(导出文件源)

**Status:** retired (2026-09-05) —— 被 **T33**(`docs/plans/tickets/T33-qoder-cn-adapter.md`)取代

本票基于「Qoder 本地无积分记录」的早期判断设计(网页导出 JSON → 适配器只读)。
后续取证推翻了前提:**`~/.qoder-cn/projects/**/*.jsonl` 的 `message.usage` 直接带
`credits/original_credits`**(research §8),CN CLI 无需任何导出,适配器直接读本地文件,
与其他来源同构——见 T33。

保留价值:导出脚本片段与 `~/.zlens/imports/` 路径约定,可作为规格 Out of Scope
「离线对账导入」票的素材;`kind`(Charged/Not Charged)与 `discount_factor` 字段
保留在 T33 的解析范围。不要按本票开工。
