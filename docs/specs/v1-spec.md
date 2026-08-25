# zlens v1 规格(Spec)

> 状态:**ready-for-agent** · 定稿:2026-08-26 · 来源:设计会话定稿(见 docs/plans/)
> 本文是 v1 的行为契约与验收依据;实现票见 `docs/plans/tickets/`。

## Problem Statement

重度使用 AI Coding Agent 之后,用户不知道 token 到底花在了哪里:哪天用得多、哪个模型吃掉了大头、缓存省了多少钱、哪些请求在重试或报错。服务商侧 dashboard 只有账号级汇总,且无法按本地项目拆分;现有社区工具(ccusage 等)不支持 ZCode 数据源,也普遍没有性能与健康度视角。

## Solution

一个 local-first 的本地 Web 工具 **zlens**:启动后浏览器打开,即看到本机 ZCode 全部模型请求的用量、成本估算、性能分位数与健康度报表。数据全程以只读方式来自 ZCode 自身持久化的 SQLite 数据库,零侵入、不影响正在进行的对话。成本折算依赖一份可自由编辑的价格表;没有公开定价的模型只显示 token 数,绝不硬编错价。

## User Stories

1. As a 个人开发者, I want 打开页面就看到全部请求的五类 token 总量(输入/输出/推理/缓存写/缓存读)分开统计, so that 我能看清真实的消耗构成而不是被"含缓存总数"误导。
2. As a 个人开发者, I want 总览页同时显示请求次数与数据覆盖的时间范围, so that 我知道统计口径从何时开始、一共基于多少条记录。
3. As a 关心成本的用户, I want 在价格表中配置每个模型的单价后页面自动折算美元成本, so that 我能把 token 数换算成可感知的花费。
4. As a 关心成本的用户, I want 缓存读按独立低价档计价, so that 成本估算反映缓存带来的实际节省。
5. As a 使用内部模型的人, I want 价格表中没有的模型只显示 token 数并明确标注"未计价", so that 工具不会给我一个错误的金额。
6. As a 价格表维护者, I want 直接编辑本地 JSON 价格文件并刷新页面即可生效, so that 改价格不需要重启服务或改代码。
7. As a 个人开发者, I want 看到按日聚合的请求量与各类 token 趋势图, so that 我能发现异常放量的一天并回忆那天做了什么。
8. As a 多模型用户, I want 按模型(provider + model)拆分的请求次数/token/成本排行, so that 我知道该优先优化哪个模型的用法。
9. As a 多项目用户, I want 按项目目录拆分的用量统计, so that 我能量化每个项目烧掉多少 token。
10. As a 追求体验的用户, I want 看到耗时与首字延迟(TTFT)的 P50/P90/P99 分位数, so that 我能客观感知模型响应快慢而不只是凭感觉。
11. As a 追求体验的用户, I want 性能面板标明 TTFT 的有效样本数, so that 我知道分位数可信度(部分请求无该数据)。
12. As a 关注稳定性的用户, I want 健康度页展示重试次数、错误类型/错误码分布、context 超限与用户取消计数, so that 我能发现系统性问题而不是单次偶发。
13. As a 深度用户, I want 所有视图都能看到数据截至最近一条记录的时间, so that 我确认看到的是准实时数据。
14. As a 正在跑对话的用户, I want zlens 查询数据库期间我的会话完全不受影响, so that 统计工具永远不值得我为它停下手头工作。
15. As a 单机用户, I want 一条命令启动、无需登录、无需联网, so that 这个工具本身足够轻。
16. As a 对 schema 变化担忧的用户, I want 当上游数据库结构变化导致查询失败时, 页面给出明确的"数据源不兼容"提示而非白屏崩溃, so that 工具坏了也是体面地坏。
17. As a 未来可能多 agent 的用户, I want 数据接入层是清晰的适配器接口, so that v2 接入其他 agent 时不需要推翻现有代码。
18. As a 开发者本人, I want 离线测试套件不依赖真实数据库也能全绿, so that CI 与日常开发永远不会因为环境缺数据而红。

## Implementation Decisions

- **单一数据源、绝对只读**:v1 仅接 ZCode;连接必须使用 SQLite 只读 URI(`mode=ro`)。并发安全已在真实环境验证(ZCode 写入期间查询无阻塞)。任何查询失败降级为结构化错误响应。
- **数据契约**(来自对真实库的实测,当前版本 0.16.5):
  - 请求粒度表:每行一次模型调用,含 session/turn 关联键、`provider_id`+`model_id`、`started_at`(epoch 毫秒)、五类 token(input / output / reasoning / cache_creation / cache_read,另有 computed_total)、`duration_ms`、`time_to_first_token_ms`(可空)、`retry_count`、`retryable`、`cancelled_by_user`、`context_exceeded`、`error_type`、`error_code`;
  - 轮粒度表:按 turn 聚合,含轮级耗时、模型请求/重试次数、工具调用与工具错误计数;
  - 会话表:`directory` / `title` / `project_id`,用于项目维度(join 请求表的 session 键)。
  - 该库非公开 API,升级可能变更结构——所有 SQL 集中在数据源适配器内,便于一处防御。
