import os
import shutil
import sys
import tempfile
import uuid

# 必须在首次 import app 之前设置，以便 Settings / database 引擎使用 SQLite 与内存 Redis
_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, _ROOT)

os.environ.setdefault("ENVIRONMENT", "dev")
os.environ["TESTING"] = "1"

# ---------------------------------------------------------------------------
# 方言矩阵：默认 SQLite（快）；设 TEST_PG_URL 则整套用例跑 **PostgreSQL**。
#
# 为什么要这个：生产是 PG、测试是 SQLite，于是"测试绿、线上炸"和"线上绿、测试炸"
# 两个方向都有盲区。2026-11 一个月内就踩了三次同类问题（影子表 DDL 语法、
# ::interval、::text），每次都是靠碰巧看到一行 warning 才发现的。
#   TEST_PG_URL=postgresql+asyncpg://root:pwd@127.0.0.1:5432/aistation_test
# 库名**必须含 test**：会话开始会 DROP SCHEMA public 重建，防误删生产库。
# ---------------------------------------------------------------------------
_PG_URL = os.environ.get("TEST_PG_URL", "").strip()
if _PG_URL:
    from urllib.parse import unquote, urlparse

    _u = urlparse(_PG_URL)
    _pg_db = (_u.path or "").lstrip("/")
    if not _pg_db or "test" not in _pg_db.lower():
        raise SystemExit(
            f"TEST_PG_URL 的库名必须包含 'test'（会被整库重建），当前：{_pg_db!r}")
    os.environ["DATABASE_TYPE"] = "postgres"
    os.environ["DATABASE_HOST"] = _u.hostname or "127.0.0.1"
    os.environ["DATABASE_PORT"] = str(_u.port or 5432)
    os.environ["DATABASE_USER"] = unquote(_u.username or "postgres")
    os.environ["DATABASE_PASSWORD"] = unquote(_u.password or "")
    os.environ["DATABASE_NAME"] = _pg_db
else:
    os.environ["DATABASE_TYPE"] = "sqlite"

# 测试期关闭 DEBUG 级日志与 SQL/连接池回显。
# 根因：``env/.env.dev`` 里 ``LOGGER_LEVEL=DEBUG``，测试因此把**每一条 SQL**
# 都经 loguru 输出（格式化 + I/O），实测这是测试变慢的主因；
# 这些输出对断言毫无价值，只在排障时临时打开。
os.environ["LOGGER_LEVEL"] = "WARNING"
os.environ["DATABASE_ECHO"] = "0"
os.environ["ECHO_POOL"] = "0"
# 与开发环境一致，测试期关闭验证码：否则依赖 `auth_headers` 登录的用例
# 在缺少 `.env.dev`（未设置 CAPTCHA_ENABLE=false）的机器上会因验证码必填而全部报错。
os.environ["CAPTCHA_ENABLE"] = "false"
# 测试环境允许嵌入了「无模型可用」时的确定性哈希回退：
# 生产默认关闭（失败必须可见），但测试不希望依赖真实嵌入网关。
os.environ.setdefault("RAG_ALLOW_HASH_FALLBACK", "true")
# 每个 pytest 会话使用独立临时 SQLite 库：避免历史行跨运行累积，
# 以及与并发运行的测试进程共用同一文件导致的计数漂移/写锁竞争。
# 路径不含 ".db"，下游按 `{DATABASE_NAME}.db` 拼接（与源码约定一致）。
# ⚠️ PG 矩阵下不能覆盖 DATABASE_NAME（否则会拿临时目录当库名连 PG）。
_TEST_DB_DIR = ""
if not _PG_URL:
    _TEST_DB_DIR = tempfile.mkdtemp(prefix="aistation_pytest_")
    os.environ["DATABASE_NAME"] = os.path.join(
        _TEST_DB_DIR, f"pytest_aistation_{uuid.uuid4().hex[:8]}"
    )

# SQLite 兼容：postgresql.JSONB 在 SQLite 上无法编译 DDL，monkey-patch 使测试可建表
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler

if not hasattr(SQLiteTypeCompiler, "visit_JSONB"):
    SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON

