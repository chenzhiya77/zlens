# zlens v2 规格:多来源接入(MiniMax + opencode)

> 状态:**ready-for-agent** · 定稿:2026-08-26 · 前置:v1 已交付(docs/specs/v1-spec.md)
> 实施票:T09 / T10 / T11(docs/plans/tickets/)

## Problem Statement

zlens v1 只统计 ZCode。用户同时在使用多个 coding agent(实测本机还有 MiniMax Code 与
opencode 在产生真实用量),分开看每个工具的 token 花销既麻烦也没有全局视角。

## Solution

新增两个数据源适配器,并在 API 层做**组合聚合**:所有既有视图自动变成"全来源合并视图",
每行数据带 `source` 标记,支持按来源过滤。不引入自有统一库——数据量小(百行级),
在适配器组合层用 Python 归并即可;未来数据量大时再引入同步库存作为优化。

## 数据源实测结论(2026-08-26,本机验证)

- **MiniMax Code**:`~/.minimax/v2/sessions/**/ledger.jsonl`,每行事件含
  `messages[].usage{input, output, cacheRead, cacheWrite, totalTokens}` 与毫秒时间戳;
  模型名在会话 `display.jsonl`;项目维度 = 会话 `workspaceDir`。无 reasoning / TTFT / 健康度字段。
- **opencode**:`~/.local/share/opencode/opencode.db`(SQLite,mode=ro),`message.data` JSON 列含
  `tokens{input, output, reasoning, cache{write, read}}`、`modelID/providerID`、
  `time{created, completed}`(可算耗时);`session.directory` 提供项目维度。无 TTFT。

## Implementation Decisions

- **组合适配器(MultiSource)**:实现既有 SourceAdapter 协议,聚合所有可用来源;
  单源部署行为不变。所有可用来源都不可用时:存在 schema 不兼容则抛 schema_incompatible,
  否则抛 source_unavailable(保住 v1 的降级语义)。
- **来源字段**:所有行级模型增加 `source`;MetaInfo.source_id 变为可用来源 id 的 `+` 连接。
- **合并规则**:总量类(overview 计数、健康度计数)跨源求和;明细类(按模型/按日/按项目)
  跨源拼接行,同一模型来自不同来源保持独立行;性能面板对耗时样本跨源合并重算分位数,
  TTFT 仅统计有样本的来源。
- **按来源过滤**:全部 GET 端点新增可选 `source` 查询参数(取可用来源 id,非法值报 404 语义错误)。
- **归一化映射**:MiniMax `usage.input/output/cacheRead/cacheWrite` →
  input/output/cache_read/cache_creation,reasoning 恒为 0;opencode `tokens.cache.write/read` →
  cache_creation/cache_read,耗时 = completed - created。
  四档必须互斥且相加 = `total_tokens`(成本逐档乘价,嵌套即重复计价):实测 ZCode 把缓存前缀
  算进 `input_tokens`(`total = input + output`),故其适配器交出 `input - cache_read -
  cache_creation`(逐行 clamp);opencode 把 reasoning 当独立加数计入 total,故并进输出档;
  MiniMax 本就互斥。
- **配置**:两个新路径进 Settings(默认指向各自标准位置,ZLENS_ 前缀环境变量可覆盖);
  路径不存在 = 该来源不可用,不影响其他来源。
- **schema 防御**:MiniMax 会话目录缺失 → 该源不可用;ledger 单行损坏 → 跳过该行(日志语义),
  目录结构整体异常 → 该源不可用。opencode 库缺失/表缺失 → 该源不可用。

## Testing Decisions

- 延续唯一 seam(HTTP API)+ fixture:新增 MiniMax 会话目录 fixture(按真实 ledger/display
  结构构造)与 opencode SQLite fixture(按真实表结构构造)。
- 新增组合测试:双 fixture 源合并后总量求和、明细行带 source、`source` 参数过滤生效、
  单源 schema 损坏时降级语义不回退。
- 既有 25 个测试必须零改动语义通过(fixture 注入时将其余来源路径指向不存在位置)。
- 真实库冒烟(live):MiniMax 5 会话、opencode 1 会话可被读出且行数 > 0。

## Out of Scope

- 自有统一统计库与水位线同步(数据量证明不需要);
- 前端按来源堆叠图表与来源级下钻页(表格展示来源列已够用);
- Claude Code / Codex / Kimi CLI / Qwen Code 适配器(后续票);
- MiniMax/opencode 的 TTFT(上游无数据)。

## Further Notes

- MiniMax ledger schemaVersion=1,漂移风险由 schema 防御兜底;
- opencode 与 ZCode 的 session 表结构高度相似,适配器可复用 zcode.py 骨架;
- 成本折算沿用 v1 价格表机制:MiniMax-M3、big-pickle 等模型默认未计价,用户可自行补价格。
