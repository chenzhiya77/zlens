# T18 — 来源枚举

**Blocked by:** None — 可独立开工
**Status:** ready-for-agent

## User story

作为用户,我想在总览页看到一排来源 chips(全部 / zcode / minimax / opencode),
并且当某个来源的目录不见了时能明确看到它被置灰、知道原因,而不是以为它没数据。

## What to build

现状:只有 `meta.source_id` 一个 `+` 连接的字符串(如 `"zcode+minimax+opencode"`),
前端靠 split 解析很脆,而且拿不到"某个源不可用及其原因"。

改动:

- `MetaInfo` 新增 `sources: list[SourceRef]`,`SourceRef = { id: str, available: bool, error: str | None }`。
- `MultiSource` 构造时已把探测失败记在 `self._errors` 里,把这份信息结构化暴露出来即可。
- **`source_id` 保留不动**(v2 契约,别破坏既有消费方)。
- 前端类型同步(`frontend/src/lib/api.ts`)。chips 本身的 UI 在 T24。

注意:chips 需要列出**已注册**的全部来源(包括不可用的),而不只是当前可用的——
否则某个源一挂掉,它就直接从界面上消失了,用户会以为自己从没用过它。

## Acceptance criteria

- [ ] `meta.sources` 列出全部已注册来源(不因不可用而缺失)
- [ ] 可用来源 `available=true`、`error=null`
- [ ] 不可用来源 `available=false` 且 `error` 携带原因(如 schema 不兼容、路径不存在)
- [ ] `source_id` 字段保持不变,既有测试零改动通过
- [ ] 与 T15 的窗口参数、既有的 `source` 参数组合生效
- [ ] 新增 `tests/test_sources_enum.py`
- [ ] `make check` 全绿

## Out of scope

- chips 的 UI 与筛选交互 = T24
- 来源级下钻页:v2 已列为 Out of Scope,不改

## Architectural decisions

- **加字段不加端点**:总览首屏本来就要拉 `meta`,多一个数组不增加请求;
  新增 `/api/sources` 端点则要多一次往返,还要单独处理它的失败态。
- **不可用的来源也要列出来**:这是"诚实展示"的一部分。一个源挂掉时,
  让它从界面消失比置灰更糟——用户会以为那段用量从来不存在。
