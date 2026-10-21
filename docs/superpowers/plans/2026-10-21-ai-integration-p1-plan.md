# AI 集成分阶段 P1：集成应用凭证与权限 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 搭建「AI 集成」底座：集成应用（app）的 appid/appkey 凭证管理、按能力品类的权限点、appid/appkey 鉴权依赖、调用审计（含 MCP 行为监控）、「AI 集成」菜单与前端页面。

**Architecture:** 新增 `app/plugin/module_ai/develop/` 自动发现子模块，内部管理面（`/ai/develop`，RBAC）管理 app 与应用密钥；开放数据面（`/ai/develop-api`，appid/appkey 鉴权）为 P2/P3/P4 的入口。三张新表：`ai_integration_apps`（应用+appkey 哈希+权限点+配额）、`ai_integration_call_logs`（调用/连接审计）、`ai_integration_mcp_sessions`（MCP 连接会话）。权限点集中定义在 `capabilities.py`。

**Tech Stack:** FastAPI + SQLAlchemy 2.0 async + PostgreSQL JSONB；前端 Vue3 + Element Plus CRUD；pytest（`PYTEST_NO_APP=1` 快速模式）。

**Spec:** `docs/superpowers/specs/2026-10-21-ai-integration-open-platform-design.md`

## Global Constraints

- 所有与用户交互文本用**中文**；代码注释用中文；提交信息 `feat(ai): 中文描述`。
- 后端位置 `backend/app/plugin/module_ai/develop/`；路由由 `module_ai/**/controller.py` 自动发现（顶层 `XxxRouter = APIRouter(...)`）。
- 模型继承：`AiIntegrationAppModel(ModelMixin, UserMixin)`；审计表直接 `MappedBase` + 自行定义 `id/created_time`。
- 启用/停用用 `enabled: bool`（对齐 `AiMcpServerModel`），不复用 `ModelMixin.status`（那是 `0/1` 软状态）。
- 迁移**手写**：`down_revision` 须为当前 head `a2b3c4d5e6f7`；对不在迁移链创建的插件表增列用 `sa.inspect(bind).has_table()`；SQLite 回归可空库全链重放。
- 鉴权统一 `Authorization: Bearer <appid>:<appkey>`；appkey 只存 `sha256`，明文仅在创建/重置时返回一次。
- 菜单/按钮权限由 `_ensure_develop_menus()` 幂等补齐（参照 `_ensure_ai_menus` + `ensure_perms`）。
- 删除/重置类操作前端必须二次确认、后端必须权限校验。
- 测试效率：纯逻辑测试用 `PYTEST_NO_APP=1` 快速模式；日常只跑单文件；提交前 `uv run pytest -q`。
- 数据归属约定（跨 P1–P4）：资源（训练任务/Agent/消息/会话/嵌入 token）用 `source_app_id` 归属到集成应用。P1 不建资源表，仅以 `ai_integration_call_logs.app_id`（=集成应用）记录调用归属；`source_app_id` 到资源表的物化在 **P2** 实现。

## Review Focus

这些输入未被任何任务的测试显式覆盖，但最可能在真实使用中咬人。每条都已在所属任务里补了测试。

1. **`Authorization` 头缺失 / 格式错**（如 `Bearer` 后无 `appid:appkey`、分隔符不是冒号）→ 应 401，不应 500 或返回可读 app 信息。（Task 4）
2. **appkey 错误 与 appid 不存在 必须返回同样的 401**，避免枚举 appid。（Task 4）
3. **`enabled=false` 或 `expire_at` 已过期的 app，即便密钥正确也应被拒**（401）。（Task 4）
4. **`capabilities` 为空 / 为 None（未勾选任何权限）** → 任何能力调用都应被拒，且 `auth/verify` 能看到空权限。（Task 4）
5. **appkey 重置后旧 key 失效、新 key 生效**；重复 `name`/`appid` 被拒。（Task 3）
6. **`appid:appkey` 里的 appkey 含特殊字符**（如 `+ / =`，若未来用 base64）也能正确解析（用 `rsplit(":", 1)` 而非 `split(":")`）。（Task 4）

---

### Task 1: 能力目录与权限点定义（纯逻辑）

**Files:**
- Create: `backend/app/plugin/module_ai/develop/__init__.py`
- Create: `backend/app/plugin/module_ai/develop/capabilities.py`
- Test: `backend/tests/test_develop_capabilities.py`

