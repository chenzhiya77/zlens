# 积分类 Agent 用量可观测性调研：Qoder / Qoder CN / Trae / WorkBuddy

> 放置理由：`docs/` 下只有 `specs/`（需求契约）与 `plans/tickets/`（实施票），没有专门放调研的目录；
> v2 spec 里已经出现「数据源实测结论」这类取证段落，说明一手取证目前塞在规格里。本报告是纯取证、
> 不构成行为契约，故新建 `docs/research/` 存放，供后续开票时引用。

- 信息获取日期：**2026-08-28**。所有结论只代表当日公开可取到的口径；这四款产品的计费与倍率都在高频改动。
- 取证渠道：官方文档站、官方定价页、官方论坛的官方帖、厂商云文档。**本机数据未做任何取证**（本会话权限不覆盖工作区之外），凡需本机确认的点全部进「待实测清单」。
- 标注约定：**官方原文写了** = 引到一手页面；**未证实** = 只有第三方文章或只有我推理；**推断** = 由一手事实导出的工程结论。
- **⚠ 阅读顺序警告**：§一~§四 建立在公开文档之上，其中三处推断已被 §六 的本机实测**推翻**
  （Qoder 落盘 token 恒为 0、WorkBuddy 本地反而有完整 token+积分、Trae 客户端缓存含逐场景消耗倍率）。
  做任何工程决策请直接引用 **§6.6 修订后的可行性分级**，不要引用 §四 的原表。

---

## 一、结论先行

| | 积分↔token 换算标准 | 官方标价（钱↔积分） | 本次请求消耗明细可查？ | 本机落盘有 token？ | zlens 可行性 |
|---|---|---|---|---|---|
| **Qoder 国际版**<br/>qoder.com | **未公布**。只有「按模型和 Token 总量计算」+ 中位数估算表 | ✅ 加量包 **$20 / 1,500 Credits**；Pro $20/月含 2,000 | 部分：IDE 右下角 Credits 按钮、官网 Settings > Usage；Credits 日志**仅记录获取**，无导出、个人无 API | **未证实**。CLI 会话 JSONL 路径已官方文档化，但字段未公开枚举 | **值得接**（CLI 优先） |
| **Qoder CN**<br/>qoder.com.cn · 本机 `~/.qoder-cn` | **未公布**，但**公布了相对倍率表**（0.1×–1.6×）+ 参考任务消耗量，且官方明写「该值不作为实际抵扣依据」 | ✅ 官网套餐/资源包页有标价 | 同国际版；CLI `/usage` 面板字段官方已枚举，**不含 token、不含逐请求明细** | **CLI 侧最可能为真**：官方 SDK 文档同时透出 Token 与 Credits；桌面 IDE 侧无任何一手说明 | **值得接**（本机用户实际用的就是这个） |
| **Trae**<br/>国内版 trae.cn / 国际版 trae.ai | 国内版 **完全未公布**（连相对倍率表都没有）；国际版是**按 token 折成美元**（Dollar Usage），性质不同 | 国内版 ✅ 加量包 **50 元 / 1000 积分**；国际版套餐直接标 `$5/$20/$90/$400 Basic Usage` | 国内版个人：只有「用量管理」面板，粒度官方未定义；**企业版**有会话级 **Token 消耗 + 金额**明细 | **一手来源缺失**。第三方实测：VS Code fork 的 `state.vscdb` 里有会话文本，**无 token、无模型名、无扣费事件**（未证实） | **需先实测**；企业版走「导入口径」而不是实时适配器 |
| **WorkBuddy**<br/>腾讯（与 CodeBuddy 共享积分） | **未公布**。官方只写「与模型 Token 定价和任务复杂度两个因素有关」 | ✅ 个人加量包 **50 元 / 1,000 Credits**；企业加量包 100 元/2,000 … 9,200 元/200,000 | 只说「登录官网个人主页 → 用量管理板块」可查看积分使用历史与当前用量；**未提 token、未提导出、未提 API** | **零一手来源**。桌面办公 agent，连项目/cwd 维度都不适用 | 桌面端**建议不做**；改接 **CodeBuddy Code CLI**（`/cost` 官方就输出 token 四档） |

三条决定性的判断：

