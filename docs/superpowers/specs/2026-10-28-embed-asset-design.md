# AI 集成开放平台「嵌入」域归位设计

> 日期：2026-10-28
> 范围：AI 集成开放平台（`module_ai/develop`）+ 智能体工作台（`module_ai/workspace`）+ 新增「资产嵌入」域

## 一、背景与问题

当前把「嵌入」(embed) 与「开放 API / MCP」全部塞在 AI 集成开放平台（`/ai/develop`）里。但二者本质不同：

- **开放 API / MCP**：面向第三方**开发者**的**二次开发**，暴露平台级管理能力（创建 agent、列表、训练、资源管理等），按 `appid:appkey` 授权。
- **嵌入**：把**某一个 agent / 工作流**（具体资产）开放给外部网页**消费**（聊天气泡 / iframe / 运行 API），不涉及平台级能力。

现状的「乱」体现在：

1. 嵌入入口在 **develop 页「应用管理」的应用卡片**里，令牌走 `appid:appkey` 换票——即嵌入被绑在「应用」上，还要绕一层开发平台凭证。
2. 弹窗里要「选目标」——从一个应用去关联某个 agent/工作流，逻辑倒挂。
3. 工作流编辑器里甚至有「嵌入对话」按钮提示「请前往 AI 集成→应用管理」，入口跟资产脱节。
4. 三种嵌入形态（聊天气泡 / iframe / 运行 API）没有清晰并列，且当前只实现了 iframe / Script SDK 两种，「运行 API」形式缺失。

## 二、目标

把「嵌入」域从开放平台剥离，**绑定到具体资产（agent / 工作流）**，并让开放平台收敛为纯二次开发（REST + MCP）。

**工作台（智能体家族）**：
- 每个 agent / workflow 卡片「更多 → 嵌入」→ 弹出嵌入弹窗。
- 弹窗**不再选目标**（卡片即目标，`kind + target_id` 固定）。
- 呈现**三种嵌入形式**：聊天气泡（Script SDK）/ iframe / 运行 API（SSE）。
- 可生成 / 吊销**独立绑定该资产**的令牌，与开放平台应用无关。

**AI 集成开放平台（develop）**：
- 收敛为纯 **REST + MCP**（二次开发），按需授权。
- 去掉嵌入口、嵌入文档、嵌入令牌治理。
- 应用（appid/appkey）继续作为 REST/MCP 鉴权凭证保留。

## 三、概念模型（两域）

```
域一：AI 集成开放平台（/ai/develop）＝ 二次开发
   应用(appid/appkey) → 按需授权 REST / MCP 能力
   暴露平台级管理能力（agent.create / agent.list / train.start / verify …）

域二：工作台资产嵌入（/ai/workspace 卡片）＝ 消费单个资产
   agent / workflow 卡片「更多 → 嵌入」
      ├─ 聊天气泡（Script SDK）
      ├─ iframe（/web/#/embed）
      └─ 运行 API（POST /ai/embed/run SSE）
   令牌独立绑定 (kind + target_id)，不依赖开放平台应用
```

## 四、架构

新增独立模块 **`backend/app/plugin/module_ai/asset_embed/`**，承载整个嵌入域（从 develop 剥离）：

- 公开面（消费端）：
  - `GET /ai/embed/meta` —— 嵌入目标元信息。
  - `POST /ai/embed/run` —— 嵌入对话（SSE），Bearer 资产令牌。
  - `GET /ai/embed/sdk.js` —— SDK 脚本（无鉴权，纯代码）。
- 管理面（工作台签发/治理）：
  - `POST /ai/asset-embed/tokens` —— 签发资产令牌（body: kind, target_id, ttl）。
  - `GET /ai/asset-embed/tokens?kind=&target_id=` —— 该资产的令牌列表。
  - `PUT /ai/asset-embed/tokens/{id}/revoke` —— 吊销。