import pytest
from fastapi.testclient import TestClient

#: ``PYTEST_NO_APP=1`` 时不构造应用——跳过 440+ 路由发现与插件扫描，
#: 每次调用省约 22 秒，供**纯逻辑测试**快速迭代；需要应用的用例会被 skip。
#: PG 矩阵下，``asyncio.run`` 会被改道到**应用的事件循环**（见下）。
#: asyncpg 连接与事件循环绑定，TestClient 在另一个循环里驱动应用，
#: 两者混用必然 "Event loop is closed"。
_PORTAL_HOLDER: dict = {"portal": None}

if _PG_URL:
    import asyncio as _asyncio_mod

    _real_asyncio_run = _asyncio_mod.run

    async def _await_coro(coro):
        return await coro

    def _run_on_app_loop(coro, **kwargs):
        portal = _PORTAL_HOLDER.get("portal")
        if portal is None:
            return _real_asyncio_run(coro, **kwargs)
        return portal.call(_await_coro, coro)

    _asyncio_mod.run = _run_on_app_loop


_SKIP_APP = os.environ.get("PYTEST_NO_APP") == "1"

if not _SKIP_APP:
    from main import create_app

# SQLite 兼容：本体 service 层用了 ``updated_time=now()``（Postgres 有，SQLite 没有）。
# 这是**测试环境差异**、不是产品缺陷，因此在连接上注册一个等价函数。
# 必须在任何连接建立之前注册，所以放在模块顶层；测试若发现连接已建，
# 先 dispose 一次连接池即可（见各测试模块的建表 fixture）。
from sqlalchemy import event as _sa_event

from app.core.database import async_engine as _async_engine


