# AI 集成开放平台 —— 阶段 2：模式 C · OAuth 2.1 用户委托（实现设计）

> 前置：`docs/superpowers/specs/2026-10-29-develop-auth-modes.md`（三模式设计，已批准）。
> 本文档把阶段 2（模式 C，OAuth 2.1 用户委托 server）的实现细节锁定，作为实施计划的依据。

---

## 一、目标与边界（锁死）

**本体**：平台新增充当 **OAuth 2.1 Authorization Server**，供**任意外部第三方**（如个人 AI 助手，**不注册平台应用**）
以「**用户委托**」方式代表平台用户访问开放数据面（REST + MCP）。

与现有 A / B 模式的硬区分：

| 维度 | A / B | C |
|------|-------|---|
| 调用主体凭证 | `Bearer <appid>:<appkey>`（应用凭证） | `Authorization: Bearer <委托access_token>`（仅此一种） |
| 谁代表用户 | A=平台级 / B=应用绑定 owner | **token 里的 `sub`=当前用户** |
| 数据范围 | A=平台级 / B=按 owner | **按 `token.sub` 过滤（复用 B 的可见性规则）** |
| 应用在平台注册？ | 是（我们的应用） | **否**（外部 client，仅注册 OAuth client） |
| 用户授权 | B=申请时同意一次 | **每个用户每次都要授权（可随时撤销）** |

**已确认决策**：
1. **client 由管理员在平台创建**（OAuth 客户端管理面，配置 redirect_uri 白名单 + 默认 scope 上限）。
2. **access/refresh token 都有状态散列落库**（支持随时撤销），校验时查库比对 sha256。
3. **数据面仅 Bearer 委托 token**，后端从 token 解出 `sub`＝用户 + 关联 client 算出可授权能力集。
4. **scope＝能力码集合**，数据范围复用 `visibility`（owner 换成 `token.sub`），不另写一套。

---

## 二、新增表（`ai_integration_oauth_*`）

### 2.1 `ai_integration_oauth_clients`（OAuth 客户端，管理员创建）
复用 `ModelMixin`（id/uuid/status/created_time/updated_time/is_deleted/...）+ 手写列（仿 `AiIntegrationAppModel`）：

| 列 | 类型 | 说明 |
|----|------|------|
| `client_id` | String(64), unique, index | 对外客户端标识（生成器，不含冒号） |
| `client_secret_hash` | String(128) | client secret 散列（sha256，不存明文） |
| `name` | String(128) | 客户端名称（唯一） |
| `description` | Text, null | 描述 |
| `enabled` | Boolean, default true | 是否启用 |
| `redirect_uris` | JSONB | 授权回调 URI 白名单（数组） |
| `allow_pkce` | Boolean, default true | 是否允许 PKCE（公共客户端） |
| `requires_approval` | Boolean, default true | 调敏感能力是否需审批（沿用语义） |
| `max_scope` | JSONB, null | 该 client 可授权的**能力码上限**（null=全部） |
| `expire_at` | DateTime, null | 客户端凭证过期时间（空为永久） |
| `created_id` / `updated_id` | Integer, FK sys_user | 创建人（管理员） |

### 2.2 `ai_integration_oauth_tokens`（委托 token，有状态落库）
复用 `ModelMixin`：

| 列 | 类型 | 说明 |
|----|------|------|
| `client_id` | String(64), index | 所属 OAuth client |
| `oauth_client_id` | Integer, FK ai_integration_oauth_clients.id | 外键（冗余定位） |
| `user_id` | Integer, FK sys_user, index | **被委托用户（`sub`）** |
| `token_type` | String(8) | `access` / `refresh` |
| `token_hash` | String(128), unique, index | 明文 token 的 sha256（**只存散列**） |
| `scope` | JSONB | 授权能力码集合（`sub` 用户被授予的能力） |
| `redirect_uri` | String(255), null | 签发时的回调（换 refresh 时校验用） |
| `code_challenge` | String(128), null | PKCE challenge（关联 authorization code） |
| `code_challenge_method` | String(16), null | `plain` / `S256` |
| `auth_code` | String(128), null | 授权码原始值（一次性，仅换 token 阶段用，换后清空） |
| `auth_code_hash` | String(128), null | 授权码散列（校验用，换后置空） |
| `expires_at` | DateTime | 过期时间（access 短 / refresh 长） |
| `revoked` | Boolean, default false | 是否已撤销 |
| `revoked_at` | DateTime, null | 撤销时间 |
| `last_used_at` | DateTime, null | 最近使用时间 |
| `created_time` | DateTime | 签发时间 |

