# 阶段 2：OAuth 2.1 用户委托 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** 让平台充当 OAuth 2.1 Authorization Server，供外部第三方（个人 AI 助手）以「用户委托」方式代表平台用户访问开放数据面（REST+MCP），数据按 `token.sub` 过滤。

**Architecture:** 新增 `ai_integration_oauth_clients`（管理员创建的 OAuth client）与 `ai_integration_oauth_tokens`（有状态散列落库的 access/refresh/授权码）两张表。新增 OAuth server 端点（authorize/token/revoke/userinfo）。新增 `get_oauth_api_auth` 依赖与 `AppContext.user_id` 字段，把 `owner_user_id` 置为 `token.sub` 复用现有 `visibility` 过滤；审计对 OAuth 走独立分支。REST 与 MCP 数据面都接入该鉴权。

**Tech Stack:** FastAPI + SQLAlchemy 2.0 + Pydantic v2 + pyjwt + hashlib/hmac；复用现有 `develop.{auth,service,registry,openapi,visibility,handlers}`。

**Spec:** `docs/superpowers/specs/2026-10-29-develop-oauth-server-design.md`

## Global Constraints

- 所有用户回复用中文；代码注释用中文；提交信息 `feat(auth): 中文描述`。
- token/secret/授权码**只存 sha256 散列**（`hashlib.sha256` + hex），明文仅在签发响应返回一次。
- 鉴权失败一律 401「鉴权失败」，**不区分失败原因**（防枚举）。
- 数据面仅 `Authorization: Bearer <委托access_token>`；OAuth 端点不用应用凭证 `get_app_api_auth`。
- 迁移用 `has_table`/`has_column` 幂等守卫；`down_revision='a0b1c2d3e4f5'`；revision id 用 `e3f4a5b6c7d8`（唯一，未占用）。
- alembic 链必须保持唯一 head（`get_heads()` 单元素），否则应用启动 `SystemExit`。
- 开发用 `--no-reload`，改后端后须杀干净（`Get-CimInstance` 按 `main.py` 命令行）并重启验证 `/openapi.json`。
- 测试用 SQLite；`PYTEST_NO_APP=1` 纯逻辑用例跳应用构造。

## Review Focus

1. **授权码一次性**：`token` 用 authorization code 换 token 后，同 code 再次兑换必须失败（code 已消费）。→ Task 3 测试。
2. **refresh 换新后旧 refresh 失效**：防止 refresh token 重放。→ Task 4 测试。
3. **revoke 后 access 立即不可用**：撤销的 token 再调数据面必须 401。→ Task 5 测试。
4. **scope 越权**：授权 scope 超出 `client.max_scope` 必须被拒；未授权 scope 的能力被 403。→ Task 2/7 测试。
5. **数据面按 sub 过滤**：委托 token 代表用户查询，只返回该用户可见（自己+平台共享+公开）的数据，看不到他人私有。→ Task 7 测试。
6. **redirect_uri 白名单与 PKCE**：非白名单 redirect_uri 被拒；公共客户端缺/错 `code_verifier` 被拒。→ Task 2 测试。

---

### Task 1: 新增 OAuth 表模型（clients + tokens）+ 迁移

**Files:**
- Modify: `backend/app/plugin/module_ai/develop/model.py`（追加两个模型类）
- Create: `backend/app/alembic/versions/e3f4a5b6c7d8_ai_integration_oauth.py`
- Test: `backend/tests/test_develop_oauth_models.py`

