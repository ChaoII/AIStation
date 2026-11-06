"""Task 3：权限审计（SQL 指纹 / 预览打码 / 写入 fail-open / 回溯查询）。

纯逻辑用例（打桩会话，不连库，``PYTEST_NO_APP=1`` 可跑）：

- ``sql_hash``：空白折叠 + 小写后稳定，且是 64 位十六进制；
- ``sql_preview``：单/双引号字面量真的被打码、按 limit 截断；
- ``write_access_log``：**fail-open** —— 会话炸了不抛，只记一条 ``log.warning``；
- ``write_access_log``：落库参数正确（None 主体 → user_id 为空、json 列序列化、
  超长字段截断，避免 PG ``value too long`` 把整条审计丢掉）。

落库用例（需要应用，``PYTEST_NO_APP=1`` 时由 ``test_client`` 自动 skip）：
写入 → ``list_access_logs`` 读回，json 列被解析成 Python list、预览已打码。
"""
from __future__ import annotations

import asyncio


def _audit():
    from app.plugin.module_ai.query.policy import audit

    return audit


# ---------------------------------------------------------------------------
# 纯逻辑：SQL 指纹
# ---------------------------------------------------------------------------
def test_sql_hash_is_stable_and_normalized():
    A = _audit()

    assert A.sql_hash("SELECT 1") == A.sql_hash("  select   1  ")
    assert A.sql_hash("SELECT 1") == A.sql_hash("select\n\t1")
    h = A.sql_hash("select 1")
    assert len(h) == 64 and h == h.lower()
    assert int(h, 16) >= 0, "必须是十六进制串"
    # 语义不同 → 指纹不同（换行/空白不算语义差异，改值才算）
    assert A.sql_hash("select 1") != A.sql_hash("select 2")


# ---------------------------------------------------------------------------
# 纯逻辑：预览打码 + 截断
# ---------------------------------------------------------------------------
def test_preview_truncates_and_masks_literals():
    A = _audit()

    s = A.sql_preview("select * from t where phone='13800138000'")
    assert "13800138000" not in s
    assert "'?'" in s, f"字面量应替换成 '?'：{s}"
    assert len(A.sql_preview("x" * 5000)) <= 2048

    # 双引号字面量同样打码（模型偶尔把值写成 "..."）
    d = A.sql_preview('select * from t where name="张三"')
    assert "张三" not in d

    # SQL 的 '' 转义要整段吃掉，不能只打掉一半
    e = A.sql_preview("select * from t where name='O''Brien' and phone='139'")
    assert "O''Brien" not in e and "139" not in e

    # 自定义 limit；limit<=0 返回空串（不返回半截）
    assert len(A.sql_preview("select 1234567890", limit=10)) == 10
    assert A.sql_preview("select 1", limit=0) == ""
    # 无字面量时原样保留（便于 explain 看清结构）
    assert A.sql_preview("select a from t") == "select a from t"


# ---------------------------------------------------------------------------
# 纯逻辑：写入 fail-open
# ---------------------------------------------------------------------------
class _FakeDB:
    def __init__(self, sink: dict):
        self.sink = sink

    async def execute(self, stmt, params=None):
        self.sink["sql"] = str(stmt)
        self.sink["params"] = params
        return None


class _FakeBegin:
    def __init__(self, db: _FakeDB):
        self.db = db

    async def __aenter__(self):
        return self.db

    async def __aexit__(self, *exc):
        return False


class _FakeSession:
    """只够 ``async with async_db_session.begin() as db: db.execute(...)`` 用。"""

    def __init__(self, sink: dict):
        self.db = _FakeDB(sink)

    def begin(self):
        return _FakeBegin(self.db)


def test_write_failure_does_not_raise(monkeypatch):
    A = _audit()

    class _BoomFactory:
        def begin(self):
            raise RuntimeError("db down")

    monkeypatch.setattr(A, "async_db_session", _BoomFactory())

    warnings: list[str] = []

    class _Log:
        @staticmethod
        def warning(msg, *a):
            warnings.append(str(msg))

    monkeypatch.setattr(A, "log", _Log)

    # 不抛就是本用例的全部要求（查询不能被审计拖垮）
    asyncio.run(
        A.write_access_log(
            principal=None,
            entry="ask",
            datasource="ds:4",
            sql="select 1",
            decision="permit",
            reason="",
            policy_ids=[],
            rewrite=[],
            elapsed_ms=1,
        )
    )
    assert warnings and "审计" in warnings[0], warnings


