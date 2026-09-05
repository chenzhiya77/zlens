# T35 — 积分单价录入(pricing.json v2 录入面)

**Blocked by:** T31(schema 已随 T31 落地:version 2 + `credit_prices` 解析与降级;
本票只做录入面与校验 UX)
**Status:** draft (2026-09-05)
**Spec:** docs/specs/v3-credit-sources-spec.md §D3(录入部分);API Contract(PUT /api/pricing)

## User story

作为积分来源用户,我要按官方资源包/订阅价录入「¥/积分」单价,让 zlens 告诉我
「这段时间烧掉的积分按官方标价值多少钱」——它是标价折算,不是实付,也不是消费金额。

## What to build

1. **`PUT /api/pricing`** 接受 `version: 2` 与 `credit_prices`;校验 `basis ∈ {plan, pack}`、
   `cny_per_credit > 0`;**非法积分单价表降级为空表而非报错**(价格表打字错误不能弄坏应用,
   沿用现规矩)。
2. **Pricing 页录入区**(frontend):两段键 `source|basis` 的编辑块,**与渠道三元组价格
   分块显示**(避免误读成模型单价);plan 与 pack 并存分别显示,禁止自动取低、禁止内置默认值
   (与「猜市场价等于造成本」同源);行内说明:套餐内等效单价(订阅费 ÷ 含量)与加量包单价
   回答不同问题,由用户自己算好录入,应用不代算。
3. **`pricing.example.json`** 更新为 v2 示例(含 `credit_prices` 注释性样例:
   `workbuddy|plan`、`qoder_cn|pack` 等)。
4. 录入后 Overview 的 `credit_value_cny` 按 basis 生效(spec 验收 3):只填 plan 不填 pack 时
   两者分别显示、plan 标价值正常;缺某上报来源的**任一** basis 单价时该 basis 总额 null。
5. AGENTS.md「价格外置」段落补积分单价形态说明(文档随代码走)。

## Acceptance criteria

- [ ] 录入 `workbuddy|plan` 0.0495 保存、重启后仍在;`basis` 非法值被拒且不弄坏整表
- [ ] Pricing 页两段键块与渠道三元组块视觉分离,plan/pack 双列并存
- [ ] 缺某上报来源单价时对应 basis 的 `credit_value_cny` 为 null,另一 basis 不受影响
- [ ] version 1 老文件经 PUT 升级到 version 2 后 token 四档语义不变(回归)
- [ ] `make check` 全绿;`pricing.example.json` 可作为新用户起点直接加载

## Architectural decisions

- `cny_per_credit` 与四档 token 单价互斥使用,但**同一个文件、同一个 version 字段**——
  不引入第二张表,`PriceTable` 内部按 basis 分派。
- 键是 `source|basis` 两段,**不带 model_id**:积分单价是来源级口径(WorkBuddy/Qoder 的
  官方标价不按模型区分 ¥/积分;逐模型差异体现在积分数本身),不与渠道三元组混键。
