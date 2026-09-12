# 模型真实性检测调研：API 提供方量化掺水 / 降配掺水 / 调包 / 动态降智的检测信号、现有工作与 zlens 落地

> 放置理由：zlens 若新增「模型真实性检测」能力，需要先回答三个问题：检测信号在学术/工业界有哪些
> 被验证过、哪些只在社区流传；这些信号里有多少能从 ZCode 本地库**已有字段**里算出来；
> 主动探针要动哪些架构红线。本报告是纯调研取证，不构成行为契约；开票时请引用本文的小节号。
>
> - 信息获取日期：**2026-09-03**。学术 arXiv 页与官方文档当日取回；GitHub star/活跃度为当日 API 快照。
> - 取证渠道：arXiv 摘要页（当日取回）、官方文档、GitHub 仓库（README/API）、官方工程博客全文；
>   中文社区帖一律标注二手。**本机 `~/.zcode/cli/db/db.sqlite` 由委托方于 2026-09-03 做过两次只读探针**
>   （82 MB SQLite、`model_usage` 3,847→3,853 行逐请求遥测、无 logprobs 落盘；信号可用性实测见 §6.5），
>   本文以「本机实测」标注之。
> - 标注约定：**官方原文写了** = 引到一手页面；**一手实测** = 论文/仓库/文档当日直接取回；
>   **未证实** = 只有第三方转述或只有推理；**推断** = 由一手事实导出的工程结论；
>   **二手** = 社区帖/媒体，仅作旁证。
> - **⚠ 阅读警告**：本文最重要的负结果是——**学术界目前没有可靠的黑盒检测「量化掺水」的软件方案**
>   （§4.1，Berkeley 团队因此转向 TEE 硬件方案）。zlens 若做这个功能，P0/P1 只能产出
>   「触发人工核验的相关性信号」，定罪必须靠 P2 主动探针或外部证据，见 §6.4。

---

## 一、结论先行

按作弊类型 × 证据层级的可行性评级（★=可行且信号较强，△=只能作弱证据/需大量对齐，✗=当前不可行）：

| 作弊类型 | P0 纯被动（`model_usage` 已有字段） | P1 离线文本分析（`message` 已有输出原文） | P2 主动探针 | 综合评级 |
|---|---|---|---|---|
| **量化掺水**（FP8/INT8/AWQ 伺服） | △ 速度特征被负载混杂（S2）；无 logprobs | △ 文体漂移无法区分量化 vs 换版本 | △ 长 CoT 探针有学术依据（§4.5）；logprobs 指纹被论文判负（§4.1） | **最难的**。软件黑盒无可靠方案，zlens 只能做「怀疑点」 |
| **降配掺水**（蒸馏版/小参版/旧快照） | △ 时序漂移可见但不能定因 | △→★ 文体漂移 + 自证矛盾可积累证据 | ★ 知识截止探针、行为指纹匹配是学术已验证路线 | **主动探针下可行性最高** |
| **调包**（换 tokenizer 的其他家族模型） | ★ `raw_usage_json` 方言突变、cache 命中率崩塌、provider_id 突变、错误串指纹 | ★ 自证家族矛盾（只能证伪） | ★ glitch token 探针、行为指纹（LLMmap 路线） | **被动侧即可发现大部分粗糙调包** |
| **动态降智**（时段路由弱模型/砍 thinking） | ★ reasoning_tokens 占比时序、TTFT/duration 分位数时段对比、finish_reason 分布 | △ | △ 需要时段化探针，成本高 | **被动侧最有价值，且最贴合 zlens 现有能力** |

四条决定性判断：

