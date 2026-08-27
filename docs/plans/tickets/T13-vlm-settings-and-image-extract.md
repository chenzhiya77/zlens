# T13 — 设置页（VLM 配置）+ 截图粘贴识别价格

**Blocked by:** T12 — 价格表管理页 + 单位标注（识别结果是预填价格表单，表单先行）
**Status:** ready-for-agent

## User story

作为 zlens 用户，我截一张模型计费标准的截图粘贴到价格表页，系统调用 VLM 识别出每个
模型的四档价格并预填到表单，我逐项确认（识别不出来的手填）后保存；VLM 的模型端点与
密钥在设置页里配置，密钥只保存在本机、绝不入库。

## What to build

后端：

- Settings 新增 VLM 配置三字段（base_url / model / api_key），读取优先级：
  环境变量 > 本机 gitignored 配置文件 > 默认值
- GET /api/settings/vlm — 返回 base_url/model 与 api_key_configured（**不回显密钥**）
- PUT /api/settings/vlm — 保存配置到本机 gitignored 配置文件；提交空密钥表示保留原值
- POST /api/settings/vlm/test — 用当前配置发一条最小文本请求验证连通性
- POST /api/pricing/extract — 接收图片 base64，调用 VLM（OpenAI 兼容 chat/completions），
  提示词要求输出结构化 JSON，解析后返回价格条目供前端预填

前端：

- 导航新增「设置」页：VLM 配置段（模型名 / Base URL / API Key 密码框 / 测试连接）
- 价格表页增加「粘贴截图识别」：拦截 Ctrl/Cmd+V 的图片粘贴，转 base64 调 extract，
  结果预填表单；识别结果可逐项修改，保存后入库

## Acceptance criteria

- [ ] 设置页可读回并保存 VLM 配置；GET 响应不含密钥明文；空密钥提交保留旧密钥
- [ ] 测试连接对配置缺失/出错给出明确错误提示
- [ ] extract 在未配置 VLM 时返回明确 503 提示（引导去设置页）
- [ ] extract 对识别失败（模型返回空/非 JSON）降级为可读错误，不崩溃
- [ ] 识别结果表单预填且可手动修改；保存遵循 T12 的校验与写回
- [ ] VLM 调用走配置的 base_url；密钥只经环境或 gitignored 配置文件，绝不进代码库
- [ ] 后端对 extract 用 mock VLM 做离线测试；live 不发真实外部请求；`make check` 全绿

## Architectural decisions

- **识别结果只是预填，不自动入库**：截图可能漏行/单位不同（每 1k vs 每 1M），
  必须用户确认——延续"不硬编错价"红线。
- **VLM 走 OpenAI 兼容协议**：一个 base_url + model + key 即可接入主流国产视觉模型
  （如硅基流动 Qwen3-VL），不绑定单一厂商。
- **密钥只写本机 gitignored 配置文件**（zlens.config.json），与 pricing.json 同模式；
  界面密码框提交空值表示"保持不变"。