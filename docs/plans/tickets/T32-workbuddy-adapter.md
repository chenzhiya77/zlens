# T32 — WorkBuddy 适配器(单一事实源 + 嵌套拆档 + 双口径)

**Blocked by:** T31
**Status:** draft (2026-09-05)
**Spec:** docs/specs/v3-credit-sources-spec.md §D5(workbuddy);取证 research §6.3、§9

## User story

作为 WorkBuddy 用户,我的 token 用量和积分扣费在本地都有真数,zlens 读一次就能同时给出
token 四档与积分账——这是四款积分类产品里唯一能双口径互相校验的来源。

## What to build

`sources/workbuddy.py`(id=`workbuddy`,Settings 新增 workbuddy 根路径,env 可覆盖):

1. **计量事实源只有一个:`projects/**/*.jsonl`(rglob)。** `workbuddy.db` 仅用于联接
   `session → cwd/title/时间`;**两处都计量必然重复计费——这是本票头号风险,实现时锁死**:
   token 与积分一律取自 jsonl 的 `providerData.rawUsage`,DB 的 `session_usage.used/size`
   是上下文占用快照(= prompt_tokens),**禁止进 token 合计**,只作占用展示。
2. **拆档**(research §6.3 实测嵌套形状,与 ZCode 同类,拆档只能在适配器):
   - `cache_read = prompt_cache_hit_tokens`(与 `prompt_tokens_details.cached_tokens` 实测相等,
     二者取其一并对不一致告警);
   - `cache_creation = prompt_cache_write_tokens`;
   - `input = prompt_tokens − cache_read − cache_creation`;`output = completion_tokens`;
   - `total = input + output + cache_read + cache_creation`,并与上游 `total_tokens` 校验相等;
   - `reasoning` 不另立加数(completion 的子集)。
3. **积分**:`credits = Σ rawUsage.credit`(逐条原始浮点求和);`credit_json`(DB)只做会话级
   合计校验,**校验不等时以 rawUsage.credit 为准并降级告警**;`credit_json` 的 hex 键语义未知,
   不参与模型归属。混元 hy 系列 credit=0 是真值(免费),必须与 credit 缺失区分(research §9.2)。
4. **渠道键**:`provider_id = providerData.requestModelId`(用户选的档位,如 `auto`),
   `model_id = providerData.model`(真实模型,如 `glm-5.2`)→ `workbuddy|auto|glm-5.2`。
   auto 档下真实模型不唯一(glm-5.2/glm-5.3 并存,§9.2),必须分行;同一真实模型经不同档位
   保持独立行(跨渠道不合并红线)。
5. **去重键**:`providerData.messageId` / `conversationRequestId`;`traceId` 保留排障。
   822 条 assistant 记录中仅 160 条带 rawUsage(其余为无用量载荷的消息)——无载荷不计费。
6. `latency_samples()` 返回空、`health_summary()` 除请求数外全 0/空(上游无字段,不编数);
   `tokens_reported=True`、`credits_reported=True`。
7. `tests/test_workbuddy.py`:fixture **照实测嵌套形状**(三套方言并存、
   `prompt_cache_hit_tokens ⊂ prompt_tokens`、`reasoning ⊂ completion`、rawUsage.credit 逐条带值、
   DB 与 JSONL 双写同一会话)→ 断言拆档恒等式成立、**双写不重复计量**、credit_json 不等时
   告警且取 rawUsage;补 credit=0(hy 免费行)与 credit 缺失两种形状。

## Acceptance criteria

- [ ] 合成 fixture 拆档后恒等式逐条成立;token 四档与 credits 同时有值且互不干扰
- [ ] DB + JSONL 双写同会话不被计两次(单一事实源断言)
- [ ] `workbuddy|auto|glm-5.2` 与 `workbuddy|auto|glm-5.3` 分行;credit=0 行如实记 0
- [ ] 文件缺失 → source_unavailable;坏行跳过;schema 异常 → schema_incompatible
- [ ] 真实本机库(live)冒烟:28 会话、160 条带用量消息可读,Σcredits ≈ 325.42(数量级校验)
- [ ] 既有测试零语义改动;`make check` 全绿;AGENTS.md Repository Map 增补该适配器

## Architectural decisions

- 双口径并存但互不折算:token 走 pricing.json 逐档乘价,credits 走第三笔账;
  glm-5.2 通道 ≈8.7K tok/credit 只是通道常数(research §9.2),**禁止做成产品系数**。
- WorkBuddy 是办公 agent:`title` 语义(ai-title)与代码项目不同,Projects 视图文案可能读起来怪,
  结构不变(spec 风险条目)。
