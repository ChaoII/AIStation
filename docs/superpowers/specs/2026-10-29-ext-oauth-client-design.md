# AI 集成开放平台 —— 阶段 3a：通用 OAuth client（平台代用户访问外部资源）设计

> 前置：`docs/superpowers/specs/2026-10-29-develop-auth-modes.md`（三模式设计，已批准）。
> 关联：阶段 2 `docs/superpowers/specs/2026-10-29-develop-oauth-server-design.md`（平台充当 OAuth **server**，已完成）。
> 本文档锁定**阶段 3a**：平台充当 OAuth **client**，代平台用户访问**外部**第三方 OAuth 保护资源，
> 消费形态先做 **http 工具注入**；MCP 复用同一 token 层，留作阶段 3b（本文档不实现 MCP 接入）。

---

## 一、目标与边界（锁死）

**方向相反于阶段 2**：
- 阶段 2：平台是 OAuth `server`，外部助手**代用户访问平台**。
- 阶段 3a：平台是 OAuth `client`，平台内智能体/App **代平台用户访问外部**第三方 OAuth 资源。

**已确认决策（与用户逐节对齐）**：
1. **通用 OAuth client 框架**：可注册任意标准 OAuth 2.x server（不绑定钉钉/飞书等某家）。
2. **消费形态先做 http 工具**：创建 http 工具时可选绑定「外部服务连接」，执行时自动注入该对话用户的 `Authorization: Bearer <access>`。
3. **MCP 复用同一 token 层，留作阶段 3b**（本文档不含 MCP 接入实现）。
4. **token 必须可还原**（平台要用它调外部 API），故外部 access/refresh **加密存储**（`cryptography.Fernet`，key 由 `SECRET_KEY` 派生），**不能**像阶段 2 只存散列。
5. **架构方案 A**：独立「外部服务连接」+「用户级 token」两张表，http 工具加绑定列。

**与三模式底座的关系**：阶段 3 是「平台出方向」，与 A/B/C（外部入方向）互不冲突，复用的是 `ai_tools` 工具执行链路而非开放面 capability 管道。

---

## 二、数据模型

### 2.1 `ai_oauth_ext_services`（外部服务连接，管理员登记）
继承 `ModelMixin + UserMixin`（`description` 复用 `ModelMixin`）。

| 列 | 类型 | 说明 |
|----|------|------|
| `name` | String(128), unique | 服务名（如「公司考勤」） |
| `authorize_url` | String(512) | 外部 OAuth authorize 端点 |
| `token_url` | String(512) | 外部 token 端点 |
| `client_id` | String(256) | 平台作为该服务 client 的 id |
| `client_secret_enc` | Text, null | client secret 的**加密密文**（Fernet，仅用于换取；不回读） |
| `client_secret_hash` | String(128) | client secret 的 sha256（**只存散列**，用于校验；不回读） |
| `redirect_uri` | String(512) | 平台回跳地址 |
| `default_scopes` | JSONB | 授权时默认请求 scope 列表 |
| `userinfo_url` | String(512), null | 可选：校验用户身份（解析 `provider_user_id`） |
| `enabled` | Boolean | 是否启用 |

### 2.2 `ai_oauth_ext_tokens`（用户级外部 token）
继承 `ModelMixin`（**不用** `UserMixin`，用 `user_id` 列）。

| 列 | 类型 | 说明 |
|----|------|------|
| `service_id` | Integer, FK `ai_oauth_ext_services.id` | 所属外部服务 |
| `user_id` | Integer, FK `sys_user.id` | 平台用户 |
| `provider_user_id` | String(256), null | 外部服务返回的用户标识（若 userinfo 解析） |
| `access_token_enc` | Text | **加密**的 access token（可还原，供调用注入） |
| `refresh_token_enc` | Text, null | 加密的 refresh token |
| `access_expires_at` | DateTime, null | access 过期时间 |
| `scope` | JSONB | 实际授权 scope |
| `revoked` | Boolean | 用户是否已撤销该外部授权 |
| `revoked_at` | DateTime, null | 撤销时间 |
| `last_used_at` | DateTime, null | 最近使用时间 |

