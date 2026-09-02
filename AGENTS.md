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
│   ├── sources/            # base.py 协议 + zcode/minimax/opencode/multi 适配器,只读
│   ├── api/                # FastAPI:create_app/routers 只读端点 + SPA 静态托管
│   └── web/static_dist/    # 前端构建产物(gitignored,由 make build-web 生成)
├── tests/                  # pytest,扁平命名 test_<feature>.py;live marker 默认排除
├── scratch/                # 一次性探针/诊断脚本(gitignored,ruff 不查;结论请写进 docs/)
└── frontend/               # React SPA(Vite+TS+Tailwind+ECharts+react-query,pnpm)
```

标注"随票落地"的目录由 docs/plans/tickets/ 对应票创建,不要提前空占位。

## 硬规矩(Cross-Cutting Rules)

1. **文档随代码走**:同一变更集里,影响用户视角须更新 README;影响结构/约定必须更新本文件。
2. **功能与修复必须带测试**:在 `tests/` 新增 `test_<feature>.py`;凡读取真实
   `~/.zcode/cli/db/db.sqlite` 的用例打 `@pytest.mark.live`(默认排除,保证离线套件永远可跑)。
3. **推送前必须通过 `make check`**(lint + test)。pre-commit 已在 commit 时强制同一检查链,
   禁止 `--no-verify` 绕过。
4. **一次性探针脚本写进 `scratch/`**:仓库根的 `.py` 会被 `ruff check .` 扫并因此卡住
   `make check`;`scratch/` 已 gitignore 且 ruff 不查。探测出的结论要落到 `docs/` 或票里,
   不要留在脚本里。

## 架构红线

- **新增数据源 = 新增一个 `sources/<name>.py` 适配器**:实现 base.py 协议并接入
  MultiSource 与 Settings 路径即可,下游九端点和全部视图零改动。数据源列表见 v2 spec。
- **数据源只读**:连接任何 agent 本地库必须使用 SQLite URI `file:...?mode=ro`;
  禁止任何写入、建表、迁移类操作。查询失败必须降级为明确错误响应,不得拖垮整个服务。
- **token 四档互斥**:适配器交出的 `input/output/cache_creation/cache_read` 必须互斥且
  相加等于 `total_tokens`(契约见 `sources/models.py`)。成本是逐档乘价,档位嵌套一次就是
  同一批 token 收两次钱。上游口径不统一(ZCode 实测把缓存前缀算进 input:`cache_read <= input`
  与 `total = input + output` 全库成立;opencode/MiniMax 分档独立,opencode 还把 reasoning
  当独立加数)。**归一只能发生在适配器**,禁止在下游公式里猜谁的数字含谁;新增适配器必须拿
  真实库验一遍恒等式再合并,测试 fixture 必须照真实形状写(嵌套就写嵌套)。
- **价格外置**:金额折算只读 `pricing.json`;键是渠道三元组 `source|provider_id|model_id`
  (`sources/models.py` 的 `model_key`,别名与价格表共用同一形状),同一模型经不同渠道
  各计价一次,禁止跨渠道合并取价;渠道不在表内时仅展示 token 数,禁止硬编码任何单价。
  新增适配器必须实现 `model_keys()` 返回该三元组。
- **基准币种人民币**:`pricing.json` 只存人民币单价,行内**没有** currency 字段,行上也不标币种。
  美元价只在**录入期**折算,且只有一处是自动的:识别到 $ 截图时按 `fx_usd_cny` 折成人民币再落库,
  截图未标明币种则按人民币原样填(不乘任何汇率)。手抄的美元价由用户自己换算成数字——界面**不提供
  行内折算按钮**,因为应用分辨不出你敲的是 $ 还是 ¥,乘错一次就把人民币价变成假数。该汇率
  **不参与成本计算、也不内置默认值**(猜市场价等于造成本)。API 成本字段用中性名 `estimated_cost`。
- **两笔钱不合并**:「按量消耗」= Σ(单价 × 用量),**未计价渠道按 ¥0 计入**(产品决策
  2026-09-02:没填价就当免费,总额永远直接给出;哪些渠道没定价看行级「—」与价格表
  「待补价」分组);
  「买断支出」= Σ `buyout_amount`(一次性付款),已付的钱不因缺单价而变未知,故不守那条规则。
  两者**永不相加**,买断价也不摊成每百万等效单价(摊出来的是假精确)。`buyout_amount`
  **留空(null)与填 0 必须可区分**——把「没填」显示成 `¥0.00` 就是撒谎。价格表页的「现总价」
  是派生显示值,一律从 `/api/overview` 取,禁止写回 `pricing.json` 或在前端重算一份公式。
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
