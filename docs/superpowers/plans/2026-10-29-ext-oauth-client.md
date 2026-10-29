# 阶段 3a：通用 OAuth client（平台代用户访问外部资源）Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让平台充当 OAuth **client**，代平台用户访问外部第三方 OAuth 保护资源：新增「外部服务连接」+「用户级加密 token」两表，http 工具可选绑定外部服务并在调用时自动注入当前对话用户的外部 Bearer。

**Architecture:** 方案 A。新增 `ai_oauth_ext_services`（管理员登记外部 OAuth server）+ `ai_oauth_ext_tokens`（`用户×服务` 的加密 access/refresh）两表；`ai_tools` 加 `oauth_ext_service_id` 绑定列。授权走 OAuth 2.1 授权码 + state 防 CSRF；token 用 `cryptography.Fernet` 加密（key 由 `SECRET_KEY` 派生），可还原用于注入。`execute_http_tool` 对绑定服务的工具，从 `_USER_ID_CTX` 取当前用户注入 `Authorization: Bearer`；未连接/已撤销报工具错误；access 过期静默用 refresh 换新。MCP 复用同一 token 层，留作阶段 3b（本计划不含）。

**Tech Stack:** FastAPI + SQLAlchemy 2.0 + Pydantic v2 + httpx + `cryptography.fernet`；复用 `agno_tools.dynamic._USER_ID_CTX`、`tools_catalog.dispatch_tool`、`get_current_user`、`AuthPermission`。

**Spec:** `docs/superpowers/specs/2026-10-29-ext-oauth-client-design.md`

## Global Constraints

- 所有用户回复用中文；代码注释用中文；提交信息 `feat(auth): 中文描述`。
- token/secret 安全：外部 access/refresh **加密存 Fernet 密文**（列名 `_enc`），`client_secret` **只存 sha256 散列**；接口/日志绝不泄明文或 `client_secret_hash`。
- 鉴权/授权失败按 spec 语义：未连接/已撤销 → 工具错误（不中断对话）；`state` 不匹配 → 拒绝。
- 迁移**手写**（dev 库有 400+ 影子表，禁用 autogenerate）；用 `has_table`/`has_column` 幂等守卫；`revision='b8c9d0e1f2a3'`，`down_revision='f5a6b7c8d9e0'`（当前唯一 head，已核对未占用）。alembic 链须保持唯一 head。
- 开发用 `--no-reload`；改后端后须杀干净（`Get-CimInstance` 按 `main.py` 命令行）并重启验证 `/openapi.json`。
- 测试用 SQLite；纯逻辑用 `PYTEST_NO_APP=1` 快测；DB 用 `test_client` 夹具；每测试造数据用唯一 `name`（`_uniq()` 后缀）。
- http 工具请求带 `X-Forwarded-For: 127.0.0.1` 头（`OperationLogRoute` 校验 request_ip，testclient 会 400）。

## Review Focus

1. **未连接服务**：绑定外部服务的工具被调用时，若当前用户未授权该服务，应返回「你尚未连接该外部服务」的工具错误，**不中断对话**，更不抛 500。→ Task 5 测试。
2. **已撤销**：用户撤销外部授权（`revoked=true`）后，再次调用绑定服务的工具必须报「未连接」而不是继续用旧 token。→ Task 5 测试。
3. **access 过期自动刷新**：access `expires_at` 已过且有 refresh 时，静默用 refresh 换新并回写，工具调用携带新 token。→ Task 6 测试。
4. **未绑定服务零回归**：`oauth_ext_service_id` 为空的 http 工具，调用行为与现在**完全一致**（不注入 Authorization、不查 token 表）。→ Task 5 回归。
5. **state 防 CSRF**：`callback` 收到的 `state` 与 `connect` 签发的不一致（或已消费），必须被拒，不换 token。→ Task 4 测试。

---

### Task 1: 新增两表模型 + 迁移 + 加密工具

**Files:**
- Create: `backend/app/plugin/module_ai/oauth_ext/__init__.py`
- Create: `backend/app/plugin/module_ai/oauth_ext/model.py`
- Create: `backend/app/plugin/module_ai/oauth_ext/schema.py`
- Create: `backend/app/plugin/module_ai/oauth_ext/security.py`（Fernet 封装）
- Create: `backend/app/alembic/versions/b8c9d0e1f2a3_ext_oauth_client.py`
- Test: `backend/tests/test_oauth_ext_models.py`

