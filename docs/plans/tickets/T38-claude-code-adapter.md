# T38 — Claude Code 适配器(真 token 四档 + 流式去重)

**Blocked by:** None(token 管线现成,无前置)
**Status:** draft (2026-09-05)
**取证:** 本机 `~/.claude`(2026-09-05,只读):549 条 usage 行 → 去重后 205 次计费调用,
14,882,245 tokens(in 2.31M / out 119K / cache_write 444K / cache_read 12.0M),四档互斥实证
(input < cache_read,即 input 不含缓存);8/23–8/25;模型 `stealth/ox-alpha`、`claude-fable-5`。

## User story

作为 Claude Code 用户,我的本地 transcript 里有真实的 token 四档用量,zlens 读一次
就能进现有 token 管线与成本折算——不需要积分语义,是所有来源里最省事的一张票。

## What to build

`sources/claude.py`(id=`claude`,Settings 新增 `claude_config_dir`,默认 `~/.claude`):

1. **布局与 Qoder CN 同源**(Qoder 的 transcript 格式即源于 Claude Code):
   `projects/<转义cwd>/<会话>.jsonl` + `<会话>/subagents/agent-*.jsonl`(rglob 全收),
   信封带 cwd/sessionId/gitBranch/entrypoint,timestamp 为 ISO Z 字符串。
2. **流式去重是本票唯一的真陷阱**:一条 API 响应被拆成多条同 `message.id` 的
   assistant 事件——或逐位相同的重放,或「全零占位事件 + 一条真用量」。
   规则(实测验证):**按 message.id 分组取四档合计最大的一条**;全零占位行
   (合计 0)在解析期直接跳过;无 id 的非零行独立保留。不处理则 token 虚增 2.1 倍。
3. **四档直取互斥值**(input_tokens / output_tokens / cache_creation_input_tokens /
   cache_read_input_tokens,上游无 total 字段,契约 total = 四档相加);
   reasoning 取 `output_tokens_details.reasoning_tokens`(output 的子集,不另立加数);
   `tokens_reported=True`、credits 恒 None(无积分账)。
4. `<synthetic>` 跳过;`.last-cleanup` 标记 → meta 保留期提示(官方 cleanupPeriodDays,
   默认 30 天);latency 空、health 仅请求数;项目维度用记录自带 cwd。
5. 渠道键 `claude|claude|<model_id>`(provider 恒 `claude`;模型名可含斜杠,
   对 `|` 分隔键无冲突)。价格由用户在 pricing.json 按官方 API 价录入;
   订阅费走 buyout 行,与按量互不相加。
6. `tests/test_claude.py`:fixture 含两种重复形态、`<synthetic>`、坏行、subagents、
   带斜杠模型名、`.last-cleanup`;live 冒烟断言去重生效(计费调用数 < 原始 usage 行数)。

## Acceptance criteria

- [ ] 两种重复形态(逐位重放 / 零占位+真用量)都只计一次;去重后四档相加 = 契约 total
- [ ] token 四档真数进管线;`tokens_reported=True`;未计价渠道按 ¥0 计入的既有规则生效
- [ ] 文件缺失 → source_unavailable;坏行跳过;`.last-cleanup` → retention_hint
- [ ] 双源 fixture 合并:总量求和、明细行带 source、`?source=claude` 过滤生效
- [ ] 既有测试零语义改动通过(直接构造 Settings 的测试钉住 `claude_config_dir` 隔离);
      注册表断言随新源扩展;`make check` 全绿
- [ ] 真实本机库(live)冒烟:计费调用数 > 100 且**小于**原始 usage 行数(去重生效)、
      total_tokens > 100 万、逐行四档恒等式成立

## Architectural decisions

- 不做积分语义、不做 entrypoint 闸门(单写者)、不为 reasonig 另立加数——
  上游给什么就是什么,归一仅限缓存档已互斥这一事实的确认。
- 模型名含斜杠(如 `stealth/ox-alpha`)是上游事实:model_id 原样保留,
  渠道键的 `|` 分隔符不受影响,禁止为了"好看"改写模型名。
