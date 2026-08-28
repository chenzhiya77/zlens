# zlens v3 规格：积分类来源接入（WorkBuddy + Qoder）与第三笔账「积分消耗」

- 取证依据：`docs/research/credit-opaque-agents-usage.md`。**引用可行性判断时只看该报告 §6.6（本机实测修订版），
  不要引用其 §四 原表** —— 其中三处推断已被本机实测推翻。
- 规格获取日期：2026-08-28。这四款产品的计费倍率高频改动，本规格里的系数与字段清单都是**当日快照**。

## Problem Statement

zlens v1–v2 的成本模型只有一种形状：**本地量出 token 四档 → 逐档乘 `pricing.json` 单价 → 得金额**。
接进来的四个新候选（Qoder、Qoder CN、Qoder IDE、Trae、WorkBuddy）全都是**积分（Credits）计费**，
这条链路在它们身上直接断裂：

1. **积分与 token 没有换算关系。** Qoder SDK 文档原文：「Token 字段与 Credits 没有固定换算关系」。
   本机标定实验（research §6.4）进一步证明由积分反推 token **不可实现**：766 条含 credits 的消息全部无法参与拟合。
2. **有的来源根本不给你 token。** 本机实测：`~/.qoder-cn/projects/**/*.jsonl` 里 989 条 `billable=true` 的消息，
   `input_tokens`/`output_tokens`/`cache_creation_input_tokens`/`cache_read_input_tokens` **恒为 0**，
   而 `credits`/`original_credits` 是真数。这些 0 不是「没用」，是**上游没上报**。
   现有数据模型无法表达这个区别 —— 按现契约渲染，Qoder 用户会看到「你用了 0 token」，这是撒谎。
3. **用户看得见积分、看不见价值。** 本机 7 个会话合计：**实扣 897.93 积分、原价 1309.98 积分**，
   差额 412.05（31.5%）全是促销折扣，且折扣率逐条不稳定（0.5×、0.6×、1.0× 都出现过）。
   官方界面对个人用户既不给 token、也不给这份「省了多少」的账。这正是 zlens 的用户场景。

## Solution

**引入第三笔账：积分消耗（`credits`）。** 与「按量消耗」（`estimated_cost`）、「买断支出」（`buyout_total`）
并列，**三者两两永不相加**。同一个来源可以只报其中一笔或两笔，缺的那笔是 `null`，不是 `0`。

配套两件事：

- **「未上报」成为一等公民**：行级新增 `tokens_reported` / `credits_reported`，让「上游没给」和「给了 0」
  在数据模型里可区分，合并视图据此标注口径。
- **积分单价外置**：`pricing.json` 升到 version 2，新增 `credit_prices`（¥/积分，按 `source|basis` 键），
  由用户录入，回答「这段时间烧掉的积分按官方标价值多少钱」。它是**标价折算**，不是实付，也不是消费金额。

新增两个适配器（`workbuddy`、`qoder_cn`），一个只读系数快照机制（`credit_rates.json`）。
下游九个端点与全部视图沿用 v2 的 MultiSource 合并零改动原则，只增列不改形。

## 数据源实测结论（2026-08-28，本机验证）

- **WorkBuddy（腾讯，与 CodeBuddy 同积分池）= 四款里唯一「token 与积分同记录」的来源。**
  两处明文存储：`~/.workbuddy/workbuddy.db`（`sessions`、`session_usage(used,size,credit_json)`、`automations`、
  `automation_runs`）与 `~/.workbuddy/projects/<项目slug>/<sessionId>.jsonl`（Claude Code 同构）。
  单条 assistant 记录里并存**三套上游方言**：`message.usage.*`、`providerData.rawUsage.*`
  （OpenAI 形 + Anthropic 形 + 火山/DeepSeek 形 + **`credit`**）、`providerData.usage.*`。
  恒等式实测全部成立（两文件合计）：

  ```
  prompt 65879 = cache_hit 32512 + cache_miss 33367
  total  66771 = prompt 65879 + completion 892
  reasoning 521 ⊂ completion 892（completion_thinking_tokens 亦 521）
  session_usage.used 合计 == Σ usage.inputTokens == 65879
  Σ rawUsage.credit == credit_json 之和 == 7.65
  ```

  → **缓存前缀嵌在 prompt 内，与 ZCode 同类**，拆档只能在适配器做。
  真实模型 `providerData.model=glm-5.2`，用户所选档位 `requestModelId=auto`。
  初步标定 `1 credit ≈ 8756 / 8701 total_tokens`（两次独立测量相差 0.6%），**样本不足以成为系数**。
  `credit_json` 的 32 位 hex 键语义未知，**已排除它是模型标识**（同模型两会话取不同值）。