> 说明：为支持「授权码换 token」与「PKCE」，用同一张表存 authorization code / access / refresh 三行
> （按 `token_type` 区分），授权码一次性使用（换后置空散列）。这是**单表收敛**，避免三张几乎相同的表。

---

## 三、新增端点

新增独立路由 `OAuthRouter`（前缀 `/develop/oauth`，开放面，不走应用凭证，需登录态或 client 凭证）。
为与数据面（`/develop-api`）隔离，**OAuth server 端点挂 `DevelopRouter` 同级**，但语义独立。

### 3.1 授权端点（用户侧，需登录态）
- `POST /develop/oauth/clients` · `GET /develop/oauth/clients`（管理面，管理员创建/列出 client）
- `GET /develop/oauth/authorize` → 展示授权页（需登录用户）：入参 `client_id`/`scope`/`redirect_uri`/`state`/`code_challenge`/`code_challenge_method`
  - 校验：client 存在且启用、`redirect_uri` 在白名单、`scope ⊆ client.max_scope`、请求方已登录
- `POST /develop/oauth/authorize` → 用户同意（`approve=true`）→ 生成**一次性授权码**回跳 `redirect_uri?code=..&state=..`
  - PKCE 必选（公共客户端）：校验 `code_challenge` 合法性；保存 `code_challenge`/`method`
- `POST /develop/oauth/token` → 用授权码换 access/refresh（`grant_type=authorization_code`）
  - client 凭证认证（`client_id:client_secret` 或 PKCE `code_verifier`），校验 `grant_type`/`code`/`redirect_uri`
- `POST /develop/oauth/token`（`grant_type=refresh_token`）→ 用 refresh 换新 access（钝化旧 refresh，签发新对）
- `POST /develop/oauth/revoke` → 撤销 access/refresh token（按 `token_hash` 定位，置 `revoked=true`）
- `GET /develop/oauth/userinfo` → 返回 `sub` 用户 + `scope`（供 client 产看委托身份）

### 3.2 端点鉴权
- `authorize` / `token` / `revoke` / `userinfo`：**不用**应用凭证 `get_app_api_auth`，改用：
  - `authorize`：`Depends(get_current_user)`（平台登录态）；
  - `token`：HTTP Basic / form `client_id` + `client_secret`（机密客户端）或 `code_verifier`（PKCE 公共客户端）；
  - `revoke` / `userinfo`：access token 本身（Bearer）。

---

## 四、数据面鉴权接入（核心：新鉴权依赖）

### 4.1 新依赖 `get_oauth_api_auth`
新增 `develop/oauth_auth.py`：FastAPI 依赖，解析 `Authorization: Bearer <委托access_token>`：

1. 取 token，sha256 后查 `ai_integration_oauth_tokens`（`token_type='access'`、`revoked=false`、未过期）；
2. 命中 → 取 `sub = user_id` + `scope`（能力码集合）+ 关联 `oauth_client`；
3. 构造 `AppContext`：
   - `app_id`：复用 `oauth_client.id`（作审计归属）；
   - `appid`：`client_id`；
   - `grants`：`set(scope)`（token 授予的能力码）；
   - `channels`：`resolve_channels(None, grants)`（全部默认出口）；
   - `quota`：client 的配额（或 None）；
   - `owner_user_id`：**`token.sub`（用户）** ← C 的核心；
   - `source_type`：`"oauth"`；
   - 新增 `ctx.user_id` 字段（表示委托的当前用户，默认 None）。
4. 解析/校验失败一律 401（不区分原因）。

### 4.2 `AppContext` 扩展（`auth.py`）
```python
@dataclass
class AppContext:
    ...
    source_type: str = "admin"
    owner_user_id: int | None = None
    user_id: int | None = None    # C 模式：委托 token.sub；A/B 为 None
    oauth_scope: set[str] | None = None  # C 模式：token 授予的能力码
```

