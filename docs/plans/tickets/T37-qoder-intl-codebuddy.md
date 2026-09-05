# T37 — Qoder 国际版 + CodeBuddy 接入(P1,前置取证)

**Blocked by:** T33(同构模板)、T34(系数来源就位)
**Status:** partial (2026-09-05) —— Qoder 国际版已接入;CodeBuddy 取证仍待做

## 取证结论(2026-09-05,已实测)

- **国际版本地有真实积分账**(修正早期判断):`~/.qoder/projects/**/*.jsonl` 489 条 usage
  记录全部带 `credits`(非零,Σ 1061.21,去重后 483 个 request_id),tokens 恒 0,
  entrypoint 全为 `cli`,type 为 `assistant`,与 CN CLI 完全同构。早期「国际版无积分载荷」
  的判断只验证了 token 档、未查积分字段,作废。
- **与 `~/.qoder-cn` 的 request_id 零交集**(483 vs 1925,无重叠)——两条独立计费流,
  同时注册不存在双写;两源积分单位不等价,由 per-source 账本与独立积分单价隔离。

## What to build(已落地部分:Qoder 国际版)

- `sources/qoder.py`(id=`qoder`):继承 `QoderCnSource`,仅覆盖 id / 根目录
  (`Settings.qoder_config_dir`,默认 `~/.qoder`)/ 保留期提示文案;retention 语义共用。
- 注册进 MultiSource;`tests/test_qoder.py`(独立身份、保留期文案差异、缺失降级、
  live 冒烟:483 条 / Σcredits > 1000)。

## What to build(待做:CodeBuddy,前置取证)

- 与 WorkBuddy 同积分池,官方 `/cost` 输出 token 四档。开工前确认:`~/.codebuddy`
  是否有真实数据、transcript 是否含逐请求 usage、四档互斥形状、credits 字段形状。
  取证结论先落 `docs/research/` 增补小节,再按 WorkBuddy 模板落适配器。

## Acceptance criteria

- [x] 国际版本地形状取证结论落票(见上);按证据实现适配器
- [x] `qoder` 与 `qoder_cn` 在来源筛选器中独立出现,积分互不合并(per-source 账本)
- [x] 离线 + live 测试通过;`make check` 全绿
- [ ] CodeBuddy 取证结论落 research;有数据则适配器 + live 冒烟,无数据则票内明确搁置理由

## Architectural decisions

- **取证先行**:两源都存在「本机数据可能与预期不同构」的风险,交付物以证据为准——
  本次取证恰好推翻了降级预案(国际版有真数据),按同构实现。
- 独立 source id 是跨区计价的唯一防线:任何「同配置文件双根目录」的合并方案都违反
  渠道不合并红线;积分数字 per-source,跨源只有标价折算后的钱可比。