- **Qoder CN CLI（本机用户正在用的这个）**：`~/.qoder-cn/projects/<转义cwd>/<sessionId>.jsonl`，
  顶层带 `cwd`/`gitBranch`/`entrypoint`/`isSidechain`/`contextWindow`，`message.usage` 有
  `credits`/`original_credits`/`billable`/`request_id`/`context_usage_ratio`/`service_tier`/`speed`/
  `inference_geo`/`server_tool_use.*`，**token 四档恒为 0**。`entrypoint` 实测全为 `cli`，可用于与 IDE 分流。
  官方 `sessionRetention.maxAge=30d` → 本地账本最长 30 天，历史窗口天然受限。
  档位倍率完整可见但**只在 Qoder IDE 的客户端缓存里**（16 档：`auto` 1.0 / `performance` 1.1 / `ultimate` 1.6 /
  `efficient` 0.3（原价 0.5）/ `qfmodel` 0.1 / `cmodel` 3.2 …），且与官方文档宣称的 0.1×–1.6× 区间**不一致**。
- **Qoder IDE**：逐次消耗本地**不存在**（747 键全扫仅 9 键含用量字段且全是配置/主题/密文；107 个
  `aicoding-chat-*` 键形状只有 `[{id,isHidden}]`；`chatSessions/*.json` 只有 VS Code 默认元数据）。
- **Trae 国内版**：会话库 `ModularData/ai-agent/database.db`（28 MB）**文件头非 SQLite 魔数，整库加密**；
  但计价参数明文（`consumption_rate`、`original_consumption_rate`、`member_discount`、`fee_model_level`、
  `saas_usage.default/max`、`max_turns.*`，按 7 场景 × 12–17 模型逐条下发）。

## Implementation Decisions

### D1 契约扩展：第三笔账与「未上报」（`sources/models.py`）

- 行级模型（`ModelUsageSummary`、`DailyModelUsage`、`ProjectModelUsage`、`DailyUsage`、`ProjectUsage`、
  `Overview`）统一新增四字段：
  - `credits: float | None = None` —— 实扣积分；`None` = 该来源不上报积分（**与 0.0 严格区分**，
    沿用 `buyout_amount` 的 null-vs-0 纪律）。
  - `original_credits: float | None = None` —— 折扣前原价积分。
  - `tokens_reported: bool = True` —— `False` 表示该来源 token 恒为 0 且不代表零消耗。
  - `credits_reported: bool = False` —— 由适配器声明；`credits` 非 `None` 的行必须 `credits_reported=True`。
- `reasoning_tokens` 继续是 `output_tokens` 的 breakdown，**不另立加数**（WorkBuddy 实测 reasoning ⊂ completion）。
- 恒等式不变：`input + output + cache_creation + cache_read == total_tokens`，**仅在 `tokens_reported=True` 时校验**。
  契约文档必须写明：`tokens_reported=False` 时四档的 0 是占位值，禁止参与任何逐档乘价。
- `MetaInfo` 新增 `credit_reporting_sources: list[str]`、`token_reporting_sources: list[str]`，
  以及 `unpriced_credits: list[str]`（已上报积分但未录积分单价的来源）。

### D2 合并语义（`sources/multi.py`）

- 金额沿用 v1/v2 规则：任一**参与计价**的渠道未定价 → `estimated_cost = null`。
- **积分采用「忽略 null 求和」而非「任一 null 则整体 null」**，理由是语义不同：某个来源不报积分不是「数据缺失」，
  而是**它没有这本账**（ZCode 就没有积分概念）。让 ZCode 的存在把 WorkBuddy 的真实积分抹成未知，是丢信息。
  代价必须在界面上补回来：合计旁标注「仅含 N 个上报积分的来源（列出）」。
  若参与集合里无任何来源上报积分 → `credits = null`（不是 0）。