**Interfaces:**
- Produces: `AiIntegrationOauthClientModel`（表 `ai_integration_oauth_clients`，列见 spec §2.1）、`AiIntegrationOauthTokenModel`（表 `ai_integration_oauth_tokens`，列见 spec §2.2）。两者继承 `ModelMixin`。
- 关键字段名（供后续任务引用）：
  - Client: `client_id`(str,unique) / `client_secret_hash`(str) / `name` / `enabled`(bool) / `redirect_uris`(list) / `allow_pkce`(bool) / `requires_approval`(bool) / `max_scope`(list|None) / `expire_at`(datetime|None)。
  - Token: `client_id`(str) / `oauth_client_id`(int) / `user_id`(int) / `token_type`(str: access/refresh) / `token_hash`(str,unique) / `scope`(list) / `redirect_uri`(str|None) / `code_challenge`(str|None) / `code_challenge_method`(str|None) / `auth_code`(str|None) / `auth_code_hash`(str|None) / `expires_at`(datetime) / `revoked`(bool) / `revoked_at`(datetime|None) / `last_used_at`(datetime|None)。

- [x] **Step 1: 写 model.py 两个模型类**

在 `model.py` 追加（仿 `AiIntegrationAppApplyModel` 用 `ModelMixin`，手写列）。JSONB 用 `from sqlalchemy.dialects.postgresql import JSONB`（该文件已 import）。

- [x] **Step 2: 写迁移文件**

`down_revision='a0b1c2d3e4f5'`，`revision='e3f4a5b6c7d8'`。upgrade 里对两表 `if "..." not in insp.get_table_names(): op.create_table(...)`（含 `ModelMixin` 的 id/uuid/status/created_time/updated_time/is_deleted/deleted_time/created_id/updated_id/deleted_id 列），并建索引（client_id/token_hash/user_id/oauth_client_id）。downgrade 反向 `drop_table`。

- [x] **Step 3: 写测试（模型字段可实例化 + 迁移可导入）**

`tests/test_develop_oauth_models.py`：
```python
def test_oauth_models_instantiations(test_client):
    from app.plugin.module_ai.develop.model import AiIntegrationOauthClientModel, AiIntegrationOauthTokenModel
    c = AiIntegrationOauthClientModel(client_id="c1", client_secret_hash="h", name="n", enabled=True, redirect_uris=["https://x/cb"], max_scope=["agent.list"])
    assert c.client_id == "c1" and c.max_scope == ["agent.list"]
    t = AiIntegrationOauthTokenModel(client_id="c1", oauth_client_id=1, user_id=2, token_type="access", token_hash="th", scope=["agent.list"], expires_at=datetime.now())
    assert t.token_type == "access" and t.revoked is False
```

- [x] **Step 4: 跑测试**

Run: `PYTEST_NO_APP=1 pytest tests/test_develop_oauth_models.py -q`
Expected: PASS

- [x] **Step 5: 提交**

```bash
git add backend/app/plugin/module_ai/develop/model.py backend/app/alembic/versions/e3f4a5b6c7d8_ai_integration_oauth.py backend/tests/test_develop_oauth_models.py
git commit -m "feat(auth): 阶段2新增OAuth客户端与委托token表模型"
```

---

### Task 2: OAuth client CRUD（管理员创建）+ 授权页展示与授权码签发

**Files:**
- Create: `backend/app/plugin/module_ai/develop/oauth_server.py`
- Create: `backend/app/plugin/module_ai/develop/oauth_schema.py`
- Modify: `backend/app/plugin/module_ai/develop/controller.py`（加 OAuthRouter + 端点）
- Modify: `backend/app/plugin/module_ai/develop/schema.py`（加 client create schema，或放 oauth_schema.py）
- Test: `backend/tests/test_develop_oauth_client.py`

**Interfaces:**
- Consumes: Task 1 的两个模型。
- Produces: `OAuthClientService`（`create_client`/`list_clients`/`verify_client`/`generate_authorize_code`）、`OAuthAuthorizeService` 或并入 `OAuthClientService` 的方法。
  - `create_client(data, auth) -> dict`（返回一次性明文 `client_secret`）
  - `list_clients() -> list[dict]`
  - `verify_client_credentials(client_id, client_secret) -> AiIntegrationOauthClientModel | None`
  - `build_authorize_page(...)` / `issue_authorization_code(client, user, scope, redirect_uri, code_challenge, method) -> dict`（含 `code`+`state`）