**唯一约束**：`UniqueConstraint(service_id, user_id)` —— 一个用户对每个外部服务只有一条 token 记录。

> 「加密」：用 `cryptography.fernet.Fernet`，key 由平台 `SECRET_KEY`（`app/config/setting.py` 的强随机 key）派生；只存密文，列名带 `_enc` 后缀，明文仅在注入时内存中出现。

### 2.3 `ai_tools` 加一列
`oauth_ext_service_id`：Integer, FK `ai_oauth_ext_services.id`, 可空。http 工具创建/编辑时可选绑定一个外部服务。

---

## 三、端点与授权流程

新增独立路由 `OAuthExtRouter`（前缀 `/oauth-ext`）。

### 3.1 管理面（复用 `AuthPermission(["module_ai:develop:*"])`，无新增权限点）
- `GET /oauth-ext/services` · `POST /oauth-ext/services` · `PUT /oauth-ext/services/{id}` · `DELETE /oauth-ext/services/{id}` —— 外部服务 CRUD。
- 列表/详情返回**不含** `client_secret_hash`。

### 3.2 用户面（`Depends(get_current_user)`，每个用户）
- `GET /oauth-ext/services` —— 列出已登记且启用的服务（附该用户是否已连接、access 是否过期）。
- `GET /oauth-ext/connect/{service_id}` —— 生成一次性 `state`（防 CSRF），拼 `authorize_url?client_id&redirect_uri&response_type=code&scope&state`，302 重定向外部授权页。
- `GET /oauth-ext/callback`（`?code&state`）—— 校验 `state` → 用 client 凭证换该用户 access/refresh → **加密**落库（有则更新）→ 重定向平台前端提示「已连接」。
- `POST /oauth-ext/tokens/{service_id}/refresh` —— 用户手动刷新。
- `DELETE /oauth-ext/tokens/{service_id}` —— 用户撤销该外部授权（`revoked=true`）。
- `GET /oauth-ext/tokens/{service_id}/status` —— 查询连接态（是否已授权、过期时间）。

### 3.3 授权码流程（OAuth 2.1 授权码 + state）
```
用户在前端点「连接某服务」
  → GET connect/{service_id} 生成 state → 跳外部 authorize
  → 用户在外登录并同意
  → 外部 302 回 callback?code&state
  → 平台校验 state → POST token_url 换 access/refresh
  → 加密落库 → 回前端「已连接」
```

`state` 用 `secrets.token_urlsafe` 生成，服务端暂存（Redis 优先，TTL 600s，与平台现有 state 机制一致）；回调校验后立即失效。

---

## 四、http 工具注入 token（核心）

**原理**：`tools_catalog.dispatch_tool` 已拿到 `user_id`（来自 `agno_tools.dynamic` 的 `_USER_ID_CTX`，智能体对话时注入当前用户 id）。阶段 3a 在 http 工具执行层做一层「绑定服务 → 带用户 token」。

**执行逻辑（`execute_http_tool` 改造）**：
1. `tool.oauth_ext_service_id` 为空 → 走现有逻辑（**不注入**，零回归）。
2. 非空 → 传入 `user_id`，调 `resolve_ext_access_token(service_id, user_id)`：
   - 无 token 行或 `revoked=true` → 返回工具错误「你尚未连接该外部服务」（不中断对话）。
   - access 过期且有 refresh → **静默用 refresh 换新 access**，回写加密，刷新 `last_used_at`。
   - 有 access → 解密，拼 `Authorization: Bearer <access>` 合并进 `headers`。
3. 其余（URL 占位替换 / query / body）不变。

**改动点**：
- `dispatch_tool` 的 http 分支：`execute_http_tool(tool, args, user_id)`（把 `user_id` 透传）。
- `execute_http_tool(tool, args, user_id=None)`：增 `user_id` 形参，内部加 token 注入。
- 新增 `oauth_ext.py`（服务层）：`resolve_ext_access_token(service_id, user_id)` → 返回可用明文 access（解密 + 自动刷新）；以及换 token / 加密解密 / 刷新封装。

**不绑定服务的工具行为完全不变**。

---

