# AI 集成开放平台·设计文档（v2：统一认证 + 嵌入能力）

- 日期：2026-10-21（v1 同日初版并已按其完成 P1；v2 为评审修订版）
- 状态：待评审
- 范围：「AI 集成」子系统**整体规划**——把平台 AI 能力（训练任务 / Agent / AI 应用 / 工作流对话 / 消息）以 **REST + MCP Server + 嵌入 SDK** 三种出口暴露给外部；**所有出口一律凭证校验、禁止匿名**；按能力品类权限控制，关键动作可审批、授权可到期、调用全审计。
- 参考模型：企业微信（WeCom）AI 开放能力 / MCP 集成；浏览器面 token 换票对齐微信 `access_token` 模型与 MCP 生态 OAuth Bearer 实践。
- **本次实施范围（P4'）**：换票 token 底座 + 三形态嵌入（见 §9）；P2 REST / P3 MCP 按 §6 统一管道排后续分期。

---

## 修订记录

| 版本 | 日期 | 变更 |
|------|------|------|
| v1 | 2026-10-21 | 初版。P1（凭证与权限底座）已按 v1 实现并全量回归。 |
| v2 | 2026-10-21 | ① **禁免密**：新增 §6 统一认证模型，原 P4「免登录 `/embed` `/public`」设计**作废**；② 嵌入范围扩为 Agent / AI 应用 / 工作流**三形态**；③ 旧工作流 `/share` 通道**整体弃用拆除**（无历史包袱）；④ embed 品类中文名定为「网页嵌入」（修正 v1 实现中的「向量嵌入」）；⑤ **界面体验列为硬性验收标准**；⑥ 明确分期：本次实施 = 换票底座 + 嵌入（P4'）。 |

---

## 1. 背景与目标

平台 `module_ai`（AI 管理）已具备：Agent、AI 应用、聊天/助手（SSE 流式）、工作流、知识库 RAG、模型与供应商、能力市场、MCP 客户端管理；`module_train` 具备训练任务与评估。但这些能力只能由平台内部登录用户经 RBAC 访问，无法被外部系统程序化调用、也无法嵌入第三方站点。

目标：外部系统申请 `appid/appkey`，经 **REST / MCP / 嵌入 SDK** 三种形态调用平台 AI 能力；**每一次调用都必须携带凭证**（服务端面 `appid:appkey`、浏览器面换票 `access_token`），按品类权限控制，全量审计可配额。

### 1.1 成功标准（v2）

- 任何开放端点**无凭证一律 401**，不存在匿名可达的业务接口。
- 第三方服务端用 `appid:appkey` 换取短期 `access_token`；浏览器与嵌入代码中**永不出现 appkey**。
- 第三方站点以 **iframe 或 `<script>` SDK** 嵌入 Agent / AI 应用 / 工作流，**换票后**免平台账号多轮流式对话，业务事件经 `postMessage` 全事件流回传宿主。
- 超出权限/过期/吊销/超限的调用被拒绝并记审计。
- **界面与交互达到平台同等质感，视觉验收不过不交付。**

---

## 2. 参考模型：企业微信 MCP 集成 + 微信 access_token

| 企业微信 / MCP 生态 | 本平台实现 |
|---------|-----------|
| 后台创建「智能机器人（AI Bot）」 | 「AI 集成」菜单创建「集成应用（app）」 |
| **Bot ID + Secret**（服务端保管） | **appid + appkey**（服务端保管，只存 sha256） |
| 按**品类（category）**授权 | 按能力品类授权：`train / agent / chat / bot / embed` |
| **短期 access_token 换票**（Secret 换 token，浏览器只持 token） | `POST /develop-api/auth/token` 换票，token 绑定 app + 目标 |
| 远程 MCP（Streamable HTTP）+ OAuth Bearer | 平台作为 MCP Server，header `Bearer appid:appkey` |
| 安全四要素：人员与 AI 权限隔离、关键动作审批、授权有效期、全量审计 | 同四要素落地 |

> 与 v1 的差异：v1 设计浏览器面为「免登录直连」，v2 评审否决（嵌入代码公开暴露，匿名面不可接受），改为换票 token（§6）。