- [x] **Step 1: 写 `oauth_schema.py`（client create schema + 授权表单 schema）**

Pydantic：`OAuthClientCreateSchema`（name/description/redirect_uris/allow_pkce/requires_approval/max_scope/expire_at）、`OAuthAuthorizeSchema`（client_id/scope/redirect_uri/state/code_challenge/code_challenge_method）。

- [x] **Step 2: 写 `oauth_server.py` 的 `OAuthClientService`**

- `_generate_client_id()`/`_generate_client_secret()`/`_generate_auth_code()`：URL-safe 随机串（复用 `secrets.token_urlsafe`）。
- `_hash(value)`：`hashlib.sha256(value.encode()).hexdigest()`。
- `create_client`：校验 name 唯一（`is_deleted=false`）、归一 `redirect_uris`/`max_scope`、生成 id/secret、存散列、返回 `_client_to_dict(client, secret=...)`（只此一次带明文）。
- `verify_client_credentials`：按 `client_id` 查（enabled/expire_at/散列比对，与 `verify_appkey` 同法）。
- `issue_authorization_code`：校验 redirect_uri 在白名单、scope ⊆ max_scope（`max_scope` 非 None 时）；生成一次性 auth code，落 `ai_integration_oauth_tokens` 行（`token_type='auth'`，存 `auth_code`/`auth_code_hash`/`code_challenge`/`method`/`user_id`/`scope`/`redirect_uri`/`expires_at`）；返回 `{code, state}`。

- [x] **Step 3: 写测试（create + redirect_uri 校验 + scope 上限 + PKCE 校验）**

`tests/test_develop_oauth_client.py`：
- `test_create_client_returns_secret_once`：创建后返回含明文 `client_secret`；库里只有散列（查询 `client_secret_hash != 明文`）。
- `test_issue_code_redirect_uri_whitelist`：非白名单 redirect_uri → `CustomException`(400)。
- `test_issue_code_scope_exceeds_max`：`max_scope=["agent.list"]` 时 scope 含 `"model.list"` → 拒绝(400)。
- `test_issue_code_pkce_challenge`：`allow_pkce` 且传 `code_challenge`，返回 code 行带 `code_challenge`/`method`。

- [x] **Step 4: 跑测试**

Run: `PYTEST_NO_APP=1 pytest tests/test_develop_oauth_client.py -q`
Expected: PASS

- [x] **Step 5: 提交**

```bash
git add backend/app/plugin/module_ai/develop/oauth_server.py backend/app/plugin/module_ai/develop/oauth_schema.py backend/tests/test_develop_oauth_client.py
git commit -m "feat(auth): 阶段2OAuth客户端CRUD与授权码签发"
```

---

### Task 3: OAuth authorization code → token 换取（授权码一次性）

**Files:**
- Modify: `backend/app/plugin/module_ai/develop/oauth_server.py`
- Test: `backend/tests/test_develop_oauth_token_exchange.py`

**Interfaces:**
- Consumes: `OAuthClientService`（`verify_client_credentials`）、Task 1 Token 模型、Task 2 `issue_authorization_code`。
- Produces: `OAuthTokenService`：
  - `exchange_code(grant_type, client, code, redirect_uri, code_verifier) -> dict`（access+refresh）
  - `_issue_access_and_refresh(client, user_id, scope, redirect_uri, code_challenge) -> dict`

- [x] **Step 1: 写测试（先 code 兑换成功，再同 code 兑换必须失败）**

