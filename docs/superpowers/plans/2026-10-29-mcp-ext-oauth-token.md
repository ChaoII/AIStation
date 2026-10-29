# 阶段 3b：MCP 复用外部 OAuth token 层 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** 让 MCP 服务器可绑定「外部 OAuth 服务」，当该 MCP 被 Agent 在某用户会话中装配建连时自动注入该用户（= 创建者）对外部服务的 `Authorization: Bearer <access>`，复用阶段 3a 的 token 层。

**Architecture:** `AiMcpServerModel` 加 `oauth_ext_service_id` 绑定列。`build_mcp_tools(servers, user_id)` 建连前对绑定服务的服务器调 `OAuthExtService.resolve_ext_access_token` 取 access（过期自动 refresh）注入 headers；未绑定/取 token 失败则跳过该 MCP（降级不中断）。装配点（`_office_caps` 与 agent 运行台）传 `user_id`。

**Tech Stack:** FastAPI + SQLAlchemy 2.0 + Pydantic v2 + agno `MCPTools` + 阶段 3a `resolve_ext_access_token`。

**Spec:** `docs/superpowers/specs/2026-10-29-mcp-ext-oauth-token-design.md`

## Global Constraints

- 迁移手写（dev 库 400+ 影子表，禁 autogenerate）；用 `has_table`/`has_column` 幂等守卫。
- 新迁移 revision `a3b4c5d6e7f8`，`down_revision='b8c9d0e1f2a3'`（当前唯一 head，已核对未被占用）。
- `oauth_ext_service_id` FK 到 `ai_oauth_ext_services.id`，可空，`index=True`。
- 注入的 `Authorization` 头**合并**到已有 headers，不覆盖用户自定义的其它头。
- 未绑定 / user_id 空 / 取 token 失败 → 跳过该 MCP（`log.warning`），不中断对话。
- 复用阶段 3a `resolve_ext_access_token(service_id, user_id) -> str`（过期内部静默 refresh）。
- 受理代码用中文注释；提交信息 `feat(auth): 中文描述`。

## Review Focus

1. 未绑定外部服务的 MCP 服务器，建连应**不带** `Authorization` 头（行为与现状完全一致）。
2. 绑定服务但当前用户**未连接/已撤销**该外部服务，该 MCP 应被跳过（tools 不含它），不抛异常。
3. `build_mcp_tools` 调用方未传 `user_id`（None）时，绑定服务应退化为不注入，保持可用。
4. **关键**：`build_mcp_tools` 目前不接收 user_id，所有装配点都必须改为传 `user_id`，否则注入永远不触发。

---

### Task 1: 给 `AiMcpServerModel` 加绑定列 + schema + 迁移

**Files:**
- Modify: `backend/app/plugin/module_ai/mcp/model.py`
- Modify: `backend/app/plugin/module_ai/mcp/schema.py`
- Create: `backend/app/alembic/versions/a3b4c5d6e7f8_mcp_oauth_ext.py`
- Test: `backend/tests/test_oauth_ext_mcp_model.py`

**Interfaces:**
- Consumes: 阶段 3a 表 `ai_oauth_ext_services`（FK 目标）。
- Produces: `AiMcpServerModel.oauth_ext_service_id` 列；`McpCreateSchema.oauth_ext_service_id` /
  `McpUpdateSchema.oauth_ext_service_id`（`int | None`）。后续 Task 2 依赖。

- [x] **Step 1: 写失败测试**

`tests/test_oauth_ext_mcp_model.py`：
```python
def test_mcp_model_instantiate(test_client):
    from app.plugin.module_ai.mcp.model import AiMcpServerModel
    s = AiMcpServerModel(name="svc", transport="streamable-http", oauth_ext_service_id=3)
    assert s.oauth_ext_service_id == 3

def test_mcp_create_schema_accepts_binding(test_client):
    from app.plugin.module_ai.mcp.schema import McpCreateSchema, McpUpdateSchema
    c = McpCreateSchema(name="x", oauth_ext_service_id=5)
    assert c.oauth_ext_service_id == 5
    u = McpUpdateSchema(oauth_ext_service_id=7)
    assert u.oauth_ext_service_id == 7
```

- [x] **Step 2: 跑测试确认失败**

Run: `pytest tests/test_oauth_ext_mcp_model.py -q`
Expected: FAIL（`AiMcpServerModel` 无 `oauth_ext_service_id` 属性 / schema 字段不存在）。

- [x] **Step 3: 实现 model 加列**

