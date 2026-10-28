# AI 对话嵌入与开放平台（REST / MCP）接入指南

> 目的：说明如何把平台的 **Agent / 工作流** 对话能力对外暴露，以及开放平台（REST + MCP）
> 供第三方二次开发的做法。二者凭证体系与目标形态不同，先分清再接入。

## 1. 概览：两套凭证、三套入口

平台的「对话能力对外」分**两套凭证体系**，容易混淆，先看表：

| | 资产嵌入（`/ai/embed/*`） | 开放平台（`/ai/develop-api/*`） |
|---|---|---|
| 面向 | 单个 **agent / 工作流** 的网页嵌入 | 第三方二次开发 / 系统集成 |
| 凭证 | `Bearer <asset_token>`（独立绑定 `kind + target_id`） | `Bearer <appid>:<appkey>`（应用 + `integration:*` 能力授权） |
| 粒度 | 一个资产一个短期令牌 | 一个应用多个能力 |
| 目标形态 | `agent` / `workflow` | `agent` / `app` / `workflow`（`chat.send`、`bot.use`） |
| 审计 | `ai_asset_embed_logs` | `ai_integration_call_logs` + MCP 会话表 |

- **资产嵌入**：给网页直接消费单个 agent/工作流的**流式对话 UI**，无需登录态。
- **开放平台**：给 AI 客户端 / 系统按**能力**调用平台（含非对话能力 `agent.*`、`train.*`）。
- **关键**：三种嵌入方式共用同一条后端流 `POST /ai/embed/run`（`AssetEmbedService.run_stream`），
  区别只在「如何把这条流呈现给网页」。

## 2. 三种嵌入方式

共同链路：`token → GET /ai/embed/meta 取目标信息 → POST /ai/embed/run 流式对话`。

### 2.1 聊天气泡（Script SDK）

```html
<script src="https://<host>/api/v1/ai/embed/sdk.js"></script>
<div id="ai-assistant" style="width:420px;height:620px"></div>
<script>
  AiAssistant.init({
    container: "#ai-assistant",
    token: "<asset_token>",          // 工作台为某 agent/工作流签发
    apiBase: "https://<host>/api/v1/ai",
    webBase: "https://<host>/web",
    theme: { primary: "#409eff" },   // 可选
  });
</script>
```

- SDK（`static/ai-assistant.js`）零依赖 IIFE，挂到 `window.AiAssistant`。
- 实际是**在宿主页注入一个 `<iframe>`** 指向 `webBase/#/embed?token=…&primary=…`，自身不渲染聊天 UI。
- `postMessage` 双向契约：

| 方向 | 事件 / 命令 |
|---|---|
| 上行（嵌入页 → 宿主） | `ready` `user_message` `reply_start` `reply_delta` `reply_done` `error` `token_expired` |
| 下行（宿主 → 嵌入页） | `setToken` `sendMessage` `resize` `destroy` |

- 安全：仅接受 `source==='ai-embed'`、`ev.source===iframe.contentWindow`、来源等于 `webBase` 的消息。
- 适合「组件化气泡」，宿主可订阅事件、`setToken` 续期。

### 2.2 iframe

```html
<iframe
  src="https://<host>/web/#/embed?token=<asset_token>"
  width="420" height="620"
  style="border:0;border-radius:12px"
></iframe>
```

- 直接嵌 `EmbedChat.vue`（独立公开路由，无平台登录）。
- 页面从 URL 取 token → 调 `/ai/embed/meta` → 用 `useEmbedChat` 消费 `/ai/embed/run`，按 `protocol` 自动选 transport。
- 本地 `localStorage` 按「令牌前缀 + kind + target_id」存 `sid` + 历史转写（刷新可恢复）；
  令牌过期 401 时向宿主发 `token_expired`。
- 适合「整块嵌进第三方页面」。

### 2.3 运行 API（SSE）

```bash
curl -N "https://<host>/api/v1/ai/embed/run" \
  -H "Authorization: Bearer <asset_token>" \
  -H "Content-Type: application/json" \
  -d '{"sid": "your-session-id", "message": "你好"}'
```

- 返回 **SSE 流**（`data: {…}`，收尾 `data: [DONE]`），请求头带共享契约
  `Cache-Control: no-transform`、`X-Accel-Buffering: no`、`Content-Encoding: identity`。
- **协议按目标形态分流（接入门槛，务必注意）**：

| 目标 | 帧类型 | 说明 |
|---|---|---|
| `workflow` | AI SDK UI Message Stream | `data-run` / `node-status` / `data-finish`，前端 `DefaultChatTransport` 解析 |
| `agent` | Agno 原生事件流 | `RunStarted` / `RunContent` / `ToolCall*` / `RunError` / `RunCompleted`，前端 `AgnoChatTransport` 解析 |

