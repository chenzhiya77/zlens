# T22 — 导出 Markdown

**Blocked by:** T15 — 日期窗口参数;T19 — 表格排序参数
**Status:** done (2026-08-29)

## User story

作为用户,我想把按模型明细导出成 Markdown 表格,贴进自己的笔记或周报,或者直接喂给
LLM 让它帮我分析哪几个模型最烧钱。

## What to build

新增 `GET /api/export`,**固定输出 Markdown 表格**,不做 csv、不保留 `format` 参数。

复用 `start` / `end` / `source` / `sort` / `order` 全部参数,内容为按模型明细
(`by_model` 全字段)。

**硬要求:**

1. **null 写「未计价」**。不能是 `0` 或 `0.00`——导出的数字会被拿去做账,
   写 0 就是把"不知道"固化成"免费"。
2. **只导原始整数**。token 列导 `549382910` 而不是 `5.49 亿`,成本列导 `21.22` 而不是
   `¥ 21.22`。导出是给人二次加工的,格式化过的数字不可再算。
3. **别名不进导出**。别名是 localStorage 里的客户端状态(`frontend/src/lib/alias.ts`),
   后端不知道它存在。只导出 `model_id`,并在文件头注明别名未包含。
4. **文件头带一段口径说明**:四档互斥且相加等于总计、成本为估算值、「未计价」的含义、
   生成时间。否则这张表脱离应用后会被误读。

前端:导出按钮触发下载,文件名带日期,如 `zlens-models-2026-08-29.md`。

## Acceptance criteria

- [ ] `GET /api/export` 返回 Markdown 表格,响应头带正确的 `Content-Type` 与
      `Content-Disposition` 文件名
- [ ] `estimated_cost` 为 null 的行 → 单元格写「未计价」,**不是 0**
- [ ] token 列为原始整数,成本列不带货币符号
- [ ] 文件头含口径说明与生成时间
- [ ] `start` / `end` / `source` / `sort` / `order` 全部生效
- [ ] 新增 `tests/test_export.py`:空数据、全未计价、部分未计价三种情况
- [ ] 前端导出按钮可下载文件
- [ ] `make check` 全绿

## Out of scope

- CSV 格式:已决定不做(本机单机工具的导出主要去处是笔记/周报/LLM,md 更对路)
- 导出项目维度 / 趋势维度:本票只做按模型明细
- 别名导出:别名只存在于浏览器 localStorage,服务端拿不到

## Architectural decisions

- **只做 md,不留 `format` 参数**。加参数意味着要维护两套序列化与两套测试,
  而 csv 的用法(进 Excel 做透视)在这个工具上不成立。将来真要 csv 再加,
  届时属于新增能力而不是删减。
- **只导原始整数**。Markdown 表格的读者既有终端用户也有程序,
  格式化过的数字(「5.49 亿」)对前者好看、对后者是脏数据;原始值对两者都安全。
- **口径说明必须跟着文件走**。这份数据离开 zlens 之后就没有任何上下文了,
  「未计价」三个字如果不解释,读表的人会当成 0。
