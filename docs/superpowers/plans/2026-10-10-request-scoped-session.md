# 请求作用域会话 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让每个 HTTP 请求只占一条数据库连接（服务层透明复用请求会话），并把会话归还点搬到 ASGI 中间件，消除「被取消的请求漏连接 → 池死锁 → 必须重启」的根因。

**Architecture:** 纯 ASGI 中间件为请求建一条会话并写入 ContextVar（同时记录 owner task）；`async_db_session` 从 `async_sessionmaker` 换成上下文感知包装器——**仅当同任务时**复用请求会话，否则新建（后台任务/子任务行为不变）。`db_getter` 优先返回请求会话。看门狗保留为兜底。

**Tech Stack:** Python 3.13、FastAPI/Starlette（纯 ASGI middleware）、SQLAlchemy 2.0 async、pytest（SQLite + `TestClient`）。

**Spec:** `docs/superpowers/specs/2026-10-10-request-scoped-session-design.md`

## Global Constraints

- 后端命令一律在 `backend/` 下用 `uv run`；测试为 `uv run pytest`。
- **`async_db_session` 的导入路径与调用形式（`()` 与 `.begin()`）不得变**——全仓 761 处调用点零改动。
- 中间件**必须是纯 ASGI 类**；禁止 `BaseHTTPMiddleware`（会为下游新建任务，破坏 owner-task 判定）。
- `MAX_OVERFLOW` / `POOL_SIZE` 不改（用户确认 `POOL_SIZE=48` 维持）。
- 新增代码注释、文档、提交信息一律中文；提交信息格式 `type(scope): 中文描述`。
- 测试沿用仓库既有风格：**同步 `def test_*()` + 内部 `async def _run()` + `asyncio.run(_run())`**（无 pytest-asyncio）。

## Review Focus

以下 5 类是 spec 隐含、但容易被一次性改动碰坏、且最可能伤害使用者的输入/失败模式：

1. **请求被取消/客户端断开**——必须仍归还连接（这是本次修复的根因场景，也是最难验证的）。
2. **请求内 `asyncio.create_task` 子任务**——绝不能复用请求会话，否则请求结束时会话被关，子任务崩溃。
3. **无请求上下文的后台任务/调度器**——必须仍各自新建会话（训练/推理/定时任务）。
4. **WebSocket 请求**——中间件必须透传，不得给 WS 建请求会话。
5. **长连接流式响应（SSE/媒体流）**——会话会被持有到流结束，流内写入不得丢。

---

### Task 1: ContextVar 访问器 + 上下文感知会话包装器

**Files:**
- Modify: `backend/app/core/database.py`（在 `async_engine, async_db_session = ...` 附近，约 111-112 行；以及 `_LEAK_*` 常量附近新增访问器）
- Test: `backend/tests/test_request_session.py`（新建）

**Interfaces:**
- Consumes: 现有 `create_async_engine_and_session()` 返回的 `async_sessionmaker[AsyncSession]`。
- Produces（后续任务依赖这些精确名字）：
  - `activate_request_session(session: AsyncSession) -> contextvars.Token`
  - `deactivate_request_session(token: contextvars.Token) -> None`
  - `current_request_session() -> AsyncSession | None`
  - `_SessionFactory(factory: async_sessionmaker[AsyncSession])`，实现 `__call__()` 与 `begin()`（均为 `@asynccontextmanager`）
  - `async_db_session: _SessionFactory`（模块级对象，导出名不变）

- [ ] **Step 1: 写失败测试**

创建 `backend/tests/test_request_session.py`：

```python
"""请求作用域会话：同任务复用、跨任务隔离、无上下文新建。"""
import asyncio
import contextvars  # noqa: F401 - 类型标注可见性

from app.core.database import (
    activate_request_session,
    async_db_session,
    current_request_session,
    deactivate_request_session,
)


def test_no_ambient_creates_new_session_and_accessor_is_none():
    async def _run():
        assert current_request_session() is None
        async with async_db_session() as s:
            assert s is not None
        async with async_db_session.begin() as s2:
            assert s2 is not None

    asyncio.run(_run())


def test_ambient_session_is_reused_in_same_task():
    async def _run():
        async with async_db_session() as outer:  # 无 ambient → 真会话
            token = activate_request_session(outer)
            try:
                assert current_request_session() is outer
                async with async_db_session() as inner:
                    assert inner is outer
                async with async_db_session.begin() as inner2:
                    assert inner2 is outer
            finally:
                deactivate_request_session(token)
        assert current_request_session() is None

    asyncio.run(_run())


def test_child_task_does_not_reuse_ambient_session():
    async def _run():
        async with async_db_session() as outer:
            token = activate_request_session(outer)
            seen = {}

            async def _child():
                seen["ambient"] = current_request_session()
                async with async_db_session() as s:
                    seen["child_session"] = s

            try:
                await asyncio.create_task(_child())
            finally:
                deactivate_request_session(token)

            assert seen["ambient"] is None          # 子任务不得看到请求会话
            assert seen["child_session"] is not outer

    asyncio.run(_run())
```