`tests/test_develop_oauth_token_exchange.py`：
- `test_exchange_code_returns_token_pair`：先 `issue_authorization_code` 得 code；用 `verify_client_credentials` + `exchange_code` 兑换 → 返回含 `access_token`/`refresh_token`/`token_type="Bearer"`/`expires_in`/`scope`。
- `test_exchange_code_code_used_once`：同 code 第二次 `exchange_code` → `CustomException`(400「授权码已失效」)。
- `test_exchange_code_pkce_verifier`：`code_challenge_method='S256'` 时，传入错误 `code_verifier` → 拒绝(400)；正确 verifier → 通过。

- [x] **Step 2: 跑测试确认失败**

Run: `PYTEST_NO_APP=1 pytest tests/test_develop_oauth_token_exchange.py -q`
Expected: FAIL（方法未定义）

- [x] **Step 3: 实现 `exchange_code` + `_issue_access_and_refresh`**

校验 `grant_type=='authorization_code'`、client 凭证、redirect_uri 匹配、授权码未消费（`auth_code_hash` 匹配且未用）、PKCE verifier（`S256` 用 `sha256(verifier).hexdigest()` 比对 `code_challenge`）。成功后**置空 `auth_code`/`auth_code_hash`**（一次性），生成 access（短 TTL，如 `settings.ACCESSTOKEN ...` 用 `settings.OAUTH_ACCESS_TOKEN_TTL` 或默认 3600s）与 refresh（默认 30 天）两行，各存散列，返回明文一次。

- [x] **Step 4: 跑测试确认通过**

Run: `PYTEST_NO_APP=1 pytest tests/test_develop_oauth_token_exchange.py -q`
Expected: PASS

- [x] **Step 5: 提交**

```bash
git add backend/app/plugin/module_ai/develop/oauth_server.py backend/tests/test_develop_oauth_token_exchange.py
git commit -m "feat(auth): 阶段2OAuth授权码换token（一次性）"
```

---

### Task 4: refresh token 续期（换新后旧 refresh 失效）

**Files:**
- Modify: `backend/app/plugin/module_ai/develop/oauth_server.py`
- Test: `backend/tests/test_develop_oauth_refresh.py`

**Interfaces:**
- Consumes: Task 3 `_issue_access_and_refresh`。
- Produces: `OAuthTokenService.refresh(client, refresh_token) -> dict`

- [x] **Step 1: 写测试**

`tests/test_develop_oauth_refresh.py`：
- `test_refresh_returns_new_pair`：兑换得 refresh；`refresh(client, refresh_token)` → 返回新 access+refresh。
- `test_refresh_old_refresh_invalid`：用第一次的 refresh 换新后，再次用旧 refresh 换 → `CustomException`(401「令牌已失效」)（旧 refresh 行被 `revoked=true`）。

- [x] **Step 2: 跑测试确认失败**

Run: `PYTEST_NO_APP=1 pytest tests/test_develop_oauth_refresh.py -q`
Expected: FAIL

- [x] **Step 3: 实现 `refresh`**

按 `token_hash` 查 `token_type='refresh'` 且未撤销未过期；命中 → 置该行 `revoked=true`/`revoked_at=now`（旧 refresh 作废），再 `_issue_access_and_refresh` 生成新对。

- [x] **Step 4: 跑测试确认通过**

Run: `PYTEST_NO_APP=1 pytest tests/test_develop_oauth_refresh.py -q`
Expected: PASS

- [x] **Step 5: 提交**

```bash
git add backend/app/plugin/module_ai/develop/oauth_server.py backend/tests/test_develop_oauth_refresh.py
git commit -m "feat(auth): 阶段2OAuth refresh续期与旧refresh失效"
```

---

### Task 5: revoke 撤销 + AppContext.user_id 字段 + 数据面鉴权依赖

**Files:**
- Modify: `backend/app/plugin/module_ai/develop/oauth_server.py`（revoke 方法）
- Create: `backend/app/plugin/module_ai/develop/oauth_auth.py`（`get_oauth_api_auth`）
- Modify: `backend/app/plugin/module_ai/develop/auth.py`（`AppContext` 加 `user_id`）
- Test: `backend/tests/test_develop_oauth_revoke_auth.py`

