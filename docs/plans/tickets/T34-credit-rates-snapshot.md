# T34 — 系数快照抓取器(core/rates.py + /api/credit-rates)

**Blocked by:** None(可与 T31 并行)
**Status:** draft (2026-09-05)
**Spec:** docs/specs/v3-credit-sources-spec.md §D4;取证 research §6.5(安全边界)

## User story

作为 Qoder/Trae 用户,我想把客户端缓存里的计价倍率(16 档 price_factor 等)抓一份快照
在 zlens 里查看誊抄——但它是厂商私有口径,只能看,永远不能替我算钱。

## What to build

新 `core/rates.py` + gitignored `credit_rates.json`:

1. **快照结构**:`{ version, captured_at, source, kind: "client-cache", provenance: "<文件路径>",
   entries: [{ model_id, display_name, price_factor, original_price_factor, max_input_tokens,
   context_tiers, promotion }] }`。
2. **抓取来源只有两处明文客户端缓存**:
   - Qoder IDE `state.vscdb` 的 `aicoding.modelConfigs.cache.{assistant,experts,quest}`
     (16 档:`auto` 1.0 / `performance` 1.1 / `ultimate` 1.6 / `efficient` 0.3(原价 0.5)/
     `qfmodel` 0.1 / `cmodel` 3.2 …,与官方文档宣称 0.1×–1.6× 不一致——快照价值就在此);
   - Trae CN `state.vscdb` 的 `…_AI.agent.model.model_list_map`
     (`consumption_rate`、`original_consumption_rate`、`member_discount`、`fee_model_level` 等)。
3. **安全边界(research §6.5,测试断言级)**:
   - **字段白名单抓取**,只取上表计价字段;键名/路径命中 `ak`/`sk`/`api_key`/`secret`/
     `base_url`/`auth_type`/`jwt`/`token` 的一律丢弃;
   - **任何 `secret://` 前缀的 KV 不读、不解密、不回显**(`secret://aicoding.auth.creditUsage`
     是加密 Buffer,同命名空间含 `customModel.apiKey.*`);
   - Trae 的 `terminal.integrated.bufferState` 含 `TRAE_JWT_TOKEN_PATH` 等环境变量,
     **禁止扫终端状态缓冲**。
4. **端点**:`GET /api/credit-rates`(无快照文件返回空态,不是 500/503);
   `POST /api/credit-rates/capture`(用户显式动作,只写 `credit_rates.json` 一个本地文件,
   永不写 pricing.json、永不写上游任何库;来源不存在/被加密/字段漂移降级为明确错误响应,
   沿用 SourceError 语义)。zlens 无 CLI 入口,本票不引入。
5. `tests/test_rates.py`:只喂白名单字段;断言 `secret://` 键、`ak/base_url/auth_type` 路径
   **永不出现在快照里**;系数落在文档宣称区间外时产出告警项。

## Acceptance criteria

- [ ] 抓一次:快照含 `captured_at` 与 `provenance`;界面(设置页按钮 + 展示,T36 落地 UI)
      标注「客户端缓存快照,非官方文档 · 抓取于 <日期>」
- [ ] `cmodel 3.2×` 这类越界值触发可见告警
- [ ] 快照内不含任何 `secret://` 或凭据字段(测试断言)
- [ ] 来源缺失/加密/漂移 → 明确错误响应,不拖垮服务
- [ ] 快照文件任何数值**不参与** `credit_value_cny` 或任何金额计算(架构红线,评审要点)
- [ ] `make check` 全绿

## Architectural decisions

- 快照只用于**展示与人工誊抄**:界面系数漂移已被实证(`efficient` 0.5→0.3;文档与客户端不一致
  是事实),快照必须带时间、可比对。
- 抓取是用户显式动作,不是后台轮询;`POST` 写本机 gitignored 文件,沿用
  `PUT /api/pricing` / `POST /api/pricing/extract` 的既有「端点写用户本机文件」先例。