- [ ] **Step 2: 跑测试确认失败**

Run: `uv run pytest tests/test_request_session.py -v`
Expected: FAIL — `ImportError: cannot import name 'activate_request_session'`

- [ ] **Step 3: 在 `backend/app/core/database.py` 实现**

按 spec 第 3.1、3.2 节实现（签名与判定逻辑以 spec 为准）：

1. 模块级 `_request_session: ContextVar[tuple[AsyncSession, asyncio.Task] | None]`。
2. `activate_request_session` / `deactivate_request_session` / `current_request_session`
   （`current_request_session` 用 `asyncio.current_task()` 与 owner 比对，`RuntimeError` 时返回 `None`）。
3. `_SessionFactory`：`__call__()` 与 `begin()` 用 `@asynccontextmanager`；
   ambient 命中则 `yield ambient`（不关闭、不另起事务），否则走内部 `async_sessionmaker`。
4. 把 `async_engine, async_db_session = create_async_engine_and_session(...)`
   改为先接原始工厂、再包装：
   `async_engine, _async_session_factory = create_async_engine_and_session(settings.ASYNC_DB_URI)`
   `async_db_session = _SessionFactory(_async_session_factory)`。
5. 顶部补 `from collections.abc import AsyncIterator`、`from contextlib import asynccontextmanager`。

注意：`db_leak_watchdog`、`async_pool_warmup`、`create_tables` 直接用 `async_engine`，不受影响。

- [ ] **Step 4: 跑测试确认通过**

Run: `uv run pytest tests/test_request_session.py -v`
Expected: PASS（3 passed）

- [ ] **Step 5: 提交**

```bash
git add backend/app/core/database.py backend/tests/test_request_session.py
git commit -m "feat(db): 请求作用域会话包装器（同任务复用、跨任务隔离）"
```

---

### Task 2: 纯 ASGI 会话中间件 + 注册

**Files:**
- Modify: `backend/app/core/middlewares.py`（新增 `DBSessionMiddleware` 类）
- Modify: `backend/app/config/setting.py:591-595`（`MIDDLEWARE_LIST` 末尾追加）
- Test: `backend/tests/test_request_session_middleware.py`（新建）

**Interfaces:**
- Consumes（Task 1）: `async_db_session`、`activate_request_session`、`deactivate_request_session`、`current_request_session`。
- Produces: `app.core.middlewares.DBSessionMiddleware(app: ASGIApp)`；
  `settings.MIDDLEWARE_LIST` 在 `SQL_DB_ENABLE` 时含
  `"app.core.middlewares.DBSessionMiddleware"`，且**位于列表最后一项**（注册后为最内层）。

- [ ] **Step 1: 写失败测试**

创建 `backend/tests/test_request_session_middleware.py`：