**Interfaces:**
- Consumes: Task 1 模型、Task 4 前各方法。
- Produces: `OAuthTokenService.revoke(token) -> None`；`get_oauth_api_auth` 依赖返回带 `user_id`/`source_type='oauth'` 的 `AppContext`。

- [x] **Step 1: 给 `AppContext` 加 `user_id` 字段**

`auth.py` 的 `AppContext` dataclass 追加：`user_id: int | None = None` 与 `oauth_scope: set[str] | None = None`。

- [x] **Step 2: 写测试**

`tests/test_develop_oauth_revoke_auth.py`：
- `test_revoke_invalidates_token`：兑换得 access；`revoke(access_token)` 后 `get_oauth_api_auth`（或内部校验函数）→ 401。
- `test_get_oauth_api_auth_builds_ctx`：伪造有效 access 行（未撤销未过期），解析 `Bearer <token>` → 返回 ctx 的 `user_id==sub`、`source_type=='oauth'`、`grants==set(scope)`、`owner_user_id==sub`。
- `test_get_oauth_api_auth_bad_token_401`：无效 token → `CustomException`(401)。

- [x] **Step 3: 实现 `revoke` 与 `get_oauth_api_auth`**

`revoke`：按 `token_hash` 查行，置 `revoked=true`/`revoked_at=now`（刷新 `last_used_at`）。
`get_oauth_api_auth(Authorization: str|None = Header(None))`：`_parse_oauth_bearer`（纯 token，无冒号 appid:appkey）→ sha256 查 `ai_integration_oauth_tokens`（access、未撤销、未过期）→ 取 `sub=user_id`+`scope`+关联 client → 构造 `AppContext(app_id=client.id, appid=client.client_id, grants=set(scope), channels=resolve_channels(None, set(scope)), quota=None, source_type='oauth', owner_user_id=user_id, user_id=user_id, oauth_scope=set(scope))`。失败统一 401。

- [x] **Step 4: 跑测试确认通过**

Run: `PYTEST_NO_APP=1 pytest tests/test_develop_oauth_revoke_auth.py -q`
Expected: PASS

- [x] **Step 5: 提交**

```bash
git add backend/app/plugin/module_ai/develop/oauth_server.py backend/app/plugin/module_ai/develop/oauth_auth.py backend/app/plugin/module_ai/develop/auth.py backend/tests/test_develop_oauth_revoke_auth.py
git commit -m "feat(auth): 阶段2OAuth撤销与数据面鉴权依赖"
```

---

### Task 6: OAuth 端点接入 controller（authorize/token/revoke/userinfo）+ REST 数据面

**Files:**
- Modify: `backend/app/plugin/module_ai/develop/controller.py`
- Test: `backend/tests/test_develop_oauth_endpoints.py`

**Interfaces:**
- Consumes: Task 2/3/4/5 服务方法与 `get_oauth_api_auth`。
- Produces: `OAuthRouter`（前缀 `/develop/oauth`），端点 `GET/POST /authorize`、`POST /token`、`POST /revoke`、`GET /userinfo`；`OpenApiRouter` 增 OAuth 数据面端点（或复用 open_capability_invoke，但用 `get_oauth_api_auth`）。

- [x] **Step 1: 加 OAuthRouter 端点**

`authorize`：`GET` 展示授权页（`Depends(get_current_user)`）、`POST` 同意 → `issue_authorization_code` 后重定向 `redirect_uri?code&state`。`token`（Form，`client_id`/`client_secret` 或 PKCE）、`revoke`、`userinfo`（`Depends(get_oauth_api_auth)`）。重定向用 `RedirectResponse`。

- [x] **Step 2: 写端点集成测试**

`tests/test_develop_oauth_endpoints.py`（用 test_client 登录态 + 造 client/token）：
- `test_authorize_post_redirects_with_code`、`test_token_endpoint_returns_pair`、`test_revoke_endpoint`、`test_userinfo_returns_sub`。