**Interfaces:**
- Produces:
  - `CATEGORIES: dict[str, str]`（品类码→中文名：`train/agent/chat/bot/embed`）
  - `PERMISSION_CODES: list[str]`（全部合法权限点）
  - `CATEGORY_PERMS: dict[str, list[str]]`（品类→权限点列表）
  - `is_valid_perm(perm: str) -> bool`
  - `normalize_permissions(perms: list[str]) -> set[str]`（去重 + 丢弃非法项，不抛错）
  - `permissions_by_category(perms: list[str]) -> dict[str, list[str]]`（按品类分组）

- [ ] **Step 1: 写失败测试**

```python
# tests/test_develop_capabilities.py （PYTEST_NO_APP=1）
from app.plugin.module_ai.develop.capabilities import (
    CATEGORIES, PERMISSION_CODES, is_valid_perm, normalize_permissions, permissions_by_category,
)

def test_categories_have_perms():
    for cat, name in CATEGORIES.items():
        assert name  # 有中文名
        assert CATEGORIES.keys() == {"train", "agent", "chat", "bot", "embed"}
        assert cat in CATEGORY_PERMS and CATEGORY_PERMS[cat]

def test_permission_codes_are_integration_scoped():
    assert all(p.startswith("integration:") for p in PERMISSION_CODES)
    for perms in CATEGORY_PERMS.values():
        assert len(perms) == len(set(perms))  # 不重复

def test_is_valid_perm():
    assert is_valid_perm("integration:train:create")
    assert not is_valid_perm("integration:xxx:yyy")
    assert not is_valid_perm("module_ai:train:create")

def test_normalize_permissions_drops_invalid_and_dedupes():
    got = normalize_permissions(["integration:agent:create", "integration:agent:create", "bad"])
    assert got == {"integration:agent:create"}

def test_permissions_by_category_groups():
    got = permissions_by_category(["integration:agent:create", "integration:chat:send"])
    assert set(got["agent"]) == {"integration:agent:create"}
    assert set(got["chat"]) == {"integration:chat:send"}
```

- [ ] **Step 2: 运行确认失败**

Run（backend 目录）：`uv run pytest tests/test_develop_capabilities.py -q`
Expected: FAIL（`ModuleNotFoundError`）。

- [ ] **Step 3: 实现 `capabilities.py`**

定义 `CATEGORIES`、`CATEGORY_PERMS`、`PERMISSION_CODES`（`CATEGORY_PERMS` 值展开拼起来）、`is_valid_perm`、`normalize_permissions`（去重 + `is_valid_perm` 过滤）、`permissions_by_category`。权限点全集：
`integration:train:{create,query,start,stop}`、`integration:agent:{create,query,update,delete}`、`integration:chat:{send,query}`、`integration:bot:use`、`integration:embed:use`。

- [ ] **Step 4: 运行确认通过**

Run: `uv run pytest -q`（backend）
Expected: PASS（本文件含 `PYTEST_NO_APP` 判定则直接通过）。

- [ ] **Step 5: 提交**

```bash
git add backend/app/plugin/module_ai/develop tests/test_develop_capabilities.py
git commit -m "feat(ai): 定义 AI 集成能力品类与权限点"
```

---

### Task 2: 数据模型（3 张表）+ 手写迁移

**Files:**
- Create: `backend/app/plugin/module_ai/develop/model.py`
- Create: `backend/app/alembic/versions/2026_10_21_ai_integration_develop.py`
- Test: `backend/tests/test_develop_models.py`

**Interfaces:**
- Consumes: `MappedBase`, `ModelMixin`, `UserMixin`（`app.core.base_model`）
- Produces:
  - `AiIntegrationAppModel`（`__tablename__="ai_integration_apps"`）：`appid`(String64, unique, index), `appkey_hash`(String128), `name`(String128, unique), `enabled`(Boolean, default True), `expire_at`(DateTime, null), `capabilities`(JSONB list, default list), `quota`(JSONB dict, null), `requires_approval`(Boolean, default True), `source_type`(String16, default "admin"), `last_call_at`(DateTime, null), `call_count`(Integer, default 0)
  - `AiIntegrationCallLogModel`（`__tablename__="ai_integration_call_logs"`，直接 `MappedBase` + 自定义 `id/created_time`）：`app_id`(Integer, index), `appid`(String64), `category`(String16), `capability`(String64), `log_type`(String16), `method`(String16), `transport`(String16), `session_id`(String64, null), `client_info`(String128, null), `request_path`(String255), `request_body`(JSONB, null), `status`(String16), `error`(String255, null), `latency_ms`(Integer, default 0), `cost_tokens`(Integer, default 0), `result_summary`(String512, null)
  - `AiIntegrationMcpSessionModel`（`__tablename__="ai_integration_mcp_sessions"`，直接 `MappedBase` + 自定义 `id/created_time`）：`app_id`(Integer, index), `appid`(String64), `session_id`(String64), `transport`(String16), `client_info`(String128, null), `started_at`(DateTime), `ended_at`(DateTime, null), `duration_s`(Integer, default 0), `tool_calls`(Integer, default 0), `close_reason`(String64, null)