develop 模块**移除**：`EmbedRouter(/embed/*)`、`OpenApiRouter /auth/token`（换票）、`DevelopRouter /tokens`（嵌入令牌管理）、嵌入相关能力/权限（`integration:embed:*`）、接入文档嵌入段、应用卡片「嵌入」入口、`EmbedDialog` 引用。

## 五、后端改动

### 5.1 数据模型：新建资产令牌表

新建 **`AiAssetAccessTokenModel`**（表 `ai_asset_access_tokens`）：

```
id, kind(agent/workflow), target_id, token_hash(sha256, unique),
issued_by(asset_owner/exchange 明确即 admin), expires_at, revoked, use_count,
last_used_at, created_id(签发人), created_time, updated_time, is_deleted, deleted_time
```

- **无** `app_id` / `appid` —— 独立绑定资产。
- 明文令牌仅签发响应返回一次，库内只存散列。
- TTL 可配置（默认 24h，下限 60s，上限 30 天），支持手动吊销。
- 建表方式：插件启动幂等 `ensure_asset_embed_schema()`（参照 `knowledge/schema_check.py` 模式），**不走 alembic autogenerate**（本项目 dev 库 400+ 影子表，autogenerate 危险）。

### 5.2 嵌入会话映射解耦

`AiIntegrationEmbedSessionModel` 从「`(app_id, sid)` 复合唯一」改为「`(kind, target_id, sid)` 复合唯一」，去掉 app 依赖，防串会话维度改为「同资产内 sid 唯一」。

### 5.3 嵌入鉴权（`/embed/run`）

`EmbedContext` 去掉 `app_id` / `appid` / `perms` / `quota`，保留 `token_id` / `kind` / `target_id` / `expires_at` / `token_hash12`。鉴权链改为：

- 散列查令牌 → 未吊销且未过期 → 目标（agent/workflow）存在且 `enabled`。
- 任一失败统一 401（防令牌枚举）。
- 不再检查 `integration:embed:use`（签发即已授权；签发时由工作台侧校验用户权限）。
- 限流键由 `token_hash12` / IP 承担；配额 `quota` 改为按「资产」或「令牌」维度（默认不限额，可由工作台配置）。

### 5.4 工作台签发权限

工作台卡片点「嵌入 / 生成令牌」需具备对应资产的**嵌入权限**（建议新增权限码 `module_ai:asset_embed:manage`，覆盖 agent/workflow 两类资产；或复用 `module_ai:agent:update` / `module_ai:workflow:update`）。**具体以 `writing-plans` 阶段确定，spec 定为「签发者须为该资产可管理/嵌入的用户」**。

### 5.5 移除 develop 端嵌入相关

- `controller.py`：删除 `EmbedRouter /embed/*`、`/auth/token`、`/tokens` 三个路由块；保留 REST / MCP / 日志 / 用量 / 审批。
- `auth.py`：移除 `EmbedContext`、`get_embed_ctx`（迁至 asset_embed）；保留 `AppContext`、`get_app_api_auth`、`require_app_perm`。
- `service.py`：移除 `list_tokens` / `revoke_token` / 换票相关，迁至 asset_embed。
- 完善 `openapi` / `capabilities`：删除 `integration:embed:*` 权限点与 `embed` 能力（若不再需要）。

## 六、前端改动

### 6.1 工作台卡片「嵌入」入口

`workspace/index.vue` 卡片「更多」下拉新增「嵌入」项（`onCardMore` 加 `cmd === "embed"`），携带 `it.type` + `it.id` 打开嵌入弹窗。

### 6.2 嵌入弹窗（改造，工作台侧）

新建 `workspace/components/AssetEmbedDialog.vue`（或复用/重构 `develop/components/EmbedDialog.vue` 并移动）：