---

## 3. 整体架构与分解

```
┌────────────────────────────────────────────────────────────────┐
│                AI 集成开放平台（module_ai/develop/）             │
│                                                                  │
│  内部管理面（RBAC，/ai/develop/*）                                │
│    ├─ 集成应用管理（appid/appkey、权限点、配额、到期、启停）        │
│    ├─ 嵌入管理（选目标、签发体验票、token 列表/吊销、代码生成）     │  ← v2 新增
│    ├─ 调用日志 / MCP 会话 / 审计统计                              │
│    └─ 接入文档（换票流程 / SDK / postMessage 契约）                │
│                                                                  │
│  开放数据面（全部凭证校验，禁匿名）                                │
│    ├─ REST     /ai/develop-api/*           Bearer appid:appkey   │
│    ├─ MCP      /ai/develop-api/mcp         header 同上（P3）       │
│    ├─ 换票     /ai/develop-api/auth/token  appid:appkey → token   │
│    ├─ 嵌入     /ai/embed/*                 Bearer <access_token>  │
│    └─ SDK      /ai/embed/sdk.js            静态脚本（不含凭证）     │
│                                                                  │
│  统一鉴权管道（六步，三出口共享，见 §6.3）                          │
│    凭证 → app 状态/到期 → 品类权限 → 配额/限流 → 执行 → 审计       │
└────────────────────────────────────────────────────────────────┘
```

### 3.1 能力品类（对外）

| 品类 | 权限点 | 能力 |
|------|-----------|------|
| `train` | `integration:train:create/query/start/stop` | 训练任务（P2） |
| `agent` | `integration:agent:create/query/update/delete` | Agent 管理（P2） |
| `chat` | `integration:chat:send/query` | 消息/会话（P2） |
| `bot` | `integration:bot:use` | 聊天机器人（P2） |
| `embed` | `integration:embed:use` | **网页嵌入**：把 Agent/AI 应用/工作流对话嵌入第三方站点（P4'） |

> 品类中文名以本表为准：`embed` = **网页嵌入**（v1 实现误写「向量嵌入」，P4' 一并修正前后端两处）。

### 3.2 分期与依赖

| 阶段 | 范围 | 状态 |
|------|------|------|
| **P1** | `ai_integration_apps` 等三表、appid/appkey、品类权限、鉴权依赖、审计、RBAC 管理面与前端「AI 集成」菜单 | **已完成（按 v1 实现）** |
| **P4'** | **换票 token 底座 + 三形态嵌入**（本设计 §6 + §9） | **本次实施** |
| P2 | 开放 REST 能力（能力注册表 + 数据归属 `source_app_id`） | 后续分期，依赖 §6 管道 |
| P3 | MCP Server（FastMCP + Streamable HTTP + 连接会话监控） | 后续分期，依赖 P2 注册表 |

---

## 4. 命名与路由

| 项 | 值 | 说明 |
|----|----|------|
| 菜单名 / 路由 / route_name | 「AI 集成」/ `/ai/develop` / `AiDevelop` | v1 已定，避让 `/ai/integration` |
| 前端组件 | `module_ai/develop/index.vue` | 页签：应用管理（操作列含「嵌入」弹窗，见 §9.8）/ 调用日志 / MCP 会话 / 接入文档 |
| 后端模块 | `app/plugin/module_ai/develop/` | 自动发现，容器前缀 `/ai` |
| 内部管理面 | `DevelopRouter`（`/ai/develop`） | RBAC `module_ai:develop:*` |
| 开放数据面 | `OpenApiRouter`（`/ai/develop-api`） | `Bearer appid:appkey` |
| **嵌入 API** | `EmbedRouter`（`/ai/embed`） | `Bearer <access_token>`，无 RBAC |
| **嵌入页（前端）** | `/#/embed?token=…` | Layout 外静态路由；`permission.ts` 白名单以 `/embed` **替换** `/share` |
| **SDK** | `GET /api/v1/ai/embed/sdk.js` | 静态 JS，无凭证；接入文档示例指向此真实地址 |

---

