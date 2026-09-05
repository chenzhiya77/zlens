# T33 — Qoder CN 适配器(积分账 + token 未上报 + 30 天清理告警)

**Blocked by:** T31
**Status:** draft (2026-09-05)
**Spec:** docs/specs/v3-credit-sources-spec.md §D5(qoder_cn);取证 research §8、§2.2

## User story

作为 Qoder CN CLI 用户,我的本地会话文件里直接带每条请求的 `credits/original_credits`
(token 恒为 0),zlens 读本地文件就能重建积分账——不需要登录网页导出任何东西。

## What to build

`sources/qoder_cn.py`(id=`qoder_cn`,Settings 新增 `qoder_cn_config_dir`,默认 `~/.qoder-cn`,
`ZLENS_QODERCN_CONFIG_DIR` 可覆盖):

1. **`tokens_reported=False` 是本源的立身之本**(research §6.2/§2.2:989 条 billable 消息
   四档恒 0 而 credits 是真数——0 是「上游没上报」,不是零消耗):四档一律 0 且不参与乘价,
   界面显示「未提供」而非 0(T36 落地)。
2. **只收 `entrypoint == "cli"` 的记录**(本机实测全为 cli;这是未来 IDE 也写同一目录时
   唯一的防重复计量闸门)。
3. **子代理 transcript 必须纳入**(research §8.3):`projects/<cwd>/<sessionId>/subagents/agent-*.jsonl`
   含独立 usage/credits(本机 45 条 billable、12.53 积分),一层 glob 会漏;需 rglob 或显式
   `subagents/` 处理;子代理记录自带 `agentId`/`parent_tool_use_id`/`isSidechain` 可识别归属。
4. **积分**:`credits = usage.credits`、`original_credits = usage.original_credits`,逐条保留
   (折扣是逐条属性且随会话消失,幸存集 ratio=1.0、被删集才有 0.5×/0.6×——禁止按来源配
   常数折扣);credits 小数最深 9 位,求和用原始浮点,仅展示层取 2 位。
   **credits 缺失(None)与 0 分开处理**:官方 SDK 文档明写「Credits 为可选字段,缺失不要当 0」。
5. **过滤**:`model == "<synthetic>"` 跳过;`billable` 明确为 false 的消息计入请求数但不计积分。
6. **渠道键**:`provider_id = "qoder"` 常量(上游无 provider 字段,沿用 opencode 先例,不解析
   档位名不猜渠道);`model_id = message.model`(档位名,如 `qfmodel`)。
7. **去重**:`request_id` 全局唯一(832/832 无重复),比 timestamp 稳;`version` 字段记录 CLI 版本。
8. **30 天清理告警**:官方 `sessionRetention.maxAge=30d` → 本地账本最长 30 天,历史窗口由厂商
   决定;检测到 `.last-cleanup` 即在 meta/健康度提示(spec 风险条目)。
   `service_tier/speed/inference_geo/iterations/server_tool_use` 本机为常数,保留字段不建列。
9. `tests/test_qoder_cn.py`:fixture 含 token 全 0 + credits 非零、`<synthetic>`、`billable=false`、
   `entrypoint="ide"`、subagents 目录、credits 缺失 → 断言 `tokens_reported=False`、0 token 不进
   乘价、只收 cli、缺失保持 null、子代理被计入。

## Acceptance criteria

- [ ] 合成 fixture:积分天 × 档位折叠正确,credits/original_credits 逐条保留,tokens_reported=False
- [ ] 子代理目录被扫描计入,主会话与子代理不重复计量(request_id 去重)
- [ ] credits 缺失保持 null;billable=false 计请求数不计积分;`<synthetic>` 跳过
- [ ] 文件缺失 → source_unavailable;关键字段缺失 → schema_incompatible;坏行跳过
- [ ] 真实本机库(live)冒烟:行数 > 0,Σcredits 与 §8 幸存集口径数量级一致
- [ ] 既有测试零语义改动;`make check` 全绿;AGENTS.md Repository Map 增补该适配器

## Architectural decisions

- 与未来的 Qoder 国际版适配器(T37)**独立 source id**:官方明写两区定价不同、积分不等价、不互通。
- 数据获取零网络:本地 jsonl 即事实源(与本会话早前探索的「网页导出」方案相比,本方案无需登录态,
  v3 规格据此改判——旧 T29 已退役)。
