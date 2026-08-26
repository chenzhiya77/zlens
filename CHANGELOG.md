# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- 前端壳与总览视图(React SPA:六视图导航、KPI 大数字卡片行、按模型明细表、
  未计价模型提示、数据源错误降级提示);生产构建由 FastAPI 托管为单进程,
  开发期 Vite 代理 `/api`。
- 项目骨架:uv 依赖管理 + ruff(E/F/I/UP)+ pytest(live marker 分层)+ pre-commit local hooks,
  治理模式沿用 deer-flow(AGENTS.md 单一事实源、文档随代码同步、push 前 make check)。
- v1 需求规格 `docs/specs/v1-spec.md` 与实施票 `docs/plans/tickets/`。
- 只读查询 API:`/api/meta`、`/api/overview`(含价格表成本估算)、`/api/trends/daily`、
  `/api/models`、`/api/projects`、`/api/performance`(P50/P90/P99)、`/api/health`。