## 5. P1 已实现内容（v1 存档，作为 v2 基座）

> 以下为已落地代码的既成事实，P4'/P2/P3 直接复用，不再重新设计。

### 5.1 数据模型（三表，手写迁移已并链）

- `ai_integration_apps`（ModelMixin/UserMixin）：`appid`（`ai_`+8 位去混淆）、`appkey_hash`（sha256）、`name` 唯一、`enabled`、`expire_at`、`capabilities` JSONB、`quota` JSONB、`requires_approval`、`last_call_at`、`call_count`。
- `ai_integration_call_logs`（MappedBase 只增不改）：`app_id` FK、`appid` 冗余、`category`、`capability`、`log_type`、`method`（REST/MCP/EMBED）、`transport`、`session_id`、`request_path`、`request_body` 脱敏、`status`（success/denied/error）、`latency_ms`、`cost_tokens`、`result_summary`。
- `ai_integration_mcp_sessions`（MappedBase）：连接级监控，P3 消费。

### 5.2 凭证与鉴权（已实现）

- `appid = ai_ + 8 位随机（去 0/O/1/l/I）`；`appkey = token_urlsafe(32)`，只存 sha256，明文仅创建/重置返回一次；`hmac.compare_digest` 比对；失败统一 401 不区分原因。
- `Bearer appid:appkey` 解析用 `split(":", 1)`（首冒号，appkey 可含冒号）。
- 管理面 RBAC：`module_ai:develop:{query,create,update,delete,reset}`；菜单种子 `_ensure_develop_menus()` 幂等。

### 5.3 管理端页面（已实现）

四页签：应用管理（CRUD/启停/权限分组勾选/AppKey 重置，均二次确认）、调用日志（应用/品类/出海口/状态过滤）、MCP 会话、接入文档。**P4' 将重写接入文档内容并新增嵌入管理弹窗（§9.7）。**

---

## 6. 统一认证与授权模型（v2 核心，本次实施）

### 6.1 凭证两层，禁匿名

| 出口 | 凭证 | 适用 |
|------|------|------|
| REST / MCP（服务端↔服务端） | `Authorization: Bearer <appid>:<appkey>` | 第三方后端直接调用，密钥不离服务器 |
| 嵌入（浏览器↔平台） | `Authorization: Bearer <access_token>` | 浏览器只持短期票，**永不见 appkey** |

- **铁律**：任何开放业务端点缺凭证 → 401；appkey 不得出现在任何网页/嵌入代码/SDK 输出中（接入文档明确警告）。
- 管理面 RBAC（JWT）与开放面（appid/appkey、token）**完全隔离**，不共用端点、不混用鉴权语义。

### 6.2 换票端点

```
POST /api/v1/ai/develop-api/auth/token
Header: Authorization: Bearer <appid>:<appkey>
Body:   { "kind": "agent" | "app" | "workflow", "target_id": 123, "ttl": 1800? }
Resp:   { "token": "…", "expires_in": 1800, "expires_at": "YYYY-MM-DD HH:mm:ss" }
```

- 校验顺序：凭证（P1 依赖）→ `require_app_perm("integration:embed:use")`（否则 403 + denied 审计）→ 目标存在且未软删（查对应表）→ 签发。
- **token 绑定 `app + kind + target_id`**，单目标最小权限；默认 TTL 30 分钟，上限 24 小时。
- 库中只存 `token_hash = sha256(token)`；明文仅此响应返回一次。
- `issued_by`：`exchange`（换票）/ `admin`（管理弹窗「体验 Token」，固定 2 小时，方便当场试用）。
- 每次签发（成功/拒绝）写 `call_logs`：`category=embed`、`capability=token.issue`、`method=REST`。

### 6.3 六步鉴权管道（三出口共享，每请求执行）

1. **凭证校验**：解析并查 token/appid → 无效、过期、吊销、禁用、到期 → **401**（统一文案，不泄露原因）。
2. **app 状态**：`enabled=true` 且 `expire_at` 为空或未到。
3. **品类权限**：所需权限点 ∈ `app.capabilities` → 否则 **403 + denied 审计**。
4. **配额 + 限流**：
   - 配额：`app.quota` 含 `embed` 键时按「自然日次数」限额，Redis `INCR quota:embed:{app_id}:{yyyymmdd}`，超限 **429**；缺省/0 = 不限。
   - 限流：Redis 滑动窗口，**token 键 + IP 键**双限：默认每 token 30 条/分钟、每 IP 60 条/分钟（env 可调），超限 **429** + 中文提示。
