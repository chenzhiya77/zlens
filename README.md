# zlens

Local-first 的 AI Coding Agent token 用量与成本分析工具。v2 支持多数据源:
ZCode(`~/.zcode/cli/db/db.sqlite`)、MiniMax Code(`~/.minimax/v2/sessions`)、
opencode(`~/.local/share/opencode/opencode.db`),列表后续可扩展。

打开即查:五类 token 总览、日趋势、按模型 / 按项目拆分、性能分位数(TTFT / 耗时)、
健康度(重试与错误)。多来源合并展示,每行可追溯到来源;全程只读,不影响正在进行的对话。

## 快速开始

```bash
make install                          # 后端 + 前端依赖 + pre-commit 钩子
cp pricing.example.json pricing.json  # 可选:启用成本折算(USD / 1M tokens)
make build-web && make dev            # 生产形态:单进程 http://127.0.0.1:8000
# 或前端热更开发:make dev-all(页面在 http://127.0.0.1:5173)
```

## 文档

- 设计规格:`docs/specs/v1-spec.md`
- 实施票:`docs/plans/tickets/`
- Agent 协作约定:[AGENTS.md](./AGENTS.md)

## 边界

- 仅统计本机、且自 ZCode 启用该数据库(2026-08-25)以来的记录;账号级总量请查看服务商 dashboard。
- 无公开定价的模型(如内部模型)默认只显示 token 数,不折算金额。