- [ ] **Step 1: 写失败测试**

```python
# tests/test_develop_models.py
from app.plugin.module_ai.develop.model import (
    AiIntegrationAppModel, AiIntegrationCallLogModel, AiIntegrationMcpSessionModel,
)

def test_app_model_columns():
    cols = set(AiIntegrationAppModel.__table__.columns.keys())
    assert {"id", "uuid", "appid", "appkey_hash", "name", "enabled", "expire_at",
            "capabilities", "quota", "requires_approval", "source_type",
            "last_call_at", "call_count", "created_id", "updated_id"}.issubset(cols)

def test_call_log_model_has_no_soft_delete():
    cols = set(AiIntegrationCallLogModel.__table__.columns.keys())
    assert "is_deleted" not in cols and "deleted_time" not in cols
    assert {"id", "created_time", "app_id", "log_type", "method", "status"}.issubset(cols)

def test_mcp_session_model_columns():
    cols = set(AiIntegrationMcpSessionModel.__table__.columns.keys())
    assert {"session_id", "transport", "started_at", "tool_calls"}.issubset(cols)
```

- [ ] **Step 2: 运行确认失败**

Run: `uv run pytest tests/test_develop_models.py -q`
Expected: FAIL（`ImportError`）。

- [ ] **Step 3: 实现 `model.py`**

按 Interfaces 定义三个模型。注意 `AiIntegrationAppModel` 用 `ModelMixin, UserMixin`；两个审计表直接 `MappedBase` 并自行加 `id`(Integer PK) 与 `created_time`(DateTime, default=datetime.now, index=True)。

- [ ] **Step 4: 手写迁移**

Create `backend/app/alembic/versions/2026_10_21_ai_integration_develop.py`，`revision="c1d2e3f4a5b6"`、`down_revision="a2b3c4d5e6f7"`。`upgrade()` 用 `op.create_table` 建三张表（JSONB 用 `postgresql.JSONB(astext_type=sa.Text())`；FK 用 `sa.ForeignKey("ai_integration_apps.id")`；按 `ai_market_models.py` 格式为 `id/uuid/created_time/updated_time/is_deleted/deleted_time/app_id/appid` 等列建索引）。`downgrade()` 逆序 `op.drop_table`。

- [ ] **Step 5: 运行确认通过（模型 + 迁移往返）**

Run: `uv run pytest tests/test_develop_models.py -q`
Expected: PASS
Run: `uv run main.py upgrade --env=dev`（若有 dev 库；或针对回归库执行 upgrade/downgrade 往返）
Expected: 三表创建成功；`downgrade` 后三表删除。

- [ ] **Step 6: 提交**

```bash
git add backend/app/plugin/module_ai/develop/model.py backend/app/alembic/versions/2026_10_21_ai_integration_develop.py tests/test_develop_models.py
git commit -m "feat(ai): AI 集成三表模型与手写迁移"
```

---

### Task 3: schema + service（app CRUD、appid/appkey 生成与重置）

**Files:**
- Create: `backend/app/plugin/module_ai/develop/schema.py`
- Create: `backend/app/plugin/module_ai/develop/service.py`
- Test: `backend/tests/test_develop_crud.py`