5. **执行**：handler 直接复用现有 service（嵌入 run 复用与已登录 `/run/stream` 相同的 service 函数），资源落 `source_app_id = app.id`（§8 归属约定在 P4' 落地于会话行）。
6. **审计**：成功/拒绝/异常都写 `ai_integration_call_logs`（`method` 按出口 = `REST`/`MCP`/`EMBED`；token 只留前 6 位前缀）。

### 6.4 token 生命周期与续期契约

- 过期/吊销即拒（401）；吊销为管理端动作，DB 置 `revoked=true`，立即生效。
- 嵌入页收到 401 → SDK 向宿主发 `token_expired` 事件 → **第三方服务端**用 `appid:appkey` 重新换票 → 调 `AiAssistant.setToken(新票)` 热替换 → 对话（`sid` 会话）不中断。
- 客户端**没有任何刷新凭证能力**（安全边界：刷新只能发生在持有 appkey 的第三方服务端）。

### 6.5 MCP（P3 摘要，维持 v1 设计）

`FastMCP` + Streamable HTTP 挂 `/ai/develop-api/mcp`，header `Bearer appid:appkey` 走同一管道；工具调用写 `call_logs(method=MCP)`，连接/断开写 `mcp_sessions`。

---

## 7. 统一能力注册表（P2/P3 设计，v1 内容保留）

REST / MCP / 嵌入三态共用能力 handler，注册表只做「元数据 + 分发」，不重写业务：

```python
class Capability:
    code: str          # "train.create_task"
    perm: str          # "integration:train:create"
    category: str
    name: str; description: str
    input_schema: dict # JSON Schema
    returns: str
    handler: Callable  # 复用现有 service
    requires_approval: bool
    mcp: dict; rest: dict
```

- 统一层注入：`get_app_api_auth` → `AppContext(app_id, app, perms, quota)` → 六步管道（§6.3）。
- P4' 的嵌入 run **不走注册表**（它是传输层复用而非新能力暴露）；P2 起的业务能力一律入册。

---

## 8. 数据归属约定（跨分期）

- 资源（训练任务 / Agent / 消息 / 会话 / token）落 `source_app_id`（FK `ai_integration_apps.id`，空 = 内部用户创建）。
- P1 仅记录 `call_logs.app_id` 归属；**P4' 起嵌入会话行物化 `source_app_id`**；P2/P3 在创建路径统一打标并按归属过滤。

---

## 9. P4' 嵌入能力详细设计（本次实施）

### 9.1 数据模型：`ai_integration_access_tokens`

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | Integer PK | 主键 |
| `app_id` | Integer FK `ai_integration_apps.id` | 所属应用 |
| `appid` | String(64) | 冗余展示 |
| `kind` | String(16) | `agent` / `app` / `workflow` |
| `target_id` | Integer | 目标主键 |
| `token_hash` | String(128) unique index | sha256(token)，明文不落库 |
| `expires_at` | DateTime | 过期时间 |
| `revoked` | Boolean default false | 吊销标记 |
| `issued_by` | String(16) | `exchange` / `admin` |
| `use_count` / `last_used_at` | Integer / DateTime | 使用统计 |
| `created_time` / `updated_time` / `is_deleted` | — | 复用 `ModelMixin` 审计列 |

- 迁移**手写**：`down_revision` = 当前 head；建表用 `checkfirst` 语义防重放；**同一迁移内删除** `ai_workflows.share_token` 列（先 `has_column` 判断，SQLite 全链重放安全）。
- 吊销 = `revoked=true`（软语义，保留审计行）；不做物理删。

### 9.2 端点清单（P4'）