```python
"""DBSessionMiddleware：ambient 可见性、透传、提交/回滚、取消时归还。"""
import asyncio

from sqlalchemy import text

from app.core.database import async_db_session, current_request_session
from app.core.middlewares import DBSessionMiddleware


async def _receive():
    return {"type": "http.request", "body": b"", "more_body": False}


async def _send(_message):
    return None


def test_http_request_sees_ambient_then_cleared():
    async def _run():
        seen = {}

        async def inner(scope, receive, send):
            seen["ambient"] = current_request_session()
            await send({"type": "http.response.start", "status": 200, "headers": []})
            await send({"type": "http.response.body", "body": b""})

        mw = DBSessionMiddleware(inner)
        await mw({"type": "http", "method": "GET", "path": "/", "headers": []}, _receive, _send)
        assert seen["ambient"] is not None
        assert current_request_session() is None

    asyncio.run(_run())


def test_non_http_scope_is_passthrough():
    async def _run():
        seen = {}

        async def inner(scope, receive, send):
            seen["ambient"] = current_request_session()

        mw = DBSessionMiddleware(inner)
        await mw({"type": "websocket", "path": "/ws", "headers": []}, _receive, _send)
        assert seen["ambient"] is None

    asyncio.run(_run())


def test_commits_on_success():
    async def _run():
        async def inner(scope, receive, send):
            async with async_db_session.begin() as db:
                await db.execute(text("CREATE TABLE IF NOT EXISTS _mw_probe (v int)"))
                await db.execute(text("DELETE FROM _mw_probe"))
                await db.execute(text("INSERT INTO _mw_probe VALUES (7)"))
            await send({"type": "http.response.start", "status": 200, "headers": []})
            await send({"type": "http.response.body", "body": b""})

        mw = DBSessionMiddleware(inner)
        await mw({"type": "http", "method": "GET", "path": "/", "headers": []}, _receive, _send)
        async with async_db_session() as db:  # 新会话能读到 → 中间件已提交
            rows = (await db.execute(text("SELECT v FROM _mw_probe"))).fetchall()
            assert [r[0] for r in rows] == [7]

    asyncio.run(_run())


def test_rolls_back_on_error():
    async def _run():
        async def inner(scope, receive, send):
            async with async_db_session.begin() as db:
                await db.execute(text("CREATE TABLE IF NOT EXISTS _mw_probe2 (v int)"))
                await db.execute(text("DELETE FROM _mw_probe2"))
                await db.execute(text("INSERT INTO _mw_probe2 VALUES (9)"))
            raise RuntimeError("boom")

        mw = DBSessionMiddleware(inner)
        try:
            await mw({"type": "http", "method": "GET", "path": "/", "headers": []}, _receive, _send)
        except RuntimeError:
            pass
        async with async_db_session() as db:
            rows = (await db.execute(text("SELECT v FROM _mw_probe2"))).fetchall()
            assert rows == []

    asyncio.run(_run())


def test_session_is_released_when_request_is_cancelled():
    async def _run():
        captured = {}

        async def inner(scope, receive, send):
            captured["session"] = current_request_session()
            await asyncio.Event().wait()  # 永不返回，等主任务取消

        mw = DBSessionMiddleware(inner)
        task = asyncio.create_task(
            mw({"type": "http", "method": "GET", "path": "/", "headers": []}, _receive, _send)
        )
        await asyncio.sleep(0.05)
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        session = captured["session"]
        assert session is not None
        assert not session.in_transaction()  # 已归还/收尾，无悬挂事务

    asyncio.run(_run())
```

- [ ] **Step 2: 跑测试确认失败**

Run: `uv run pytest tests/test_request_session_middleware.py -v`
Expected: FAIL — `ImportError: cannot import name 'DBSessionMiddleware'`

- [ ] **Step 3: 实现 `DBSessionMiddleware`**

在 `backend/app/core/middlewares.py` 顶部补
`from app.core.database import async_db_session, activate_request_session, deactivate_request_session`，
并按 spec 第 3.3 节实现 `DBSessionMiddleware`（纯 ASGI 类，非 `BaseHTTPMiddleware`）：
`scope["type"] != "http"` 直接透传；否则在**设置 ambient 之前**用 `async_db_session()`
建真会话 → `activate_request_session` → `await self.app(...)`；
异常时 `rollback` 后重新抛出；正常且 `session.in_transaction()` 时 `commit`；
`finally` 里 `deactivate` + `asyncio.shield(session.close())`（均 `with suppress(Exception)`）。

- [ ] **Step 4: 注册中间件**

`backend/app/config/setting.py` 的 `MIDDLEWARE_LIST` 末尾追加
（保持是列表最后一项）：

```python
"app.core.middlewares.DBSessionMiddleware" if self.SQL_DB_ENABLE else None,
```

- [ ] **Step 5: 跑测试确认通过**

Run: `uv run pytest tests/test_request_session_middleware.py -v`
Expected: PASS（5 passed）

- [ ] **Step 6: 提交**

```bash
git add backend/app/core/middlewares.py backend/app/config/setting.py backend/tests/test_request_session_middleware.py
git commit -m "feat(db): 纯 ASGI 会话中间件，请求内复用连接并保证归还"
```

---

### Task 3: `db_getter` 优先复用请求会话

**Files:**
- Modify: `backend/app/core/dependencies.py:23-53`（`db_getter`）
- Test: `backend/tests/test_request_session.py`（追加用例）