- 固定 `kind + target_id`（不再选目标），标题带资产名。
- 顶部**三种形式 tab**：
  1. **聊天气泡**：Script SDK（`<script src=.../embed/sdk.js>` + `AiAssistant.init(...)`）。
  2. **iframe**：`<iframe src="{webBase}/#/embed?token=...">`。
  3. **运行 API**：`POST /ai/embed/run` 的 SSE 示例（curl + EventSource + 请求体 `{sid, message}`），代码块高亮。
- 「生成令牌」+ 令牌治理表（列表 / 过期 / 吊销），调 `/ai/asset-embed/tokens`。
- 样式遵循 Element Plus / `--el-*`，与工作台一致；代码块用项目 `MarkdownRenderer` 或 `pre`+高亮。

### 6.3 三种嵌入形式代码（`examples` 层）

在嵌入弹窗内以 markdown/代码块呈现三种形式各自的接入代码。资产令牌由工作台签发后，宿主**无需再走 appid/appkey 换票**（简化）。

### 6.4 develop 页收敛

- 删除应用卡片「嵌入」按钮（`openEmbed` / `embedVisible` / `EmbedDialog` 引用 / 109-114 行 tooltip）。
- 删除接入文档「网页嵌入」卡片及 `EMBED_MD`。
- 文档保留 REST / MCP 两段。
- 调用日志 / 用量 / 审批页签只保留 REST / MCP 视角；`method=EMBED` 相关可从 develop 审计视图剔除（嵌入审计归工作台）。

### 6.5 工作流编辑器「嵌入对话」按钮

`WorkflowEditor.vue` `showEmbedHint` 改为：跳转工作台并打开该工作流的嵌入弹窗（或直接弹出资产嵌入弹窗），删除「请前往应用管理」提示。

## 七、审计归属

嵌入调用（`method=EMBED`）日志仍写入 `ai_integration_call_logs`（或迁至独立嵌入审计表），但**在 UI 上归工作台**：卡片「嵌入」弹窗内展示该资产近期嵌入调用统计（成功/失败/次数），develop 页不再展示嵌入审计。

## 八、安全性

- 令牌只存散列；明文仅签发时返回一次。
- 统一 401，防令牌枚举；TTL + 手动吊销；限流（token/IP 双键）。
- `sdk.js` 无鉴权（纯代码，不含凭证）。
- 前端代码示例中 `appkey` 永不出现（已改为资产令牌，无 appkey）。
- 删除类操作（吊销令牌）二次确认。

## 九、测试

- 后端：新建 `test_asset_embed.py`（签发/列表/吊销/鉴权/过期/防枚举/目标禁用）。更新 `test_develop_*` 移除嵌入相关断言。
- 前端：`pnpm run type-check` / `lint`。
- 手工/浏览器：工作台卡片打开嵌入弹窗、三形式代码、生成/吊销令牌；develop 页无嵌入残留；调用日志无 EMBED 污染。

## 十、迁移

- 新建 `ai_asset_access_tokens`、改造 `ai_integration_embed_sessions`（唯一约束改 `(kind,target_id,sid)`）。
- 旧的应用级嵌入令牌：**视为废弃**（dev 库可保留原数据不清理；新令牌走资产表）。接入文档 / UI 不再展示旧令牌。
- `method=EMBED` 旧日志保留不影响。

## 十一、验收标准

1. 工作台 agent/workflow 卡片「更多 → 嵌入」可打开弹窗，呈现三种嵌入形式，可生成/吊销资产的令牌。
2. 嵌入弹窗不再要求选目标、不出现 appid/appkey 换票。
3. develop 页无任何嵌入入口/文档/令牌治理残留；只保留 REST + MCP。
4. `/ai/embed/run` 凭资产令牌可正常流式对话（聊天气泡 / iframe / 运行 API 三种方式都能跑通）。
5. 权限：只有具备该资产管理/嵌入权限的用户能签发令牌。
6. 调用日志 / 用量在 develop 页不再出现 `EMBED`；嵌入审计在工作台卡片可见。