def test_execute_failure_does_not_raise(monkeypatch):
    """异常发生在 ``execute``（而不是 settle 之前）也必须吞掉。"""
    A = _audit()

    class _BoomDB:
        async def execute(self, stmt, params=None):
            raise RuntimeError("insert 拒绝")

    class _Ctx:
        async def __aenter__(self):
            return _BoomDB()

        async def __aexit__(self, *exc):
            return False

    class _BoomFactory:
        def begin(self):
            return _Ctx()

    monkeypatch.setattr(A, "async_db_session", _BoomFactory())
    warnings: list[str] = []

    class _Log:
        @staticmethod
        def warning(msg, *a):
            warnings.append(str(msg))

    monkeypatch.setattr(A, "log", _Log)

    asyncio.run(
        A.write_access_log(
            principal=None,
            entry="ask",
            datasource="ds:4",
            sql="select 1",
            decision="permit",
            reason="",
            policy_ids=[],
            rewrite=[],
            elapsed_ms=1,
        )
    )
    assert warnings and "审计" in warnings[0], warnings


def test_write_params_are_normalized(monkeypatch):
    """落库参数：None 主体、指纹/预览、json 列、超长字段截断。"""
    A = _audit()
    sink: dict = {}
    monkeypatch.setattr(A, "async_db_session", _FakeSession(sink))

    asyncio.run(
        A.write_access_log(
            principal=None,
            entry="ask",
            datasource="ds:4",
            sql="select * from t where phone='13800138000'",
            decision="deny",
            reason="r" * 400,
            policy_ids=[3, 7],
            rewrite=[{"mask": "LEFT(phone,3)"}],
            elapsed_ms=12,
        )
    )

    p = sink["params"]
    assert "ai_query_access_log" in sink["sql"]
    assert p["uid"] is None, "没有主体时 user_id 必须为空，不能伪造 0/匿名"
    assert p["h"] == A.sql_hash("select * from t where phone='13800138000'")
    assert "13800138000" not in p["prev"]
    assert p["dec"] == "deny"
    assert len(p["reason"]) == 255, "reason 必须截断到列宽，否则 PG 会整条写失败"
    assert p["pids"] == "[3, 7]"
    assert p["rw"] == '[{"mask": "LEFT(phone,3)"}]'
    assert p["ms"] == 12


def test_principal_user_id_is_used(monkeypatch):
    from app.plugin.module_ai.query.policy.principal import Principal

    A = _audit()
    sink: dict = {}
    monkeypatch.setattr(A, "async_db_session", _FakeSession(sink))

    principal = Principal(
        user_id=42, is_superuser=False, roles=("USER",), attrs={}, entry="ask"
    )
    asyncio.run(
        A.write_access_log(
            principal=principal,
            entry="ask",
            datasource="ds:4",
            sql="select 1",
            decision="permit",
            reason="",
            policy_ids=[],
            rewrite=[],
            elapsed_ms=0,
        )
    )
    assert sink["params"]["uid"] == 42


def test_unserializable_rewrite_still_writes(monkeypatch):
    """rewrite 里有环状对象：序列化失败也不能丢掉整条审计。"""
    A = _audit()
    sink: dict = {}
    monkeypatch.setattr(A, "async_db_session", _FakeSession(sink))

    loop: list = []
    loop.append(loop)

    asyncio.run(
        A.write_access_log(
            principal=None,
            entry="ask",
            datasource="ds:4",
            sql="select 1",
            decision="permit",
            reason="",
            policy_ids=[1],
            rewrite=loop,
            elapsed_ms=0,
        )
    )
    assert sink["params"]["rw"] == "[]"
    assert sink["params"]["pids"] == "[1]"


# ---------------------------------------------------------------------------
# 纯逻辑：回溯查询（limit 钳制 + json 列解析）
# ---------------------------------------------------------------------------
class _FakeResult:
    def __init__(self, rows):
        self._rows = rows

    def fetchall(self):
        return self._rows