| 方法与路径 | 鉴权 | 说明 |
|---|---|---|
| `POST /ai/develop-api/auth/token` | `Bearer appid:appkey` + `embed:use` | 换票（§6.2） |
| `POST /ai/embed/run`（SSE） | `Bearer <token>` | 对话主通道，见 9.3 |
| `GET /ai/embed/meta` | `Bearer <token>` | `{kind, target_id, name, welcome, expire_at}` |
| `GET /ai/embed/sdk.js` | 无（静态代码，不含凭证） | SDK 本体 |
| `GET /ai/develop/tokens?app_id=` | RBAC `develop:query` | 该应用 token 列表（不含明文） |
| `POST /ai/develop/tokens` | RBAC `develop:create` | 管理端签体验票（issued_by=admin，2h） |
| `PUT /ai/develop/tokens/{id}/revoke` | RBAC `develop:update` | 吊销 |

### 9.3 对话通道 `POST /ai/embed/run`

- 请求：`Header: Bearer <token>`；`Body: { sid, message }`。**kind/target/app 全部从 token 推导**，请求体不携带目标参数（防参数走私）。
- 校验走 §6.3 六步管道；`sid` 与 token 绑定不匹配 → 403（防跨会话串用，见 9.4）。
- 执行：按 `kind` 复用现有 run service（`/ai/agents/{id}/run/stream`、`/ai/apps/{id}/run/stream`、`/ai/workflows/{id}/run/stream` 底层同一函数），返回 SSE 流（复用 `ui_stream_response`），响应头带 `Cache-Control: no-transform`、`X-Accel-Buffering: no`。
- 审计：`category=embed`、`capability=run`、`method=EMBED`、`request_body={sid, message截断}`、`result_summary` 记回复摘要；耗时计 `latency_ms`。

### 9.4 会话与续接

- 嵌入页生成 `sid`（uuid，存**宿主域** localStorage，key 含 token 前缀避免跨目标串号）。
- 首次 `run` 创建平台会话行（复用 run 服务既有会话模型），打 `source_app_id = app.id`；同 `sid` 续接历史。
- 闲置 TTL 24 小时（超期后同 sid 重新开新会话）；`(token, sid, app)` 三元绑定校验。

### 9.5 限流与配额

- 限流：Redis 滑动窗口，键 `rl:embed:token:{hash前缀}` 与 `rl:embed:ip:{ip}`；默认每 token 30 条/分钟、每 IP 60 条/分钟，env 可调。
- 配额：见 §6.3 第 4 步（按 app 按日）。
- 超限返回 429 中文文案，嵌入页渲染友好提示，postMessage `error`（reason=rate_limited / quota）。

### 9.6 前端嵌入页 `/#/embed`（**视觉硬标准**）

**结构**：Layout 外独立路由，整页为一个悬浮 **widget 质感对话卡片**（自适应 iframe 尺寸）：

- **头部**：目标名 + 状态点（绿 = token 有效，依据 `meta.expire_at` 本地判定；过期由覆盖层接管）+「AIStation 驱动」小字标识；加载期骨架屏。
- **消息流**：气泡式（用户右侧主色、助手左侧头像），Markdown 富文本（复用 `RichContent`）、流式打字机、引用来源可展开；工具调用事件在嵌入页**不渲染**（widget 简洁优先，事件仍在流内透传给 postMessage 监听者）。
- **输入区**：自适应高度 textarea；Enter 发送、Shift+Enter 换行；发送中态 +「停止生成」（断开 SSE 流，行为对齐既有已登录对话的停止实现）；禁用态与错误态。
- **空态**：欢迎语（`meta.welcome`，默认取目标 description，兜底「有什么可以帮你？」）。
- **品牌化**：`init({ theme: { primary } })` 注入 CSS 变量，第三方换主色；未传则平台主色。
- **状态覆盖层**：① 初始化骨架；② token 过期页（「凭证已过期」+ 自动发 `token_expired`）；③ 限流/配额内联提示条；④ 网络错误重试条。
- **视觉规范**：与平台同源（Element Plus 变量、`--el-*`，不造次级主题），气泡/圆角/阴影/间距成体系；**逐屏截图多模态验收，不合格返工**。