- [x] **Step 3: 跑测试确认通过**

Run: `pytest tests/test_develop_oauth_endpoints.py -q`
Expected: PASS

- [x] **Step 4: 提交**

```bash
git add backend/app/plugin/module_ai/develop/controller.py backend/tests/test_develop_oauth_endpoints.py
git commit -m "feat(auth): 阶段2OAuth端点接入controller"
```

---

### Task 7: 数据面按 sub 过滤 + 审计独立分支（OAuth 无应用行）

**Files:**
- Modify: `backend/app/plugin/module_ai/develop/openapi.py`（`audit_call` 对 OAuth 分支）
- Modify: `backend/app/plugin/module_ai/develop/service.py`（`log_call` 或新增 OAuth 审计）
- Modify: `backend/app/plugin/module_ai/develop/handlers/*.py` 无需改（`app_visible_where` 已按 `owner_user_id`）
- Test: `backend/tests/test_develop_oauth_data_view.py`

**Interfaces:**
- Consumes: Task 5 `get_oauth_api_auth`。
- Produces: 让 `invoke_capability` 对 OAuth ctx 审计不依赖 `ai_integration_apps` 行。

- [x] **Step 1: 写测试（委托 token 数据面过滤 + 审计不崩）**

`tests/test_develop_oauth_data_view.py`：
- `test_oauth_invoke_filters_by_sub`：造两个用户（100/200）私有知识库＋平台共享库；用 `get_oauth_api_auth` 得到的 ctx（sub=100, scope 含 knowledge.list）+ `invoke_capability(ctx,'knowledge.list',...)` → 只返回用户 100 的私有 + 平台共享，**不含** 200 的私有。
- `test_oauth_invoke_audit_does_not_crash`：OAuth ctx 调 `invoke_capability` 成功，审计调用不抛（`ai_integration_call_logs` 落库，`appid` 为 client_id）。

- [x] **Step 2: 跑测试确认失败**

Run: `pytest tests/test_develop_oauth_data_view.py -q`
Expected: 部分失败（审计依赖应用行）

- [x] **Step 3: 实现审计适配**

`openapi.audit_call`：改造为读取 `ctx.app`（或直接传 `ctx`），当 `ctx.source_type=='oauth'` 时用 `ai_integration_oauth_clients` 行（`id`/`client_id`），调用 `log_call` 的 OAuth 分支（新增 `log_oauth_call(client_row, ...)`，不更新 `ai_integration_apps` 计数；`ai_integration_call_logs.app_id` 存 `oauth_client.id`，`appid` 存 `client_id`）。若 `app_id` FK 非空限制冲突，则迁移把 `ai_integration_call_logs.app_id` 改可空（见 Task 8）。

- [x] **Step 4: 跑测试确认通过**

Run: `pytest tests/test_develop_oauth_data_view.py -q`
Expected: PASS

- [x] **Step 5: 提交**

```bash
git add backend/app/plugin/module_ai/develop/openapi.py backend/app/plugin/module_ai/develop/service.py backend/tests/test_develop_oauth_data_view.py
git commit -m "feat(auth): 阶段2OAuth数据面按sub过滤与审计适配"
```

---

### Task 8: 审计表 app_id 可空（如需要）+ MCP 数据面接入

**Files:**
- Modify: `backend/app/plugin/module_ai/develop/mcp_server.py`（`McpAuthMiddleware` 支持 OAuth token）
- Modify: `backend/app/plugin/module_ai/develop/model.py`（`AiIntegrationCallLogModel.app_id` 可空，如冲突才需）
- Modify: `backend/app/alembic/versions/...`（若改列）
- Test: `backend/tests/test_develop_oauth_mcp.py`

**Interfaces:**
- Consumes: Task 5 `get_oauth_api_auth` 的解析逻辑。
- Produces: MCP 传输层在收到纯 token 时解析为 OAuth ctx。