**Interfaces:**
- Produces:
  - `AiOauthExtServiceModel`（表 `ai_oauth_ext_services`，继承 `ModelMixin + UserMixin`；字段见 spec §2.1，含 `client_secret_enc` 加密列 + `client_secret_hash` 散列列）。
  - `AiOauthExtTokenModel`（表 `ai_oauth_ext_tokens`，继承 `ModelMixin`；字段见 spec §2.2；`UniqueConstraint('service_id','user_id')`）。
  - `oauth_ext/security.py`：
    - `derive_fernet_key(secret_key: str) -> bytes`（从 `SECRET_KEY` 派生长度 32 的 urlsafe base64 bytes，供 `Fernet`）。
    - `encrypt_secret(secret_key: str, plaintext: str) -> str` / `decrypt_secret(secret_key: str, ciphertext: str) -> str`。

- [x] **Step 1: 写模型字段测试（实例化 + 加密往返）**

```python
# tests/test_oauth_ext_models.py
def test_models_instantiate_and_encrypt_roundtrip(test_client):
    from app.plugin.module_ai.oauth_ext.model import (
        AiOauthExtServiceModel, AiOauthExtTokenModel,
    )
    from app.plugin.module_ai.oauth_ext.security import (
        derive_fernet_key, encrypt_secret, decrypt_secret,
    )
    svc = AiOauthExtServiceModel(
        name="考勤", authorize_url="https://x/authorize", token_url="https://x/token",
        client_id="c1", client_secret_hash="h", redirect_uri="https://x/cb",
        default_scopes=["attendance"], enabled=True,
    )
    assert svc.client_id == "c1" and svc.default_scopes == ["attendance"]
    tok = AiOauthExtTokenModel(
        service_id=1, user_id=2, access_token_enc="enc", refresh_token_enc="re",
        scope=["attendance"], revoked=False,
    )
    assert tok.revoked is False
    key = derive_fernet_key("some-secret-key-value-32chars-min!!")
    enc = encrypt_secret("some-secret-key-value-32chars-min!!", "my-token")
    assert enc != "my-token"
    assert decrypt_secret("some-secret-key-value-32chars-min!!", enc) == "my-token"
```

- [x] **Step 2: 跑测试确认失败**

Run: `PYTEST_NO_APP=1 pytest tests/test_oauth_ext_models.py -q`
Expected: FAIL（模块/方法未定义）

- [x] **Step 3: 实现 `model.py`（两模型类）**

仿 `ModelMixin` 手写列；`AiOauthExtTokenModel` 加 `__table_args__ = (UniqueConstraint("service_id", "user_id", name="uq_oauth_ext_tok_svc_user"), {"comment": ...})`。`client_secret_hash` 用 String(128)。

- [x] **Step 4: 实现 `security.py`（Fernet 封装）**

`derive_fernet_key`：base64 urlsafe 编码 `sha256(secret_key)` 的前 32 字节（`base64.urlsafe_b64encode(hashlib.sha256(secret_key.encode()).digest())`），满足 Fernet 的 32-byte urlsafe base64。`encrypt_secret`/`decrypt_secret` 用 `Fernet(key)`。

- [x] **Step 5: 实现迁移 `b8c9d0e1f2a3_ext_oauth_client.py`**

`revision='b8c9d0e1f2a3'`，`down_revision='f5a6b7c8d9e0'`。upgrade 里对两表 `if "..." not in insp.get_table_names(): op.create_table(...)`，含 `ModelMixin` 全部列（id/uuid/status/description/created_time/updated_time/is_deleted/deleted_time + UserMixin 的 created_id/updated_id/deleted_id for service 表），建索引（`client_id`、`user_id`、`service_id`、唯一约束）。downgrade 反向 `drop_table`。

- [x] **Step 6: 跑测试确认通过 + 校验 head 唯一**

