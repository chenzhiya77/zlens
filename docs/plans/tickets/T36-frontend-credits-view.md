# T36 — 前端积分视图(Overview 卡片区 / 表格列 / 未提供标记)

**Blocked by:** T31、T32、T33、T35
**Status:** draft (2026-09-05)
**Spec:** docs/specs/v3-credit-sources-spec.md §D6;验收 1/3/4

## User story

打开 zlens,积分来源的用量以「积分」呈现、token 来源以「token」呈现,三种钱
(按量消耗 / 买断支出 / 积分标价值)各占各的卡片,谁也不会混进谁的合计里;
「没上报」永远显示为「未提供」而不是 0。

## What to build

1. **Overview 新增「积分消耗」卡片区**:实扣(`credit_total`)/ 原价(`credit_original_total`)/
   折扣差额(`discount_credits`)/ 标价值(`credit_value_cny`)各自成列,**不做合计条**;
   合计旁标注「仅含 N 个上报积分的来源(列出)」(spec D2 的界面补偿);三笔钱
   (按量消耗 / 买断支出 / 积分标价值)在界面上任何位置都没有相加关系。
2. **`tokens_reported=false` 的来源**:任何图表画「未提供」标记,**禁止画 0**(画 0 等于
   宣称无消耗);token 合计旁明确列出「未计入 token 口径的来源」(spec 验收 1)。
3. **Models / Trends / Projects 表加积分列**;来源筛选器不变(直接吃新 source id)。
4. **别名与格式纪律**:积分统一 2 位小数;`null` 显示「未上报」,`0` 显示 `0.00`,
   二者不可混同(与 buyout 的 null-vs-0 渲染纪律同构);标价值文案用「标价值」,
   **禁止出现「花费/支出」字样**(spec D3:它不是实付)。
5. 设置页「抓取计价系数」按钮与快照展示(T34 的 UI 面:抓取时间、来源路径、非官方口径标注、
   越界告警)。
6. README / CHANGELOG 同步(文档随代码走;本票是 v3 的用户可见面收官)。

## Acceptance criteria

- [ ] 切到 Qoder CN 来源:积分数字有值,token 处显示「未提供」而非 0;合并视图 token 合计旁
      列出未计入来源(spec 验收 1)
- [ ] 三个总额在界面任何位置无相加关系;「同时存在三笔的来源」用例覆盖(spec 验收 4)
- [ ] 积分列 null=「未上报」、0=0.00;标价值文案不出现「花费/支出」
- [ ] WorkBuddy(办公 agent)的 Projects 标题读起来不破坏布局(结构适用,文案可容忍)
- [ ] `make check`(lint + test + build-web)全绿;浏览器冒烟走一遍真实本机数据

## Architectural decisions

- 前端**零重算**:所有合计/派生量来自 `/api/overview` 与 `/api/meta`(沿用「现总价」纪律),
  `discount_credits` 只展示不写回、不前端另算。
- 图表的「未提供」是数据驱动(`tokens_reported=false`),**不按 source id 硬编码特例**——
  未来任何新积分源自动获得同一渲染规则。