- 第三方用裸 SSE 需自行区分两种帧格式；若只想拿最终文本，可只关注各自事件里的文本增量，或后续接统一归一层。
- 审计在流结束时异步写入 `ai_asset_embed_logs`；首帧 `data-embed` 携带 `session_reset`，用于前端清上下文。

### 2.4 令牌治理

- 签发：工作台「更多 → 嵌入」→「生成令牌」（`POST /ai/asset-embed/tokens`，需 `module_ai:asset_embed:manage`）。
- 特征：`secrets.token_urlsafe(32)`，库内**只存 sha256 散列**（明文仅签发时返回一次）；TTL 缺省 24h（60s–30 天）；`revoked` 软吊销即时生效。
- 鉴权链 `get_embed_ctx`：散列查 → 未吊销且未过期 → 目标存在且**启用** → 否则**统一 401**（防令牌枚举），成功累加 `use_count`。
- 限流：令牌 / IP 双键固定窗口（`EMBED_RATE_TOKEN_PER_MIN` / `EMBED_RATE_IP_PER_MIN`，Redis 缺失时降级放行）。

## 3. 开放平台 REST API

- 端点：`POST /ai/develop-api/capabilities/{code}`，body `{"payload": {…}}`；
  凭证 `Authorization: Bearer <appid>:<appkey>`。
- `GET /ai/develop-api/capabilities`：按当前应用授权过滤的能力清单；
  `POST /ai/develop-api/auth/verify`：鉴权验证。
- 统一走 `invoke_capability` **五步管道**：查注册表 → 权限点校验（403）→ 限流/配额（429）→
  执行 handler → 审计（成功/拒绝/异常都写，**凭证键打码**）。
- 凭证解析 `_parse_bearer` 在**首个冒号**切分（保证 appkey 可含冒号）；校验失败统一 401。
- 管理面（需平台登录）另有：应用 CRUD、`reset-key`、用量/导出、`/apps/{id}/try` 试调、调用审批
  （`requires_approval` 能力先入待审批队列，管理员批准后执行）。

对话类能力：`chat.send`（agent/app/workflow 非流式聚合回复）、`chat.sessions`、`chat.messages`、
`bot.use`（app）。它们与资产嵌入复用同一套「目标/会话」解析（`develop/embed.py`）。

## 4. 开放平台 MCP

- 端点：`/ai/develop-api/mcp`（**Streamable HTTP**），凭证与 REST 同款 `Bearer <appid>:<appkey>`。
- 基于 `mcp` 2.x 的 **`MCPServer`**（`FastMCP` 的继任者）。
- **工具即能力**：注册表中 `mcp_tool` 非空的能力各注册一个工具，用 `inspect.Signature`
  从 `input_schema` 注入参数签名；工具调用统一走 `invoke_capability(…, method="MCP")`，**不重写业务**。
- 鉴权在传输层（`McpAuthMiddleware`）：凭证错误直接 401，不进 MCP 协议层。
- 按授权过滤：`list_tools` 只返回当前应用已授权能力（未授权不暴露）。
- 资源 / 提示词：`aistation://capabilities`（JSON 能力清单）、`platform_guide`（接入引导）。
- 会话审计：`initialize` 落一行 `ai_integration_mcp_sessions`，后续按 `mcp-session-id` 更新
  （工具调用数 / 时长 / 关闭原因）。

> 挂载说明：用 `Route` 而非 `app.mount()`——`Mount` 会对 `/mcp` 回 307 并丢自定义头，
> 很多 MCP 客户端不跟随重定向会连不上。

## 5. 边界与选型建议

| 场景 | 推荐入口 |
|---|---|
| 第三方网页嵌入单个 agent/工作流的**对话 UI** | 资产嵌入（SDK / iframe） |
| 系统直接调平台**能力**（含非对话能力） | 开放 REST / MCP |
| AI 客户端（Cursor / Claude 等）接入 | 开放 MCP（工具即能力） |
| 嵌入「AI 应用（app）」 | 当前资产嵌入仅支持 agent/workflow；app 对话走 `bot.use` |

## 6. 安全要点

- **令牌即凭证**：资产令牌可直接放网页（短期、可吊销、绑定单目标）；但**切勿把 `appid:appkey` 等
  服务端密钥写进前端**，开放平台凭证只能放在服务端请求头。
- **iframe / URL 携带令牌**：token 会进浏览器历史与 Referer，属设计取舍；
  建议 `webBase` 与宿主**同源**部署，页面加 `Referrer-Policy`，并提醒令牌短期有效、过期即失效。
- **统一 401**：资产令牌与开放平台凭证校验失败均不区分原因返回 401，避免枚举。
- **审计脱敏**：任何出口都不落 `appkey` / `access_token` 明文（审计层打码）。