**Interfaces:**
- Consumes: `AiIntegrationAppModel`, `normalize_permissions`, `CustomException`（`app.core.exceptions`）, `async_db_session`, `AuthSchema`
- Produces:
  - `DevelopCreateSchema`: `name`(str), `description`(str|None), `capabilities`(list[str]|None), `expire_at`(datetime|None), `quota`(dict|None), `requires_approval`(bool|None=True)
  - `DevelopUpdateSchema`: 同上字段均可空
  - `_generate_appid() -> str`（`ai_` + 8 位去易混淆字符随机）
  - `_hash_appkey(appkey: str) -> str`（sha256 hex）
  - `DevelopService.list_apps(keyword=None, page=1, page_size=20) -> dict`（返回 `{page_no,page_size,total,has_next,items}`，`items` 不含 `appkey_hash`，含 `appid_masked`）
  - `DevelopService.get_app(app_id) -> dict | None`
  - `DevelopService.create_app(data, auth: AuthSchema) -> dict`（**含一次性明文 `appkey`**）
  - `DevelopService.update_app(app_id, data, auth) -> dict | None`
  - `DevelopService.delete_app(ids, auth) -> None`（软删，释放唯一 `name/appid` 用 `__deleted_{id}_{ts}` 后缀）
  - `DevelopService.toggle_app(app_id, enabled, auth) -> dict | None`
  - `DevelopService.reset_appkey(app_id, auth) -> dict`（返回 `{appid, appkey}` 明文一次）
  - `DevelopService.verify_appkey(appid, appkey) -> AiIntegrationAppModel | None`（查+校验+状态+到期，失败返回 None）
  - `DevelopService.log_call(app, *, category, capability, log_type="invoke", method="REST", transport=None, session_id=None, client_info=None, request_path=None, request_body=None, status, error=None, latency_ms=0, cost_tokens=0, result_summary=None) -> None`（写 `ai_integration_call_logs`，并顺手更新 app 的 `last_call_at`/`call_count`）

- [ ] **Step 1: 写失败测试**

```python
# tests/test_develop_crud.py
import hashlib
import pytest
from app.plugin.module_ai.develop.service import _generate_appid, _hash_appkey, DevelopService
from app.plugin.module_ai.develop.schema import DevelopCreateSchema
from app.core.exceptions import CustomException

class _User:  # 兼容 auth.user.id / auth.user.is_superuser
    id = 1
    is_superuser = True

class _Auth:  # 轻量 auth 桩，避免依赖完整 AuthSchema 构造
    user = _User()

def test_generate_appid_format_and_uniqueness():
    ids = {_generate_appid() for _ in range(1000)}
    assert all(i.startswith("ai_") and len(i) == 11 for i in ids)
    assert len(ids) == 1000  # 无明显重复/易混淆

def test_hash_appkey_sha256():
    assert _hash_appkey("abc") == hashlib.sha256("abc".encode()).hexdigest()
    assert _hash_appkey("abc") != _hash_appkey("abd")

@pytest.mark.app  # 需要 DB 的用例
async def test_create_app_returns_plaintext_key_once():
    res = await DevelopService.create_app(
        DevelopCreateSchema(name="demo", capabilities=["integration:agent:create"]), _Auth())
    assert res["appid"].startswith("ai_")
    assert res["appkey"] and len(res["appkey"]) >= 32
    assert "appkey_hash" not in res
    # 再查库：哈希存在，但无明文
    row = await DevelopService.get_app(res["id"])
    assert "appkey_hash" not in row and "appkey" not in row

@pytest.mark.app
async def test_duplicate_name_rejected():
    await DevelopService.create_app(DevelopCreateSchema(name="dup"), _Auth())
    with pytest.raises(CustomException):
        await DevelopService.create_app(DevelopCreateSchema(name="dup"), _Auth())

@pytest.mark.app
async def test_reset_appkey_old_fails_new_works():
    created = await DevelopService.create_app(DevelopCreateSchema(name="r"), _Auth())
    old = created["appkey"]
    reset = await DevelopService.reset_appkey(created["id"], _Auth())
    assert reset["appkey"] != old
    assert await DevelopService.verify_appkey(created["appid"], old) is None
    assert await DevelopService.verify_appkey(created["appid"], reset["appkey"]) is not None

@pytest.mark.app
async def test_disabled_or_expired_app_auth_fails():
    from datetime import datetime, timedelta
    c = await DevelopService.create_app(DevelopCreateSchema(
        name="e", expire_at=datetime.now()-timedelta(days=1)), _Auth())
    assert await DevelopService.verify_appkey(c["appid"], c["appkey"]) is None
    await DevelopService.toggle_app(c["id"], False, _Auth())
    assert await DevelopService.verify_appkey(c["appid"], c["appkey"]) is None
```

- [ ] **Step 2: 运行确认失败**

Run: `uv run pytest tests/test_develop_crud.py -q`
Expected: FAIL（`ImportError` / `AttributeError`）。

- [ ] **Step 3: 实现 `schema.py`**

按 Interfaces 用 Pydantic v2 定义 `DevelopCreateSchema` / `DevelopUpdateSchema`。

- [ ] **Step 4: 实现 `service.py`**