1. **「不公布换算标准」是官方自己承认的事实，不是我们没找到。** Qoder SDK 文档原文：
   「Token 字段（例如 `input_tokens`、`output_tokens`）与 Credits **没有固定换算关系**」
   （[docs.qoder.cn/cli/sdk/cost-usage](https://docs.qoder.cn/cli/sdk/cost-usage.md)）。
   这就把 zlens 的路线钉死了：**不能把积分折算成 token，只能反过来——本地量出 token，另起一栏显示积分。**
2. **缺口在 token 层，不在钱层。** 四款产品全都公布了「积分的人民币/美元标价」（加量包单价、套餐含积分量），
   所以「这段时间用掉多少人民币」其实是**可严格计算的**，完全不需要官方系数。真正拿不到的是物理量（token）
   和跨 agent 可比性。这直接影响 zlens 的价值主张排序，见第三节路径 E。
3. **Trae 是四者里本机可观测性最差的一个**，Qoder 是**唯一一个官方就给出逐模型倍率表和参考任务消耗量的**，
   所以反向标定在 Qoder 上的先验最好。

---

## 二、逐产品详述

### 2.1 Qoder 国际版（qoder.com / docs.qoder.com）

**换算标准。** [Credits 文档](https://docs.qoder.com/zh/Credits)（页脚版权为 `© 2026 BRIGHT ZENITH PRIVATE LIMITED`）
定义 Credits 为「AI 模型的资源配额，用于衡量 AI 执行任务时消耗的计算资源」，并说明「Credits 按模型和 Token 总量计算」，
但**没有给出任何 `1 credit = N token` 的公式，也没有逐模型系数表**。它给的是**按操作类型 × 上下文窗口的中位数估算表**：

| 操作 | 50K 上下文 | 200K 上下文 |
|---|---|---|
| Editor – Ask | ~3 Credits/请求 | ~4 |
| Editor – Agent | ~7 | ~12 |
| Quest – Agent | / | ~50 |
| Quest – Experts | / | ~75 |
| Knowledge – Repo Wiki | / | ~50/仓库 |

官方限定语是「**统计估算，实际扣减以实时用量为准**」，并说明费率会随新功能调整。
其他官方规则：**模型调用失败不扣减 Credits，仅成功才计费**；额度耗尽后仍保留每日限次的基础模型调用；
扣减优先级为「先到期先扣，同期先 Plan 后 Add-on」。

**标价（官方原文）。** [定价页](https://docs.qoder.com/zh/account/pricing)：体验版免费；Pro `20 USD/月 / 每月 2,000 Credits`；
Pro+ `60 USD/月 / 6,000`；Ultra `200 USD/月 / 20,000`；Pro 试用 2 周含 300 Credits；
资源包 `20 美元 / 1,500 Credits`。→ 等效单价：**套餐内 ~$0.010/credit，加量包 ~$0.0133/credit**。

**消耗明细可查性。** IDE 右下角 Credits 用量按钮（预览）；官网 头像 → Settings > Usage（Plan Credits / Add-on Credits / 到期时间）；
**Credits 日志官方明写「仅展示获取记录」**（获取原因、数量、生效与到期日期），不是消耗明细。
该页**未提及任何导出功能或用量 API**。

**本机数据。** CLI 会话存储是官方文档化的：`~/.qoder/projects/<项目路径经过处理后的名称>/<session-id>.jsonl`
与同名目录下的 `state.json`，配置根 `~/.qoder`，可用 `QODER_CONFIG_DIR` 覆盖；
提供 `--list-sessions` / `-r <id>` / `--fork-session` / `/export`（导出到文件或剪贴板）
（[docs.qoder.com/zh/cli/sessions](https://docs.qoder.com/zh/cli/sessions)）。
官方只描述 JSONL 内容为「保存对话记录……你的输入、Qoder 的回复和工具调用」，**未枚举字段**
→ JSONL 里到底有没有 token/credits，属**未证实**，必须本机复核。

**最重要的突破口（一手）：** [CLI SDK 成本和用量](https://docs.qoder.com/zh/cli/sdk/cost-usage) 表明 SDK 层
**同时**透出 Credits 与 Token：
- 单次模型请求：assistant 消息上的 `message.message.usage` → `credits`、`original_credits`（折扣**前**的值）、`billable`（该请求是否计入用量）；
- 会话累计：Result 消息的 `total_credits` 与 `modelUsage` / `model_usage`（按模型累计 credits）；
- 账号额度：`getUsageInfo()` → `userQuota{total,used,remaining,percentage,unit}`、`addOnQuota`（其 `detailUrl` 官方说明「指向用量明细页」）、`orgResourcePackage`、`totalUsagePercentage`、`isQuotaExceeded`、`session.total_credits`、`session.model_usage`；
- 上下文占用：`getContextUsage()` → `contextWindow.usedPercentage`、`skills.items[].percentageOfContext`，且官方明说「各分类值是**本地估算**」。

两条对 zlens 极有价值的官方告诫：**「Token 反映模型输入、输出和缓存的文本量，不能直接换算成 Credits」**、
**「不要从 Result 消息的 `usage` 字段读取 Credits——`result.usage` 用于 Token 等用量数据」**。
→ **官方口径明确：token 与 credits 是两个独立量，二者都要采，不许互推。** 这正好对上 zlens 的
「两笔钱不合并」与「禁止在下游公式里猜」两条红线。另外「Credits 字段为可选字段，缺失不要当 0」也与
zlens 现有的 `estimated_cost: float | None` 语义一致。

### 2.2 Qoder CN（qoder.com.cn / docs.qoder.cn，本机 `~/.qoder-cn`）

**先分清三条产品线，否则会接错账号。** 官方 [Credits 文档](https://help.aliyun.com/zh/lingma/credits)（页首已挂迁移公告，指向 `docs.qoder.cn`）明写：
- **Qoder CN 与 Qoder 定价不同，两者的 Credits 不等价，不可互通使用** → zlens 必须当成**两个 source id**，
  且 `model_key` 三元组天然区分（`qoder|…` vs `qoder_cn|…`），符合「禁止跨渠道合并取价」。
- 自 **2026-06-20** 起，订阅 **Qoder CN（全家桶）** 后，个人版 Credits 可在 Desktop / JetBrains 插件 / QoderWork CN /
  **Qoder CN CLI** / Mobile 之间共享消耗；企业 Teams/Enterprise VPC 当前只在 QoderWork CN 与 Qoder CLI CN 间共享。
- **原灵码订单（`commodityCode` 含 `lingma_` 前缀）的 Credits 与全家桶订单不互通**；原灵码在
  `qoder.console.aliyun.com`，全家桶在 `qoder.com.cn`，两边用量互不可见。

**换算标准：仍未公布，但给了本调研中最接近系数的东西。** [模型选择器文档](https://docs.qoder.cn/qoder/model-selector.md)
公布了两张表（均为官方原文）：

档位倍率 + **单示例任务消耗**：Auto ~1.0× / 10 Credits、极致 Ultimate ~1.6× / 20、Performance ~1.1× / 11、
Efficient ~0.3× / 3、Lite 免费 / 0。
逐模型倍率：Qwen3.8-Max 0.5×、Qwen3.8-Flash 0.1×、Qwen3.7-Max 0.5×、Qwen3.7-Plus 0.1×、
DeepSeek-V4-Pro 0.8×、DeepSeek-V4-Flash 0.3×、GLM-5.3 0.6×、Kimi-K3 0.8×、Kimi-K2.7-Code 0.3×、MiniMax-M3 0.2×。

同时官方挂了三层免责：**「由于不同任务和代码库的差异，实际消耗倍率可能存在一定差异」**、
「表中倍率为**综合预估值**……**最终以实际消耗为准**」、
模型选择器上的倍率「为 Qoder 产品团队基于特定任务场景**模拟测算**结果，**该值不作为实际抵扣依据**」；
并提示 DeepSeek-V4-Pro/Flash **采用峰谷计价**。
FAQ 里唯一关于公式的表述是：「Credit 用量取决于请求使用的 Token、所选档位或模型、**参数配置**和工具调用」——
而参数面板暴露 200K/400K/1M 上下文与 low…max 思考强度，说明系数还随参数变化，静态表必然不完备。
→ **官方事实：存在与 token 单调相关的倍率体系；未公布实际抵扣公式。推断：以「示例任务 = 10 Credits × 倍率」
为锚 + 本地实测 token，可做一条量纲对齐线，但它仍是推断。**

**消耗明细。** 与国际版同构：Desktop/JetBrains 右下角 Credits 按钮；QoderWork CN 右上角按钮；
**Qoder CN CLI 执行斜杠命令 `/usage`**；仅 QoderWork CN 与 Qoder CN CLI 支持在官网 Settings > Usage 查看。
`/usage` 面板字段官方已完整枚举（[查看用量与额度](https://docs.qoder.cn/cli/usage.md)）：
套餐、套餐到期时间、Plan Credits Used、Add-on Credits Used、组织资源包、**API 总时长**、墙钟总时长、**代码改动总行数**；
并且官方说明这些数据的来源不同——「套餐、到期时间和各类额度**来自你的账号配额**；API 时长、墙钟时长和代码改动
**来自当前会话的统计**」→ **积分数值是服务端下发的，不是本地算出来的**（重要：本地没有任何可信的积分账本）。

**本机数据（一手，路径明确）。** [配置项/环境变量/文件路径全表](https://docs.qoder.cn/cli/settings-reference.md)：
- 用户级配置 `~/.qoder-cn/settings.json`；项目级 `<项目>/.qoder/settings.json`；本地级 `<项目>/.qoder/settings.local.json`；
- 环境变量 `QODERCN_CONFIG_DIR`（默认 **`~/.qoder-cn`**，与本机观察一致）、`QODERCN_PERSONAL_ACCESS_TOKEN`、
  `QODERCN_MODEL`、`QODERCN_WORKING_DIR`、`QODERCN_SESSION_ID`；
- [管理会话](https://docs.qoder.cn/cli/sessions.md)：`~/.qoder-cn/projects/<项目路径经过处理后的名称>/<session-id>.jsonl`
  与 `<session-id>/state.json`，命令 `qodercn --list-sessions`、`-r`、`--fork-session`、`/export`。

**⚠ 两个必须写进适配器的硬约束（一手）：**
1. **会话自动清理默认开启**：`general.sessionRetention.enabled = true`，`maxAge = "30d"`，`minRetention = "1d"`
   → 本地账本最长只有 30 天，历史回溯窗口天然受限；zlens 要么定期抓取入库，要么在健康度里明确提示用户关自动清理。
2. **本地采集有合规开关**：`privacy.usageStatisticsEnabled = true`（共享使用数据，关闭进入隐私模式）、
   `aiCodeStatistics.enabled = true`（记录并上报 AI 生成代码统计）。zlens 只读本地文件，不改这两个开关，
   但报告/界面里不能暗示「本地统计 = 上报统计」。

**另一条几乎确定的技术路线（推断，需验证）：** `settings-reference` 里的键名——`ui.showMemoryUsage`、
`ui.terminalBackgroundPollingInterval`、`ui.renderProcess`、`tools.disableLLMCorrection`、`mcp.lazyLoad`、
`security.toolSandboxing`、`security.disableYoloMode`、`security.blockGitExtensions`、
`security.environmentVariableRedaction.enabled`、`advanced.autoConfigureMemory`、`advanced.excludedEnvVars`、
`context.fileName`、`output.format` ——与开源 **Gemini CLI** 的设置模式高度同名；且 SDK 消息流形状
（`type: assistant|result`、`usage`、`modelUsage`、`total_cost_*`）是 Claude Code/Gemini CLI 那一族。
→ **推断**：`.jsonl` 大概率按消息记录了 `usage`/`usageMetadata`（含 token）。这决定了 Qoder CLI 适配器是否可行，
**是本次调研最该先做的一个本机验证**（见待实测 #1）。

**桌面 IDE 侧（信息很少）。** 唯一一手路径来自[问题排查指南](https://docs.qoder.cn/support/troubleshooting-guide.md)：
原灵码血统的进程与目录是 `C:\Users\<用户名>\.lingma\bin\2.X.X\x86_64_windows\lingma.exe`、
`~/.lingma`（macOS/Linux），应用日志为 `lingma.log`，诊断脚本输出 `Qoder CN_Log_日期时间.txt`。
这些是排障日志，**没有用量数据**。→ Qoder CN **IDE** 的会话/token 落盘位置**零一手来源，需实测**。

**企业用量 API（个人版不可用）。** [用量 API](https://docs.qoder.cn/enterprise/usage-api.md)：
`GET https://api.qoder.com.cn/v1/organizations/{org_id}/members/{member_id}/usage-events`，
Bearer `<api_key>`，参数 `startDate/endDate`（**跨度不得超过 7 天**）、`sources`、`operations`、`modelTiers`、
`maxResults`（默认 20，**最大 100**）、`nextToken`。
响应 `usages[]` 字段：`eventId`、`timestamp`（Unix 毫秒）、`userId`、`memberId`、`userEmail`、
`source`（如 `IDE`/`Web`）、`operation`（如 `Agent`/`Inline Chat`）、`modelTier`（`Standard`/`Premium`）、
`credits`、`cost`。
→ **两个要点**：(a) **没有 token 字段**，只有积分与 `modelTier` 档位；(b) 示例里 `credits: 1.5` 与 `cost: 1.5`
数值相同，说明这个 `cost` **就是积分，不是货币**——zlens 的中性字段名 `estimated_cost` 若直接吃这个 `cost`，
会犯「把积分当人民币」的错。且需 org_id + member_id + 组织 API Key，**只对 Teams/Enterprise 管理员成立**。

### 2.3 Trae（字节跳动）：国内版与国际版是两种性质

**国内版 trae.cn（docs.trae.cn）= 积分制，且比 Qoder 更不透明。**

- 2026-08-12 公告「[重磅更新：以积分为核心的计费模式正式上线](https://docs.trae.cn/ide_coming-soon)」+
  [套餐与计费](https://docs.trae.cn/ide_plans-and-billing)：Lite ¥49（连续包月 ¥45）/ 2000 **Work 专属积分**、
  Pro ¥99/¥89 / 4000 通用积分、Pro+ ¥239/¥219 / 12000、Ultra ¥699/¥629 / 40000，均 31 个自然日有效；
  加量包「**每 1000 积分 50 元**」（1,000–20,000 档）；「Seed-2.1-Turbo 和 Seed-Code 模型计费享 **2.5 折**」；
  「**仅调用 TRAE 内置模型时会消耗积分；调用自定义模型不会消耗积分**」；
  升档抵扣公式「可抵扣金额 = 未使用会员积分 ÷ 原套餐发放的会员积分总量 × 原订单实付金额」；
  退款仅限「请求因敏感词拦截、底层模型报错或死循环而失败」。
- **没有 1 积分 = N token 的任何官方数字。** 而且连 Qoder 那种相对倍率表都没有：
  [内置模型页](https://docs.trae.cn/ide_models.md) 只列了 Seed-2.1-Pro/Turbo、Seed-Code、GLM-5.3/5.3-Flash/5.2、
  DeepSeek-V4-Pro/Flash、Kimi-K3/K2.7-Code、MiniMax-M3、Qwen3.8-Max/3.7-Plus 等模型与「哪些档位可用」，
  **不含任何倍率/单价**。
- 个人明细：[订阅管理](https://docs.trae.cn/ide_subscription-management.md) 只说「在页面右上角点击头像 → **用量管理**」，
  「你可以查看总可用积分、积分类型和用量明细」——**粒度、字段、是否含 token、能否导出，官方全部未写**。
  争议本身已成公开话题，如官方论坛帖标题「[Trae 积分的争议，不是贵不贵，是 Token 消耗说不清](https://forum.trae.cn/t/topic/173627)」
  （仅取到标题，正文未取，**内容细节未证实**）。
- **企业版反而是全的。** [查看个人用量](https://docs.trae.cn/enterprise_check-individual-usage) 显示：TRAE 企业版控制台 →
  账户中心 → 个人用量 → 用量管理，可「按模型查看用量」，「基础用量/超额用量」报告「**消耗的金额**」，企业模型报告「**Token 用量**」，
  还有「你可以查看 CUE 功能消耗的 **Token 总量**」；按会话维度明细字段为
  「时间、客户端、模型名称、Session ID、消耗来源、**Token 消耗**、**模型调用次数**」，并且官方注明
  「**如需查看详细输入和输出数据，需导出数据**」。企业侧另有一整套 OpenAPI（按成员/按会话 ID 查用量明细、
  模型维度用量、AI 使用数据统计、OpenAPI 调用日志）。
  → **推断**：Trae 的 token 级数据在服务端是存在的，个人版只是不给你看；企业版可行但需要凭证与管理员身份。
- 云端数据归属：[云端智能体数据存储声明](https://docs.trae.cn/work_data-storage-policy-for-remote-agents.md) 只说
  「系统需在云端对部分数据进行必要的存储与处理」，含「你与云端智能体的对话内容」「会话中的上下文信息」
  「**会话维度的必要指标信息**（用于保障系统运行和会话状态维护）」；**未提 token、未提用户可否取回**。
  「会话维度的必要指标信息」这句是**唯一暗示服务端有指标数据**的官方措辞，但不足以支撑任何结论。
- 本机日志（一手，只到这一步）：[获取日志或 SessionID](https://docs.trae.cn/ide_get-logs-or-session-id.md)
  让你用命令面板执行「开发人员：Open All Logs Folder」拿到日志目录，以及双击左上角头像复制 SessionID。
  **官方从未说明会话/用量数据落在本地哪个文件。**

**国际版 trae.ai = 按 token 折美元（Dollar Usage），性质完全不同，透明度明显更高。**
[trae.ai/pricing](https://www.trae.ai/pricing) 官方原文：「**All AI requests are billed based on the number of
tokens processed.**」「**TRAE converts the token cost into Dollar Usage**, which is deducted from your monthly balance.」
套餐是「Monthly Basic Usage」= $5(Lite)/$20(Pro)/$90(Pro+)/$400(Ultra)，Free 为 "Limited usage" + 5000/月（补全类），
「Additional usage is billed based on actual token consumption」，「Bonus Usage」为赠送；
同时明说「Different models have different computational costs」并**不提供**逐模型单价表，只把细则推给文档。
官方论坛 FAQ「[TRAE 国际版计费方案升级常见问题](https://forum.trae.cn/t/topic/207)」（2026-02-25）补充：
旧套餐换算「**6 Requests = $1 Dollar Usage**」，IDE 内「可查看 Usage 余额和有效期」，
网页活动记录「包含对话使用的**模型**、发生的**时间**、消耗的 **Dollar Usage 额度**」。
→ 国际版的计量单位**本身就是货币**，所以 zlens 若要接国际版 Trae，几乎不需要换算，缺的只是 token 明细；
**这一条国内版完全不具备，两个版本必须分开设计，不要做成一个 source。**

**本机数据可观测性（第三方实测，未证实）。**
[掘金《Codex CLI / Trae / Copilot 数据源接入》](https://juejin.cn/post/7640357289836281882)（作者自述为其
ChatCrystal 导入实现的整理）给出 Trae 为 **SQLite `state.vscdb`**，位于
Windows `%APPDATA%\Trae\User\workspaceStorage\`、macOS `~/Library/Application Support/Trae/User/workspaceStorage/`、
Linux `~/.config/Trae/User/workspaceStorage/`，所有会话塞在 ItemTable 的键
**`memento/icube-ai-agent-storage`**，JSON 含 `sessionId`/`createdAt`/`updatedAt` 和
`messages[]`（`role`/`content`/`turnIndex`），Agent 回复嵌在 `agentTaskContent` 下；
该文同时明确：Trae 的记录里**没有 token 计数、没有模型名、没有扣费事件**。
另一篇[《AI 编程助手数据提取终极指南》](https://www.xugj520.cn/archives/ai-coding-assistant-data-extraction-2.html)
说 Trae 数据在 `~/.trae` 与 `~/Library/Application Support/Trae`，「既有 JSONL 文件，也有 SQLite 数据库」，
可提取「聊天记录、代理数据、工具使用情况和代码差异」。
→ **两篇相互矛盾**（有无模型名/是否 JSONL/是否另有 `~/.trae`）。我**更信第一篇**：它给到了具体表名与 key 名、
形状与 VS Code fork 常识一致，属于「看过文件的人」写的；第二篇是泛化的采集方案综述，字段样例是给 Claude 的。
但这仍是**二手**，Trae 的全部本机结论都要过一遍本机才敢写适配器。

### 2.4 WorkBuddy（腾讯）

**身份判定（先解决歧义）。** WorkBuddy 是**腾讯**的产品，与腾讯云代码助手 **CodeBuddy 同一产品线、共享积分**——
官方云文档《计费概述》标题即为「WorkBuddy Enterprise 计费概述」，正文原文
「**CodeBuddy 和 WorkBuddy 同一账号积分共享，无需分别订阅**」
（[cloud.tencent.com/document/product/1831/134333](https://cloud.tencent.com.cn/document/product/1831/134333)）。
佐证：腾讯云官方文档站产品号 1831、[Tencent Cloud 产品页](https://www.tencentcloud.com/zh/products/workbuddy)、
应用宝包名 `com.tencent.workbuddy.app`、活动页「[WorkBuddy 打通腾讯生态](https://cloud.tencent.com/act/pro/workbuddy)」。
定位是**桌面端通用办公 agent**（整理文件、生成 PPT、处理 Excel/数据），不是 IDE/编码 agent
（媒体侧描述如「腾讯 WorkBuddy 领跑桌面端 AI 智能体赛道」，[新浪财经](https://finance.sina.com.cn/stock/relnews/hk/2026-08-03/doc-inikzuyf6173064.shtml)）。
**歧义处理说明**：我把「非腾讯的 WorkBuddy」也搜过一轮，中文检索命中的 WorkBuddy 全部指向腾讯；
**同时必须警告**——`https://workbuddy.homes/` 和 [`AlephAITech/WorkBuddyGuide`](https://github.com/AlephAITech/WorkBuddyGuide)
虽然自称「官方渠道」，实际页脚是 `Copyright © 2026 WorkBuddy Guide Contributors`、自我标注
「本项目是**社区维护**的 WorkBuddy 实战知识库」，**不是官方**，不可作为一手出处引用。
我没有做穷尽式的同名产品排查，故对「市面上不存在其他同名 AI 产品」不下结论，只下「**在 AI agent 语境下 WorkBuddy 唯一可信指向腾讯**」。

**换算标准：官方承认按 token，但不给任何数字。** [积分说明](https://cloud.tencent.com/document/product/1831/134339) 原文：
- 「**积分（Credits）系用于衡量 AI 任务执行过程中的资源消耗量**」「CodeBuddy 和 WorkBuddy 采用基于积分（Credits）的资源配额管理机制」「在 CodeBuddy 和 WorkBuddy 中，所有对话相关请求均需消耗积分」；
- 「**积分（Credits）的消耗量与模型 Token 定价和任务复杂度两个因素有关**」「不同模型的单位 Token 处理单价不同」「其输入和输出 Token 的处理单价更高」「**每处理相同数量 Token 消耗的积分（Credits）更多**」「简单任务（如简短问答）消耗较少」「复杂任务（如长代码分析、多轮对话、知识库检索）需更多推理计算和 Token 处理」；
- **无公式、无系数表、无 worked example**；额度数字本身也推给《计费概述》。

**标价（官方数字，可直接当量纲）。** 《计费概述》：个人版 ¥99/¥199/¥999 每月，基础积分 2,000/4,000/20,000（限时加赠后每月实得 4,000/9,000/50,000）；
连续包月 7 折（¥70/¥140/¥700）；年付 7 折与连续包年再 8 折（¥672/¥1,344/¥6,720 每年）；
个人加量包「**1,000 Credits / 50 元**，1 个月有效」；企业席位 ¥198 与 ¥316 每人每月（含 2,000 积分/人，每月刷新）；
企业加量包 2,000/100 元、5,000/245、10,000/480、50,000/2,375、200,000/9,200（6 个月）。
→ 等效单价 **¥0.046–0.05/积分**，与 Trae 国内版（¥0.05/积分）几乎一致，Qoder 国际版 $0.0133/credit ≈ ¥0.095（汇率按 7.1 估）。

**消耗明细。** 官方只写到「各个模型的用量明细查询：登录官网，单击右上角头像，进入个人主页；在用量管理板块查看当前可用/已用积分」、
「可通过官网个人主页查看积分（Credits）使用历史及当前用量」、企业「可通过企业管理后台查看企业成员积分用量明细」；
**未提 token 是否显示、未提导出、未提 API**（与 Trae 企业版形成鲜明对照）。
缺口在舆论侧也被明确记录：有第三方「[两个月记账实测，以及一个大胆推测](https://m.toutiao.com/article/7675299296568279604/)」
靠自己记流水反推扣费规则（仅标题级证据），这正是用户所说的消费者知情权空白的实证。

**编码侧的近亲，才是该接的那个。** [CodeBuddy 成本管理文档](https://www.codebuddy.ai/docs/zh/cli/costs) 官方原文：
「`/cost` 命令提供当前会话的详细 **Token 使用统计**」，示例输出
`Usage by model:` / `claude-sonnet-4: 875.5k input, 11.7k output, 714.3k cache read, 0 cache write`。
→ **这正是 zlens 的 token 四档**（cache write = `cache_creation_tokens`），且**不含积分**。
`/context` 给出 `glm-4.7 · 38.1k/200k tokens (19%)` 与分类估算。
[CLI 参考](https://www.codebuddy.ai/docs/zh/cli/cli-reference) 显示它是 Claude Code 形状：`-c/--continue`、
`-r/--resume "<session-id>"`、`-p/--print`、`--output-format text|json|stream-json`、`--include-partial-messages`、
`--max-turns`、后台任务 `codebuddy ps|logs|attach|kill`，日志目录 **`~/.codebuddy/logs/`**，
且存在 `--no-session-persistence`（反证**默认持久化 transcript**，官方文档另有「`.codebuddy` 目录结构说明」页）。
官方还提醒「后台任务会为 `--resume` 摘要之前的对话」「Prompt 预测」——「这些后台进程即使没有活跃交互也会消耗少量 Token」
→ 对反向标定是**系统性噪声源**，必须计入。

---

## 三、官方不公布换算标准时，zlens 还能怎么把用量算出来

前提共识（来自 AGENTS.md 红线，不可谈判）：归一只能发生在适配器；**禁止在下游公式里猜谁的数字含谁**；
金额只读 `pricing.json`，**禁止硬编码单价、禁止内置汇率**；`estimated_cost` 用中性名；两笔钱永不合并。
以下五条路径按「可信度」从高到低排。

### 路径 A：本地量真 token，单价由用户自填（**首选，绕开官方系数**）

适用：**Qoder CN CLI**、**CodeBuddy Code CLI**（二者都在官方层面透出了逐请求 token）。
做法：适配器只从本地记录取 `input/output/cache_creation/cache_read` + 模型名 + 时间戳 + cwd，
`model_key = "<source>|<provider>|<model>"`，金额完全走现有 `pricing.json`；**积分不参与成本公式**，
另存一列 `credits_consumed` 作为独立展示量。
误差与风险：
- **恒等式必须先验**。`models.py` 要求四档互斥且相加等于 `total`；ZCode 的教训是缓存前缀被算进 input。
  Qoder/Trae 这类国产 agent 上游多为 Anthropic/OpenAI 混合形状，**必须先拿真实库跑一遍恒等式再合并**，
  fixture 照真实形状写（嵌套就写嵌套）。
- 用户自填的单价算出的钱 **≠ 用户实付的钱**（因为有官方折扣：Qoder 的 `original_credits` vs `credits`、
  Trae 的 Seed 2.5 折与 GLM 补贴、Qwen 系列特惠、DeepSeek 峰谷计价）。所以界面上「按量消耗」与
  「积分折算等效金额」必须并列且**永不相加**。

### 路径 B：本地只有请求数 → 用官方中位数或 tokenizer 估算，且只能标注为估算

适用：**Trae**（本机大概率只有会话文本 + 时间）。
- **B1 官方中位数**：只有 Qoder 给了可用的中位数表（Ask ~3 / Agent ~7 / Quest Agent ~50 / Experts ~75 Credits，
  且区分 50K/200K 上下文）。Trae/WorkBuddy **没有对应表**，B1 对它们不可用。
- **B2 本地 tokenizer 估算**：用 tiktoken 类近似估 prompt/completion 量，作为**下界**。
  风险必须写清楚：Qwen / DeepSeek / GLM / Kimi 的中文 BPE 与 cl100k/o200k 差异显著（中文 token 数可差数十百分点），
  代码/工具结果占比越高偏差越大；上下文压缩、系统提示词、工具定义都不在你看到的消息里 →
  **估算只能落在一个显式标记为 estimate 的字段，禁止进 `estimated_cost` 的求和口径**。
  这一条与「猜市场价等于造成本」同源。

### 路径 C：反向标定 —— 把黑盒定价「测」出来（**可做，但产物不是事实**）

原理：同一时间窗内，令本地测得的各档 token 为 `in/out/cc/cr`、模型为 `m`，账号侧面板（或 `/usage`、
或企业 `usage-events` 汇总）读到的积分为 `C_m`，拟合
`C_m ≈ k_m · (in + w_out·out + w_cc·cc + w_cr·cr)`，逐模型解出 `k_m` 与各档权重。

- **需要什么数据**：(1) 逐模型分档 token（路径 A 的本地产物）；(2) **同窗口**账号侧积分总量；
  (3) 尽量对齐的时间基准（面板通常只给「已用/总量」，不给时间分桶 → 往往需要用户手工在两个时点各截一次，
  即差分法）。Qoder SDK 的 `original_credits`（折扣前）是**消除折扣噪声的关键字段**，优先用它标定。
- **精度受什么影响**：官方中位数不是逐请求值；**折扣/补贴/峰谷计价**；上下文窗口与思考强度参数（Qoder 直接暴露
  200K/400K/1M 与 low…max，二者都抬消耗）；重试与刷新会独立计费（Qoder 官方明写「反复重试会累计消耗」）；
  CodeBuddy 的后台摘要/Prompt 预测会消耗未被用户感知的 token；面板四舍五入（企业 API 示例 `credits: 1.5` 只有一位小数）；
  **本地 30 天自动清理**限制可用样本窗口；账号侧面板延迟。
  → 现实结论：**单模型样本 ≥ 数十次请求、且折扣状态恒定（同一模型、同一参数、避开促销）时，
  倍率类系数可标到 ±10–30%；一旦跨模型/跨参数，残差会吞掉精度。**
- **它属于推断，界面必须怎么标才不撒谎**：
  (1) 文案固定为「**本地标定估算，非官方口径**」，并给出拟合样本数、时间窗、残差/置信区间；样本不足时**整块不显示**（不给 0，不给 NaN）；
  (2) **禁止写回 `pricing.json` 冒充单价**，也禁止进入「任一渠道未计价则总额为 null」那条规则的计算；
     要用户**显式**把它作为「自定义价」录入才算计价——与现在「手抄美元价由用户自己换算成数字」完全同构；
  (3) 禁止把它显示成官方扣费额；官方扣费额与标定推算值必须两栏并列，让差异可见（这正是消费者知情权诉求的落点）；
  (4) Qoder 已公布 0.1×–1.6× 倍率表，**标定结果应与官方倍率表做一致性校验并在偏离时告警** —— 这是 Qoder
     比 Trae/WorkBuddy 更适合做标定的原因（有免费的先验）。

### 路径 D：走官方 HTTP 用量/账单 API（**等于破例，建议不做**）

现状：Qoder 有[企业用量 API](https://docs.qoder.cn/enterprise/usage-api.md)（org + member + API Key，≤7 天窗口，100/页，**无 token**，`cost` 实为积分）；
Trae 有企业版数据分析/用量明细 OpenAPI；WorkBuddy/CodeBuddy **未公布任何个人用量 API**；
四者的**个人版都没有**可编程用量查询。

代价（必须单独说明，因为它动的是架构红线「数据源只读本地库」）：
1. 需要**凭证生命周期**（PAT / API Key / OAuth）、密钥存储、刷新与失效处理 → zlens 目前是零凭证工具；
2. 需要**网络出口**与超时降级策略；「查询失败必须降级为明确错误响应」这条要重新定义（远程失败 vs 本地缺文件是两类事）；
3. **只对 Team/Enterprise 管理员成立**，个人用户拿不到 → 覆盖面与本仓库的目标用户几乎不重叠；
4. 会引入**跨源时钟与去重**问题（服务端事件流 + 本地 JSONL 双写同一次消耗）；
5. 前端「只与自家 `/api/*` 通信」这条**不破**（远程拉取放后端即可），破的是「只读本地库」。

**建议**：不做实时远程适配器。改为「**离线对账导入**」——用户从面板/导出的 CSV/JSON（或截图）粘进来，
落成一个本地的 `reconciliation` 输入，与本地测得的积分/token 求差、出残差报告。
理由：零凭证、零破例，且正好复用 T08（e2e acceptance live reconciliation）与 T13（截图/视觉模型取数）的既有肌肉。
Qoder 的 `addOnQuota.detailUrl` 与 Trae 的「需导出数据」说明**导出口是存在的，只是不在个人版文档里**。

### 路径 E（推荐作为这四款的主口径）：不换算 token，直接用官方「积分标价」算钱

因为 1 积分的人民币/美元标价是**官方公布值**，「这段时间的消耗按官方标价折算值多少钱」可以完全绕开黑盒系数：
`Σcredits × (用户录入的 ¥/credit)`。
- 语义上正好落到 zlens 现有的两笔钱框架：**积分是买来的配额**（订阅费/加量包 = `buyout_amount`，一次性付款，不因缺单价而变未知）；
  **消耗积分 × 官方标价 = 按量等效金额**（走 `pricing.json`，由用户录入，不内置默认值）。
- 用户录哪个价必须自己选：套餐内等效单价（WorkBuddy ¥99/2000 ≈ ¥0.0495；Qoder $20/2000 = $0.010）
  与加量包单价（¥0.05 / $0.0133）**不同**，两者都是真数但回答不同问题 →
  **禁止内置默认、禁止自动取低**，交给价格表录入流程（T12/T13 已建好的形状）。
- 它**不满足**「我用了多少 token」的知情权，但**满足**「这次任务花了我多少钱」的知情权。
  产品叙事上应该把这一点讲明白，别用「成本估算」一个词把两件事糊过去。

---

## 四、可行性分级

| 目标 | 分级 | 理由 | 下一步最小验证动作 |
|---|---|---|---|
| **Qoder CN CLI**（`qodercn`，`~/.qoder-cn`） | **值得接（P0）** | 会话路径与配置路径**官方文档化**；SDK 官方同时透出 Token 与 Credits；本机用户就在用 | 只读打开 `~/.qoder-cn/projects/**/*.jsonl`，确认 assistant 记录是否含 `usage`（`input_tokens`/`output_tokens`/cache 各档）与 `credits`；跑四档相加 == total 的恒等式；确认 30d 保留的实际删除行为 |
| **CodeBuddy Code CLI**（`~/.codebuddy`） | **值得接（P1）** | `/cost` **官方就输出 token 四档**；Claude Code 形状（`--output-format json`、`-r`、transcript 默认持久化）；与 WorkBuddy 共享积分 | 跑 `codebuddy -p "hi" --output-format json` 取全量 result 字段；按官方「`.codebuddy` 目录结构说明」定位 transcript；确认逐请求 token 是否落盘 |
| **Qoder 国际版 CLI** | **值得接（P1，与 CN 分开）** | 与 CN 同构（`~/.qoder`），但 **Credits 不等价、定价不同** → 必须两个 source id | 同上；另确认国际版 CLI 是否同样透出 `credits/original_credits/billable` |
| **Qoder CN IDE / Desktop**（含 JetBrains、原灵码 `~/.lingma`） | **需要先实测本机数据才能判断** | 桌面端会话落盘位置**零一手文档**；`/usage` 面板无 token；只有排障日志路径已知 | 在 `%APPDATA%` 与 `~/.lingma` 下找会话/索引存储（`state.vscdb` 类），确认有无 token/模型名/扣费事件 |
| **Trae 国内版** | **需要先实测；预期只能降级接** | 积分↔token 完全无官方数字（连倍率表都没有）；第三方实测本机 `state.vscdb` 只有会话文本，**无 token/无模型/无扣费** | 只读 `state.vscdb` → `ItemTable` → `memento/icube-ai-agent-storage`，核对该键的真实字段（尤其有无 model/token）；同时截图个人版「用量管理」面板，确认个人侧是否显示 token |
| **Trae 企业版**（按会话 Token 明细） | **不做实时适配器；做导入口径** | 有 token + 金额明细与 OpenAPI，但需 org 管理员凭证 → 破「只读本地」红线且人群极窄 | 让一个企业版用户手工导出一次会话明细，看列名与单位，决定「导入对账」的解析器形状 |
| **Trae 国际版** | **可以接，但要单独 source** | Dollar Usage 本身就是货币量纲，缺口只在 token 明细；与国内版机制不同，不能共用适配器 | 取一次国际版「活动记录」导出/截图，确认 model + 时间 + Dollar Usage 三列是否真的逐请求可得 |
| **WorkBuddy 桌面端** | **建议不做**（作为用量数据源） | 官方无 token 显示、无导出、无个人 API、本机落盘零一手来源；且它是办公 agent，**没有项目/cwd 维度**，与 zlens 的 projects 视图语义不匹配 | 若仍要接：只做取证——`%APPDATA%`/`~/.workbuddy` 下有无任务/会话记录、能否拿到积分变动事件；拿不到就停 |

**总体取向（推断）**：这四款里真正能兑现「积分黑盒 → 用户看得懂的用量」的，不是桌面 IDE/办公客户端，
而是它们各自的 **CLI**（Qoder CN CLI、CodeBuddy Code CLI）——只有 CLI 这一族官方就承认「Token 与 Credits 是两个量、
都要给」。桌面 IDE 与办公客户端在官方口径上就是「只给积分余额」。所以 zlens v3 若以「积分类 agent 知情权」为卖点，
**优先级应是 CLI > 桌面（待实测） > 办公客户端（不做）**，而 Trae 国内版在实测前不值得排期。

---

## 五、待实测清单（本机，全部为「未证实」）

1. `~/.qoder-cn/projects/<proj>/<session-id>.jsonl` 每条记录的字段全表：**是否含 `usage`/token 四档、`credits`、`model`、`cwd`、时间戳**；四档相加是否等于 total（若嵌套，照真实形状写 fixture）。
2. 同目录 `<session-id>/state.json` 的内容（模型、上下文窗口、思考强度、是否含累计积分）。
3. `~/.qoder-cn` 下是否存在**独立于会话**的用量/事件类文件（telemetry、logs、stats）；`aiCodeStatistics` 与 `privacy.usageStatisticsEnabled` 的实际落盘产物。
4. 会话保留：`sessionRetention.maxAge=30d` 的实际删除行为与时间基准（写入时间还是最后活动时间）；zlens 的抓取频率与提示文案。
5. Windows 下 Qoder CN Desktop / JetBrains 插件 / 原灵码的本地存储：`%APPDATA%\<产品>\User\globalStorage\state.vscdb`、`~/.lingma`，有无会话与用量。
6. Trae：`%APPDATA%\Trae\User\workspaceStorage\<hash>\state.vscdb` 的 `memento/icube-ai-agent-storage` 真实字段（有无 model/token/credit）；命令面板「开发人员：Open All Logs Folder」打开的目录里有无用量行。
7. Trae 个人版「用量管理」面板实际显示粒度（是否逐请求、是否显示 token）；企业版导出文件的列名与单位。
8. WorkBuddy：本地有无任务/会话记录目录；有无任何积分变动事件落盘。
9. CodeBuddy Code：`.codebuddy` 目录结构、transcript 是否 JSONL、`--output-format json` 的 result 全字段（是否含 `total_cost`/`usage`/`modelUsage`）。
10. **对账（决定路径 C 是否成立）**：同一时间窗内，本地逐请求 `credits` 求和 vs `/usage` 面板/官网 Usage 页的「已用 Credits」是否一致；差多少；`credits` 与 `original_credits` 的比值是否稳定（折扣噪声有多大）。
11. 积分的小数位与截断方式（面板/`usage-events` 是否四舍五入到 1 位），决定标定残差的分辨率下限。
12. `model_key` 三元组取法：这四款的模型标识里 `provider_id` 从哪来（Qoder 面板只给档位 `Standard/Premium` 与模型名，不给 provider）——**这直接决定价格表键能不能落地**，实测前不要开写适配器。

---

## 六、本机实测取证（2026-08-28 第二轮，工作区外只读探测）

方法：`scratch/_probe_external_sources.py`、`_probe_deep.py`、`_probe_dig2/3/4.py`、`_probe_calib.py`。
全程 SQLite `mode=ro`，只输出路径名/表名/列名/字段路径与聚合计数，不读取任何值。样本为本机真实数据。

### 6.1 三处必须修订的判断

| 本报告先前判断（基于文档） | 本机实测结果 | 影响 |
|---|---|---|
| 「Qoder CLI 的 jsonl 大概率含 token 四档」（§2.2 推断、待实测 #1） | **token 四档全部为 0**。7 个会话文件、989 条 `billable=true` 消息，`input_tokens`/`output_tokens`/`cache_creation_input_tokens`/`cache_read_input_tokens` **无一例外为 0**；同时 `credits` 是真数 | 路径 A（本地量真 token）对 Qoder **不成立**；Qoder 只能走路径 E |
| 「WorkBuddy 桌面端建议不做：无 token 显示、本机零一手来源、没有项目维度」（§2.4、§四） | **反转**。`~/.workbuddy/projects/<项目slug>/<uuid>.jsonl` 含**真 token**（三套上游方言 + `rawUsage.credit`），`workbuddy.db` 明文，`sessions.cwd`/`project_id` 俱在 | WorkBuddy 升为**本次最优先目标**，不是不做的对象 |
| 「Trae 国内版连相对倍率表都没有」（§2.3，基于官方文档） | 文档确实没有，但客户端本地缓存 `…_AI.agent.model.model_list_map`（471 字段路径）明文含 **`features.discount.data.consumption_rate` / `original_consumption_rate` / `member_discount` / `is_discount_matched`、`fee_model_level`、`saas_usage.default/max`、`max_turns.default/max`、`is_internal_usage_limit`**，按 7 个场景（builder / builder_v3 / chat_v3 / code_reviewer / code_review_summary / refactor / solo_agent）逐模型给出 | Trae 的「黑盒」只对**流水**成立，**计价参数是明文的** |

### 6.2 逐条回答第五章待实测清单

- **#1 Qoder CLI jsonl 字段（已答）**：路径确认为 `~/.qoder-cn/projects/<转义cwd>/<sessionId>.jsonl`（本机 3 个项目、7 个文件、11.9 MB）。
  `message.usage` 实测字段：`credits`、`original_credits`、`billable`、`context_usage_ratio`、`request_id`、`service_tier`、
  `speed`、`inference_geo`、`iterations`、`server_tool_use.{web_search_requests,web_fetch_requests}`、
  `cache_creation.{ephemeral_5m_input_tokens,ephemeral_1h_input_tokens}` —— **以及恒为 0 的四个 token 档**。
  顶层另有 `cwd`、`gitBranch`、`entrypoint`、`isSidechain`、`contextWindow`、`toolUseResult.resolvedModel`。
  **本机合计：实扣 897.93 积分，原价 1309.98 积分，折扣幅度 31.5%**（其中一个会话 `400.116 / 800.232` 恰好对折）。
  → 「`credits` vs `original_credits` 并排显示」在本机就有真实差异可展示，不是理论特性。
- **#2 `state.json`（部分答）**：会话另有同名目录 `projects/<转义cwd>/<uuid>/`、`tasks/<uuid>/`、`file-history/<uuid>/`、
  `%LOCALAPPDATA%\Temp\qoder-cli-cn\<转义cwd>\<uuid>\` 四处并存（本次未逐个开文件）。
- **#3 独立用量文件（已答：无）**：`~/.qoder-cn/.cache` 只有 `endpoint-cache.json`、`dns-cache.json`；
  `.models/catalog-v6`（80 KB）非 JSON、头部不可辨识；顶层另有同名 `catalog-v6`。均无用量。
- **#5 Qoder IDE（已答：只有系数，没有流水）**：`%APPDATA%\Qoder\User\globalStorage\state.vscdb` 5.6 MB、747 键，
  **全库扫描仅 9 个键的值含用量类字段**，且全是配置/主题：`aicoding.modelConfigs.cache.{assistant,experts,quest}`、
  `aicoding.customModels`、`chat.cachedLanguageModels`、`secret://aicoding.auth.creditUsage`。
  会话侧：`aicoding-chat-<uuid>.state.hidden` 共 **107 个键，形状只有 `[{id,isHidden}]`**；
  `workspaceStorage/<hash>/chatSessions/*.json` 仅 VS Code 默认 8 字段元数据（`creationDate`/`lastMessageDate`/
  `requesterUsername`/`sessionId`/…，**无 messages、无 usage**）；三个最大 workspaceStorage 库用量命中 0。**结论：IDE 侧逐次消耗本地不可得。**
  但**档位系数表完整可得**（16 档，`auto` 1.0 / `ultimate` 1.6 / `performance` 1.1 / `efficient` 0.3（原价 0.5，说明调过价）/
  `qmodel_38max` 0.5 / `qfmodel` 0.1 / `kmodel_latest` 0.8 / `dmodel` 0.8 / `mmodel` 0.2 / `cmodel` 3.2 …），
  含 `displayName`、`maxInputTokens`、`contextConfig.{200K,272K,400K,1M}.tokenCount`、`promotion.*`、`source`、`strategies[].tag`。
  → **注意与文档不一致**：官方倍率表区间是 0.1×–1.6×，本机快照里 `cmodel` 为 **3.2×** → 印证「文档是综合预估、客户端才是下发值」，
  也说明**系数必须按快照抓取并标注时间**，不能抄文档。
- **#6 Trae（部分答，且改判）**：会话库 `%APPDATA%\Trae CN\ModularData\ai-agent\database.db`（28 MB）**文件头不是
  `SQLite format 3` 魔数，是随机字节 → 整库加密**，逐次用量本地不可得。
  第三方文章所说的 `memento/icube-ai-agent-storage` 键**本次未复核**（我的关键字过滤器未覆盖 `icube`），列为遗留。
  `%APPDATA%\Trae CN\User\workspaceStorage` 最大 4 库扫描：用量命中 0–1（唯一命中是终端状态缓冲，见 6.5）。
- **#8 WorkBuddy（已答，且反转）**：见 6.1 与 6.3。
- **#10 对账（部分答）**：`credits/original_credits` 比值**不稳定**（0.5×、0.6×、1.0× 都出现）→ 折扣噪声确实存在，
  标定时必须只用 `original_credits`；但面板对账（本地求和 vs 官网「已用 Credits」）本次未做。
- **#12 `provider_id` 从哪来（已答）**：Qoder 本地记录**只有档位名**（`qfmodel`/`qmodel_38max`），无 provider 字段。
  可用来源是 IDE 缓存的 modelConfigs 条目里的 `source` 与 `strategies[].tag`；CLI 侧则只能 (a) 与该缓存做名称联接后取，
  或 (b) 沿用 opencode 先例 `provider_id` 恒为源常量、由 `model_id`（档位名）承载渠道差异。
  → 两个 source id（`qoder` / `qoder_cn`）+ 档位名作 `model_id` 即可落地，**不阻塞开票**。

### 6.3 WorkBuddy 实测细节（本轮最大收获）

两处存储，均明文：

1. `~/.workbuddy/workbuddy.db`：`sessions(id, cwd, user_id, title, status, created_at, updated_at, deleted_at,
   is_playground, source_mode, is_background_automation, mode, model, expert_id, expert_locale,
   expert_runtime_identity, expert_marketplace, permission_mode, last_activity_at, use_sandbox_cli, project_id)`；
   `session_usage(session_id, used, size, updated_at, credit_json)`；另有 `automations(model_id, model_is_thinking, …)`、
   `automation_runs`、`workspaces`。实测 `used=32922/32957`、`size=168000`（上下文占用/窗口），
   `credit_json={"<32位hex>": 3.81}` / `{"<另一hex>": 3.84}`。
2. `~/.workbuddy/projects/<项目slug>/<uuid>.jsonl`（Claude Code 同构，`type` 有 `message`/`reasoning`/`ai-title`/
   `file-history-snapshot`）。单条 assistant 记录里**同时存在三种上游方言的 usage**：
   - `message.usage.{input_tokens, output_tokens, cache_read_input_tokens, total_tokens}`
   - `providerData.rawUsage.*`：OpenAI 形状（`prompt_tokens`、`completion_tokens`、`total_tokens`、
     `prompt_tokens_details.{cached_tokens,reasoning_tokens,audio_tokens,accepted_prediction_tokens,rejected_prediction_tokens}`、
     `completion_tokens_details.*`）、Anthropic 形状（`cache_creation_input_tokens`、`cache_read_input_tokens`、
     `cache_creation`）、火山/DeepSeek 形状（`prompt_cache_hit_tokens`、`prompt_cache_miss_tokens`、
     `prompt_cache_write_tokens`、`cached_tokens`、`completion_thinking_tokens`），**以及 `credit`**
   - `providerData.usage.{inputTokens, outputTokens, totalTokens, requests,
     inputTokensDetails[].cached_tokens, outputTokensDetails[].reasoning_tokens}`
   模型标识：`providerData.model=glm-5.2`、`requestModelId=auto`、`requestModelName=Auto`、`traceId`、
   `messageId`、`conversationRequestId`（后三者是天然的去重键）。

**恒等式实测（嵌套，和 ZCode 同类）**，两文件合计：

```
prompt_tokens 65879 = prompt_cache_hit 32512 + prompt_cache_miss 33367   ✓
total_tokens  66771 = prompt 65879 + completion 892                      ✓
reasoning 521 ⊂ completion 892（completion_thinking_tokens 亦为 521）    ✓
session_usage.used 合计 65879 == providerData.usage.inputTokens 65879     ✓
credit_json 两值之和 7.65 == Σ rawUsage.credit 7.65                       ✓
```

→ 适配器必须像 `zcode.py` 那样在**适配器层**拆档：`input = prompt_tokens − cache_read`、`cache_read = cached_tokens`、
`reasoning` 不另立加数（它是 output 的子集）。`fixture 必须照这个嵌套形状写`，否则同一批 token 会计两次费。

**credit↔token 标定成功**（这是四款里唯一标定出来的）：
`1 credit ≈ 8756 total_tokens`（会话 A）与 `≈ 8701`（会话 B），两次独立测量相差 **0.6%**。
样本仅 2 会话、单模型（`glm-5.2`），**不足以成为系数**，但证明 WorkBuddy 是唯一「同一条记录里既有真 token
又有官方扣费积分」的产品 —— 反向标定（路径 C）只在它身上有可执行的数据基础。

**遗留**：`credit_json` 的 32 位 hex 键，两会话模型相同（`glm-5.2`）却取值不同，且在全库任何列都查不到 →
**可以排除「hex 是模型标识」**（先前推测作废）。需换用不同模型/不同账号的更多会话才能定语义。

### 6.4 反向标定实验：Qoder 路线判死（负结果，重要）

按 §三 路径 C 设想，用 `base = (context_usage_ratio × contextWindow) / (credits / priceFactor)` 求「每积分对应多少
token」，若 `base` 近似常数即可反推 token。实测：**766 条含 credits 的消息，766 条全部无法参与** ——
`context_usage_ratio` 在这些记录上为 0 或缺失，`contextWindow` 又不在同一类记录上（它挂在别的 `type` 上，
本机仅 90 条记录带该字段）。叠加官方 SDK 文档原文「Token 与 Credits **没有固定换算关系**」，
**Qoder 侧由积分反推 token 的路线判定为不成立**，不应再投入。
这不是取证不充分，而是与官方声明互相印证：**积分是服务端按任务动态算出来的，本地没有还原它所需的物理量。**

### 6.5 安全边界（必须写进适配器与票的边界条款）

- `secret://aicoding.auth.creditUsage` 是 `{"type":"Buffer","data":[118,49,…]}` —— VS Code 加密密文，
  且同一 `secret://` 命名空间下还有 `auth.userInfo`、`auth.userPlan`、`customModel.apiKey.*`。
  **只读明文 KV，任何 `secret://` 前缀一律不碰、不解密。**
- Trae 的模型配置 blob 里混着 `selectedModel.ak` / `base_url` / `auth_type`（BYOK 凭据）。
  取用 `model_list_map` 时**必须白名单取计价字段名，禁止整块落库或回显**。
- Trae 的 `terminal.integrated.bufferState` 里出现 `TRAE_JWT_TOKEN_PATH` 等环境变量。
  **任何情况下不要扫终端状态缓冲。**
- Qoder 的 `~/.qoder-cn/.auth`、`~/.codex/auth.json` 之类凭据目录同理：适配器路径清单必须显式排除。

### 6.6 修订后的可行性分级

| 目标 | 修订前 | **修订后** | 依据 |
|---|---|---|---|
| **WorkBuddy** | 建议不做 | **值得接（P0）** | 明文 SQLite + JSONL；真 token + 官方积分同记录；恒等式可校验；有 cwd/project 维度；credit↔token 已初步标定 |
| **Qoder CN CLI**（本机这个） | 值得接 P0 | **值得接（P0），但口径改为「积分账」** | 积分逐条可信；token 恒为 0 → 只能显示积分 + 折扣差额，禁止显示 token |
| **Qoder IDE** | 需实测 | **只接系数表，不接消耗** | 系数/倍率明文可得；逐次消耗本地不存在 |
| **Trae 国内版** | 需实测，预期降级 | **接「计价参数 + 配额」，消耗暂缓** | 倍率/折扣/上限明文；会话库整库加密 |
| **CodeBuddy Code CLI** | 值得接 P1 | **保持，升 P1**；本机未安装（`~/.codebuddy` 待确认） | 官方 `/cost` 就出 token 四档，且与 WorkBuddy 同积分池 |
| Qoder 国际版 CLI | P1 | 保持 P1，`qoder` 与 `qoder_cn` 两个 source id | 官方明写两者积分不等价 |

### 6.7 本轮之后仍待实测

1. WorkBuddy `credit_json` 的 hex 键语义（需跨模型、跨账号样本）。
2. WorkBuddy `~/.workbuddy/app` 下的 LevelDB 类文件（`data_1/data_2`）与 `Session Storage`，有无积分变动事件流。
3. Trae `memento/icube-ai-agent-storage` 键的真实字段（本轮未复核，第三方称只有会话文本）。
4. Qoder `<session-id>/state.json` 是否含累计积分与模型参数（本轮只定位未开文件）。
5. CodeBuddy Code 是否在本机可用（`~/.codebuddy`），以及 `/cost` 是否随 transcript 落盘。
6. Qoder 会话 30 天自动清理的实际删除行为（官方 `sessionRetention.maxAge=30d`）；本机已有 `.last-cleanup` 痕迹。
7. 对账：本地逐条 `credits` 求和 vs 官网/`/usage` 面板「已用 Credits」的差额与小数位截断。

---

## 七、来源清单

**Qoder / Qoder CN（一手）**
- [Qoder Credits（国际版）](https://docs.qoder.com/zh/Credits) — Credits 定义、中位数估算表、失败不扣费、Usage/Credits 日志
- [Qoder 定价（国际版）](https://docs.qoder.com/zh/account/pricing) — 套餐与「20 美元 / 1,500 Credits」
- [Qoder CLI 管理会话（国际版）](https://docs.qoder.com/zh/cli/sessions) — `~/.qoder/projects/...jsonl`
- [Qoder CLI SDK 成本和用量（国际版）](https://docs.qoder.com/zh/cli/sdk/cost-usage)
- [Qoder CN 文档索引 llms.txt](https://docs.qoder.cn/llms.txt)
- [Qoder CN CLI 配置项/环境变量/文件路径](https://docs.qoder.cn/cli/settings-reference.md) — `~/.qoder-cn`、`QODERCN_*`、sessionRetention 30d、privacy
- [Qoder CN 管理会话](https://docs.qoder.cn/cli/sessions.md)
- [Qoder CN 查看用量与额度](https://docs.qoder.cn/cli/usage.md) — `/usage` 面板字段
- [Qoder CN 使用洞察](https://docs.qoder.cn/cli/insights.md) — 数据来源为本地会话元数据与 facets
- [Qoder CN SDK 成本和用量](https://docs.qoder.cn/cli/sdk/cost-usage.md) — **「Token 与 Credits 没有固定换算关系」的官方原文**
- [Qoder CN 模型选择器](https://docs.qoder.cn/qoder/model-selector.md) — 逐模型 Credit 消耗倍率表
- [Qoder CN Hooks 参考](https://docs.qoder.cn/cli/hooks-reference.md) — `transcript_path`/`cwd`/`session_id`，27 种事件
- [Qoder CN 用量 API（企业）](https://docs.qoder.cn/enterprise/usage-api.md) — `usage-events` 字段，≤7 天，无 token
- [Qoder CN 问题排查指南](https://docs.qoder.cn/support/troubleshooting-guide.md) — `~/.lingma`、`lingma.log`
- [阿里云 Qoder CN Credits（旧站，含不互通与倍率免责原文）](https://help.aliyun.com/zh/lingma/credits)

**Trae（一手）**
- [TRAE CN 套餐与计费](https://docs.trae.cn/ide_plans-and-billing) — 档位/积分/加量包 ¥50 每 1000 积分/升档公式
- [TRAE CN 积分计费上线公告](https://docs.trae.cn/ide_coming-soon)
- [TRAE CN 内置模型](https://docs.trae.cn/ide_models.md) — 模型清单（无倍率）
- [TRAE CN 订阅管理](https://docs.trae.cn/ide_subscription-management.md) — 用量管理面板（个人侧无 token）
- [TRAE CN 查看个人用量（企业）](https://docs.trae.cn/enterprise_check-individual-usage) — 会话级 Token 消耗/金额/导出
- [TRAE CN 云端智能体数据存储声明](https://docs.trae.cn/work_data-storage-policy-for-remote-agents.md)
- [TRAE CN 获取日志或 SessionID](https://docs.trae.cn/ide_get-logs-or-session-id.md)
- [TRAE 国际版定价](https://www.trae.ai/pricing) — 「billed based on the number of tokens processed」、Dollar Usage/Basic Usage
- [官方 FAQ：国际版计费方案升级](https://forum.trae.cn/t/topic/207) — 「6 Requests = $1 Dollar Usage」、活动记录含模型/时间/Dollar Usage
- 论坛帖标题（正文未取）：[Trae 积分的争议，不是贵不贵，是 Token 消耗说不清](https://forum.trae.cn/t/topic/173627)

**WorkBuddy / CodeBuddy（一手）**
- [腾讯云《计费概述》WorkBuddy Enterprise](https://cloud.tencent.com.cn/document/product/1831/134333) — 积分共享声明、套餐与加量包标价
- [腾讯云《积分说明》](https://cloud.tencent.com/document/product/1831/134339) — 「消耗量与模型 Token 定价和任务复杂度有关」（无系数）
- [CodeBuddy Code 成本管理](https://www.codebuddy.ai/docs/zh/cli/costs) — `/cost` 的 token 四档输出
- [CodeBuddy Code CLI 参考](https://www.codebuddy.ai/docs/zh/cli/cli-reference) — `--output-format json`、`~/.codebuddy/logs/`
- [Tencent Cloud WorkBuddy 产品页](https://www.tencentcloud.com/zh/products/workbuddy) ／ [活动页](https://cloud.tencent.com/act/pro/workbuddy)

**二手（仅作旁证，标注为未证实）**
- [掘金：Codex CLI / Trae / Copilot 数据源接入](https://juejin.cn/post/7640357289836281882) — Trae `state.vscdb` + `memento/icube-ai-agent-storage`
- [AI 编程助手数据提取终极指南](https://www.xugj520.cn/archives/ai-coding-assistant-data-extraction-2.html) — 与上一篇相互矛盾处已在正文说明
- [coding-agent-visualizer](https://github.com/everettjf/coding-agent-visualizer) — 各家 transcript 路径形状旁证
- [新浪财经：腾讯 WorkBuddy 领跑桌面端 AI 智能体赛道](https://finance.sina.com.cn/stock/relnews/hk/2026-08-03/doc-inikzuyf6173064.shtml) — 产品定位旁证
- [头条：WorkBuddy 的积分到底怎么扣？两个月记账实测](https://m.toutiao.com/article/7675299296568279604/) — 缺口实证（仅标题级）
- [workbuddy.homes](https://workbuddy.homes/) ／ [WorkBuddyGuide](https://github.com/AlephAITech/WorkBuddyGuide) — **社区站，明确不可当官方出处**

---

## 八、2026-08-28 晚间第三次实测：Qoder CN 深挖（账本缩水 + 第二账本）

方法：`scratch/_probe_v3_verify.py`、`_probe_qodercn_deep.py`、`_probe_qodercn_deep2.py`、
`_probe_qodercn_logs.py`、`_probe_qodercn_logs2.py`、`_probe_qodercn_logs3.py`。全程只读。

### 8.1 账本缩水实锤与机制排查

同日两个时点对比:`~/.qoder-cn/projects` 上午(§6.2 #1)7 个 jsonl、989 条 billable、
实扣 897.93 / 原价 1309.98;晚间复测只剩 3 个 jsonl(2 主会话 + 1 子代理)、832 条、
实扣 507.81 / 原价 507.81(**折扣归零**——被删的恰是全部带 0.5×/0.6× 折扣的会话)。

排查结论:

- **不是 30 天保留清理**。`.last-cleanup` 内容 `2026-08-27T13:59:57Z` = 安装当晚,mtime 未再更新。
  它是安装标记,不是周期清理标记(修订 D5「检测到 .last-cleanup 即告警」的说法)。
- **不是回收站**。`C:\$Recycle.Bin` 无当日大 jsonl → 程序化删除(应用内删除或 IDE 会话管理)。
  被删会话在 `projects/`、`tasks/`、`file-history/` 的目录被同步清除,是**完整的会话删除流程**,
  非文件损坏。具体由用户触发还是 IDE 自动触发,磁盘上无法分辨。
- 被删内容:全部 transcript 属于 `C:\Users\h7242\Documents\Qoder\2026-08-27\5a22f190` 与
  `D:\appdevelop\Qoder CN IDE` 两个项目目录(约 157 条消息、≈390.12 实扣积分)。
  **这部分积分本地已不可恢复**(见 8.2,logs/sessions 不含 credits)。
- 趋势图历史边界由厂商/操作决定的判断(§ Further Notes)**本机已发生**,快照入库的产品决策
  紧迫性上调。

### 8.2 新发现:logs/sessions 第二账本(事件流,无 credits)

`~/.qoder-cn/logs/sessions/<转义cwd>/<sessionId>/segments/<run>.jsonl` 是**按会话组织的结构化
事件流**(本机 134 个会话目录、8.8 MB,jsonl transcript 只有 3 个会话):

- 事件类型:`session.config.loaded`(cwd/模型/permission_mode)、`input.prompt.received/submitted`、
  `model.request.started`(903)、`model.response.completed`(896,含 `request_id`/`provider`/`model`/
  `stop_reason`/token 四档)、turn/loop/tool/hook 全过程。
- **token 四档恒 0、无 credits 字段** → 不能恢复被删积分,不是钱账;但它是**请求级账本**,
  且**会话删除流程不清除它**。
- **transcript 缺席的消耗在这里现形**:134 会话中 36 个有完成响应,其中 34 次响应属于
  **没有任何 transcript 的 headless 会话**(模型 `qmodel` 20 次、`gfmodel` 14 次;39 个会话的
  首条 prompt 是「你正在为 Qoder 任务监控编写简短的会话 Recap」)——IDE 后台任务确实在烧模型,
  但这些调用**永远不会出现在 projects/**/*.jsonl** 里。
  → transcript 积分账对 IDE 后台消耗存在**系统性少计**(本机今日 ≈34 次/占比虽小但恒存在),
  T17 口径须声明「只计 CLI transcript 可见消耗」。
- 会话日志里的 `provider` 字段实测 = `"qoder"`,佐证 D5 的 provider_id 常量取法。
- `session.config.loaded.interactive` 实测**恒为 false**(主交互会话也是),不可用作分流特征;
  `entrypoint` 字段只在 transcript 里有,日志流没有。

### 8.3 T17 适配器新事实

- **子代理 transcript 必须纳入**:`projects/<cwd>/<sessionId>/subagents/agent-*.jsonl` 含独立
  usage/credits(本机研究子代理 45 条 billable、12.53 积分),规格里「`projects/*/*.jsonl`」的
  一层 glob 会漏掉它;需 rglob 或显式 `subagents/` 处理。子代理记录自带 `agentId`/
  `parent_tool_use_id`/`isSidechain=223` 可识别归属;`task-*.json` + `*.meta.json` 记录任务映射。
- **`request_id` 全局唯一**:832/832 无重复,是比 timestamp 更稳的去重键。
- **credits 小数位最深 9 位**(如 `9.294178267`、`0.08709017899999999`):逐条禁止提前舍入,
  求和用原始浮点,仅展示层取 2 位(印证 D6)。
- 折扣是**逐条**属性且随会话消失:幸存集全部 ratio=1.0,被删集才有 0.5×/0.6×;
  `original_credits` 必须逐条保留,不能按来源配常数折扣。
- `service_tier`/`speed`/`inference_geo`/`iterations`/`server_tool_use` 本机为常数
  (`standard`/`standard`/`''`/`[]`/全 0),当前无口径价值,保留字段不建列。
- CLI 版本 `1.1.31` 写在每条记录顶层 `version` 字段。
- `state.json`(projects/<cwd>/<uuid>/)只有压缩簿记与加密 items,**无累计积分**
  (§6.7 #4 结案:该处不藏账)。`compression-v2/state.json` 为上下文压缩状态。
- `.models/catalog-v6`(82 KB)为整体编码 blob(头 `UUUDAS1k…`),CLI 侧提不出档位系数,
  D4 依赖 IDE `state.vscdb` 的结论不变。
- Temp 孤儿目录(`%LOCALAPPDATA%\Temp\qoder-cli-cn\`)是 **task 运行目录**(`*.output`),
  不是会话残留,无计费数据。

### 8.4 对账含义

本地可重建的积分账 =「transcript 可见」账:今日幸存 507.81 + 已删 ≈390.12 + headless 后台
(34 次,积分未知,本地无任何数字)。官网面板若显示更多,差额即 headless + 已删会话的
服务器侧数据——**本地永远补不齐**,印证 §三 路径 E 需要配对账导入(v2 的 T08/T13 肌肉),
且快照/对账的优先级因 8.1 的删除事实上调。