`mcp/model.py`：`from sqlalchemy import Boolean, ForeignKey, Integer, String, Text`（加 `ForeignKey`、`Integer`）。
在 `description` 列后加：
```python
oauth_ext_service_id: Mapped[int | None] = mapped_column(
    Integer,
    ForeignKey("ai_oauth_ext_services.id"),
    nullable=True,
    default=None,
    index=True,
    comment="绑定的外部OAuth服务ID（MCP建连时注入Bearer）",
)
```

- [x] **Step 4: 实现 schema 加字段**

`mcp/schema.py`：`McpCreateSchema` 与 `McpUpdateSchema` 各加：
```python
oauth_ext_service_id: int | None = Field(default=None, description="绑定的外部OAuth服务ID（MCP建连时注入Bearer）")
```

- [x] **Step 5: 写迁移文件 `a3b4c5d6e7f8_mcp_oauth_ext.py`**

```python
"""AI 集成开放平台：ai_mcp_servers 增列 oauth_ext_service_id（绑定外部OAuth服务）

Revision ID: a3b4c5d6e7f8
Revises: b8c9d0e1f2a3
Create Date: 2026-10-29 18:00:00.000000

手写迁移（autogenerate 会因影子表产生无关 DROP）。仅追加一列，用 has_column 幂等守卫。
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "a3b4c5d6e7f8"
down_revision: str | None = "b8c9d0e1f2a3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if "ai_mcp_servers" in insp.get_table_names():
        cols = {c["name"] for c in insp.get_columns("ai_mcp_servers")}
        if "oauth_ext_service_id" not in cols:
            op.add_column(
                "ai_mcp_servers",
                sa.Column("oauth_ext_service_id", sa.Integer(), nullable=True, comment="绑定的外部OAuth服务ID（MCP建连时注入Bearer）"),
            )
            op.create_index(op.f("ix_ai_mcp_servers_oauth_ext_service_id"), "ai_mcp_servers", ["oauth_ext_service_id"], unique=False)


def downgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if "ai_mcp_servers" in insp.get_table_names():
        cols = {c["name"] for c in insp.get_columns("ai_mcp_servers")}
        if "oauth_ext_service_id" in cols:
            op.drop_index(op.f("ix_ai_mcp_servers_oauth_ext_service_id"), table_name="ai_mcp_servers")
            op.drop_column("ai_mcp_servers", "oauth_ext_service_id")
```

- [x] **Step 6: 跑测试确认通过**

Run: `pytest tests/test_oauth_ext_mcp_model.py -q`
Expected: PASS

- [x] **Step 7: ruff + 校验 head + 提交**

Run: `ruff check app/plugin/module_ai/mcp/ app/alembic/versions/a3b4c5d6e7f8_mcp_oauth_ext.py`
Expected: All checks passed
Run: `python -c "from alembic.config import Config; from alembic.script import ScriptDirectory; print(ScriptDirectory.from_config(Config('alembic.ini')).get_heads())"`
Expected: `['a3b4c5d6e7f8']`

```bash
git add backend/app/plugin/module_ai/mcp/model.py backend/app/plugin/module_ai/mcp/schema.py backend/app/alembic/versions/a3b4c5d6e7f8_mcp_oauth_ext.py backend/tests/test_oauth_ext_mcp_model.py
git commit -m "feat(auth): 阶段3b MCP服务器加外部OAuth绑定列+迁移"
```

---

### Task 2: service 处理绑定列 + `build_mcp_tools` 注入 Bearer

**Files:**
- Modify: `backend/app/plugin/module_ai/mcp/service.py`（`_to_dict` / `create` / `update`）
- Modify: `backend/app/plugin/module_ai/mcp/tools.py`（`build_mcp_tools`）
- Test: `backend/tests/test_oauth_ext_mcp_inject.py`

**Interfaces:**
- Consumes: Task 1 的 `oauth_ext_service_id` 列；阶段 3a `OAuthExtService.resolve_ext_access_token`、
  `OAuthExtService.get_service`。
- Produces: `build_mcp_tools(servers: list[dict] | None, user_id: int | None = None) -> list`；
  `_to_dict`/`create`/`update` 处理 `oauth_ext_service_id`。Task 3 的装配点调用依赖此签名。

- [x] **Step 1: 写失败测试**

