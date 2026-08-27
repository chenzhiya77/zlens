# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- 多来源支持:新增 MiniMax Code 与 opencode 数据源适配器;API 层 MultiSource 合并展示,\n  每个明细行带 `source` 标记,全部端点支持 `?source=` 过滤;前端表格与错误分布显示来源。\n- 六个数据视图全部升级为多来源合并视图(趋势序列按\"来源/模型\"区分)。\n- 全部六个数据视图:总览、日趋势(多序列折线 + 时间范围切换 + 每日/每周/累计活动图)、
  按模型(占比环形图 + 排行)、按项目、性能(P50/P90/P99)、健康度(重试/错误分布)。
- 前端壳与总览视图(React SPA:六视图导航、KPI 大数字卡片行、按模型明细表、
  未计价模型提示、数据源错误降级提示);生产构建由 FastAPI 托管为单进程,
  开发期 Vite 代理 `/api`。
- 项目骨架:uv 依赖管理 + ruff(E/F/I/UP)+ pytest(live marker 分层)+ pre-commit local hooks,
  治理模式沿用 deer-flow(AGENTS.md 单一事实源、文档随代码同步、push 前 make check)。
- v1 需求规格 `docs/specs/v1-spec.md` 与实施票 `docs/plans/tickets/`。
- 只读查询 API:`/api/meta`、`/api/overview`(含价格表成本估算)、`/api/trends/daily`、
  `/api/models`、`/api/projects`、`/api/performance`(P50/P90/P99)、`/api/health`。
- VLM 截图识别:设置页可配置视觉语言模型(OpenAI 兼容,密钥只存本机 gitignored 配置);
  价格表页按模型粘贴单价截图,识别结果只预填被选中的那一行,互不影响。
- 主题设置:设置页新增「主题」区块——深色/浅色外观切换 + 六种主题色(天蓝/青色/翡翠/
  靛紫/琥珀/玫红),选择立即生效并保存在本机浏览器(localStorage)。

### Fixed

- VLM 配置保存后「测试连接 / 截图识别」立即生效(重新叠加本机配置,不再使用服务启动时快照)。
- 浏览器自动填充会把输入框(如 VLM API Key)涂成白色底,现与页面主题一致(深/浅色均保持)。
- 密钥安全:`zlens.config.json`(含 VLM Key)不再纳入版本库跟踪(gitignore)。
