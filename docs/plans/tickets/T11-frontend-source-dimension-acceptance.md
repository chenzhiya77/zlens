# T11 — 前端来源维度 + v2 端到端验收

**Blocked by:** T10 — opencode 适配器
**Status:** done (2026-08-29)

## User story

作为多 agent 用户,我在页面表格里能直接看到每行数据来自哪个来源,合并总额与分来源明细
一眼可辨。

## What to build

前端消费 source 字段:模型明细表与项目明细表新增"来源"列;健康度错误分布标注来源;
总览数据范围行展示可用来源清单;API 类型定义同步。随后做 v2 端到端验收:三来源真实数据
冒烟、与各源原始数据对账、文档同步(README/AGENTS/CHANGELOG)。

## Acceptance criteria

- [ ] 模型/项目表格显示来源列;健康度错误行标注来源
- [ ] 总览页展示可用来源清单(如 zcode+minimax+opencode)
- [ ] 三来源真实数据下 `make check` 全绿;live 冒烟通过
- [ ] README / AGENTS.md / CHANGELOG 与多来源行为一致
- [ ] 对账:合并 overview 的 ZCode 部分仍与独立统计脚本一致(回归不破坏 v1 口径)