Run: `PYTEST_NO_APP=1 pytest tests/test_oauth_ext_models.py -q`
Expected: PASS
Run: `python -c "from alembic.config import Config; from alembic.script import ScriptDirectory; s=ScriptDirectory.from_config(Config('alembic.ini')); print(s.get_heads())"`
Expected: `['b8c9d0e1f2a3']`（唯一 head）

- [x] **Step 7: 提交**

```bash
git add backend/app/plugin/module_ai/oauth_ext/ backend/app/alembic/versions/b8c9d0e1f2a3_ext_oauth_client.py backend/tests/test_oauth_ext_models.py
git commit -m "feat(auth): 阶段3外部服务与用户token表模型+加密工具"
```

---

### Task 2: 外部服务 CRUD（管理面）

**Files:**
- Create: `backend/app/plugin/module_ai/oauth_ext/service.py`（`OAuthExtService` 类 + `_hash_secret`/`_service_to_dict`）
- Create: `backend/app/plugin/module_ai/oauth_ext/controller.py`（`OAuthExtRouter`）
- Modify: `backend/app/plugin/module_ai/oauth_ext/__init__.py`（导出 model 注册 metadata + router）
- Test: `backend/tests/test_oauth_ext_service_crud.py`

**Interfaces:**
- Consumes: Task 1 `AiOauthExtServiceModel`、`_hash`（sha256）。
- Produces:
  - `OAuthExtService.create_service(data, auth) -> dict`（返回一次性明文 `client_secret`；仅存 `client_secret_hash`）。
  - `OAuthExtService.list_services() -> list[dict]` / `get_service(service_id) -> AiOauthExtServiceModel | None` / `update_service(...)` / `delete_service(...)`。
  - `OAuthExtRouter`（`prefix="/oauth-ext"`，`route_class=OperationLogRoute`），管理面端点 `GET/POST /oauth-ext/services`、`PUT/DELETE /oauth-ext/services/{id}`，全部 `AuthPermission(["module_ai:develop:*"])`。
  - `_hash_secret`（`hashlib.sha256` + hex，供在后面任务复用）。

- [x] **Step 1: 写 schema 与创建测试**

`schema.py`：`OAuthExtServiceCreateSchema`（name/authorize_url/token_url/client_id/client_secret/redirect_uri/default_scopes/userinfo_url/enabled）、`OAuthExtServiceUpdateSchema`（全部可选）。测试：
```python
def test_service_create_returns_secret_once(test_client, auth_headers):
    r = test_client.post("/api/v1/ai/oauth-ext/services", headers=auth_headers, json={
        "name": f"svc-{uniq}", "authorize_url": "https://x/authorize",
        "token_url": "https://x/token", "client_id": "cid",
        "client_secret": "sec", "redirect_uri": "https://x/cb",
        "default_scopes": ["attendance"], "enabled": True,
    })
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert data["client_secret"] == "sec"          # 一次明文
    assert "client_secret_hash" not in data          # 不回显散列
def test_service_list_hides_secret(test_client, auth_headers):
    # 创建后 list，items 里无 client_secret_hash
```

- [x] **Step 2: 跑测试确认失败**

Run: `pytest tests/test_oauth_ext_service_crud.py -q`（需 `test_client` 应用；不设 `PYTEST_NO_APP`）
Expected: FAIL（路由未定义）

- [x] **Step 3: 实现 `service.py` + `controller.py`**

`create_service`：校验 `name` 唯一（`is_deleted=false`）、归一 `default_scopes`；生成 `client_secret`（`secrets.token_urlsafe`）返回明文一次，库存 `_hash_secret(secret)`；`_service_to_dict` 不含 `client_secret_hash`。controller 挂 `OAuthExtRouter`（前缀 `/oauth-ext`）。

- [x] **Step 4: 跑测试确认通过**

Run: `pytest tests/test_oauth_ext_service_crud.py -q`
Expected: PASS

- [x] **Step 5: ruff + 提交**

Run: `ruff check app/plugin/module_ai/oauth_ext/`
Expected: All checks passed

```bash
git add backend/app/plugin/module_ai/oauth_ext/
git commit -m "feat(auth): 阶段3外部服务CRUD（管理面，secret只存散列）"
```

---

### Task 3: 用户授权（connect 生成 state / callback 换 token 加密落库）

