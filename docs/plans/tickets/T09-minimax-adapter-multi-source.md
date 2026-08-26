# T09 — MiniMax 适配器 + 多来源组合层

**Blocked by:** None — can start immediately(v2 首票)
**Status:** ready-for-agent

## User story

作为同时使用 ZCode 和 MiniMax Code 的用户,我打开 zlens 就能看到两个工具合并后的总用量,
每行数据标明来自哪个 agent——不用再分别开两个工具查。

## What to build

MiniMax 数据源适配器:扫描会话目录下的 ledger.jsonl(过滤带 usage 的事件)与 display.jsonl
(取模型名),归一化为统一 schema(reasoning 恒 0,无耗时/健康度)。同时落地多来源组合层
MultiSource:聚合全部可用来源,行级数据带 `source`,总量类求和、明细类拼接;全部 GET 端点
新增可选 `source` 过滤参数;来源全部不可用时保住 v1 的两种降级错误语义。

## Acceptance criteria

- [ ] 合成 MiniMax 会话 fixture(ledger + display)被完整解析:token 四类映射正确、
      模型名取自 display、时间戳来自事件
- [ ] 损坏的 ledger 行被跳过,目录缺失时该源不可用
- [ ] 双源 fixture 合并:overview 计数求和、明细行各带 source、`?source=` 过滤生效
- [ ] 仅配置损坏 schema 的 ZCode 时错误码仍为 schema_incompatible;仅缺失时为 source_unavailable
- [ ] 既有 25 个离线测试零语义改动通过;`make check` 全绿
- [ ] 真实 MiniMax 数据(live)可读出且行数 > 0

## Architectural decisions

- **组合层而非统一库**:百行级数据在内存归并即可,统一库留作未来优化——避免为两个小来源
  建整套同步机制。
- **可用性探测在装配时做一次**:错误随适配器保留;全部失败时优先抛 schema_incompatible
  (更具体、可指导用户修复),否则 source_unavailable。
