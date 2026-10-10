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
os.environ["DATABASE_TYPE"] = "sqlite"

# 测试期关闭 DEBUG 级日志与 SQL/连接池回显。
# 根因：``env/.env.dev`` 里 ``LOGGER_LEVEL=DEBUG``，测试因此把**每一条 SQL**
# 都经 loguru 输出（格式化 + I/O），实测这是测试变慢的主因；
# 这些输出对断言毫无价值，只在排障时临时打开。
os.environ["LOGGER_LEVEL"] = "WARNING"
os.environ["DATABASE_ECHO"] = "0"
os.environ["ECHO_POOL"] = "0"
# 每个 pytest 会话使用独立临时 SQLite 库：避免历史行跨运行累积，
# 以及与并发运行的测试进程共用同一文件导致的计数漂移/写锁竞争。
# 路径不含 ".db"，下游按 `{DATABASE_NAME}.db` 拼接（与源码约定一致）。
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

# 创建测试客户端（依赖上述环境变量）
app = create_app()


@pytest.fixture(scope="session", autouse=True)
def _session_database(test_client):
    """
    会话级自动夹具：确保任何用例执行前应用生命周期已启动（建表 + 种子数据），
    使结果的正确性不依赖「之前的测试恰好先用了 test_client」这一顺序假设；
    会话结束后清理本次运行的临时库目录。
    """
    try:
        yield test_client
    finally:
        shutil.rmtree(_TEST_DB_DIR, ignore_errors=True)


@pytest.fixture(scope="session")
def test_client():
    """
    会话级 HTTP 测试客户端（与 ``conftest`` 中单例 ``app`` 对齐，只启动一次生命周期）。

    若使用 ``module`` 作用域，多个测试文件各开一个 ``TestClient`` 会重复驱动同一
    ``app`` 的 lifespan，易导致第二次 ``__enter__`` 时出现 ``CancelledError``。

    返回:
    - TestClient: 供用例发起的同步测试客户端（yield 注入）。
    """
    with TestClient(app) as client:
        yield client


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