`_generate_appid` 用 `secrets.choice` 从无易混淆字符表（如去掉 `0O1lI`）取 8 位；`_hash_appkey` 用 `hashlib.sha256`。`verify_appkey` 先查 `appid`，再比对 `enabled`、`expire_at`（`expire_at` 非空且 `< now` 视为过期），最后用 `hmac.compare_digest(_hash_appkey(appkey), row.appkey_hash)`；任一失败返回 None。`create_app` 校验 `name` 唯一、`capabilities` 用 `normalize_permissions` 归一，生成 appid+appkey，存哈希，返回 dict（`appid`/`name`/`capabilities`/`appkey` 明文一次）。`reset_appkey` 生成新 appkey 覆盖哈希并返回一次。`list_apps` 分页并 `appid_masked`（如 `ai_ab**...**`）。

- [ ] **Step 5: 运行确认通过**

Run: `uv run pytest tests/test_develop_crud.py -q`
Expected: PASS。

- [ ] **Step 6: 提交**

```bash
git add backend/app/plugin/module_ai/develop/schema.py backend/app/plugin/module_ai/develop/service.py tests/test_develop_crud.py
git commit -m "feat(ai): AI 集成应用 CRUD 与 appid/appkey 生成重置"
```

---

### Task 4: 鉴权依赖 `get_app_api_auth` + `AppContext`

**Files:**
- Create: `backend/app/plugin/module_ai/develop/auth.py`
- Test: `backend/tests/test_develop_auth.py`

**Interfaces:**
- Consumes: `DevelopService.verify_appkey`, `CustomException`
- Produces:
  - `AppContext`（dataclass）：`app_id:int`、`appid:str`、`perms:set[str]`、`quota:dict|None`、`app:dict`
  - `_parse_bearer(authorization: str | None) -> tuple[str, str] | None`（纯函数，返回 `(appid, appkey)`；缺失/非 `Bearer ` 前缀/无冒号返回 None）
  - `async def get_app_api_auth(authorization: str | None = Header(None)) -> AppContext`（解析失败或校验不过抛 `CustomException(msg="鉴权失败", code=10401, status_code=401)`）
  - `def require_app_perm(ctx: AppContext, perm: str) -> None`（未授权抛 `CustomException(msg="无权限操作", code=10403, status_code=403)`）

- [ ] **Step 1: 写失败测试**

```python
# tests/test_develop_auth.py
import pytest
from app.plugin.module_ai.develop.auth import AppContext, require_app_perm, _parse_bearer
from app.core.exceptions import CustomException

def test_parse_bearer_valid():
    assert _parse_bearer("Bearer ai_x:abc:def") == ("ai_x", "abc:def")  # rsplit：appkey 可含冒号

def test_parse_bearer_missing_or_malformed():
    assert _parse_bearer(None) is None
    assert _parse_bearer("") is None
    assert _parse_bearer("Basic xxx") is None
    assert _parse_bearer("Bearer no-colon") is None

def test_require_app_perm_ok_and_denied():
    ctx = AppContext(app_id=1, appid="ai_x", perms={"integration:chat:send"}, quota=None, app={})
    require_app_perm(ctx, "integration:chat:send")  # 不抛
    with pytest.raises(CustomException) as ei:
        require_app_perm(ctx, "integration:train:create")
    assert ei.value.code == 10403

def test_empty_perms_denies_everything():
    ctx = AppContext(app_id=1, appid="ai_x", perms=set(), quota=None, app={})
    with pytest.raises(CustomException):
        require_app_perm(ctx, "integration:bot:use")
```

- [ ] **Step 2: 运行确认失败**

Run: `uv run pytest tests/test_develop_auth.py -q`
Expected: FAIL（`ImportError`）。

- [ ] **Step 3: 实现 `auth.py`**

`_parse_bearer`：`authorization` 若非 `Bearer ` 前缀则返回 None；取 `authorization[7:].strip()`，用 `credentials.rsplit(":", 1)`，不足两段返回 None。`get_app_api_auth`：`parsed = _parse_bearer(authorization)`，None → 401；调 `DevelopService.verify_appkey(appid, appkey)`，`None` → 401（不区分原因）；构造 `AppContext`（`perms = set(row.capabilities or [])`）。`require_app_perm`：`if perm not in ctx.perms: raise CustomException(...403)`。

- [ ] **Step 4: 运行确认通过（含 Review Focus 1/2/3/4 的鉴权集成验证在 Task 5 补）**

Run: `uv run pytest tests/test_develop_auth.py -q`
Expected: PASS。

- [ ] **Step 5: 提交**

```bash
git add backend/app/plugin/module_ai/develop/auth.py tests/test_develop_auth.py
git commit -m "feat(ai): 开放数据面 appid/appkey 鉴权依赖"
```