- **token 合计保持可加**（同理），但 `tokens_reported=False` 的来源必须出现在「未计入 token 口径」的提示里。
  这是 v3 唯一一处「跨源相加会少算」的已知口径，**必须显式标注，禁止静默**。

### D3 积分单价外置（`core/cost.py` + `pricing.example.json`）

- `PriceTable.version` 升到 `2`，新增顶层：

  ```json
  "credit_prices": {
    "workbuddy|plan": { "cny_per_credit": 0.0495, "note": "¥99 / 2000 积分" },
    "workbuddy|pack": { "cny_per_credit": 0.05, "note": "加量包 1000 积分 / 50 元" }
  }
  ```

- 键是**两段** `source|basis`，`basis ∈ {plan, pack}`：套餐内等效单价与加量包单价都是真数，
  但回答不同问题（「订阅摊下来」vs「额外买要花」）→ **两条并存，界面分别显示，禁止自动取低、禁止内置默认值**
  （与 v2.4「猜市场价等于造成本」同源）。
- `enrich_overview` 新增派生量：
  - `credit_total: float | None` —— 参与来源实扣积分合计。
  - `credit_original_total: float | None` —— 原价合计。
  - `discount_credits: float | None` —— `原价 − 实扣`，**纯派生展示值，禁止写回 `pricing.json`，
    禁止在前端另算一份公式**（沿用 v2.4「现总价」的既有纪律）。
  - `credit_value_cny: float | None` —— `Σ credits × cny_per_credit`；**任一上报积分的来源在该 basis 下缺单价
    → 整体 null**（半张账单会系统性低估，与 unpriced-gating 同构）。
- **三笔钱两两不相加**：`estimated_cost`（按量消耗）、`buyout_total`（买断/套餐已付）、`credit_value_cny`
  （积分标价值）。`credit_value_cny` 不是实付、不是消耗金额，文案必须用「标价值」而不是「花费」。

### D4 系数快照（新 `core/rates.py` + gitignored `credit_rates.json`）

- 结构：`{ version, captured_at, source, kind: "client-cache", provenance: "<文件路径>",
  entries: [{ model_id, display_name, price_factor, original_price_factor, max_input_tokens,
  context_tiers, promotion }] }`。
- 抓取来源**只有两处明文客户端缓存**：Qoder IDE `state.vscdb` 的 `aicoding.modelConfigs.cache.{assistant,
  experts,quest}`；Trae CN `state.vscdb` 的 `…_AI.agent.model.model_list_map`。
- **字段白名单抓取**：只取上表列出的计价字段；键名或路径命中 `ak`/`sk`/`api_key`/`secret`/`base_url`/
  `auth_type`/`jwt`/`token` 的一律丢弃。**任何 `secret://` 前缀的 KV 不读、不解密、不回显**
  （本机 `secret://aicoding.auth.creditUsage` 是 VS Code 加密 Buffer，同命名空间含 `customModel.apiKey.*`）。
  Trae 的 `terminal.integrated.bufferState` 含 `TRAE_JWT_TOKEN_PATH` 等环境变量 → **禁止扫终端状态缓冲**。
- **快照只用于展示与人工誊抄**：界面标注「客户端缓存快照，非官方文档 · 抓取于 <日期>」；
  当 `price_factor` 落在官方文档宣称区间之外时告警（本机实证：`cmodel` 3.2× > 文档上限 1.6×）。
  **禁止让快照参与 `credit_value_cny` 或任何金额计算** —— 否则等于内置了厂商系数。
- 抓取是用户显式动作（设置页按钮 → `POST /api/credit-rates/capture`），只写 `credit_rates.json` 一个本地文件，
  **永不写 `pricing.json`，永不写上游任何库**。zlens 目前**没有 CLI 入口**（`src/zlens/` 下无 `__main__.py`），
  v3 不为抓取这件事引入 CLI。

### D5 新适配器