**Files:**
- Modify: `backend/app/plugin/module_ai/oauth_ext/service.py`（`OAuthExtService.connect_redirect` / `OAuthExtService.handle_callback`）
- Modify: `backend/app/plugin/module_ai/oauth_ext/controller.py`（用户面端点）
- Test: `backend/tests/test_oauth_ext_authorize.py`

**Interfaces:**
- Consumes: Task 1 模型/加密、Task 2 `OAuthExtService.get_service` + `_hash_secret`。
- Produces:
  - `OAuthExtService.get_or_create_token_row(service_id, user_id, access, refresh, scope, expires_at, provider_user_id=None, db=None) -> AiOauthExtTokenModel`（upsert，加密存）。
  - `OAuthExtService.resolve_state(service_id, user_id) -> str` / `consume_state(service_id, state) -> bool`（Redis 或内存，TTL 600s）。
  - `OAuthExtService.exchange_code(service, code, redirect_uri) -> (access, refresh, expires_in, scope, provider_user_id)`（httpx POST token_url，表单 `grant_type=authorization_code` + client 凭证 + code）。仅换 token；`client_secret` 用 `service.client_secret_hash` 不直接可得 → **需存明文？**：见下面 Step 说明。

- [x] **Step 1: 处理 client_secret 换取的可还原性**

`client_secret_hash` 只存散列用于换取时**需要明文**。决策：在 `exchange_code` 换取时用 `service.client_secret` **不存**——但换取必须带明文。保守做法：把 `client_secret` 也加密存一列 `client_secret_enc`（仅用于换取，不回读）。修改 Task 1 模型加 `client_secret_enc`（Text, null），`create_service` 同时存散列+加密。`service.py` 提供 `decrypt_client_secret(service) -> str`。

- [x] **Step 2: 写授权测试（mock 外部 token 端点）**

用 `httpx.MockTransport` 或 monkeypatch `exchange_code` 的 POST：
```python
def test_callback_exchanges_and_stores(test_client, auth_headers, monkeypatch):
    # 建服务 -> connect 得 state -> monkeypatch 外部 token 返回 access/refresh -> callback?code&state -> token 落库加密
def test_callback_bad_state_rejected(test_client, auth_headers):
    # callback 传错误 state -> 被拒（不换 token）
```

- [x] **Step 3: 跑测试确认失败**

Run: `pytest tests/test_oauth_ext_authorize.py -q`
Expected: FAIL

- [x] **Step 4: 实现 connect/callback**

`connect_redirect(service, user_id)`：生成 `state`、存 Redis（`oauth_ext:state:{service_id}:{user_id}`，TTL 600），拼 `authorize_url?client_id&redirect_uri&response_type=code&scope&state`。
`handle_callback(service_id, user_id, code, state, redirect_uri)`：`consume_state` 校验 state → `exchange_code`（带 `decrypt_client_secret`）→ `get_or_create_token_row` 加密落库 → 返回用户信息。

- [x] **Step 5: 跑测试确认通过**

Run: `pytest tests/test_oauth_ext_authorize.py -q`
Expected: PASS

- [x] **Step 6: ruff + 提交**

```bash
git add backend/app/plugin/module_ai/oauth_ext/
git commit -m "feat(auth): 阶段3用户授权connect/callback换token加密落库"
```

---

### Task 4: 用户 token 刷新 / 撤销 / 连接态查询

**Files:**
- Modify: `backend/app/plugin/module_ai/oauth_ext/service.py`
- Modify: `backend/app/plugin/module_ai/oauth_ext/controller.py`
- Test: `backend/tests/test_oauth_ext_token_lifecycle.py`

**Interfaces:**
- Produces:
  - `OAuthExtService.refresh_token(service, user_id) -> str|None`（用 refresh 换新 access，回写；无 refresh 返回 None）。
  - `OAuthExtService.revoke(service_id, user_id) -> None`（置 `revoked=true`）。
  - `OAuthExtService.connection_status(service_id, user_id) -> dict`（`{connected, expired, access_expires_at}`）。
  - 端点：`POST /oauth-ext/tokens/{service_id}/refresh`、`DELETE /oauth-ext/tokens/{service_id}`、`GET /oauth-ext/tokens/{service_id}/status`（用户面 `Depends(get_current_user)`）。