---

### Task 5: 开放数据面 `OpenApiRouter`（`/ai/develop-api`）+ 鉴权验证端点

**Files:**
- Create: `backend/app/plugin/module_ai/develop/controller.py`
- Test: `backend/tests/test_develop_openapi.py`

**Interfaces:**
- Consumes: `get_app_api_auth`, `require_app_perm`, `SuccessResponse`/`ErrorResponse`（`app.common.response`）
- Produces:
  - `OpenApiRouter = APIRouter(route_class=OperationLogRoute, prefix="/develop-api", tags=["AI-集成开放API"])`
  - 端点 `GET /auth/verify` → `SuccessResponse(data={appid, name, perms:[...], categories:{...}, expire_at, enabled})`（经 `get_app_api_auth`，无需 `require_app_perm`）

- [ ] **Step 1: 写失败测试**

```python
# tests/test_develop_openapi.py
import pytest
from httpx import AsyncClient

@pytest.mark.app
async def test_auth_verify_ok(client: AsyncClient, create_app: dict):
    # fixture create_app: 用 DevelopService 造一个有效 app，返回 {appid, appkey, id}
    resp = await client.get(
        "/api/v1/ai/develop-api/auth/verify",
        headers={"Authorization": f"Bearer {create_app['appid']}:{create_app['appkey']}"})
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["appid"] == create_app["appid"]
    assert "perms" in data and isinstance(data["perms"], list)
    # 写入成功 audit
    import asyncio
    from app.core.database import async_db_session
    from app.plugin.module_ai.develop.model import AiIntegrationCallLogModel
    from sqlalchemy import select, func
    async with async_db_session() as db:
        cnt = await db.scalar(select(func.count()).select_from(AiIntegrationCallLogModel))
    assert cnt and cnt >= 1

@pytest.mark.app
async def test_auth_verify_401_wrong_key(client: AsyncClient, create_app: dict):
    resp = await client.get(
        "/api/v1/ai/develop-api/auth/verify",
        headers={"Authorization": f"Bearer {create_app['appid']}:wrong"})
    assert resp.status_code == 401

@pytest.mark.app
async def test_auth_verify_401_unknown_app(client: AsyncClient):
    resp = await client.get(
        "/api/v1/ai/develop-api/auth/verify",
        headers={"Authorization": "Bearer ai_nonexistent:xyz"})
    assert resp.status_code == 401

@pytest.mark.app
async def test_auth_verify_missing_or_malformed_header_401(client: AsyncClient):
    assert (await client.get("/api/v1/ai/develop-api/auth/verify")).status_code == 401
    assert (await client.get(
        "/api/v1/ai/develop-api/auth/verify",
        headers={"Authorization": "Bearer no-colon"})).status_code == 401
```

- [ ] **Step 2: 运行确认失败**

Run: `uv run pytest tests/test_develop_openapi.py -q`
Expected: FAIL（路由不存在 → 404/500）。

- [ ] **Step 3: 实现 `controller.py` 中的 `OpenApiRouter`**

定义 `OpenApiRouter`，加 `GET /auth/verify`，依赖 `get_app_api_auth`，返回 app 信息 + `perms`（按品类 `permissions_by_category` 分组可选）；成功时 `await DevelopService.log_call(ctx.app, category="auth", capability="verify", method="REST", request_path="/auth/verify", status="success")` 写审计。

- [ ] **Step 4: 运行确认通过**

Run: `uv run pytest tests/test_develop_openapi.py -q`
Expected: PASS（含 Review Focus 1/2）。

- [ ] **Step 5: 提交**

```bash
git add backend/app/plugin/module_ai/develop/controller.py tests/test_develop_openapi.py
git commit -m "feat(ai): 开放数据面鉴权验证端点"
```

---

### Task 6: 内部管理面 `DevelopRouter`（`/ai/develop`）+ 审计查询

**Files:**
- Modify: `backend/app/plugin/module_ai/develop/controller.py`
- Test: `backend/tests/test_develop_admin.py`

**Interfaces:**
- Consumes: `DevelopService`, `AuthPermission(["module_ai:develop:*"])`, `ErrorResponse`
- Produces:
  - `DevelopRouter = APIRouter(route_class=OperationLogRoute, prefix="/develop", tags=["AI-集成管理"])`
  - 端点：`GET /list`（分页+keyword）、`GET /detail/{id}`、`POST /create`、`PUT /update/{id}`、`DELETE /delete`（ids body）、`PUT /toggle/{id}`（enabled body）、`POST /reset-key/{id}`、`GET /call-logs`（app_id/category/method/status 过滤分页）、`GET /mcp-sessions`（app_id 过滤分页）