- [x] **Step 1: 写测试（MCP 工具调用带委托 token）**

`tests/test_develop_oauth_mcp.py`：模拟 `McpAuthMiddleware` 对 `Bearer <oauth_access_token>`（无冒号）解析得到带 `user_id` 的 ctx，`list_tools` 按 scope 过滤。

- [x] **Step 2: 跑测试确认失败**

Run: `pytest tests/test_develop_oauth_mcp.py -q`
Expected: FAIL

- [x] **Step 3: 实现 MCP 鉴权分支**

`McpAuthMiddleware.__call__`：`_parse_bearer` 若得到 `(appid, appkey)` 走原逻辑；否则若 Header 是纯 token（无冒号），改为调 `oauth_auth` 的解析函数得到 ctx 并写入 `CURRENT_APP_CTX`（`source_type='oauth'`）。若 `ai_integration_call_logs.app_id` 非空约束导致 OAuth 审计失败，则把该列改为 nullable（迁移 + model 同步）。

- [x] **Step 4: 跑测试确认通过**

Run: `pytest tests/test_develop_oauth_mcp.py -q`
Expected: PASS

- [x] **Step 5: 提交**

```bash
git add backend/app/plugin/module_ai/develop/mcp_server.py backend/app/plugin/module_ai/develop/model.py backend/tests/test_develop_oauth_mcp.py
git commit -m "feat(auth): 阶段2OAuth接入MCP数据面"
```

---

### Task 9: 新增 OAuth app 权限点 & 菜单（管理员管理入口）

**Files:**
- Modify: `backend/app/plugin/module_ai/develop/capabilities.py`（新增 `module_ai:develop:oauth` 权限点，或复用 `module_ai:develop:*`）
- Modify: `backend/app/scripts/init_app.py`（如项目模式需要 `_ensure_ai_menus` 注册 OAuth 菜单/权限）
- Test: `backend/tests/test_develop_oauth_perms.py`

**Interfaces:**
- Consumes: 前面的表与端点。
- Produces: 管理面可列出/创建 OAuth client 的权限与菜单入口。

- [x] **Step 1: 确认现有 `AuthPermission(["module_ai:develop:create"])` 是否已覆盖**

若 `module_ai:develop:*` 已含 create，OAuth client 管理端点直接用它（无需新权限点）。**先核对** `perms.py`/`capabilities.py` 现有 `develop` 权限点。

- [x] **Step 2: 更新菜单权限（如需）**

若需独立权限点/菜单，在 `init_app._ensure_ai_menus` 或对应函数幂等补齐 `module_ai:develop:oauth:*` 与前端菜单。

- [x] **Step 3: 写/跑权限测试**

`tests/test_develop_oauth_perms.py`：验证非管理员访问 client 管理端点被 403，管理员可创建。
Run: `pytest tests/test_develop_oauth_perms.py -q`
Expected: PASS

- [x] **Step 4: 提交**

```bash
git add backend/app/plugin/module_ai/develop/capabilities.py backend/app/scripts/init_app.py backend/tests/test_develop_oauth_perms.py
git commit -m "feat(auth): 阶段2OAuth管理权限与菜单"
```

---

## 执行说明

- 每 Task 的测试都用 `test_client` 夹具（DB 用例），纯逻辑用 `PYTEST_NO_APP=1`。
- 完成后跑 `develop` 相关全量回归：`pytest tests/ -k develop -q`（train 品类 MinIO 环境依赖用例会失败，属环境问题，可忽略）。并跑 `ruff check app/plugin/module_ai/develop/`。
- 改完后端后杀干净重启（`--no-reload`），验证 `/openapi.json` 出现 `/develop/oauth/*` 端点。
- `ai_integration_call_logs.app_id` 若需改可空：单独迁移文件用 `has_column` 幂等改 nullable，**保持唯一 head**。