- [x] **Step 1: 写测试**

```python
def test_refresh_when_access_expired(test_client, auth_headers, monkeypatch):
    # 造 token 行(access过期+有refresh) -> refresh -> 新access写回
def test_revoke_marks_revoked(test_client, auth_headers):
    # DELETE -> 行 revoked=True
def test_connection_status(test_client, auth_headers):
    # 未连接 -> {connected:False}; 已连接 -> {connected:True, expired:...}
```

- [x] **Step 2: 跑测试确认失败**

Run: `pytest tests/test_oauth_ext_token_lifecycle.py -q`
Expected: FAIL

- [x] **Step 3: 实现 refresh/revoke/status**

`refresh_token`：查 `(service_id, user_id)` 行未撤销、有 `refresh_token_enc`，POST `token_url` 表单 `grant_type=refresh_token` + client 凭证 + refresh，得新 access（+可能新的 refresh），解密/加密回写，刷新 `last_used_at`。`revoke`：置 `revoked=true`/`revoked_at`。`connection_status` 解析 `access_expires_at`。

- [x] **Step 4: 跑测试确认通过**

Run: `pytest tests/test_oauth_ext_token_lifecycle.py -q`
Expected: PASS

- [x] **Step 5: ruff + 提交**

```bash
git add backend/app/plugin/module_ai/oauth_ext/
git commit -m "feat(auth): 阶段3用户token刷新/撤销/连接态"
```

---

### Task 5: http 工具绑定外部服务 + 调用注入 Bearer

**Files:**
- Modify: `backend/app/plugin/module_ai/tools_catalog/model.py`（`AiToolModel` 加 `oauth_ext_service_id`）
- Modify: `backend/app/plugin/module_ai/tools_catalog/schema.py`（`AiToolCreateSchema`/`AiToolUpdateSchema` 加 `oauth_ext_service_id`）
- Modify: `backend/app/plugin/module_ai/tools_catalog/service.py`（`execute_http_tool(tool, args, user_id=None)` + `dispatch_tool` http 分支透传 `user_id`）
- Modify: `backend/app/alembic/versions/b8c9d0e1f2a3_ext_oauth_client.py`（`ai_tools` 加列）
- Test: `backend/tests/test_oauth_ext_tool_inject.py`

**Interfaces:**
- Consumes: Task 1-4（`get_service`、`resolve_ext_access_token`）。**本 Task 需在 `oauth_ext/service.py` 新增**：
  - `OAuthExtService.resolve_ext_access_token(service_id, user_id) -> dict`（`{"ok": True, "token": 明文access}` 或 `{"ok": False, "error": "你尚未连接该外部服务"}`；access 过期时静默 refresh 再返回）。
- Produces: 绑定服务的 http 工具执行时注入 `Authorization: Bearer`；未绑定工具行为不变。

- [x] **Step 1: 改 model/schema 加绑定列 + 迁移加列（幂等）**

`model.py`：`oauth_ext_service_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("ai_oauth_ext_services.id"), nullable=True, index=True, comment="绑定的外部服务ID（OAuth注入）")`。迁移 `b8c9d0e1f2a3` upgrade 追加 `if "oauth_ext_service_id" not in cols: op.add_column("ai_tools", sa.Column("oauth_ext_service_id", sa.Integer(), nullable=True))`（`has_column` 幂等）。schema 加可选 `oauth_ext_service_id`。

- [x] **Step 2: 写注入测试（先失败）**

```python
def test_http_tool_injects_bearer(test_client, auth_headers, monkeypatch):
    # 建服务+授权token行 -> 建绑定该服务的http工具 -> 调用 -> 请求带 Authorization: Bearer <access>
def test_http_tool_unbound_no_auth(test_client, auth_headers):
    # 未绑定服务的http工具 -> 请求不含 Authorization
def test_http_tool_not_connected_returns_error(test_client, auth_headers):
    # 绑定服务但用户未授权/已撤销 -> 返回{"error": "你尚未连接该外部服务"}，不抛异常
```

- [x] **Step 3: 跑测试确认失败**

Run: `pytest tests/test_oauth_ext_tool_inject.py -q`
Expected: FAIL