### 4.3 可见性复用
各 handler 现有 `app_visible_where(app_ctx, model)` 已按 `owner_user_id` 过滤（自己+平台共享+公开）。
C 模式把 `owner_user_id` 置为 `token.sub`，**自动**得到「该用户可见范围」。无需改 handler。
（`app_visible_where` 的规则对 `owner_user_id` 非空即生效，`source_type` 不影响。）

### 4.4 REST 接入
- 新增 `OAuthApiRouter`（前缀 `/develop-api/oauth`，或复用 `OpenApiRouter`），
  处理函数用 `Depends(get_oauth_api_auth)` 拿到带 `user_id` 的 `AppContext`，
  再走 `invoke_capability(ctx, code, payload)`（能力/限流/配额/审计全部复用）。
- 说明：`invoke_capability` 已按 `ctx` 鉴权与审计；`require_capability` 用 `ctx.grants`（=token scope）。
- `audit_call` 按 `ctx.app_id` 取应用行 → **OAuth 无 `ai_integration_apps` 行**，审计需适配：
  传 `client_id` 为 `appid`，且 `app_id` 用 oauth_client 行（或审计表加可空 `client_id` 列）。
  → **决策**：`audit_call` 对 `source_type='oauth'` 的 ctx 改用 `ai_integration_oauth_clients` 行，
  并在 `ai_integration_call_logs.appid` 存 `client_id`；`app_id` FK 可空（OAuth 时存 oauth_client.id）。

### 4.5 MCP 接入
- MCP 传输层的 `McpAuthMiddleware` 现在只认 `_parse_bearer`（appid:appkey）。
  → 扩展：若 `Authorization` 不是 `appid:appkey`（无 `: ` 冒号对，是纯 token），
  则改用 `get_oauth_api_auth` 逻辑解析委托 token，得到带 `user_id` 的 `AppContext` 写入 `CURRENT_APP_CTX`。
  - `list_tools` 过滤已按 `ctx.grants`（=token scope），OAuth 同样生效。

---

## 五、安全要点

1. **state 防 CSRF**：`authorize` 生成随机 `state`，回跳时校验一致。
2. **redirect_uri 白名单**：仅允许 client 登记的 `redirect_uris`。
3. **PKCE**：公共客户端（无 secret）强制 `code_challenge`（`S256` 优先），换 token 时校验 `code_verifier`。
4. **token 只存散列**：access/refresh/授权码都存 sha256，明文仅在签发响应返回一次。
5. **撤销**：`revoke` 置 `revoked=true`；refresh 换新后旧 refresh 失效（复用旧 token 检测）。
6. **scope 上限**：授权 scope 必须 ⊆ client.max_scope，且 API 校验。
7. **敏感操作**：`cap.requires_approval` 且 client `requires_approval` 时进入审批队列（复用现有流程）。

---

## 六、迁移

新增手写迁移 `e3f4a5b6c7d8_ai_integration_oauth.py`（`down_revision='a0b1c2d3e4f5'`）。
用 `has_table`/`has_column` 幂等守卫（继承本项目迁移惯例），避免空库全链重放失败。
**revision id 必须唯一**（`b1c2d3e4f5a6`/`d4e5f6a7b8c9` 均已占用，勿用）。

---

## 七、测试计划

- `tests/test_develop_oauth_server.py`：
  1. client CRUD（管理员创建/校验 redirect_uri/scope 上限）；
  2. authorize 生成授权码（state/redirect_uri 校验、PKCE 校验）；
  3. token 用授权码换 access+refresh（校验 code 一次性、redirect_uri、PKCE）；
  4. refresh 续期（旧 refresh 失效）；
  5. revoke 后 access 不可用；
  6. 数据面：带 `user_id` 的 ctx 过滤（复用 B 可见性）；
  7. 越权：scope 超 max_scope 被拒；未授权 scope 能力被 403。

---

## 八、验收标准（对应三模式 spec §六 第 3 条）

- 外部助手走授权码 → 用户同意 → 拿 token → 调 MCP/REST 只返回 `sub`（该用户）数据；
- 敏感操作按用户角色/scope 校验；可撤销；
- 与 A/B 同走一个能力注册表与调用审计，无独立重复实现。