- [ ] **Step 1: 写失败测试**

```python
# tests/test_develop_admin.py
import pytest
from httpx import AsyncClient

@pytest.mark.app
async def test_admin_list_requires_perm(client: AsyncClient, auth_headers: dict):
    # auth_headers: admin 登录头；若无该权限则 403，需先给 admin 授 module_ai:develop:query
    resp = await client.get("/api/v1/ai/develop/list", headers=auth_headers)
    assert resp.status_code == 200
    assert "items" in resp.json()["data"]

@pytest.mark.app
async def test_admin_create_and_reset(client: AsyncClient, auth_headers: dict):
    resp = await client.post("/api/v1/ai/develop/create", json={
        "name": "外部客户", "capabilities": ["integration:agent:create"]}, headers=auth_headers)
    assert resp.status_code == 200
    appid = resp.json()["data"]["appid"]
    assert "appkey" in resp.json()["data"]
    rid = resp.json()["data"]["id"]
    r2 = await client.post(f"/api/v1/ai/develop/reset-key/{rid}", headers=auth_headers)
    assert r2.status_code == 200 and "appkey" in r2.json()["data"]
```

- [ ] **Step 2: 运行确认失败**

Run: `uv run pytest tests/test_develop_admin.py -q`
Expected: FAIL（路由不存在 / 403）。

- [ ] **Step 3: 实现 `DevelopRouter` 各端点**

每个端点 `Depends(AuthPermission([...]))`，调用 `DevelopService`，用 `SuccessResponse`/`ErrorResponse` 包裹。`reset-key`、`delete` 返回明确提示。

- [ ] **Step 4: 运行确认通过**

Run: `uv run pytest tests/test_develop_admin.py -q`
Expected: PASS。

- [ ] **Step 5: 提交**

```bash
git add backend/app/plugin/module_ai/develop/controller.py tests/test_develop_admin.py
git commit -m "feat(ai): AI 集成管理面路由与审计查询"
```

---

### Task 7: 菜单与按钮权限种子 `_ensure_develop_menus()`

**Files:**
- Modify: `backend/app/scripts/init_app.py`（`AI_BUTTON_PERMS` 增项 + 新增 `_ensure_develop_menus` + 在启动序列 `await _ensure_ai_menus()` 附近的 `~1610` 调用）
- Test: `backend/tests/test_ai_menus.py`（补充断言）

**Interfaces:**
- Consumes: `ensure_perms`, `MenuModel`, `RoleMenusModel`, `async_db_session`
- Produces: 菜单「AI 集成」`route_name=AiDevelop`、`/ai/develop`、`module_ai/develop/index`、`module_ai:develop:query`、父级为 `AI`；按钮权限 `module_ai:develop:{query,create,update,delete,reset}`

- [ ] **Step 1: 在 `AI_BUTTON_PERMS` 追加**

```python
# AI 集成开放平台（应用凭证、appid/appkey、审计）
("module_ai:develop:query", "查询AI集成应用"),
("module_ai:develop:create", "新增AI集成应用"),
("module_ai:develop:update", "编辑AI集成应用"),
("module_ai:develop:delete", "删除AI集成应用"),
("module_ai:develop:reset", "重置AI集成应用密钥"),
```

- [ ] **Step 2: 写失败测试（`tests/test_ai_menus.py` 追加）**

```python
def test_develop_menu_registered():
    # 复用该文件既有 fixture/断言模式，断言存在 route_name=AiDevelop 且 permission 为 module_ai:develop:query
```

- [ ] **Step 3: 实现 `_ensure_develop_menus()`**

参照 `_ensure_ai_menus`：查 `AI` 父菜单，若无则 warning 返回；若 `AiDevelop` 菜单不存在则建（type=2），存在则更新为未隐藏；`db.flush()` 后给 `role_id=1` 补 `RoleMenusModel`；再用 `ensure_perms(existing, develop_button_perms)` 补 type=3 按钮权限。在启动序列（`await _ensure_ai_menus()` 后）调用。

- [ ] **Step 4: 运行确认通过**

Run: `uv run pytest tests/test_ai_menus.py -q`（及 `uv run main.py run --env=dev --no-reload` 后菜单/权限出现）
Expected: PASS（菜单与按钮权限幂等存在，不重复）。

- [ ] **Step 5: 提交**

```bash
git add backend/app/scripts/init_app.py tests/test_ai_menus.py
git commit -m "feat(ai): 注册 AI 集成菜单与按钮权限"
```

