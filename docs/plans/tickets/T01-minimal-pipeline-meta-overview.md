# T01 — 最小数据通路:meta + 总览(token 口径)

**Blocked by:** None — can start immediately
**Status:** done (2026-08-29)

## User story

作为个人开发者,我启动服务后在浏览器地址栏请求两个接口,就能看到本机 ZCode 的数据覆盖范围和五类 token 的总量聚合——这是 zlens 第一条贯通"数据库 → 只读查询 → HTTP JSON"的完整链路。

## What to build

打通端到端最小闭环:配置装载(默认指向本机 ZCode 数据库,路径可被环境变量覆盖)、数据源适配器协议及 ZCode 实现(只读连接、失败降级)、FastAPI 应用工厂骨架,以及 `meta`(覆盖时间范围、记录总数、生成时间)与 `overview`(总计 + 按模型分组的五类 token 聚合)两个只读端点。同时建立阶段一的核心测试资产:镜像真实三表结构的合成 fixture 库,使整套查询逻辑可在任何机器离线验证。其余端点不在本票范围,不要提前占位。

## Acceptance criteria

- [ ] 服务启动后 GET meta 端点返回数据起止时间、请求总数、响应生成时间
- [ ] GET overview 端点返回五类 token 各自总量与计算总值,并附按 provider+model 分组的同口径明细
- [ ] 全部查询断言运行在合成 fixture 库上,离线套件不触碰真实数据库即全绿
- [ ] 对一个故意残缺 schema 的合成库,相关端点返回专用的"数据源不兼容"结构化错误,而非未处理异常
- [ ] 数据库连接使用只读 URI;对真实库的手工冒烟确认查询期间 ZCode 会话不受影响
- [ ] `make check` 全绿

## Architectural decisions

- **只读是红线**:连接串必须携带 SQLite 只读参数;该决定来自设计会话中"零侵入"的产品承诺与并发实测。
- **SQL 只住在适配器里**:上游是非公开 schema,升级可能变更;所有 SQL 集中一处便于防御与未来多源隔离。