- **`sources/workbuddy.py`（id=`workbuddy`，P0）**
  - **计量事实源只有一个：`projects/**/*.jsonl`。** `workbuddy.db` 仅用于联接 `session → cwd/title/时间`。
    两处都计量必然重复计费 —— 这是 v3 最大的单点风险，票里要写死。
  - 拆档（实测嵌套形状）：`cache_read = prompt_cache_hit_tokens`（与 `prompt_tokens_details.cached_tokens`
    实测相等，二者取其一并对不一致告警）、`cache_creation = prompt_cache_write_tokens`、
    `input = prompt_tokens − cache_read − cache_creation`、`output = completion_tokens`、
    `total = input + output + cache_read + cache_creation`，并与上游 `total_tokens` 校验相等。
  - `credits = rawUsage.credit`（逐条求和）。`credit_json` 的 hex 键**只做会话级合计校验**，
    不参与模型归属；校验不等时以 `rawUsage.credit` 为准并降级告警。
  - 渠道键：`provider_id = providerData.requestModelId`（用户选的档位，如 `auto`），
    `model_id = providerData.model`（解析后的真实模型，如 `glm-5.2`）→ `workbuddy|auto|glm-5.2`。
    同一真实模型经不同档位保持独立行、独立计价（跨渠道不合并红线）。
  - `session_usage.used/size` 是上下文占用快照（= prompt_tokens），**禁止进 token 合计**，只作占用展示。
  - 去重键：`providerData.messageId` / `conversationRequestId`；`traceId` 保留作排障。
  - `latency_samples()` 返回空、`health_summary()` 除请求数外全 0/空（上游无字段，不编数）。
- **`sources/qoder_cn.py`（id=`qoder_cn`，P0）**
  - 只读 `~/.qoder-cn/projects/*/*.jsonl`；`QODERCN_CONFIG_DIR` 可覆盖根（沿用 Settings 路径注入）。
  - **`tokens_reported=False` 是本源的立身之本**：四档一律 0 且不参与乘价。
  - 只收 `entrypoint == "cli"` 的记录（未来若 IDE 也写同一目录，这是唯一的防重复计量闸门）。
  - `credits = usage.credits`、`original_credits = usage.original_credits`；
    跳过 `model == "<synthetic>"` 与 `billable` 明确为 `false` 的消息（后者计入请求数但不计积分）。
  - `provider_id = "qoder"` 常量（上游无 provider 字段，沿用 opencode `data.get("providerID") or "opencode"` 先例，
    不解析档位名、不猜渠道）；`model_id = message.model`（档位名，如 `qfmodel`）。
  - `credits` 缺失（`None`）与 0 分开处理：官方 SDK 文档明写「Credits 为可选字段，缺失不要当 0」。
  - `MetaInfo.first_request_at` 即本地窗口起点；健康度页须提示 30 天自动清理（检测到 `.last-cleanup` 即告警）。
- **`sources/qoder.py`（id=`qoder`，P1，国际版）**：与 `qoder_cn` 同构，根 `~/.qoder`。
  **必须是独立 source id** —— 官方明写两者定价不同、积分不等价、不可互通。
- **`codebuddy`（P1，前置取证）**：与 WorkBuddy 同积分池，官方 `/cost` 就输出 token 四档。
  **开工前先确认 `~/.codebuddy` 存在及 transcript 是否含逐请求 usage**（research §6.7 待实测 #5）。
- **明确不做适配器**：`qoder_ide`（本地无流水，只作为 D4 的系数来源）、`trae_cn`（整库加密，
  只作为 D4 的系数来源）。

### D6 前端口径（`frontend/src/`）

- Overview 新增「积分消耗」卡片区：实扣 / 原价 / 折扣差额 / 标价值（三笔各自成列，**不做合计条**）。
- 任何图表遇到 `tokens_reported=false` 的来源：**画「未提供」标记，禁止画 0**（画 0 等于宣称无消耗）。
- Models / Trends / Projects 表加积分列；来源筛选器不变。
- Pricing 页新增积分单价录入区（两段键 `source|basis`，与渠道三元组分块显示，避免误以为是模型单价）。
- 设置页新增「抓取计价系数」按钮与快照展示（含抓取时间与来源路径 + 非官方口径标注）。
- 别名与格式：积分显示统一 2 位小数、`null` 显示「未上报」，`0` 显示 `0.00`（二者不可混同）。

## API Contract 变更