## 五、安全要点

1. **token 加密**：外部 access/refresh 只存 Fernet 密文（key 由 `SECRET_KEY` 派生），列名 `_enc`，接口/日志绝不泄明文。
2. **client_secret 只存散列**：用于换取，不回读；管理面列表/详情不出 `client_secret_hash`。
3. **state 防 CSRF**：`connect` 生成一次性随机 state，`callback` 校验一致后失效。
4. **回调校验**：`callback` 只认登记 `redirect_uri`；再校验 code 交换成功 + 用户身份（有 `userinfo_url` 则校验 `provider_user_id` 归属）。
5. **撤销**：用户可随时删该外部授权（`revoked=true`），已注入 token 下次调用即失效。
6. **最小 scope**：授权时只请求服务登记者/需要的最小 scope，不过度授权。

---

## 六、迁移

新增手写迁移 `b8c9d0e1f2a3_ext_oauth_client.py`（`down_revision='f5a6b7c8d9e0'`，即当前唯一 head）。
用 `has_table` / `has_column` 幂等守卫（继承本项目迁移惯例），避免空库全链重放失败；`revision id` 须唯一，且 alembic 链保持唯一 head。

> ⚠️ 本项目 dev 库有 400+ 张未被模型覆盖的历史/影子表（`ont_*`），**迁移必须手写**，禁用 autogenerate。

---

## 七、测试计划

`tests/test_oauth_ext_*.py`（校验 OAuth 常量与纯逻辑用 `PYTEST_NO_APP=1` 快测；DB 用 test_client）：
1. 服务 CRUD（创建/校验白名单/`client_secret_hash` 不泄出）。
2. 授权码流程（mock 外部 token 端点：`connect` 生成 `state` → `callback` 换 token 落库加密；state 不匹配被拒）。
3. token 加密解密往返（明文不入库可验、密文可还原）。
4. 刷新（access 过期用 refresh 静默换新 + 回写）。
5. 撤销（删除后工具调用报「未连接」）。
6. **http 工具注入**（绑定服务的工具调用带 `Bearer`；未绑定不含；未授权报错不中断对话）。
7. 回归：现有 `test_develop_*` / `test_*tool*` 全量不受影响（未绑定工具零回归）。

---

## 八、验收标准

1. 管理员可登记任意标准 OAuth server 作为外部服务（authorize/token/redirect/scopes/client 凭证）。
2. 平台用户可点「连接」走授权码流程，把外部账号授权给平台；外部 access/refresh 加密落库。
3. 创建 http 工具可选绑定某外部服务；智能体对话中调用该工具时，**自动注入当前对话用户的外部 Bearer**。
4. 未连接/已撤销/过期自动处理：未连接报工具错误；过期用 refresh 静默换新。
5. 管理面/接口/日志不泄出 client_secret 或 token 明文。
6. **不绑定服务的既有 http 工具零回归**；MCP 接入留作阶段 3b（复用同一 token 层）。
7. 后端测试覆盖上述服务 CRUD/授权码/加密/刷新/撤销/注入；现有 develop/tool 测试全量通过。

---

## 九、涉及文件

- `backend/app/plugin/module_ai/tools_catalog/model.py`（`ai_tools` 加 `oauth_ext_service_id` 列）
- `backend/app/plugin/module_ai/oauth_ext/model.py` / `schema.py` / `service.py` / `controller.py`（新子模块：两模型 + schema + `resolve_ext_access_token` + CRUD/connect/callback/refresh/revoke）
- `backend/app/plugin/module_ai/tools_catalog/service.py`（`execute_http_tool` 注入 + `dispatch_tool` 透传 `user_id`）
- `backend/app/plugin/module_ai/tools_catalog/schema.py`（`AiToolCreateSchema`/`AiToolUpdateSchema` 加 `oauth_ext_service_id`）
- `backend/app/alembic/versions/b8c9d0e1f2a3_ext_oauth_client.py`（新迁移，down=`f5a6b7c8d9e0`）
- `backend/app/plugin/module_ai/tools_catalog/__init__.py`（如需注册 router）
- `backend/tests/test_oauth_ext_*.py`