**Interfaces:**
- Consumes（Task 1）: `current_request_session()`、`async_db_session`。
- Produces: `db_getter()` 行为——有 ambient 时 `yield` 同一会话且**不关闭**；无 ambient 时保持原行为（自建 + `begin()` + `shield(close)`）。

- [ ] **Step 1: 写失败测试**

在 `backend/tests/test_request_session.py` 追加：

```python
def test_db_getter_yields_ambient_session_when_present():
    async def _run():
        from sqlalchemy import text

        from app.core.dependencies import db_getter

        async with async_db_session() as outer:
            token = activate_request_session(outer)
            try:
                agen = db_getter()
                got = await agen.__anext__()
                assert got is outer
                try:
                    await agen.__anext__()
                except StopAsyncIteration:
                    pass
                # 生成器收尾后，请求会话必须仍可继续使用（db_getter 不得关闭它）
                assert (await got.execute(text("SELECT 1"))) is not None
            finally:
                deactivate_request_session(token)

    asyncio.run(_run())


def test_db_getter_falls_back_without_ambient():
    async def _run():
        from app.core.dependencies import db_getter

        assert current_request_session() is None
        agen = db_getter()
        got = await agen.__anext__()
        assert got is not None
        try:
            await agen.__anext__()
        except StopAsyncIteration:
            pass

    asyncio.run(_run())
```

- [ ] **Step 2: 跑测试确认失败**

Run: `uv run pytest tests/test_request_session.py -v`
Expected: FAIL —— `got is not outer`（当前 `db_getter` 总会自建新会话）

- [ ] **Step 3: 实现**

按 spec 第 3.5 节改写 `db_getter`：开头取 `current_request_session()`，
命中则 `yield` 后 `return`；否则保留现有 `async with async_db_session()` +
`session.begin()` + `finally: shield(close)` 分支。

- [ ] **Step 4: 跑测试确认通过**

Run: `uv run pytest tests/test_request_session.py -v`
Expected: PASS（5 passed）

- [ ] **Step 5: 提交**

```bash
git add backend/app/core/dependencies.py backend/tests/test_request_session.py
git commit -m "refactor(db): db_getter 优先复用请求会话，取消路径仍兜底归还"
```

---

### Task 4: 全量回归 + 真实连接/并发验证 + 文档更新

**Files:**
- Modify: `AGENTS.md`（AI 模块一节的连接超时说明：补「一请求一连接」与中间件）
- Modify: `docs/connection-pool-leak-diagnosis.md`（第 4 节「还没解决的」标注已修复项）
- Modify: `docs/fix-plan-2026-10-10.md`（勾掉 ①②）

**Interfaces:**
- Consumes: Task 1-3 全部产物。
- Produces: 无新代码；产出验证结论与文档。

- [ ] **Step 1: 全量后端回归**

Run: `cd backend && uv run pytest -q`
Expected: 仅剩既有 3 个 Alembic 失败；其余全绿（对照基线 1939 passed / 35 skipped）。

- [ ] **Step 2: 静态检查**

Run: `cd backend && uv run ruff check`
Expected: 无新增告警。

- [ ] **Step 3: 真实连接数验证（开发栈）**

启动后端后，用 `pg_stat_activity` 在单个请求执行期高频采样：
Expected: 峰值连接 = **1**（此前 `active=2, idle in transaction=1`）。

- [ ] **Step 4: 并发死锁复现验证**

对同一 POST 接口打 30 并发（脚本与上一轮复现方式一致）。
Expected: 全部成功（此前 20 全成功、**30 只成功 1 个并死锁 60s**）。

- [ ] **Step 5: 浏览器巡检 + 泄漏验证**

Run: `cd frontend && npx playwright test e2e/ai-pages-audit.spec.ts --project=chromium --reporter=list`
巡检**含流式（SSE）页面与在 ③ 中新加的弹窗/编辑流程**。随后查：
`SELECT state, count(*) FROM pg_stat_activity WHERE datname='aistation' GROUP BY state;`
Expected: 12 页 0 报错 0 超时；巡检后 `idle in transaction` = **0**，且**不重启后端**仍可用。

- [ ] **Step 6: 更新文档并提交**

```bash
git add AGENTS.md docs/connection-pool-leak-diagnosis.md docs/fix-plan-2026-10-10.md
git commit -m "docs(db): 记录请求作用域会话已落地与验证结论"
```