- `GET /api/overview` / `GET /api/models` / `GET /api/trends/daily` / `GET /api/projects`：行级新增 `credits`、
  `original_credits`、`tokens_reported`、`credits_reported`；`overview` 新增 `credit_total`、
  `credit_original_total`、`discount_credits`、`credit_value_cny`、`credit_reporting_sources`、
  `token_reporting_sources`。
  **全部字段带默认值，旧客户端读法不破坏**（新增只增不改名，沿用 v2 的兼容策略）。
- `GET /api/meta`：新增 `credit_reporting_sources`、`token_reporting_sources`、`unpriced_credits`。
- 新端点 `GET /api/credit-rates`：无快照文件时返回空态（不是 500，不是 503）。
- 新端点 `POST /api/credit-rates/capture`：从本机客户端缓存抓一次快照并落 `credit_rates.json`；
  来源不存在/被加密/字段漂移一律降级为**明确错误响应**（沿用 `SourceError` 语义，不得拖垮服务）。
  它**不破坏「端点只读」惯例**：仓库已有 `PUT /api/pricing` 与 `POST /api/pricing/extract` 先例 ——
  写用户本机的 gitignored 文件、调用用户自配的外部模型，本来就是既有形状；新端点同样只写那一个本地文件。
- `PUT /api/pricing`：接受 `version: 2` 与 `credit_prices`，校验 `basis ∈ {plan, pack}`、
  `cny_per_credit > 0`；非法积分单价表**降级为空表而非报错**（价格表打字错误不能弄坏应用，沿用现规矩）。
- 七个既有 GET 端点的 `?source=` 过滤参数不变，直接吃新 source id。

## Testing Decisions

- 延续「唯一 seam = HTTP API + fixture」，每个新源一个 `tests/test_<source>.py`：
  - `test_workbuddy.py`：fixture **照实测嵌套形状**（三套方言并存、`prompt_cache_hit_tokens ⊂ prompt_tokens`、
    `reasoning ⊂ completion`、`rawUsage.credit` 逐条带值、DB 与 JSONL 双写同一会话）→
    断言拆档后恒等式成立、断言**双写不重复计量**、断言 `credit_json` 与 `Σ rawUsage.credit` 不等时告警且取后者。
  - `test_qoder_cn.py`：fixture 含 token 全 0 + credits 非零、`<synthetic>`、`billable=false`、
    `entrypoint="ide"` 的记录 → 断言 `tokens_reported=False`、断言 0 token 不进任何乘价、
    断言只收 cli 记录、断言 credits 缺失保持 `null` 不被当 0。
  - `test_credits.py`（成本层）：三笔账两两不相加的回归；`credit_prices` 缺一即 `credit_value_cny=null`；
    `discount_credits` 为派生值且不写回；`version 1` 老价格表仍可加载。
  - `test_multi_credits.py`：混合「报积分/不报积分」「报 token/不报 token」四象限来源时，
    合计与 `*_reporting_sources` 标注正确。
  - `test_rates.py`：只喂白名单字段；断言 `secret://` 键、`ak/base_url/auth_type` 路径**永不出现在快照里**；
    系数落在文档区间外时产出告警项。
- 读取真实本机库的用例一律打 `@pytest.mark.live`（默认排除），保证离线套件永远可跑。
- 既有测试（v1 的 25 个 + v2/v2.4 全部）语义零改动通过；fixture 注入时把其余来源路径指向不存在位置。

## Out of Scope

- **官方远程用量/账单 API 适配器。** Qoder 企业 `usage-events`、Trae 企业 OpenAPI 都要凭证与管理员身份，
  破「数据源只读本地库」红线且目标人群几乎不重叠。替代方案是**离线对账导入**（复用 T08 对账肌肉 +
  T13 截图取数），另立票。
- **由积分反推 token，或任何形式的 token 估算进成本。** 官方声明无固定换算 + 本机标定失败，双重否证。
  tokenizer 估算只允许落在显式标 `estimate` 的独立字段，**禁止进 `total_tokens` 与 `estimated_cost`**。
- **内置 ¥/credit 单价或默认汇率。** 与「不硬编码单价、不内置默认汇率」同源。
- Qoder IDE / Trae 的**消耗**适配器（前者本地无流水，后者整库加密）。
- WorkBuddy `credit_json` hex 键语义、`~/.workbuddy/app` LevelDB 是否含积分事件流 —— 取证未完，不阻塞本规格。
- 前端按来源堆叠图表与来源级下钻页（v2 已延后，v3 继续延后）。
- Claude Code / Codex / Kimi / Kiro / Cursor 接入（v2 后续票另议；本机实测显示 Claude 四档互斥、
  Codex 无 `total` 字段需自行相加、Kimi/Kiro/Cursor 本机无数据）。