**接入安全**：页面只认 URL 上的 token；不存 appkey；`permission.ts` 白名单 `/share → /embed`。

### 9.7 SDK 与 postMessage 契约

**上行（iframe → 宿主，全部经 `postMessage`）**，信封：

```json
{ "source": "ai-embed", "version": 1, "event": "<name>", "payload": { } }
```

| event | payload | 时机 |
|---|---|---|
| `ready` | `{kind, target_id, name, expire_at}` | 页面初始化完成 |
| `user_message` | `{sid, message}` | 消息发出 |
| `reply_start` | `{sid}` | 开始流式回复 |
| `reply_delta` | `{sid, text}` | 流式增量（高频） |
| `reply_done` | `{sid, text}` | 回复完成（全量） |
| `error` | `{sid?, reason, message}` | 业务/网络/限流错误 |
| `token_expired` | `{}` | 401 过期/吊销，需宿主换票 |

**下行（宿主 → iframe）**：`{ "source": "ai-host", "version": 1, "command": ..., "payload": ... }`，命令集 `setToken / sendMessage / resize / destroy`。

**SDK（`sdk.js`）API**：

```js
const ai = AiAssistant.init({
  container: "#chat",            // 挂载点
  token: "<access_token>",       // 由宿主服务端换票后注入
  apiBase: "https://<host>/api/v1/ai",   // 缺省 = sdk.js 自身 src 去掉 "/embed/sdk.js" 后缀
  webBase: "https://<host>/web",         // 嵌入页地址；缺省取 apiBase 的 origin + "/web"
  theme: { primary: "#409eff" }  // 可选品牌色
});
ai.setToken(t); ai.sendMessage(s); ai.resize(w, h); ai.destroy();
ai.on(event, cb);               // 同时向 window 广播原生 message，纯 iframe 用户可自行监听
```

- SDK 校验 `event.origin === apiBase 的 origin`；宿主侧建议同样校验 iframe 来源（文档示例给出）。
- 纯 iframe 模式：`<iframe src="{webBase}/#/embed?token=…" width=… height=… style="border:0">`，直接监听 `message` 即可，不依赖 sdk.js。

### 9.8 管理 UI：应用行「嵌入」弹窗（AI 集成菜单）

- 入口：应用管理操作列新增「嵌入」按钮（`v-hasPerm module_ai:develop:query`），600px `el-dialog`，单根。
- **目标选择**：形态 radio（Agent / AI 应用 / 工作流）+ 目标下拉（searchable，数据源复用各自 list 接口，仅列启用项）。
- **代码生成**：`el-tabs` 两页签——「iframe 直嵌」与「Script SDK」；代码块（等宽、可复制按钮）；下方说明「token 为短期凭证：请服务端调 `/auth/token` 换票获取，代码中为 `{access_token}` 占位符」。
- **体验 Token**：主按钮签 2 小时票 → 弹一次性展示（复用 AppKey reveal 交互样式）→「填入代码」自动替换占位符，便于当场复制即用。
- **Token 列表**：该应用全部 token（形态/目标/签发方式/过期/使用次数/最后使用/状态），吊销按钮 + **二次确认**（文案含影响范围与不可逆性）。
- **事件契约**：postMessage 事件小表（9.7 压缩版）+ 指向接入文档页签。
- **接入文档页签重写**：换票 curl 流程、SDK 完整示例（指向真实 `sdk.js` 地址）、事件表；P2/P3 端点标注「即将开放」，**删除不存在的 `/chat/send` 误导示例**。
- **品类名修正**：`embed: "向量嵌入" → "网页嵌入"`（`backend/.../capabilities.py` 与前端 `CATEGORIES` 两处同步）。

### 9.9 旧通道拆除清单（无历史包袱）

| 项 | 处理 |
|---|---|
| 前端路由 `/share` + `views/module_ai/workflow/ShareRun.vue` | 删除 |
| `plugins/permission.ts` 白名单 | `/share` → `/embed` |
| `AiWorkflowModel.share_token` 列 | 迁移删除（`has_column` 防护） |
| `POST /workflows/{id}/share`、`POST /workflows/share/run` | 删除端点 |
| `generate_share_token` / `_get_by_share_token` / `share_ui_stream` / `AiWorkflowShareRunSchema` | 删除 |
| 工作流编辑器「分享」「复制嵌入代码」按钮及相关状态 | 删除，替换为提示文案：「对话嵌入请前往 AI 集成 → 嵌入」 |
| share 相关测试 | 删除或改造为断言「端点已不存在」 |