@_sa_event.listens_for(_async_engine.sync_engine, "connect")
def _register_sqlite_now(dbapi_conn, _rec):  # pragma: no cover - 运行时钩子
    from datetime import datetime

    try:
        dbapi_conn.create_function(
            "now", 0, lambda: datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    except Exception:  # noqa: BLE001
        pass


# 应用实例与会话级客户端（默认构造；PYTEST_NO_APP=1 时跳过）
app = create_app() if not _SKIP_APP else None
_client = None


#: PG 矩阵下的测试 DDL 兼容层。
#:
#: 存量测试里有 48 处手写 ``id INTEGER PRIMARY KEY AUTOINCREMENT``（历史遗留：
#: 那时只有 SQLite 测试库）。PG 会直接语法错，而"把 48 处改成双方言"属于测试
#: 基础设施迁移，不该和产品改动混在一起。这里在执行前统一翻成 ``BIGSERIAL``。
#: **仅测试期、仅 PG 生效**，产品代码不受影响。
if _PG_URL:
    from sqlalchemy import event as _sa_ev

    from app.core.database import async_engine as _pg_engine

    @_sa_ev.listens_for(_pg_engine.sync_engine, "before_cursor_execute", retval=True)
    def _pg_rewrite_sqlite_ddl(conn, cursor, statement, parameters, context, executemany):
        if "AUTOINCREMENT" in statement:
            statement = statement.replace(
                "INTEGER PRIMARY KEY AUTOINCREMENT", "BIGSERIAL PRIMARY KEY")
        return statement, parameters


@pytest.fixture(scope="session", autouse=True)
def _pg_clean_schema():
    """PG 矩阵专用：会话开始前重建 ``public``（SQLite 下什么都不做）。"""
    if not _PG_URL:
        yield
        return

    import asyncio as _asyncio
    from urllib.parse import quote_plus

    from sqlalchemy import text as _t
    from sqlalchemy.ext.asyncio import create_async_engine as _mk

    from app.config.setting import settings as _st

    async def _reset():
        # **独立引擎**：不能用 app.core.database.async_engine —— 它的 asyncpg 连接
        # 绑在当前事件循环上，而 TestClient 后面会在另一个循环里跑，混用会 CancelledError。
        url = (f"postgresql+asyncpg://{_st.DATABASE_USER}:{quote_plus(_st.DATABASE_PASSWORD)}"
               f"@{_st.DATABASE_HOST}:{_st.DATABASE_PORT}/{_st.DATABASE_NAME}")
        eng = _mk(url, isolation_level="AUTOCOMMIT")
        try:
            async with eng.connect() as conn:
                await conn.execute(_t("DROP SCHEMA IF EXISTS public CASCADE"))
                await conn.execute(_t("CREATE SCHEMA public"))
        finally:
            await eng.dispose()

    _asyncio.run(_reset())
    yield


@pytest.fixture(scope="session", autouse=True)
def _session_database():
    """会话级自动夹具：启动应用生命周期（建表 + 种子数据），并在会话结束后清理临时库。

    由本夹具**自己**启动 ``TestClient``（而不是依赖 ``test_client``），因此
    ``test_client`` 复用它返回同一实例——避免重复驱动同一 ``app`` 的 lifespan
    （那会导致第二次 ``__enter__`` 出现 ``CancelledError``）。
    ``PYTEST_NO_APP=1`` 时不启动应用。
    """
    global _client
    try:
        if _SKIP_APP:
            yield None
        else:
            with TestClient(app) as client:
                _client = client
                _PORTAL_HOLDER["portal"] = getattr(client, "portal", None)
                yield client
    finally:
        _client = None
        shutil.rmtree(_TEST_DB_DIR, ignore_errors=True)


@pytest.fixture(scope="session")
def test_client(_session_database):
    """会话级 HTTP 测试客户端（返回 :func:`_session_database` 已启动的那一个）。

    返回:
    - TestClient: 供用例发起的同步测试客户端。
    """
    if _SKIP_APP or _client is None:
        pytest.skip("PYTEST_NO_APP=1：跳过需要应用的用例")
    return _client


@pytest.fixture
def query_cfg_legacy(monkeypatch):
    """把问数**工程配置读取**打桩为 ``policy_engine=legacy``（纯逻辑用例专用）。

    P1（T7）起 ``_execute_one`` 会读开关（``AiQueryService._cfg()`` → 库）：
    ``PYTEST_NO_APP=1`` 没有应用生命周期（不建表、ORM 映射未配置），读库必炸，
    guard 会按 fail-closed 一律拒 —— 纯逻辑用例就被"基础设施不可用"带红了。

    这里只桩**配置读取**，守卫（星号止血/三态开关/审计编排/legacy_check 调用）仍真跑；
    字段级 ACL、白名单、执行层照旧由各用例自己打桩。
    """
    from app.plugin.module_ai.query.service import AiQueryService

    async def _cfg(cls):  # noqa: ANN001 - 与产品签名一致（classmethod）
        return {"policy_engine": "legacy"}

    monkeypatch.setattr(AiQueryService, "_cfg", classmethod(_cfg))


@pytest.fixture(scope="session")
def db_run(test_client):
    """在**应用的**事件循环里跑协程。

    为什么需要：``asyncpg`` 的连接是**事件循环绑定**的，而 ``TestClient`` 会在
    自己的 anyio 事件循环里驱动应用。测试若用 ``asyncio.run(...)`` 再碰同一个引擎，
    PG 矩阵下会拿到 "Event loop is closed"（SQLite/aiosqlite 不会，所以这个坑
    只在 PG 上暴露）。
    """
    import asyncio as _asyncio

    async def _await(coro):
        return await coro

    portal = getattr(test_client, "portal", None)

    def _run(coro):
        if portal is not None:
            return portal.call(_await, coro)
        return _asyncio.run(coro)

    return _run


@pytest.fixture(scope="session")
def auth_headers(test_client):
    """登录 admin 返回带 Bearer 的请求头，供接口测试复用。"""
    login = test_client.post(
        "/api/v1/system/auth/login",
        data={"username": "admin", "password": "123456"},
        headers={"X-Forwarded-For": "127.0.0.1"},
    )
    assert login.status_code == 200, login.text
    token = login.json()["data"]["access_token"]
    # X-Forwarded-For 需随每个请求携带：OperationLogRoute 记录的 DELETE 等写操作
    # 会校验 request_ip 合法性，缺失时 request.client.host="testclient" 会返回 400。
    return {
        "Authorization": f"Bearer {token}",
        "X-Forwarded-For": "127.0.0.1",
    }