## Acceptance Criteria

1. 打开 Qoder 来源：积分数字有值，token 处显示「未提供」而**不是 0**；关掉来源筛选改看合并视图时，
   token 合计旁明确列出「未计入 token 口径的来源」。
2. 打开 WorkBuddy 来源：token 四档相加等于其上游 `total_tokens`；同一会话不因 DB + JSONL 双写被计两次
   （用真实本机库跑 live 冒烟核对）。
3. `pricing.json` 只填 `workbuddy|plan` 不填 `workbuddy|pack` 时，两者分别显示、`credit_value_cny` 按所选
   basis 计算且**不因缺另一条而变 null**；但缺某上报来源的**任一** basis 单价时该 basis 的总额为 null。
4. 三个总额（按量消耗 / 买断支出 / 积分标价值）在界面上任何位置都**没有相加关系**，自动化测试覆盖
   「同时存在三笔的来源」用例。
5. 抓一次系数：快照文件里有 `captured_at` 与 `provenance`，界面显示非官方口径标注与抓取日期，
   且 `cmodel 3.2×` 这类越界值触发可见告警；快照内**不含任何 `secret://` 或凭据字段**（测试断言）。
6. `make check`（lint + test + build-web）通过；离线套件在无 WorkBuddy/Qoder 安装的机器上全绿。

## Further Notes / 风险

- **30 天清理**（Qoder 官方默认开）会截断历史：趋势图的历史边界由厂商决定，不由我们决定。
  需要产品层决策：是否定期抓快照入库（会引入 zlens 自有存储，破「无自有库」现状），或仅在健康度提示。
- **双写重复计量**是 WorkBuddy 的头号风险（DB 与 JSONL 各有一份消耗），必须锁死单一事实源。
- **系数漂移**：本机 `efficient` 的 `priceFactor` 已从 0.5 降到 0.3；文档与客户端不一致已是事实。
  快照必须带时间，界面必须可比对。
- **积分小数位与截断方式未知**（面板可能四舍五入到 1 位）→ 影响折扣差额的分辨率，不影响合计正确性。
- WorkBuddy 是**办公 agent**：`title` 语义（`ai-title` 记录）与代码项目不同，Projects 视图的排序/文案
  可能读起来怪；但 `cwd`/`project_id` 维度实测存在，视图结构本身适用。
- 任何 `pricing.json` 与 `credit_rates.json` 的变化都是**用户本机文件**，不参与 git；
  本规格不引入任何需要网络出口的默认行为。
- 文档同步（硬规矩 1）：合并实现票时必须同步 `AGENTS.md` 的 Repository Map（`sources/` 新增两个适配器、
  `core/rates.py`）、数据源列表（v2 spec 的「后续票」清单需注明 Qoder/Trae/WorkBuddy 的改判结论）、
  架构红线（新增「三笔账两两不相加」与「凭据字段禁读」两条）、README 与 CHANGELOG。

## 票切分（写入 `docs/plans/tickets/` 时沿用本规格编号）

| 票 | 主题 | Blocked by |
|---|---|---|
| T15 | 契约扩展：`credits`/`tokens_reported` 与三笔账合计语义（含 `test_credits.py`） | 无 |
| T16 | WorkBuddy 适配器（单一事实源 + 嵌套拆档 + live 冒烟） | T15 |
| T17 | Qoder CN 适配器（积分账 + token 未上报 + 30 天清理告警） | T15 |
| T18 | 系数快照抓取器（`core/rates.py` + `/api/credit-rates` + 白名单与告警测试） | 无 |
| T19 | 积分单价录入（`pricing.json` v2 + Pricing 页录入区 + 校验降级） | T15 |
| T20 | 前端积分视图（Overview 卡片区 / 表格列 / 未提供标记） | T15, T16, T17, T19 |
| T21 | Qoder 国际版 + CodeBuddy 接入（前置取证 `~/.codebuddy`） | T17, T18 |
