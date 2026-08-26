# T10 — opencode 适配器

**Blocked by:** T09 — MiniMax 适配器 + 多来源组合层
**Status:** ready-for-agent

## User story

作为 opencode 桌面版用户,我在 zlens 里能看到 opencode 的每次请求用量,并与 ZCode、
MiniMax 合并展示——opencode 的耗时还能进入性能面板。

## What to build

opencode 数据源适配器:只读打开 opencode.db,解析 message.data JSON(assistant 且含 tokens),
关联 session 表取项目目录;耗时 = time.completed - time.created;模型取 modelID/providerID。
归一化:tokens.cache.write/read → cache_creation/cache_read,reasoning 直取。

## Acceptance criteria

- [ ] 合成 opencode SQLite fixture 被完整解析:五类 token、模型、耗时、项目目录全部正确
- [ ] 库文件缺失或表缺失时该源不可用,不影响其他来源
- [ ] 与 MiniMax/ZCode 三源合并后各视图数值正确(fixture 断言)
- [ ] 真实 opencode 库(live)可读出且行数 > 0
- [ ] `make check` 全绿

## Architectural decisions

- **复用 zcode.py 的 SQLite 只读骨架**(mode=ro + schema 防御),差异仅在 JSON 列解析。