`tests/test_oauth_ext_mcp_inject.py`：
```python
# 用 mock 捕获 MCPTools 构造；绑定服务时 headers 含 Authorization: Bearer
def test_build_mcp_tools_injects_bearer(monkeypatch):
    import asyncio
    from app.plugin.module_ai.mcp import tools as mcp_tools

    captured = {}
    def fake_mcp_tools(**kwargs):
        captured.update(kwargs)
        return object()
    import agno.tools.mcp as agno_mcp
    monkeypatch.setattr(agno_mcp, "MCPTools", fake_mcp_tools)

    async def fake_resolve(service_id, user_id):
        return "ext-access-token"
    from app.plugin.module_ai.oauth_ext.service import OAuthExtService
    monkeypatch.setattr(OAuthExtService, "resolve_ext_access_token", staticmethod(fake_resolve))

    result = asyncio.run(mcp_tools.build_mcp_tools(
        [{"name": "m", "transport": "streamable-http", "url": "https://x/mcp", "headers": {"X-A": "1"}, "oauth_ext_service_id": 5}],
        user_id=1,
    ))
    assert len(result) == 1
    assert captured["headers"]["Authorization"] == "Bearer ext-access-token"
    assert captured["headers"]["X-A"] == "1"  # 不覆盖用户自定义头

def test_build_mcp_tools_unbound_no_auth(monkeypatch):
    import asyncio
    from app.plugin.module_ai.mcp import tools as mcp_tools
    captured = {}
    def fake_mcp_tools(**kwargs):
        captured.update(kwargs)
        return object()
    import agno.tools.mcp as agno_mcp
    monkeypatch.setattr(agno_mcp, "MCPTools", fake_mcp_tools)
    asyncio.run(mcp_tools.build_mcp_tools([{"name": "m", "transport": "streamable-http", "url": "https://x/mcp", "headers": {"X-A": "1"}}], user_id=1))
    assert "Authorization" not in (captured.get("headers") or {})

def test_build_mcp_tools_not_connected_skips(monkeypatch):
    """绑定服务但用户未连接/已撤销 -> 该服务器被跳过，不抛异常。"""
    import asyncio
    from app.plugin.module_ai.mcp import tools as mcp_tools
    import agno.tools.mcp as agno_mcp
    from app.plugin.module_ai.oauth_ext.service import OAuthExtService
    from app.core.exceptions import CustomException

    calls = []
    def fake_mcp_tools(**kwargs):
        calls.append(kwargs)
        return object()
    monkeypatch.setattr(agno_mcp, "MCPTools", fake_mcp_tools)

    async def fake_resolve(service_id, user_id):
        raise CustomException(msg="你尚未连接该外部服务", code=10404, status_code=404)
    monkeypatch.setattr(OAuthExtService, "resolve_ext_access_token", staticmethod(fake_resolve))

    result = asyncio.run(mcp_tools.build_mcp_tools(
        [{"name": "m", "transport": "streamable-http", "url": "https://x/mcp", "oauth_ext_service_id": 5}],
        user_id=1,
    ))
    assert len(result) == 0   # 服务器被跳过
    assert len(calls) == 0    # 未构造任何 MCPTools
```

- [x] **Step 2: 跑测试确认失败**

Run: `pytest tests/test_oauth_ext_mcp_inject.py -q`
Expected: FAIL（`build_mcp_tools` 不接受 `user_id` / 不注入 Bearer）。

- [x] **Step 3: `mcp/service.py` 处理绑定列**

- `_to_dict` 增加 `"oauth_ext_service_id": getattr(s, "oauth_ext_service_id", None)`。
- `create` 构造 `AiMcpServerModel(...)` 时加 `oauth_ext_service_id=getattr(data, "oauth_ext_service_id", None)`。
- `update` 的字段循环加 `"oauth_ext_service_id"`（仅显式传入时 setattr，与其它字段一致）。

- [x] **Step 4: `mcp/tools.py` 扩展 `build_mcp_tools(servers, user_id=None)`**

**决定：`build_mcp_tools` 改为 `async def`**（因为注入需 `await resolve_ext_access_token`），签名：
```python
async def build_mcp_tools(servers: list[dict] | None, user_id: int | None = None) -> list:
```
具体：
1. 函数体整体改为 async（原有逻辑保持，含两处 `MCPTools` 构造的 stdio / streamable-http 分支）。
2. 在 `for s in servers:` 循环内、构造 `MCPTools` 前，先计算 `headers`：
   - 对 streamable-http/sse 分支：`s.get("headers")` 经 `_str_map` 后作为基础 headers。
   - 若 `oauth_ext_service_id` 非空且 `user_id` 非空：
     ```python
     from app.plugin.module_ai.oauth_ext.service import OAuthExtService
     try:
         access = await OAuthExtService.resolve_ext_access_token(service_id, user_id)
     except Exception as e:  # noqa: BLE001  未连接/已撤销/刷新失败 -> 跳过该服务器
         log.warning(f"MCP 服务器 {name} 外部OAuth授权不可用，已跳过：{e}")
         continue
     headers = headers or {}
     headers["Authorization"] = f"Bearer {access}"
     ```
   - 把合并后的 `headers` 传给 `MCPTools(headers=...)`。
