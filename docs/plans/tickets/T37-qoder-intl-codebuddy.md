# T37 — Qoder 国际版 + CodeBuddy 接入(P1,前置取证)

**Blocked by:** T33(同构模板)、T34(系数来源就位)
**Status:** draft (2026-09-05)
**Spec:** docs/specs/v3-credit-sources-spec.md §D5(qoder 国际版 / codebuddy);research §6.7 #5

## User story

同时使用 Qoder 国际版与 CodeBuddy 的用户,希望在 zlens 里看到与 CN 区**分开**的积分账
(官方明写两区积分不等价、不互通),以及与 WorkBuddy 同池的 CodeBuddy 用量。

## What to build

1. **`sources/qoder.py`(id=`qoder`,P1)**:与 `qoder_cn` 完全同构,根目录 `~/.qoder`。
   **必须是独立 source id**——官方明写 Qoder CN 与 Qoder 的积分定价不同、不等价、不可互通。
   开工前先实测国际版本地文件形状是否与 CN 一致(本会话早前探索记录:`~/.qoder/projects/*.jsonl`
   的 usage 四档恒 0 且**未见 credits 字段**——若国际版本地确实无积分载荷,本票降级为
   「只接系数/占位」,以取证结论为准,不编数)。
2. **CodeBuddy(P1,前置取证)**:与 WorkBuddy 同积分池,官方 `/cost` 就输出 token 四档。
   开工前确认:`~/.codebuddy` 是否有真实数据(research §6.7 #5:本机目录存在但未取证)、
   transcript 是否含逐请求 usage、四档互斥形状、credits 字段形状。取证结论先落
   `docs/research/` 增补小节,再按 WorkBuddy 模板落适配器。
3. 两个新源的测试沿用 T32/T33 的断言模式(恒等式 / null-vs-0 / 去重键 / 降级语义),
   fixture 照实测形状合成。

## Acceptance criteria

- [ ] 国际版本地形状取证结论落 research(有无 credits 载荷、entrypoint 分布),据此定实现或降级
- [ ] CodeBuddy 取证结论落 research;有数据则适配器 + live 冒烟,无数据则票内明确搁置理由
- [ ] 若实现:`qoder` 与 `qoder_cn` 在来源筛选器中独立出现,积分互不合并
- [ ] 既有测试零语义改动;`make check` 全绿

## Architectural decisions

- **取证先行**:P1 两源都存在「本机数据可能与 CN 不同构」的风险,票的第一个交付物是
  research 增补小节,实现与否由取证决定——禁止按 CN 形状想象式实现。
- 独立 source id 是跨区计价的唯一防线:任何「同配置文件双根目录」的合并方案都违反
  渠道不合并红线。