class _ListSessionFactory:
    """够 ``async with async_db_session() as db: db.execute(...)`` 用。"""

    def __init__(self, sink: dict, rows):
        self.sink = sink
        self.rows = rows

    def __call__(self):
        sink, rows = self.sink, self.rows

        class _Ctx:
            async def __aenter__(self):
                class _DB:
                    async def execute(self, stmt, params=None):
                        sink["sql"] = str(stmt)
                        sink["params"] = params
                        return _FakeResult(rows)

                return _DB()

            async def __aexit__(self, *exc):
                return False

        return _Ctx()


def test_list_clamps_limit_and_parses_json_columns(monkeypatch):
    from datetime import datetime

    A = _audit()
    sink: dict = {}
    rows = [
        (
            9, 42, "ask", "ds:4", "h" * 64, "select * from t where phone='?'",
            "deny", "no policy", "[1, 2]", '[{"mask": "LEFT(phone,3)"}]', 7,
            datetime(2026, 11, 6, 12, 0, 0),
        )
    ]
    factory = _ListSessionFactory(sink, rows)
    monkeypatch.setattr(A, "async_db_session", factory)

    got = asyncio.run(A.list_access_logs(limit=0))
    assert sink["params"]["n"] == 1, "limit<=0 必须钳到 1（不能 LIMIT NULL/负数）"
    assert "ORDER BY id DESC" in sink["sql"], "回溯必须新的在前"
    assert got[0]["policy_ids"] == [1, 2], "jsonb 读回是字符串，必须解析成 list"
    assert got[0]["rewrite"] == [{"mask": "LEFT(phone,3)"}]
    assert got[0]["created_time"] == "2026-11-06 12:00:00"
    assert got[0]["user_id"] == 42 and got[0]["decision"] == "deny"

    assert asyncio.run(A.list_access_logs(limit=99999)) is not None
    assert sink["params"]["n"] == 1000
    # 非法 limit 退回默认 100，而不是把 SQL 弄坏
    asyncio.run(A.list_access_logs(limit="abc"))
    assert sink["params"]["n"] == 100


# ---------------------------------------------------------------------------
# 落库：写入 → 回溯查询
# ---------------------------------------------------------------------------
def test_write_then_list_roundtrip(test_client, db_run):
    from sqlalchemy import text

    from app.core.database import async_db_session
    from app.plugin.module_ai.query.policy.audit import (
        list_access_logs,
        sql_hash,
        write_access_log,
    )
    from app.plugin.module_ai.query.policy.model import ensure_policy_tables

    ds = "t_audit_rt"

    async def _cleanup():
        async with async_db_session.begin() as db:
            await db.execute(
                text("DELETE FROM ai_query_access_log WHERE datasource=:d"), {"d": ds}
            )

    async def _go():
        await ensure_policy_tables()
        await _cleanup()
        try:
            await write_access_log(
                principal=None,
                entry="ask",
                datasource=ds,
                sql="select * from t where phone='13800138000'",
                decision="permit",
                reason="everyone allow",
                policy_ids=[1, 2],
                rewrite=[{"mask": "LEFT(phone,3)"}],
                elapsed_ms=7,
            )
            await write_access_log(
                principal=None,
                entry="cron",
                datasource=ds,
                sql="select count(*) from t",
                decision="deny",
                reason="no policy",
                policy_ids=[],
                rewrite=[],
                elapsed_ms=3,
            )
            rows = [r for r in await list_access_logs(limit=50) if r["datasource"] == ds]
        finally:
            await _cleanup()
        return rows

    rows = db_run(_go())

    assert len(rows) == 2, rows
    assert [r["decision"] for r in rows] == ["deny", "permit"], "新的在前"
    permit = rows[1]
    assert permit["user_id"] is None
    assert permit["sql_hash"] == sql_hash("select * from t where phone='13800138000'")
    assert "13800138000" not in permit["sql_preview"]
    assert permit["policy_ids"] == [1, 2], "json 列必须解析成 list 返回"
    assert permit["rewrite"] == [{"mask": "LEFT(phone,3)"}]
    assert permit["elapsed_ms"] == 7
    assert permit["created_time"], "created_time 不能为空（默认值要走通）"
    assert rows[0]["policy_ids"] == [] and rows[0]["rewrite"] == []