3. **stdio 分支不注入 Authorization**（stdio 用 `env` 传环境变量，OAuth Bearer 不适用）；仅对
   streamable-http/sse（有 url 的）分支注入。
4. 未绑定服务 / `user_id` 为 None 时 `headers` 原样（不注入），行为与现状一致。
> 注：两处装配点（`_office_caps` 与 agent 运行台）原本同步调用 `build_mcp_tools(servers)`，
> 改 async 后必须 `await`（Task 3 处理）。若本任务改完 async 后其它同步调用点报错，
> 一并确认是否还有未覆盖的调用点（当前仅这两处）。

- [x] **Step 5: 跑测试确认通过**

Run: `pytest tests/test_oauth_ext_mcp_inject.py -q`
Expected: PASS

- [x] **Step 6: ruff + 提交**

Run: `ruff check app/plugin/module_ai/mcp/`
Expected: All checks passed

```bash
git add backend/app/plugin/module_ai/mcp/service.py backend/app/plugin/module_ai/mcp/tools.py backend/tests/test_oauth_ext_mcp_inject.py
git commit -m "feat(auth): 阶段3b build_mcp_tools建连前注入外部OAuth Bearer"
```

---

### Task 3: 装配点传 user_id + 收尾回归 + 重启验证

**Files:**
- Modify: `backend/app/plugin/module_ai/agent/service.py`（`_office_caps` L202、agent 运行台 L1944）
- Test: 现有 `tests/` 回归

**Interfaces:**
- Consumes: Task 2 的 `build_mcp_tools(servers, user_id)`（现为 async）。
- Produces: 两处装配点 `await build_mcp_tools(servers, user_id)` / `await build_mcp_tools(servers, uid)`。

- [x] **Step 1: 两处装配点改为 async + 传 user_id**

- `_office_caps`（约 L202）：`out["extra_tools"].extend(await build_mcp_tools(servers, user_id))`。
- agent 运行台（约 L1944）：`mcp_tools = await build_mcp_tools(servers, uid)`。
> 注：`_office_caps` 与运行台本就是 async 函数，`await build_mcp_tools(...)` 即可；`build_mcp_tools`
> 需保持可 `await`（Task 2 已改 async）。若 `build_mcp_tools` 因 async 改动导致其它同步调用处报错，
> 检查是否还有未覆盖的调用点（当前仅这两处）。

- [x] **Step 2: 红包回归测试（无关绑定行为不变）**

Run: `pytest tests/ -k "mcp or oauth" -q`
Expected: 既有 MCP/oauth 用例通过（无新失败）。

- [x] **Step 3: 校验 head 唯一**

Run: `python -c "from alembic.config import Config; from alembic.script import ScriptDirectory; print(ScriptDirectory.from_config(Config('alembic.ini')).get_heads())"`
Expected: `['a3b4c5d6e7f8']`

- [x] **Step 4: 重启后端（--no-reload）并验证**

按 AGENTS.md 规矩：确认 8002 是 `--no-reload` main.py 实例后重启；等就绪后：
`Invoke-WebRequest http://127.0.0.1:8002/openapi.json`
Expected: HTTP 200 且含 `/ai/mcp` 端点（MCP 管理路由已存在）。

- [x] **Step 5: 提交**

```bash
git add backend/app/plugin/module_ai/agent/service.py
git commit -m "feat(auth): 阶段3b MCP装配点传user_id注入外部Bearer"
```

- [x] **Step 6: 勾选计划 Task 并收尾**

本计划各 Task 的 checkbox 全部勾选；确认 `docs/superpowers/plans/2026-10-29-mcp-ext-oauth-token.md` 与 spec 对齐。

---

## 执行说明

- 每 Task 的 DB 测试用 `test_client` + `auth_headers`（带 `X-Forwarded-For`）；纯逻辑用 `PYTEST_NO_APP=1`。
- `build_mcp_tools` 改为 async 是**本计划唯一**的结构性改动，务必同步两处装配点为 `await`。
- 阶段 3b 无新 token 表 / 无新刷新逻辑；一切复用阶段 3a。
- `revision='a3b4c5d6e7f8'` 已核对未占用；`down_revision='b8c9d0e1f2a3'` 是当前唯一 head。
