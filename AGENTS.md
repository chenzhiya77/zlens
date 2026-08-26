# AGENTS.md — zlens

zlens 是一个 local-first 的 AI Coding Agent 用量与成本分析工具。v1 数据源只有
ZCode(`~/.zcode/cli/db/db.sqlite`,全程只读),架构上通过 `sources/base.py`
预留多源适配器接口。

本文档是仓库的**唯一事实源**,任何 coding agent 开工前必读;`CLAUDE.md` 只是它
的导入别名,不要在别名里写内容。改动仓库结构或约定时必须同步更新本文件。

## Repository Map

```
zlens/
├── AGENTS.md               # 本文件:唯一事实源
├── CLAUDE.md               # @AGENTS.md 导入别名(勿写内容)
├── Makefile                # 薄壳命令入口(见下方命令表)
├── pyproject.toml          # 项目元数据与依赖(uv 管理)
├── ruff.toml               # lint/format 配置(Python 唯一静态检查工具)
├── .pre-commit-config.yaml # local hooks,与 make check 完全同款
├── pricing.example.json    # 价格表模板;拷贝为 pricing.json 使用(gitignored)
├── docs/
│   ├── specs/              # 需求规格:v1 行为契约与验收标准
│   └── plans/tickets/      # 实施票:每票一文件,含目标/边界/验收/阻塞边
├── src/zlens/              # 后端包(Python >=3.12,src layout)
│   ├── core/               # config.py(配置)、cost.py(成本估算)、stats.py(分位数)
│   ├── sources/            # base.py 适配器协议 + zcode.py(mode=ro 只读)
│   ├── api/                # FastAPI:create_app/routers 只读端点 + SPA 静态托管
│   └── web/static_dist/    # 前端构建产物(gitignored,由 make build-web 生成)
├── tests/                  # pytest,扁平命名 test_<feature>.py;live marker 默认排除
└── frontend/               # React SPA(Vite+TS+Tailwind+ECharts+react-query,pnpm)
```

标注"随票落地"的目录由 docs/plans/tickets/ 对应票创建,不要提前空占位。

## 硬规矩(Cross-Cutting Rules)

1. **文档随代码走**:同一变更集里,影响用户视角须更新 README;影响结构/约定必须更新本文件。
2. **功能与修复必须带测试**:在 `tests/` 新增 `test_<feature>.py`;凡读取真实
   `~/.zcode/cli/db/db.sqlite` 的用例打 `@pytest.mark.live`(默认排除,保证离线套件永远可跑)。
3. **推送前必须通过 `make check`**(lint + test)。pre-commit 已在 commit 时强制同一检查链,
   禁止 `--no-verify` 绕过。

## 架构红线

- **数据源只读**:连接 `~/.zcode/cli/db/db.sqlite` 必须使用 SQLite URI `file:...?mode=ro`;
  禁止任何写入、建表、迁移类操作。查询失败必须降级为明确错误响应,不得拖垮整个服务。
- **价格外置**:金额折算只读 `pricing.json`;模型不在表内时仅展示 token 数,
  禁止硬编码任何单价。
- **分层单向**:`api → core/sources`,禁止反向 import。`sources/base.py` 是多源扩展点,
  v1 只有 zcode 一个实现;不为第二来源预写实现代码。
- **单进程交付**:生产形态为 FastAPI 托管前端构建产物;开发期 Vite proxy `/api` 到 :8000。
  前端运行期只与自家 `/api/*` 通信。

## 命令

| 命令 | 作用 |
|---|---|
| make install | uv sync + pre-commit install + pnpm install(前端) |
| make dev | 启动 FastAPI 开发服务器 http://127.0.0.1:8000(reload) |
| make dev-web | 启动 Vite 开发服务器 http://127.0.0.1:5173(/api 代理到 :8000) |
| make dev-all | 同时启动后端与 Vite 开发服务器 |
| make build-web | 前端类型检查 + 构建,产物落 src/zlens/web/static_dist |
| make test | 离线测试(默认排除 live) |
| make test-live | 含真实本地库的测试 |
| make lint | ruff check + ruff format --check |
| make format | ruff 自动修复 + 格式化 |
| make check | lint + test + build-web,推送前必跑 |

## 代码风格

- Python:ruff 规则集 E/F/I/UP,line-length=100,target py312,isort
  first-party=["zlens"],双引号。
- 测试:扁平命名 `test_<feature>.py`;私有 helper `_` 前缀;真实库用例打 live marker。
- 提交信息:祈使句一行主题,票号前缀(如 `T01: ...`);每张 ticket 至少一个独立提交。

## 版本

CHANGELOG.md 遵循 Keep a Changelog 1.1.0 + SemVer;日常累积在 `[Unreleased]`,
发版时改名为 `## [x.y.z] — YYYY-MM-DD`。