---

### Task 8: 前端 API + 「AI 集成」页面

**Files:**
- Create: `frontend/src/api/module_ai/develop.ts`
- Create: `frontend/src/views/module_ai/develop/index.vue`（页签：应用管理 / 调用日志 / MCP 会话 / 接入文档）
- Test: `frontend/src/views/module_ai/develop/` 页面可被 `pnpm run type-check` 通过 + 无 `v-hasPerm` 引号错误

**Interfaces:**
- Consumes: `useCrudList`, `PageSearch`/`PageContent`/`EnhancedDialog`（若用现成 CRUD 组件）或参照 `module_ai/provider/index.vue` 的 `el-form`+`el-table`+`el-dialog` 模式；`v-hasPerm`
- Produces:
  - API 函数 `getDevelopAppList/createApp/updateApp/deleteApp/toggleApp/resetAppkey/getCallLogs/getMcpSessions/verifyAuth`（`/ai/develop/...` 前缀）
  - 页面：应用管理（列：名称、appid（打码+可复制）、状态、到期、权限点、调用次数）；「查看/重置 appkey」弹窗（appkey 明文一次性、`ElMessageBox.confirm` 二次确认）；启用/停用；新建/编辑弹窗含 `el-checkbox-group` 勾选能力权限点（来自 `GET /auth/verify` 或后端返回的 `CATEGORIES`/`CATEGORY_PERMS`）。

- [ ] **Step 1: 写 `develop.ts`（API 封装）**

按 `module_ai/provider.ts` 风格列出上述函数。

- [ ] **Step 2: 写页面 `index.vue`**

参照 `module_ai/provider/index.vue`：单根容器 `<div class="app-container">`；页签用 `el-tabs`；应用管理用 `el-table` + `el-dialog`；权限点勾选用 `el-checkbox-group`（数据源 `CATEGORY_PERMS`）；重置/删除用 `ElMessageBox.confirm`（文案含影响范围与不可逆性）；所有操作按钮带 `v-hasPerm`。调用日志与 MCP 会话两个只读列表（分页 + 过滤），「接入文档」静态展示 REST/MCP/嵌入示例。

- [ ] **Step 3: 类型检查**

Run（frontend 目录）：`pnpm run type-check`
Expected: 通过；确认模板内所有 `v-hasPerm` 的值是带内层单引号的字符串表达式（如 `v-hasPerm="'module_ai:develop:create'"`），避免 `TS1005`。

- [ ] **Step 4: 视觉核对**

用无头浏览器打开 `/ai/develop` 截图，与既有 `module_ai/provider` 页面样式对齐（字号 `--el-font-size-base`、`--el-*` 变量、Element Plus 组件；不写死 `#409eff` 等）。

- [ ] **Step 5: 提交**

```bash
git add frontend/src/api/module_ai/develop.ts frontend/src/views/module_ai/develop
git commit -m "feat(ai): 新增 AI 集成管理页面（应用/日志/接入文档）"
```

---

### Task 9: 全量回归（提交前）

**Files:**
- None（验证性任务）

- [ ] **Step 1: 后端全量测试**

Run（backend 目录）：`uv run pytest -q -n 4`
Expected: 全通过（含新增 `test_develop_*`、`test_ai_menus` 更新）。**不要用 `-n 8`**。

- [ ] **Step 2: 后端 lint**

Run: `uv run ruff check && uv run ruff check --fix`
Expected: 无错误。

- [ ] **Step 3: 前端类型检查 + lint**

Run（frontend）：`pnpm run type-check && pnpm run lint`
Expected: 通过（忽略既有 `LivePlayer.vue`/`live/index.vue`/`playback/index.vue` 的存量错误）。

- [ ] **Step 4: 提交收尾**

```bash
git add -A
git commit -m "chore(ai): AI 集成 P1 全量回归通过"
```

---

## 里程碑验收（对照 spec §8）

- 能在「AI 集成」菜单创建应用并拿到 appid/appkey；`/ai/develop-api/auth/verify` 用明文 key 调通、错误 key 401。
- 用 appid/appkey 调开放端点鉴权正确：过期/停用/无权限被拒并记录。
- 调用与 MCP 行为写入 `ai_integration_call_logs` / `ai_integration_mcp_sessions`，前端「调用日志/MCP 会话」可查。
- appkey 重置后旧 key 失效、新 key 生效；重复 name 被拒。
- 菜单与按钮权限（`module_ai:develop:*`）幂等注册，admin 可见「AI 集成」。