- [x] **Step 4: 实现 `resolve_ext_access_token` + `execute_http_tool` 注入**

`resolve_ext_access_token`：查 `(service_id, user_id)` 行，`revoked`→`{"ok":False,...}`；access 未过期→解密返回；过期且有 refresh→`refresh_token` 后返回；无行/无 refresh→`{"ok":False,"error":"你尚未连接该外部服务"}`。
`execute_http_tool(tool, args, user_id=None)`：若 `tool.oauth_ext_service_id` 非空且 `user_id` 非空 → `resolve_ext_access_token`；`ok` 则 `headers["Authorization"] = f"Bearer {token}"`，否则返回该错误 dict。`dispatch_tool` http 分支改 `execute_http_tool(tool, args, user_id)`。

- [x] **Step 5: 跑测试确认通过 + 全量回归**

Run: `pytest tests/test_oauth_ext_tool_inject.py -q`
Expected: PASS
Run: `pytest tests/ -k "tool or develop or oauth" -q`
Expected: 既有 tool/develop 用例不因未绑定工具而回归（未绑定工具请求不含 Authorization）。

- [x] **Step 6: ruff + 提交**

Run: `ruff check app/plugin/module_ai/oauth_ext/ app/plugin/module_ai/tools_catalog/`
Expected: All checks passed

```bash
git add backend/app/plugin/module_ai/oauth_ext/ backend/app/plugin/module_ai/tools_catalog/ backend/app/alembic/versions/b8c9d0e1f2a3_ext_oauth_client.py backend/tests/test_oauth_ext_tool_inject.py
git commit -m "feat(auth): 阶段3http工具绑定外部服务并自动注入Bearer"
```

---

### Task 6: 收尾回归 + 重启验证

**Files:**
- Test: 全部 `tests/test_oauth_ext_*.py` + `tests/test_develop_*.py` + `tests/test_*tool*.py`

**Interfaces:**
- Consumes: 全部任务。

- [x] **Step 1: 跑全部 oauth_ext 测试**

Run: `pytest tests/test_oauth_ext_models.py tests/test_oauth_ext_service_crud.py tests/test_oauth_ext_authorize.py tests/test_oauth_ext_token_lifecycle.py tests/test_oauth_ext_tool_inject.py -q`
Expected: 全部 PASS

- [x] **Step 2: 跑 develop + tool 回归**

Run: `pytest tests/ -k "develop or oauth or tool" -q`
Expected: 通过（既有 `test_develop_insights::test_stats_shape_and_counts` 数据耦合单跑通过、`test_develop_train` MinIO 环境依赖可忽略；其余不因阶段3失败）。

- [x] **Step 3: 校验 alembic head 唯一**

Run: `python -c "from alembic.config import Config; from alembic.script import ScriptDirectory; s=ScriptDirectory.from_config(Config('alembic.ini')); print(s.get_heads())"`
Expected: `['b8c9d0e1f2a3']`

- [x] **Step 4: 重启后端（--no-reload）并验证**

```powershell
Get-CimInstance Win32_Process -Filter "Name='python.exe'" | Where-Object { $_.CommandLine -like '*main.py*' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }
# 确认端口空后启动
$env:SERVER_PORT="8002"; $env:CAPTCHA_ENABLE="false"; .\.venv\Scripts\python.exe main.py run --env=dev --no-reload
```
等待就绪后：
`Invoke-WebRequest http://127.0.0.1:8002/openapi.json`
Expected: 出现 `/ai/oauth-ext/*` 端点（services/connect/callback/tokens）。

- [x] **Step 5: 提交计划勾选 + 收尾**

本计划各 Task 的 checkbox 全部勾选。

---

## 执行说明

- 每 Task 的 DB 测试用 `test_client` + `auth_headers`（带 `X-Forwarded-For`）；纯逻辑用 `PYTEST_NO_APP=1`。
- `cryptography` 已在依赖中（45.0.2），无需新增。
- 阶段 3b（MCP 复用 token 层）不在此计划，勿混入。
- `revision='b8c9d0e1f2a3'` 已核对未占用；`down_revision='f5a6b7c8d9e0'` 是当前唯一 head。