---

## 10. 测试方案

- **纯逻辑（`PYTEST_NO_APP=1` 快速模式）**：token 生成/哈希/过期判定、换票入参校验、权限点判定、postMessage 事件构造。
- **DB**：`ai_integration_access_tokens` 建表与 CRUD；迁移 upgrade/downgrade 往返；**SQLite 空库全链重放**（含删 `share_token` 列分支）。
- **集成**：
  - 换票四态：正常 200 / 无 `embed:use` 403 / app 禁用或过期 401 / 目标不存在 404。
  - run 四态：无凭证 401 / 过期 401 / 吊销 401 / 超限 429；sid 绑定不匹配 403。
  - 三形态（agent/app/workflow）run 各至少一条成功用例（mock run service）。
  - 审计断言：签发与 run 均落 `call_logs`，`method=EMBED`、`category=embed`，token 脱敏。
  - 旧 `/share` 端点 404、`share_token` 列不存在。
- **前端**：`pnpm run type-check` 与 `pnpm run lint` 零新增报错。
- **视觉验收（硬标准）**：嵌入页各状态（骨架/正常对话/过期/限流/网络错误）+ 嵌入弹窗逐屏截图，与平台既有页面对照核对质感，**不通过不交付**。
- **端到端**：仓库内置**演示宿主页**（第三方视角静态 HTML：页内提供「凭证换票」表单，粘贴 appid/appkey **模拟宿主服务端**完成换票，并醒目标注「生产环境必须在服务端换票，切勿把 appkey 放进网页」），实测 iframe 与 SDK 两模式：换票 → 多轮流式 → 7 类事件齐收 → `setToken` 续期不断话；旧 `/share` 链接确认失效。
- **回归**：`uv run pytest -q -n 4` 全量；既有 develop 测试保持全绿。

---

## 11. 里程碑与验收（v2）

- **P4' 验收（本次）**：
  1. `/ai/embed/*` 无凭证一律 401——**零匿名面**。
  2. 管理弹窗完成「选目标 → 签体验票 → 生成两种嵌入代码 → 列表/吊销」闭环，交互与平台风格一致。
  3. 演示宿主页两模式（iframe / SDK）**换票后**免平台账号多轮流式对话。
  4. 宿主收到全部 7 类 postMessage 事件；`setToken` 过期续期不断话。
  5. 审计可见 `method=EMBED` 完整流水；限流/配额生效返回 429。
  6. 旧 `/share` 链接失效；工作流旧分享 UI 不复存在。
  7. **视觉验收通过**（截图逐屏核对，结构、状态、质感达标）。
- **P2 验收**：appid 调用「创建训练任务/创建 Agent/发消息/聊天」，资源归属对应 app，超权限 403。
- **P3 验收**：MCP header 鉴权调用工具；管理端能看到连接与工具调用流水。

---

## 12. 待办 / 风险

- **换票依赖第三方服务端**：嵌入方必须有后端才能换票（安全模型的既定代价），接入文档必须醒目标注；无后端的场景不提供降级匿名通道（禁免密是铁律）。
- **token 暴露面**：嵌入页 URL 中的 token 可被宿主页访客读取——以「短 TTL + 单目标 + 限流 + 可吊销」四重缓解；文档建议宿主页不把 iframe src 回写进可公开爬取的 DOM。
- **迁移风险**：删列与建表同链，谨防 `autogenerate`；SQLite 回归必须覆盖。
- **文档超前误导**：P2/P3 未开放端点在接入文档标注「即将开放」，只展示真实可用示例。
- **appkey 保管**（v1 遗留）：明文仅一次返回，前端只展示引导提示。
- **SSE 经代理缓冲**：响应头 `no-transform` / `X-Accel-Buffering: no` 必须带，避免整块到达。