1. **「量化检测」是学术前沿未解问题，不是 zlens 工程力问题。** Berkeley 的审计论文实测结论：
   文本统计测试「query-intensive 且对细微替换失效」；logprobs 方法「被生产环境推理非确定性击败」
   （[arXiv 2504.04715](https://arxiv.org/abs/2504.04715)，§4.1）。他们的出路是 TEE 硬件。
   zlens 若宣传「能检测量化掺水」就是唬人。
2. **调包与降智在 zlens 有独有的一手数据优势。** `raw_usage_json`（上游 usage 原文）与
   `provider_metadata_json` 的键形方言、`cache_read_input_tokens` 的时序、`reasoning_tokens` 独立档——
   这三样是多数通用检测工具没有的逐请求落盘，构成 zlens 差异化（§6.1）。
3. **所有 P0 信号是相关性不是因果。** 延迟、缓存命中、token 构成同时受任务类型、上下文长度、
   服务端负载、用户参数影响。任何信号必须「同渠道自身时序对照 + 跨渠道同 model_id 对照 +
   样本量门槛」三重对齐后才允许显示，且文案不得写「已证实掺水」。
4. **模型自证（「我是谁」）只能证伪、不能证实。** Anthropic 官方系统提示文档一手承认 Claude 的
   身份信息完全来自 system prompt 注入（§4.3）——中转站改 system prompt 即可让任何模型自称旗舰。
   自报「我是 X」无证据价值；自报「我不是 X / 我是别的家族」才是反证。

---

## 二、威胁模型

**对手**：API 提供方 = 官方云、中转站/聚合商（shadow API，见 §5.4）、或 ZCode 自身的上游路由层。
对手能力分级（从轻到重）：

- **L1 参数级降智**：不改模型，只砍 thinking 预算/输出上限/温度/截断（最常见、最难与用户配置区分）；
- **L2 基础设施级降智**：路由到不同的伺服配置（量化副本、旧快照、不同 batch/服务器池）
  ——Anthropic 官方 postmortem 证明这类事故真实存在且可以「sticky」（§5.1）；
- **L3 模型级替换**：换成蒸馏版/小参版（同家族），行为相似度高，检测最难；
- **L4 家族级调包**：换 tokenizer 的其他家族模型（最粗糙，但社区报告并不罕见，§5.4）。

**受害者侧的观测面**（即 zlens 手里的东西）：逐请求遥测（时间/时长/token 四档/错误）、
assistant 输出全文、上游 usage 原文。**没有** logprobs、没有权重、没有服务端指标。
这决定了：zlens 的检测器本质是「**黑盒侧旁路信号 + 主动探针**」，而不是白盒验证。

**与 ZCode 场景的耦合**：`provider_id` 是不透明 UUID（本机实测），一个 `model_id`（如
`kimi-k3`、`stealth/ox-alpha`）背后可能对应多个动态路由的 provider——这既是噪声（同一渠道内
信号被稀释），也是信号源（provider 集合突变本身就是路由切换证据，§6.1 P0-6）。

---

## 三、信号盘点

逐信号给出：原理 / 信号强度 / 成本 / 误报风险 / 被动或主动 / 一手依据。
信号编号 S1–S17，zlens 字段映射统一放 §6。

### 3.1 量化掺水（FP8/INT8/AWQ/GPTQ 伺服）

- **S1 输出分布双样本检验**（被动/主动混合）：对 API 与本地参考权重（或历史基线）采同样本，
  检验输出分布是否一致。一手依据：[Model Equality Testing (arXiv 2410.20247)](https://arxiv.org/abs/2410.20247)
  ——MMD + 字符串核，每题约 10 个样本，对各类失真中位 power 77.4%；**但 Cai 等复现指出该方法
  恰恰识别不了量化**（[arXiv 2504.04715](https://arxiv.org/abs/2504.04715) 转述）。强度：△；
  误报：高（采样温度、提示模板差异即足以改变分布）。
- **S2 速度/延迟特征**（被动）：量化推理解码吞吐通常显著高于全精度，但服务端批量、负载、
  机房位置造成的波动**远大于**量化带来的差值。Artificial Analysis 官方把 output speed 与 TTFT
  作为逐端点评测指标（[methodology](https://artificialanalysis.ai/methodology)），证明该量可测；
  但它测的是端点基准均值，zlens 测的是混有任务异质性的真实流量。强度：△（只能做「比外部
  基准显著偏快/偏慢」的怀疑点）；误报：极高；成本：零（纯被动）。
- **S3 logprobs/熵分布指纹**（主动，需端点支持 logprobs）：原理是量化权重的 logit 分布有系统性
  偏移。**一手负结果**：Cai 等明确记录 logprobs 类方法「被生产环境固有的推理非确定性击败」
  （vLLM/不同 batch/温度采样的数值抖动），并在其开源仓库 [sunblaze-ucb/llm-api-audit](https://github.com/sunblaze-ucb/llm-api-audit)
  中实现了 logprobs 收集与分类器供复现。强度：✗（当前不可作强证据）。**ZCode 本地无 logprobs
  落盘（本机实测）**，此类信号只能 P2 探针采集。
- **S4 长 CoT 能力探针**（主动）：量化对推理模型的伤害集中在长思考链上，通用基准几乎无损
  ——一手依据：[Quantization Hurts Reasoning? An Empirical Study on Quantized Reasoning Models
  (arXiv 2504.04823)](https://arxiv.org/abs/2504.04823)（华为诺亚，2025-04，题名即结论）。这意味着
  「短题测不出量化、长链探针才可能测出」——设计探针时应选长链数学/多步代码题而非闲聊。
  强度：△→★（方向有学术依据，工程上需要固定题库+多次采样）；成本：每次探针真金白银；
  误报：中（模型版本更新本身会改变长链表现）。
- **S5 提供方量化元数据对账**（半被动，拉元数据不发模型请求）：OpenRouter 官方要求 provider
  录入量化档位，枚举 `int4/int8/fp4/mxfp4/nvfp4/fp6/fp8/mxfp8/fp16/bf16/fp32`
  （[for-providers 文档](https://openrouter.ai/docs/guides/community/for-providers)，官方原文写了），
  且请求参数 `provider: {"quantizations": [...]}` 允许用户按精度筛 provider
  （[provider-selection 文档](https://openrouter.ai/docs/guides/routing/provider-selection)，官方原文写了）。
  zlens 可拉取该元数据与本地实测信号对账：「该渠道自报 FP8」本身即用户知情权信息。
  注意 DeepSeek R1 官方权重本就是 FP8 训练——「FP8」不等于「掺水」，必须以官方发布精度为基线
  （社区广泛讨论，二手；R1 FP8 为官方发布事实）。

### 3.2 降配掺水（蒸馏版/小参数版/旧快照）

- **S6 知识截止日期探针**（主动）：用固定时间敏感题集探测模型知识边界；若「旗舰」答不出
  明显晚于旧快照截止期的事件，或答出的截止期与声称版本不符，即降配证据。一手依据：
  [FreshLLMs/FreshQA (arXiv 2310.03214)](https://arxiv.org/abs/2310.03214)——600 题、区分
  never/slow/fast-changing 知识、含人工基线（Findings of ACL 2024；代码
  [freshllms/freshqa](https://github.com/freshllms/freshqa)）。LLMmap 的探针集也含
  「your data cutoff date?」类自报题（§4.2，但自报可被 system prompt 伪造，行为题不可）。
  强度：★（区分快照代际）；误报：中（RAG/联网注入会污染，agent 场景要禁工具再测）；成本：低。
- **S7 行为指纹匹配**（主动）：固定探针题集 → 响应编码 → 与参考模板做分类/距离匹配。
  一手依据：LLMmap（§4.2）对 42 个 LLM 版本 >95% 识别率（论文摘要/USENIX 页，一手实测），
  开源 v0.2 预置 52 个 LLM 的行为模板、支持 OpenAI/Anthropic 后端、提供
  `add_new_template.py` 免重训扩模板（README，一手实测）。强度：★（对 L3/L4 都有效，
  对 L3 需要同家族细粒度模板）；误报：中（system prompt 与 agent 框架包装会改变行为，
  需裸端点或固定包装）；成本：每次几十条请求。
- **S8 能力悬崖探针**（主动）：小参版在长上下文/多步工具调用/指令保持上有悬崖式衰减；
  用固定极限题（超长检索、多约束指令）对比声称版本的能力上界。强度：△（需校准基线）；
  误报：高（与 S4 同源的版本漂移问题）。
- **S9 时序漂移监控**（被动+可选主动）：对同一 model_key 用固定探针/固定统计量做纵向对比。
  方法论一手依据：[How is ChatGPT's behavior changing over time? (arXiv 2307.09009)](https://arxiv.org/abs/2307.09009)
  （Chen, Zaharia, Zou，2023-07，v2 2023-10）：GPT-4 在素数判断任务上 97.6%→2.4% 的漂移案例，
  核心方法论是「**固定探针集 + 跨时间窗口复测**」。注意该文的方法学后被社区与后续研究质疑
  （CoT/格式混杂导致的部分结论不可复现，未证实——但「持续纵向监控」这一方法论本身已被广泛接受）。
  强度：★（发现变化），✗（归因——变化可能是官方更新而非掺水）；这正是「检测器只能报警不能定罪」
  的学理依据。

### 3.3 调包（换 tokenizer 的其他家族模型）

- **S10 自证话术挖掘**（被动，P1）：从输出原文中挖掘「我是 GPT-4/Claude/Gemini…」话术。
  **只能证伪**：Anthropic 官方系统提示文档原文「Claude can provide the information here if asked,
  **but does not know any other details about Claude models**」
  （[Claude Sonnet 4 system prompt](https://platform.claude.com/docs/release-notes/system-prompts/claude-sonnet-4)，
  官方原文写了）——模型身份来自注入，中转站改注入即可伪造「我是旗舰」。因此：
  自称与声称不符（如声称 Claude 却自称 GPT）→ 强反证；自称一致 → 零证据价值。
  强度：★（证伪方向）；误报：低（训练数据残留模仿会造成「口癖自称」，需按家族×版本统计而非单条）。
- **S11 tokenizer 指纹**（被动 P0 + 主动 P2 两用）：
  - 被动面：换 tokenizer **必然毁掉前缀缓存命中**。同一渠道 `cache_read_input_tokens` 占比
    突然崩塌且持续走低，在排除上游缓存策略变更后，是强信号（本机有逐请求 cache_read，§6.1）。
    另一面：`input_tokens` 对同一文本的计量漂移（用户可用本地 tokenizer 估算下界对照）。
  - 主动面：glitch token 探针。SolidGoldMagikarp 类 anomalous token 是**词表级**现象——
    只存在于特定 tokenizer 词表，跨家族互异。一手依据：Rumbelow & Watkins 的
    [SolidGoldMagikarp 系列](https://www.lesswrong.com/posts/aPeJE8bSo6rAFoLqg/solidgoldmagikarp-plus-prompt-generation)
    （LessWrong，2023-01，原始发现）；学术化：
    [Glitch Tokens in Large Language Models (arXiv 2404.09894)](https://arxiv.org/abs/2404.09894)
    （系统实证研究）、[Fishing for Magikarp (arXiv 2405.05417)](https://arxiv.org/abs/2405.05417)
    （Cohere；用 embedding norm 自动检测 under-trained token）、
    [GlitchMiner (arXiv 2410.15052)](https://arxiv.org/abs/2410.15052)（v5 2025-11；venue 未核实）。
    对特定词表 glitch token 的响应模式（重复/乱码/正常）可区分家族。强度：★（家族级）；
    误报：中（需预校准每家族响应）；成本：低（一次数条请求）。
- **S12 错误串指纹**（被动，P0）：上游 SDK/网关的错误字符串、error code 命名习惯是渠道身份的
  「指纹」。ZCode 落盘 `error_type/error_code/error_message`（本机实测），同一 `model_id` 下
  错误词汇表突变提示上游被换。zlens 的 `HealthReport` 已做错误分组（`src/zlens/sources/models.py`），
  此信号是其时序化扩展。强度：△→★；误报：低-中（版本升级也会换错误文案）。
- **S13 上游 JSON 方言指纹**（被动，P0）：`raw_usage_json` 是上游 usage 原文（本机实测）。
  不同上游家族的 usage 字段形状互异（OpenAI 形状 `prompt_tokens_details`、Anthropic 形状
  `cache_creation_input_tokens`、火山/DeepSeek 形状 `prompt_cache_hit_tokens` 等——这一方言库
  在 zlens 已有实证先例，见
  [credit-opaque-agents-usage.md §6.3](./credit-opaque-agents-usage.md) 对 WorkBuddy 三方言的实测）。
  同一 `model_key` 的键形集合突变 = 上游家族变更的强证据。这是 **zlens 相对通用检测工具的
  独有信号**（多数工具拿不到逐请求原始 usage）。强度：★（对 L4 调包极强）；误报：低。

### 3.4 动态降智（高峰路由弱模型 / 砍 thinking 预算）

- **S14 时段化性能分位对比**（被动，P0）：TTFT 与 duration 按小时/时段分桶做 p50/p90/p99，
  同渠道纵向（高峰 vs 平峰）+ 跨渠道同 model_id 横向。Anthropic 官方 postmortem 证明
  「sticky 路由把短上下文请求路由到错误服务器池」真实存在且可持续数周（§5.1），时段化对比
  是发现此类问题的第一手段。强度：★（发现异常），✗（区分「官方高峰降速」与「恶意降智」）；
  误报：高（负载、网络、上下文长度混杂，必须用 §6.4 的对齐纪律）。
- **S15 reasoning_tokens 占比时序**（被动，P0）：thinking 预算被砍最直接的落盘痕迹是
  `reasoning_tokens/output_tokens` 占比与绝对值的分布突变（ZCode 把 reasoning 作为 output 的
  子档独立落盘，本机实测 + `sources/models.py` 契约）。对比维度：同 model_key 时序、
  跨渠道、用户自设思考强度参数混杂。强度：★；误报：中（任务类型与用户参数必须进对照组）。
- **S16 截断/重试/错误率时段分布**（被动，P0）：`finish_reason`、`retry_count`、
  `status/error_type` 的时段分布突变。强度：△；误报：中。
- **S17 缓存命中率突变**（被动，P0）：与 S11 被动面共享——上游路由切换/缓存策略变化都会
  打在 `cache_read` 占比上；zlens 已有 `cache_hit_rate` 概念（`ModelUsageSummary`），需要的是
  「按渠道×时段」的时序化。强度：△→★；误报：中。

---

## 四、论文与工具综述

### 4.1 模型替换审计（主动，学术主线）

| 工作 | 方法 | 对量化的结论 | 一手链接 |
|---|---|---|---|
| **Model Equality Testing**（Gao, Liang, Guestrin；v1 2024-10-26，ICLR 2025） | 双样本检验：API 输出 vs 本地参考权重输出，MMD + 字符串核，每题约 10 样本，中位 power 77.4%；对 2024 年夏 4 个 Llama 的 31 个商用端点实测，**11/31 端点分布与 Meta 参考权重不一致** | 据后续论文转述，该方法**识别不了量化**（未证实，转引自 2504.04715） | [arXiv 2410.20247](https://arxiv.org/abs/2410.20247) |
| **Are You Getting What You Pay For?**（Cai, Shi, Zhao, Song，UC Berkeley；v1 2025-04-07，v2 2025-09-29） | 系统化审计模型替换：文本统计测试、logprobs 分类器、身份提示、MMLU 蒙特卡洛基准 | **文本测试 query-intensive 且对细微替换失效；logprobs 被生产推理非确定性击败** → 转向 TEE 硬件验证 | [arXiv 2504.04715](https://arxiv.org/abs/2504.04715)、[代码 sunblaze-ucb/llm-api-audit](https://github.com/sunblaze-ucb/llm-api-audit)（13 stars，2025-04-10 最后推送，MIT，一手实测） |
| **RUT**（Zhu 等；v1 2025-06-08，v5 2026-04-09） | Rank-based uniformity test：本地部署真模型为参考，纯黑盒秩检验；宣称 query-efficient、stealthy、抗「检测到审计就换路由/混流」的对手 | 四场景实测：量化、有害微调、越狱、完全替换；自称在受限 query 预算下优于先前方法 | [arXiv 2506.06975](https://arxiv.org/abs/2506.06975) |
| **Real Money, Fake Models**（Zhang 等；v1 2026-03-02） | 首个 shadow API（中转）系统性审计：17 个 shadow API 出现在 187 篇学术论文中；三维审计（utility/safety/identity） | 最流行 shadow API 达 5,966 引用、58,639 GitHub stars（截至 2025-12-06）；与官方 API 效用分歧最高 47.21%；**身份指纹检验 45.83% 不通过**；发现直接与间接欺骗证据 | [arXiv 2603.01919](https://arxiv.org/abs/2603.01919) |

对 zlens 的含义：这一整条学术线都要求**本地部署真模型作参考**（MET/RUT）或**海量查询预算**（Cai），
对 local-first 单用户工具不现实；可直接借用的只有「固定探针 + 统计检验」的**思路**与
llm-api-audit 仓库的**探针实现**（MIT）。

### 4.2 模型指纹工具（主动）

- **LLMmap**（Pasquini, Kornaropoulos, Ateniese；[arXiv 2407.15847](https://arxiv.org/abs/2407.15847)，
  **USENIX Security 2025**）：主动指纹——向目标发少量精心设计的查询（自报题、安全题、
  true/false 题、畸形 token 题），把响应序列编码后与模板匹配；论文口径 42 个 LLM 版本 >95% 准确。
  GitHub [pasquini-dario/LLMmap](https://github.com/pasquini-dario/LLMmap)：
  **442 stars / 49 forks，最后推送 2025-07-24，MIT，v0.2 已用 PyTorch 重写**，
  预置 52 个 LLM 的 open-set 行为模板，支持 HuggingFace/OpenAI/Anthropic 后端，
  `add_new_template.py` 免重训加模板（以上 GitHub API 与 README 均为一手实测）。
  **zlens 可复用点**：探针题库结构、open-set 判定（新模型≠已知任一模板 → 直接提示「不像声称的模型」）、
  MIT 许可允许集成。**注意**：其模板按「裸模型+轻包装」训练，agent 场景的重 system prompt 需自建模板。

### 4.3 自证可靠性与知识截止探针

- 自证不可靠的一手锚点：Anthropic 官方系统提示文档（§3.3 S10 引文）。
  此外的社区总结（如 16x Engineer「The Identity Crisis」、Mammouth「Why Models Tell the Wrong Version」）
  均为**二手**，与官方文档一致但不要当一手引用。
- 知识截止探针基准：FreshQA（§3.2 S6，一手）。设计要点：禁用工具/RAG 后测；
  区分 never/slow/fast-changing；时效题库要定期滚动更新（题库本身会过时）。

### 4.4 glitch token 与 tokenizer 指纹

一手链条齐整：SolidGoldMagikarp 原始发现（LessWrong 2023-01 系列，§3.3 S11 链接）→
系统性实证（arXiv 2404.09894）→ 自动检测方法（arXiv 2405.05417，embedding norm）→
优化式挖掘（GlitchMiner，[代码](https://github.com/wooozihui/GlitchMiner)）。
**跨家族区分 tokenizer 的推论成立**（词表互异 → glitch token 响应互异），
但「用 glitch token 响应直接做渠道级分类器」**未检索到一手论文**——列为推断 + 待实测（§8）。

### 4.5 量化的伤害面（评估「掺水有多疼」）

- [Quantization Hurts Reasoning? (arXiv 2504.04823)](https://arxiv.org/abs/2504.04823)（华为诺亚，
  2025-04）：量化对（长链）推理能力的伤害显著大于通用基准所示——这是 S4 长 CoT 探针的设计依据。
- 「logprobs 熵分布区分量化权重」：**未检索到正向结果的一手论文**；唯一相关一手证据是
  Cai 等的**负结果**（生产非确定性击败 logprobs 方法）。任何「熵指纹」方案在 zlens 里只能标未证实。

### 4.6 评测/元数据平台（外部对照源）

- **OpenRouter**：provider 量化枚举与 `provider.quantizations` 请求参数（官方原文，§3.1 S5）；
  文档另记载默认在 top provider 间负载均衡、按 provider 记录吞吐/延迟分位数（滚动 5 分钟窗）——
  zlens 的本地分位数可与外部对照（[provider-selection](https://openrouter.ai/docs/guides/routing/provider-selection)）。
  社区对「低价档是否偷偷重量化」有持续质疑（r/LocalLLaMA 帖，**二手**）。
- **Artificial Analysis**：官方方法论页明确评测对象是「模型与 **inference API endpoints**」，指标含
  intelligence（v4.1.1 聚合九项评测）、output speed、TTFT（[methodology](https://artificialanalysis.ai/methodology)、
  [intelligence-benchmarking](https://artificialanalysis.ai/methodology/intelligence-benchmarking)，官方原文写了）。
  它是 zlens「同模型跨渠道对照基线」的现成外部锚。社区对其聚合口径有批评（**二手**）。
- **LMArena**：众包对战排行；方法论上「人类偏好」与「真实能力」可分离（style control）。
  相关性见 §5.3 Llama 4 事件。

---

## 五、已知事件（作弊/乌龙实证库）

按证据等级排列；「错标」类事件证明 **L2（基础设施级替换）不是阴谋论，是官方承认过的事故形态**。

1. **Anthropic「A postmortem of three recent issues」**（2025-09 发布，官方原文，本报告当日取回全文，
   [链接](https://www.anthropic.com/engineering/a-postmortem-of-three-recent-issues)）：
   三个 bug 造成 2025-08-05 至 09-04 间间歇性质量劣化——
   (a) 上下文窗口**路由 bug**：为 1M 上下文准备的服务器池错误承接短上下文请求，路由是
   **sticky** 的；最差时段（08-31）影响 16% 的 Sonnet 4 请求，期间约 **30% 的 Claude Code 用户**
   至少一条消息被错误路由；(b) Markdown 重排版服务导致的输出损坏 bug；(c) XLA:TPU 编译器
   误编译（丢失一个 bit）影响 Haiku 3.5 与 Sonnet 4 质量。
   **对 zlens 的直接价值**：这是「被动信号时段对比能发现真问题」的官方背书（S14/S16），
   也是「sticky 路由」这一混杂因素的一手出处。
   另有更早的 Claude Code 质量报告官方回应「An update on recent Claude Code quality reports」
   （[april-23-postmortem](https://www.anthropic.com/engineering/april-23-postmortem)，标题级证据，本轮未取回全文）。
2. **「2024-08 Anthropic Sonnet/Haiku 错标事件」——未检索到一手来源（如实标注）。**
   多轮定向检索（含 "mislabeled"、"served by haiku"、status page 存档）均未找到 2024-08
   Sonnet/Haiku 错标的一手承认。可证实的近亲是：上条 2025-09 postmortem（官方）；以及持续的
   社区报告——r/ClaudeCode「Sonnet-4.5 being routed to Haiku — Massive intelligence nerf」、
   GitHub anthropics/claude-code #35269「Opus & Sonnet silently blocked — only Haiku works，
   静默回退无报错」（均**二手/未证实**）。**不要在 zlens 文档里引用未经证实的 2024-08 事件。**
3. **Llama 4 Maverick 榜单特调事件**（2025-04）：Meta 官方博客宣称 Llama 4 Maverick「experimental
   chat version」在 LMArena 拿 ELO 1417（[Meta blog](https://ai.meta.com/blog/llama-4-multimodal-intelligence/)，
   官方原文写了），而该 `Llama-4-Maverick-03-26-Experimental` 变体**从未公开发布**，发布权重表现
   明显更差（Simon Willison 2025-04-05 [notes](https://simonwillison.net/2025/Apr/5/llama-4-notes/)；
   LMArena 后续禁止未公开特调变体参榜——此点为二手转述）。性质：**「评测版≠交付版」**，
   与渠道无关但直接支撑「必须对实际伺服模型做指纹」的动机。
4. **Shadow API 掺水实证**：学术一手是 §4.1 的 Real Money, Fake Models（45.83% 指纹检验不通过）；
   中文社区二手佐证：linux.do 多帖报告第三方 Claude 转发「掺水/降智，特别是 2api 类型渠道」
   （[帖 1](https://linux.do/t/topic/1280918)）、社区自制检测器
   （[GPT 掺水/降智检测器](https://linux.do/t/topic/2704354)、
   [hlwy-ai-checker 教程](https://linux.do/t/topic/2730026)，思路为「官方/高价渠道标定 → 对比中转」）、
   知乎对中转站行业乱象的汇总（降智/跑路/自签证书风险，[问题页](https://www.zhihu.com/question/2037561149353375367)，**二手**）。
5. **GPT-4「lazy/降智」争论**（2023-12 → 2024-02）：社区大规模报告 laziness → OpenAI 公开回应
   并在 gpt-4-0125-preview 更新说明中写明「更彻底地完成任务、旨在减少 laziness 情况」
   （二手报道：[CIO Dive](https://www.ciodive.com/news/openai-laziness-gpt4-turbo-model-updates/705664/)、
   [Mashable](https://mashable.com/article/chatgpt-laziness-openai-upgrade-gpt-4-turbo)；
   社区原帖：[community.openai.com](https://community.openai.com/t/gpt4-turbo-more-stupid-lazy-its-not-a-gpt4/608008)）；
   独立量化复测：Aider 的代码编辑基准显示 0125 仍比此前版本更 lazy
   （[aider.chat/docs/benchmarks-0125.html](https://aider.chat/docs/benchmarks-0125.html)，
   一手实测数据）。
   **对 zlens 的含义**：「变笨」的公说公有理持续数年无定论，主观质量判断不可行（§7），
   但**逐请求客观量**（输出截断率、编辑完成度类代理）是社区实际在用的弱证据形态。

---

## 六、zlens 落地可行性

### 6.0 总原则

- P0/P1 是「**怀疑点生成器**」：只报「该渠道在某指标上相对自身历史/相对外部基线出现 N-sigma 级偏移」，
  永不输出「已证实作弊」。定罪级证据只有 P2 探针 + 人审。
- 检测结果按 **`model_key` 三元组**（`source|provider_id|model_id`，`src/zlens/sources/models.py`）
  组织——渠道是真实性的最小归因单位，与计价/展示完全同构。
- 所有统计必须带样本量（先例：`LatencyStats.sample_count`）与时间窗；样本不足时整块不显示
  （与既有「缺数不显示、不给 0」的口径一致）。

### 6.1 P0 纯被动（零新采集，纯 SQL 聚合 `model_usage`/`session`）

| # | 信号（对应 §3） | 依据的 model_usage 字段 | 最小实现 | 误报对齐要求 |
|---|---|---|---|---|
| P0-1 | 渠道速度画像与时段对比（S2/S14） | `started_at/first_token_at/completed_at`、`duration_ms`、`time_to_first_token_ms`、`output_tokens`（tokens/s 派生） | 现有 `PerformanceReport`（duration/ttft 分位数）扩展为「按 model_key × 小时桶」；跨渠道同 model_id 并排 | 必须按 `agent/mode/variant/status` 分层或过滤；上下文长度（input 总量）作为协变量；样本量门槛 |
| P0-2 | thinking 预算时序（S15） | `reasoning_tokens`（output 子档）、`output_tokens` | `reasoning/output` 占比与绝对值的逐日分布（p50/p90）；同渠道自身历史对照 | 排除用户参数变更（agent/mode 变化点标注）；任务混杂按 `agent` 分层 |
| P0-3 | 缓存命中率时序（S11 被动面/S17） | `cache_read_input_tokens`、`cache_creation_input_tokens`、`input_tokens` | 现有 `cache_hit_rate` 概念时序化：按 model_key 逐日/逐时段；告警条件 = 显著低于该渠道自身基线 | 上游缓存策略/客户端版本变化（`session` 表有版本字段）；ZCode 已知「缓存前缀算进 input」的口径在适配器已归一 |
| P0-4 | 上游 usage 方言指纹（S13） | `raw_usage_json`、`provider_metadata_json` | 提取键路径集合（top-level + 一层嵌套），按 model_key 建立键形集合；集合突变告警 | 首次见到的新模型无基线 → 只报警不判性质 |
| P0-5 | 错误串指纹（S12） | `error_type/error_code/error_message` | 现有 `HealthReport` 错误分组时序化：词汇表(去重 error_code/type 集合)按周 diff | 上游 SDK 版本升级也会换文案 → 与 P0-4 联合判读 |
| P0-6 | provider 集合稳定性（L2 路由切换） | `provider_id`（不透明 UUID）、`model_id` | 同 model_id 的 provider_id 集合按周 diff；新 UUID 出现即事件 | 路由本来就可能动态扩容 → 是「事件」不是「罪证」 |
| P0-7 | 截断/重试时段分布（S16） | `finish_reason`、`retry_count`、`status` | 按 model_key × 时段桶的分布 diff | 与 P0-1 联合判读 |

样本量现实约束（本机实测，§6.5）：全库 3,853 行，头部渠道单渠道可算速度样本 100–604 行——
分位数与 diff 的最小样本门槛建议 ≥30/桶、报警需连续 ≥2 桶，避免把噪声当信号。

### 6.2 P1 离线文本分析（输出原文已在 `message`/`part` 的 JSON data，零出网）

- **P1-1 自证话术挖掘（S10）**：正则/轻量分类抽取 assistant 全文中的自我身份陈述；
  聚合到 model_key × 家族，输出「该渠道自称分布」。只有「自称家族 ≠ 声称家族」的累积证据
  才展示（单条忽略；官方文档已证明注入即可伪造一致的自称）。
- **P1-2 文体/代码风格漂移（S7 的被动版、S9）**：对同 model_key 的输出做窗口化风格统计
  （n-gram、句长分布、Markdown 结构习惯、代码注释风格；学术可行性旁证：
  [LLM Generated Code Stylometry for Authorship Attribution](https://www.alphaxiv.org/abs/2506.17323)
  多分类模型归因 95.40%、[Stylometry recognizes human and LLM-generated texts](https://arxiv.org/html/2507.00838v2)）。
  输出「风格分布漂移分」——**不能归因**（官方模型自身更新同样漂移），只作 P0-1/2 告警的旁证。
- **隐私卖点**：P1 全程本地计算，数据不出本机——与 zlens local-first 定位天然契合。
- 成本：本地 CPU；实现上不需要新采集管道，只需要把 `message`/`part` 的 JSON data 解析进分析层。

### 6.3 P2 主动探针（新出网模块、花真金白银、必须 opt-in）

**架构建议（对照 AGENTS.md 红线逐条）**：

1. **探针不是数据源**。「新增数据源 = 新增 `sources/<name>.py` 适配器」针对的是「读取某 agent
   本地用量账本」；探针不产生用量账本，不应塞进 `sources/` 协议（避免污染 MultiSource 与
   九端点契约）。建议独立模块 `src/zlens/probe/`（随票落地，不提前占位），由 API 层以与
   sources 同构的方式暴露结果。分层单向 `api → probe`、`api → sources` 保持。
2. **探针凭据打破「零凭证」**：探针需要向渠道发请求（用户自备 API key/中转地址）。
   这是有意的、显式的架构例外：必须 opt-in、密钥只存本地（沿用「不碰 secret://」的纪律，
   zlens 自己的凭据文件放用户配置目录并 gitignore）、探针失败一律降级为明确错误响应不得拖垮
   服务（与「查询失败必须降级」同款处理）。
3. **探针结果存储**：落 zlens 自己的本地存储（如 `~/.zlens/` 下），**绝不写回
   `~/.zcode/cli/db/db.sqlite`**（数据源只读红线）。
4. **探针花费与钱的关系**：探针请求的真实花费是「检测成本」，**既不进 `estimated_cost`
   （那是用量成本的估算口径），也不是 `buyout_amount`（那是买断付款）**——第三类独立账。
   展示口径：探针花费 = Σ(探针请求四档 token × `pricing.json` 对应渠道单价)，
   **渠道未计价时显示「无法估算探针花费」而不是猜**（复用价格表不算硬编码；不写回 pricing.json）。
   建议文案固定为「检测支出，独立于用量与买断两笔钱」。
5. **探针结果按 model_key 组织**，与 P0/P1 信号同一归因单位，前端可把「被动怀疑点」与
   「主动探针结论」放在同一渠道详情页的两栏（证据链分级展示）。

**探针题库建议（全部有 §4 一手依据）**：

| 探针 | 依据 | 请求成本 | 备注 |
|---|---|---|---|
| 知识截止题集（FreshQA 改造，禁工具） | arXiv 2310.03214 | 低（数条） | 题库版本化 + 定期滚动 |
| 行为指纹模板（LLMmap 52 模板起步，agent 包装下自建） | arXiv 2407.15847 / GitHub v0.2 | 中（几十条） | open-set 判定直接给出「不像任何已知声称模型」 |
| glitch token 响应集（跨家族校准） | arXiv 2404.09894 / 2405.05417 | 低 | 每家族需预校准；未有一手分类器论文，标推断 |
| 长 CoT 探针（长链数学/多步代码，多次采样） | arXiv 2504.04823 | 高（长输出=真钱） | 对量化掺水的主要抓手 |
| logprobs 端点能力检查 | sunblaze-ucb/llm-api-audit | 低 | 有 logprobs 才跑 S3，且结果标注「非确定性限制」 |
| 时段化复测（把上述探针按周/按时段重跑） | arXiv 2307.09009 方法论 | 持续成本 | 针对动态降智；与 P0 时段告警联动触发 |

### 6.4 展示纪律（防唬人）

- 证据分级标签：「被动统计异常（相关性）」「文本旁证」「主动探针结论」三级，UI 上不可混排；
- 每个告警必须可下钻到原始请求（request 级明细），让用户自己看证据；
- 与渠道价格表联动：告警渠道旁标注「未计价/已计价」，避免「便宜=掺水」的误导暗示；
- **禁止**把 P0 告警自动写成「该渠道为假」；禁止用主观质量评分做任何量化输出（§7）。

### 6.5 本机实测快照（2026-09-03，两次只读探针，探针脚本按仓库约定置于 scratch/）

| 实测项 | 结果 | 对应信号的含义 |
|---|---|---|
| 渠道分布 | 14 个 `(provider_id, model_id)` 组合；同模型多渠道真实存在——`glm-5.3-flash` ×2 渠道、`kimi-k3` ×3 provider、`GLM-5.3-Flash` builtin 渠道 739 条 | P0 的「跨渠道同 model_id 对照」有真实样本，不是空想 |
| 速度指纹 | `duration_ms` 100% 填充；`time_to_first_token_ms`/`first_token_at` 2,307 行；可算输出速度 2,291 行，头部渠道 100–604 行/渠道 | P0-1 单渠道已普遍越过 ≥30/桶 门槛 |
| reasoning 档 | `reasoning_tokens > 0` 共 1,322 行 | P0-2 占比时序可行 |
| 缓存档 | `cache_read_input_tokens > 0` 共 3,663 行（95%） | P0-3 基线充足 |
| `raw_usage_json` 方言 | 恰两种键形：2,934 行 `{cacheReadTokens, inputTokens, outputTokens, reasoningTokens, totalTokens}`；797 行 `{cacheReadTokens, cacheWriteTokens, inputTokens, outputTokens, totalTokens}` | **P0-4 可行且方言内聚**——键形集合突变告警有干净基线 |
| `provider_metadata_json` | 3,722/3,853 非空壳：泄漏上游原始形状，如 `{"anthropic":{"usage":{…,"service_tier":"standard"}}}`、`{"rawFinishReason":"tool_calls"}` | P0-4 的第二个证据面：上游 API 家族与 service_tier 直接落盘 |
| 错误串 | 跨渠道词汇差异显著：`Rate limit exceeded: free-models-per-day-stealth.`（OpenRouter 特征限流键名）、`MidStreamFallbackError: …OpenAIException`、`System is too busy now. Please try again later.` | P0-5 可行，存量样本即指纹 |
| 文本语料 | text part 2,753 条；`model_change` 事件 67 条 | P1-1/P1-2 语料充足 |

结论：P0-1/2/3/4/5 与 P1 在本机真实数据上全部有足量样本；§8 剩余待实测只剩时序形态类
（第 2/4/5 条，需要分析层而非新采集）与需要花钱的 P2 项（第 6/7 条）。

---

## 七、不可行 / 强烈误报信号清单（明确不做）

| 信号 | 为什么不可行 | 依据 |
|---|---|---|
| 主观「回答质量/变笨」评分 | 社区争论 2023-12 起数年无定论；2307.09009 的部分结论被质疑为评测伪影；zlens 无金标准 | §4.1/§5.5 |
| 单条回答的模型身份自报（正向） | system prompt 注入即可完全伪造 | Anthropic 官方系统提示文档（§4.3） |
| logprobs/熵分布指纹作为强证据 | 生产推理非确定性击败该方法（一手负结果）；ZCode 亦无 logprobs 落盘 | arXiv 2504.04715（§4.1） |
| 用延迟绝对值定罪量化/降智 | 负载/网络/位置/批处理波动 ≫ 量化差值 | §3.1 S2 论证；AA 官方口径证明该量需受控评测 |
| 公开 benchmark 分数直接判渠道真假 | 榜单分数≠交付版本（Llama 4 特调事件）；评测污染与版本混淆 | §5.3 |
| 拿单次 glitch token 响应下结论 | 需按家族×渠道预校准，单样本无统计力 | §3.3 S11 |
| 把 cache 命中下降单独当调包证据 | 上游缓存策略/客户端版本/提示结构变化同样致命；只可与 P0-4/5/6 联合判读 | §6.1 对齐要求 |
| 输出 token 速度跨渠道直接横比 | 不同渠道计费口径、agent 包装、流式实现不同；只能同渠道自身时序 + 受控探针 | §6.1 对齐要求 |

---

## 八、待实测清单（本机，全部为「未证实/推断」）

1. **已实测（2026-09-03，§6.5）**：`raw_usage_json` 恰两种键形方言（2,934 / 797 行，内聚可作基线）；
   `provider_metadata_json` 3,722/3,853 行有实质内容（Anthropic usage 形状、`rawFinishReason`）。
   P0-4 可行性确认。
2. `cache_read` 占比的历史时序中是否已存在可观察的断崖（P0-3 的先导验证）；与 `session` 版本字段
   的变更点对齐后还有多少残留信号。
3. **已实测（2026-09-03，§6.5）**：跨渠道错误词汇表差异显著（OpenRouter 特征限流键名
   `free-models-per-day-stealth` 等），P0-5 可行性确认；「上游 SDK 版本升级换文案」的
   误报对齐仍需时序验证。
4. `duration_ms/output_tokens` 派生 tokens/s 的分布形态（是否双峰——若是，先找混杂因子再谈检测）。
5. P1-1 自证话术在本库出现频率（agent 场景 assistant 很少自然自报身份；若频率≈0，该信号只剩探针形态）。
6. glitch token 探针在主流家族上的响应校准集（需要花真钱跑 P2，属用户 opt-in 后的实验）。
7. 「Log Probability Tracking of LLM APIs」（检索结果中出现的一篇 ICLR 论文，本轮未核实原文）
   ——若后续要支持 logprobs 探针，先核这篇再定方案。

---

## 九、参考文献汇总

**学术论文（arXiv 摘要页均为 2026-09-03 当日取回）**
- [2407.15847] LLMmap: Fingerprinting For Large Language Models — Pasquini et al., USENIX Security 2025
- [2410.20247] Model Equality Testing: Which Model Is This API Serving? — Gao, Liang, Guestrin, ICLR 2025
- [2504.04715] Are You Getting What You Pay For? Auditing Model Substitution in LLM APIs — Cai et al., UC Berkeley
- [2506.06975] Auditing Black-Box LLM APIs with a Rank-Based Uniformity Test — Zhu et al.
- [2603.01919] Real Money, Fake Models: Deceptive Model Claims in Shadow APIs — Zhang et al., 2026-03
- [2307.09009] How is ChatGPT's behavior changing over time? — Chen, Zaharia, Zou
- [2310.03214] FreshLLMs: Refreshing Large Language Models with Search Engine Augmentation — Findings of ACL 2024
- [2404.09894] Glitch Tokens in Large Language Models — Yi Liu et al.
- [2405.05417] Fishing for Magikarp: Automatically Detecting Under-trained Tokens — Land & Bartolo (Cohere)
- [2410.15052] GlitchMiner: Mining Glitch Tokens via Gradient-based Discrete Optimization（v5 2025-11；venue 未核实）
- [2504.04823] Quantization Hurts Reasoning? An Empirical Study on Quantized Reasoning Models — 华为诺亚
- [2506.17323] LLM Generated Code Stylometry for Authorship Attribution（模型归因 95.40% 多分类）
- [2507.00838] Stylometry recognizes human and LLM-generated texts in short samples

**官方文档 / 官方博客（一手）**
- [OpenRouter for-providers（量化枚举）](https://openrouter.ai/docs/guides/community/for-providers) /
  [provider-selection（quantizations 参数、负载均衡、5 分钟分位）](https://openrouter.ai/docs/guides/routing/provider-selection)
- [Artificial Analysis methodology](https://artificialanalysis.ai/methodology) /
  [intelligence-benchmarking](https://artificialanalysis.ai/methodology/intelligence-benchmarking) /
  [Intelligence Index v4.1.1](https://artificialanalysis.ai/evaluations/artificial-analysis-intelligence-index)
- [Anthropic: A postmortem of three recent issues](https://www.anthropic.com/engineering/a-postmortem-of-three-recent-issues)（2025-09，全文当日取回）/
  [april-23-postmortem](https://www.anthropic.com/engineering/april-23-postmortem)（标题级）
- [Claude Sonnet 4 系统提示（自证不可靠的一手依据）](https://platform.claude.com/docs/release-notes/system-prompts/claude-sonnet-4)
- [Meta: The Llama 4 herd](https://ai.meta.com/blog/llama-4-multimodal-intelligence/)（ELO 1417 experimental 版声明）

**GitHub 仓库（star/活跃度为 2026-09-03 GitHub API 快照）**
- [pasquini-dario/LLMmap](https://github.com/pasquini-dario/LLMmap) — 442 stars / 49 forks，最后推送 2025-07-24，MIT，v0.2（PyTorch 重写，52 LLM 模板）
- [sunblaze-ucb/llm-api-audit](https://github.com/sunblaze-ucb/llm-api-audit) — 13 stars，最后推送 2025-04-10，MIT
- [freshllms/freshqa](https://github.com/freshllms/freshqa) /
  [wooozihui/GlitchMiner](https://github.com/wooozihui/GlitchMiner)（star 数未取，活跃度未核）

**社区/二手（仅旁证，正文已逐条标注）**
- LessWrong SolidGoldMagikarp 系列（原始发现，2023-01）：
  [I](https://www.lesswrong.com/posts/aPeJE8bSo6rAFoLqg/solidgoldmagikarp-plus-prompt-generation) /
  [II](https://www.lesswrong.com/posts/Ya9LzwEbfaAMY8ABo/solidgoldmagikarp-ii-technical-details-and-more-recent) /
  [III](https://www.lesswrong.com/posts/8viQEp8KBg2QSW4Yc/solidgoldmagikarp-iii-glitch-token-archaeology)
- Simon Willison：[Llama 4 notes](https://simonwillison.net/2025/Apr/5/llama-4-notes/) /
  [Anthropic postmortem 评述](https://simonwillison.net/2025/Sep/17/anthropic-postmortem/)
- Aider 基准（gpt-4-0125 laziness 量化复测）：[benchmarks-0125](https://aider.chat/docs/benchmarks-0125.html)
- GPT-4 lazy 媒体报道：[CIO Dive](https://www.ciodive.com/news/openai-laziness-gpt4-turbo-model-updates/705664/) /
  [Mashable](https://mashable.com/article/chatgpt-laziness-openai-upgrade-gpt-4-turbo)；
  社区帖：[community.openai.com](https://community.openai.com/t/gpt4-turbo-more-stupid-lazy-its-not-a-gpt4/608008)
- 中文社区（二手）：linux.do
  [第三方 Claude 转发降智](https://linux.do/t/topic/1280918) /
  [GPT 掺水检测器](https://linux.do/t/topic/2704354) /
  [hlwy-ai-checker 教程](https://linux.do/t/topic/2730026) /
  [中转站搅局学术圈](https://linux.do/t/topic/1705364)；
  知乎 [AI 中转站乱象](https://www.zhihu.com/question/2037561149353375367)
- Reddit（二手）：[r/ClaudeCode Sonnet 被路由到 Haiku 报告](https://www.reddit.com/r/ClaudeCode/comments/1o93bcd/sonnet45_being_routed_to_haiku_massive/)；
  GitHub [anthics/claude-code #35269 静默 Haiku 回退](https://github.com/anthropics/claude-code/issues/35269)
- zlens 内部一手：本仓库
  [credit-opaque-agents-usage.md §6.3](./credit-opaque-agents-usage.md)（上游 usage 三方言实证）、
  `src/zlens/sources/models.py`（token 四档契约、cache_hit_rate、LatencyStats/HealthReport 先例）