- **v1 直查、不建自有库**:ZCode 单源下直接 SQL 聚合已够快(已验证路线);不为第二来源预写同步/存储代码。适配器接口(id / 可用性探测 / 各查询方法)是多源的预留扩展点。
- **成本层**:价格表为版本化 JSON(单位 USD / 1M tokens,档位 input / output / cache_read / cache_write 可选);模板随仓库分发,真实价格文件不入库。缺失模型→tokens-only;`cache_write` 缺档→该项成本记 0 并照常显示其余项。页面所有金额旁标注"估算"。
- **API 契约**:FastAPI 应用工厂 + lifespan 装配单例(数据源、价格表)挂 `app.state`;全部只读 GET,六组资源:`overview`、`trends/daily`、`models`、`projects`、`performance`、`health`,外加 `meta`(数据覆盖范围、生成时间、未计价模型清单)。Pydantic 模型内联在各 router(deer-flow 模式)。错误统一 HTTPException;数据源不兼容返回专用错误码由前端渲染降级提示。
- **统计口径**:`started_at` 按本地时区聚日;分位数用 P50/P90/P99;TTFT 分位数排除空值并在响应中带样本数;成本 = Σ(各档 token ÷ 1e6 × 单价)。
- **前端**:React SPA(Vite + TS + Tailwind + shadcn/ui + ECharts + react-query,pnpm 管理);开发期 Vite 将 `/api` 代理到 FastAPI :8000,生产构建产物由 FastAPI StaticFiles 托管——交付形态为单进程。六个视图对应上述六组资源,另含全局来源/时间范围说明栏。
- **视觉基准**(参照 ZCode IDE 设置中"使用统计"面板,2026-08 截图分析):KPI 大数字卡片行(大号数值 + 灰色小标签 + 细分隔线,不用重边框卡片);GitHub 风格 Token 活动热力图,配每日/每周/累计粒度切换;时间范围分段控件(近 7 日 / 近 30 日 / 全部);按模型着色的多序列趋势折线(图例色点对应模型);模型占比环形图;数值用中文单位(万)格式化;深色主题、圆角卡片分区、充分留白。官方面板没有的能力——成本金额、缓存读/写拆分、性能分位数、健康度、按项目拆分——是 zlens 的增量,借鉴其形式但不削减自身范围。
- **治理**:工程规范以 AGENTS.md 为唯一事实源(uv + ruff E/F/I/UP + pytest live marker 分层 + pre-commit local hooks + Makefile 四件套 + Keep a Changelog),细节见该文件,spec 不重复。

## Testing Decisions

- **唯一测试 seam:HTTP API 层**。测试通过 TestClient 请求真实应用,但注入两样东西:① 一个由 fixture 构造的小型合成 SQLite(镜像上述三表结构与少量边界数据:跨日多条、含重试/错误/context_exceeded/取消、含 TTFT 空值、含未知模型);② 一个临时价格文件(含已知与故意缺失的模型)。
- 只断言外部行为:响应状态码、JSON 结构与数值口径(聚合和、分位数、计价结果、"未计价"标记),不 mock 内部函数、不测私有实现。
- 边界必测:空库、schema 不兼容(建一个残缺表结构的库)触发降级错误码、未知模型 tokens-only、cache_write 缺档。
- 真实库冒烟:打 `live` marker(默认排除),只读断言 meta 端点 200 且请求数 > 0。
- Prior art:`tests/test_package.py`(包导入冒烟)。

## Out of Scope

- 多数据源接入(Claude Code / Codex / opencode 等)及其归一化存储——接口已预留,v2 再做;
- 自有统一统计库与水位线增量同步;
- Tauri 桌面壳、系统托盘、开机常驻;
- 订阅计划限额真值(逆向 OAuth usage 端点一类);
- 任何写入/修改上游数据库的能力;
- 账号级用量与服务商 dashboard 数据;
- 该数据库启用之前的历史数据(物理上不存在);
- 登录鉴权、多用户、远程部署(仅绑定 loopback 单机使用)。

## Further Notes

- 竞品结论(2026-08 调研):ccusage 已覆盖 16 个 CLI 数据源但无 GUI、无性能/健康度;cc-switch 有 Tauri 用量面板但不支持 ZCode;**没有任何现有工具支持 ZCode 或提供 TTFT/错误健康视图**——这是 zlens 的差异化立足点。
- 当前真实库规模:约 300+ 条请求记录,全部为内部模型(无公开定价),覆盖自 2026-08-25 起——因此首版运行时"未计价"路径会是主路径,属预期行为。
- 测试缝隙如需调整(例如希望对查询层单独开 seam),请在评审本 spec 时提出。
