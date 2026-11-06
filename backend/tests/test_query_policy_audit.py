"""Task 3：权限审计（SQL 指纹 / 预览打码 / 写入 fail-open / 回溯查询）。

纯逻辑用例（打桩会话，不连库，``PYTEST_NO_APP=1`` 可跑）：

- ``sql_hash``：空白折叠 + 小写后稳定，且是 64 位十六进制；
- ``sql_preview`` / ``reason``：单/双引号字面量真的被打码、按 limit/列宽截断
  （**先打码后截断**，跨边界的字面量不会泄露后半截）；
- ``write_access_log``：**fail-open** —— 会话/事务/执行/日志任一环节炸了都不抛，
  只 ``log.warning``（带 traceback）；
- ``write_access_log``：落库参数正确（None 主体 → user_id 为空、json 列序列化、
  超长字段截断，避免 PG ``value too long`` 把整条审计丢掉）。

落库用例（需要应用，``PYTEST_NO_APP=1`` 时由 ``test_client`` 自动 skip）：

- 写入 → ``list_access_logs`` 读回，json 列被解析成 list、预览与 reason 均已打码；
- **请求会话已有事务**时（``activate_request_session`` 模拟中间件），审计仍然
  真的写进库 —— 不是「异常被吞掉」就算过。
"""
from __future__ import annotations

import asyncio


def _audit():
    from app.plugin.module_ai.query.policy import audit

    return audit


def _do_write(A, **over):
    """带默认参数的写审计调用（各用例只覆盖关心的字段）。"""
    kw = {
        "principal": None,
        "entry": "ask",
        "datasource": "ds:4",
        "sql": "select 1",
        "decision": "permit",
        "reason": "",
        "policy_ids": [],
        "rewrite": [],
        "elapsed_ms": 1,
    }
    kw.update(over)
    asyncio.run(A.write_access_log(**kw))


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
# 纯逻辑：写入 fail-open（打桩独立会话）
# ---------------------------------------------------------------------------
class _FakeDB:
    def __init__(self, sink: dict):
        self.sink = sink

    async def execute(self, stmt, params=None):
        self.sink["sql"] = str(stmt)
        self.sink["params"] = params
        return None


class _FakeTx:
    def __init__(self, db: _FakeDB):
        self.db = db

    async def __aenter__(self):
        return self.db

    async def __aexit__(self, *exc):
        return False


class _FakeSession:
    """够 ``async with <session>() as s: async with s.begin(): s.execute(...)`` 用。"""

    def __init__(self, sink: dict):
        self.db = _FakeDB(sink)

    async def __aenter__(self):
        # 与真实 AsyncSession 一致：进去拿到的是**会话**（.begin() 在会话上）
        return self

    async def __aexit__(self, *exc):
        return False

    def begin(self):
        return _FakeTx(self.db)

    async def execute(self, stmt, params=None):
        return await self.db.execute(stmt, params)


def _fresh(sink: dict):
    """打桩「独立会话」工厂（实现里就是 ``async_db_session_fresh()``）。"""
    return lambda: _FakeSession(sink)


class _CaptureLog:
    """记录告警与 ``opt`` 参数（用来断言真的带了 traceback）。"""

    def __init__(self):
        self.records: list[str] = []
        self.opts: list[dict] = []
        self.fail = False

    def warning(self, msg, *a, **kw):
        if self.fail:
            raise RuntimeError("log 写不出去")
        self.records.append(str(msg))

    def opt(self, **kw):
        self.opts.append(kw)
        return self


def _capture(monkeypatch, A) -> _CaptureLog:
    cap = _CaptureLog()
    monkeypatch.setattr(A, "log", cap)
    return cap


def test_write_failure_does_not_raise(monkeypatch):
    """连会话都拿不到（池耗尽/建连失败）：不抛，只 warning。"""
    A = _audit()

    class _BoomFactory:
        def __call__(self):
            raise RuntimeError("db down")

    monkeypatch.setattr(A, "async_db_session_fresh", _BoomFactory())
    cap = _capture(monkeypatch, A)

    _do_write(A)
    assert cap.records and "审计" in cap.records[0], cap.records


def test_transaction_failure_does_not_raise(monkeypatch):
    """会话拿到了，但开事务失败（``begin()`` 抛）：同样不抛。"""
    A = _audit()

    class _BoomTx:
        async def __aenter__(self):
            raise RuntimeError("cannot begin")

        async def __aexit__(self, *exc):
            return False

    class _BoomSession(_FakeSession):
        def begin(self):
            return _BoomTx()

    monkeypatch.setattr(A, "async_db_session_fresh", lambda: _BoomSession({}))
    cap = _capture(monkeypatch, A)

    _do_write(A)
    assert cap.records and "审计" in cap.records[0], cap.records


def test_execute_failure_does_not_raise(monkeypatch):
    """异常发生在 ``execute``（事务已开）也必须吞掉。"""
    A = _audit()

    class _BoomDB(_FakeDB):
        async def execute(self, stmt, params=None):
            raise RuntimeError("insert 拒绝")

    class _BoomSession(_FakeSession):
        def __init__(self):
            super().__init__({})
            self.db = _BoomDB({})

    monkeypatch.setattr(A, "async_db_session_fresh", lambda: _BoomSession())
    cap = _capture(monkeypatch, A)

    _do_write(A)
    assert cap.records and "审计" in cap.records[0], cap.records


def test_warning_keeps_traceback(monkeypatch):
    """告警走 ``log.opt(exception=True)``（loguru 才真的带 traceback）。"""
    A = _audit()

    class _BoomFactory:
        def __call__(self):
            raise RuntimeError("db down")

    monkeypatch.setattr(A, "async_db_session_fresh", _BoomFactory())
    cap = _capture(monkeypatch, A)

    _do_write(A)
    assert {"exception": True} in cap.opts, cap.opts


def test_broken_logger_does_not_raise(monkeypatch):
    """日志设施自己坏掉时也不能把异常抛给查询主链路（fail-open 收尾）。"""
    A = _audit()

    class _BoomFactory:
        def __call__(self):
            raise RuntimeError("db down")

    monkeypatch.setattr(A, "async_db_session_fresh", _BoomFactory())
    cap = _capture(monkeypatch, A)
    cap.fail = True

    _do_write(A)  # 不抛即通过


# ---------------------------------------------------------------------------
# 纯逻辑：落库参数（None 主体 / 打码 / 截断 / json 列）
# ---------------------------------------------------------------------------
def test_write_params_are_normalized(monkeypatch):
    """落库参数：None 主体、指纹/预览、json 列、超长字段截断。"""
    A = _audit()
    sink: dict = {}
    monkeypatch.setattr(A, "async_db_session_fresh", _fresh(sink))
    cap = _capture(monkeypatch, A)

    _do_write(
        A,
        sql="select * from t where phone='13800138000'",
        decision="deny",
        reason="r" * 400,
        policy_ids=[3, 7],
        rewrite=[{"mask": "LEFT(phone,3)"}],
        elapsed_ms=12,
    )

    p = sink["params"]
    assert not cap.records, f"正常写入不该有告警：{cap.records}"
    assert "ai_query_access_log" in sink["sql"]
    assert p["uid"] is None, "没有主体时 user_id 必须为空，不能伪造 0/匿名"
    assert p["h"] == A.sql_hash("select * from t where phone='13800138000'")
    assert "13800138000" not in p["prev"]
    assert p["dec"] == "deny"
    assert len(p["reason"]) == 255, "reason 必须截断到列宽，否则 PG 会整条写失败"
    assert p["pids"] == "[3, 7]"
    assert p["rw"] == '[{"mask": "LEFT(phone,3)"}]'
    assert p["ms"] == 12


def test_reason_is_masked_like_preview(monkeypatch):
    """``reason`` 里的原始 SQL / 异常文本同样要打码（PII 不能明文进审计表）。"""
    A = _audit()
    sink: dict = {}
    monkeypatch.setattr(A, "async_db_session_fresh", _fresh(sink))

    _do_write(
        A,
        decision="deny",
        reason=(
            "命中 deny 策略：select * from t where phone='13800138000' "
            'and name="张三"（列 phone 不可见）'
        ),
    )

    reason = sink["params"]["reason"]
    assert "13800138000" not in reason, reason
    assert "张三" not in reason, reason
    assert "'?'" in reason and "命中 deny 策略" in reason, "打码后仍要保留可读的原因"


def test_reason_masked_before_truncation(monkeypatch):
    """先打码后截断：跨在 255 边界的字面量不会留下半截明文。"""
    A = _audit()
    sink: dict = {}
    monkeypatch.setattr(A, "async_db_session_fresh", _fresh(sink))

    # 前缀刚好把字面量推到列宽之外
    _do_write(A, reason="x" * 250 + " phone='13800138000'")

    reason = sink["params"]["reason"]
    assert len(reason) == 255
    assert "13800138000" not in reason, reason


def test_principal_user_id_is_used(monkeypatch):
    from app.plugin.module_ai.query.policy.principal import Principal

    A = _audit()
    sink: dict = {}
    monkeypatch.setattr(A, "async_db_session_fresh", _fresh(sink))

    principal = Principal(
        user_id=42, is_superuser=False, roles=("USER",), attrs={}, entry="ask"
    )
    _do_write(A, principal=principal, elapsed_ms=0)
    assert sink["params"]["uid"] == 42


def test_unserializable_rewrite_still_writes(monkeypatch):
    """rewrite 里有环状对象：序列化失败也不能丢掉整条审计。"""
    A = _audit()
    sink: dict = {}
    monkeypatch.setattr(A, "async_db_session_fresh", _fresh(sink))

    loop: list = []
    loop.append(loop)

    _do_write(A, policy_ids=[1], rewrite=loop, elapsed_ms=0)
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
                reason="everyone allow（原始：phone='13800138000'）",
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
    assert "13800138000" not in permit["reason"], "reason 的打码必须落库（不只是内存里）"
    assert permit["policy_ids"] == [1, 2], "json 列必须解析成 list 返回"
    assert permit["rewrite"] == [{"mask": "LEFT(phone,3)"}]
    assert permit["elapsed_ms"] == 7
    assert permit["created_time"], "created_time 不能为空（默认值要走通）"
    assert rows[0]["policy_ids"] == [] and rows[0]["rewrite"] == []


# ---------------------------------------------------------------------------
# 落库：请求会话已有事务时，审计仍然真的写进去
# ---------------------------------------------------------------------------
def test_write_succeeds_when_request_session_already_in_transaction(
    test_client, db_run
):
    """复现「问数主链路在请求作用域里」的场景。

    ``DBSessionMiddleware`` 会把一条会话登记进 ContextVar（``activate_request_session``），
    该会话通常**已经 autobegin**（鉴权/权限查询已经跑过 SELECT）。这里用真会话复现，然后：

    - 断言不抛（fail-open 的最低要求）；
    - **断言行真的写进了库**（从独立会话读回）—— 只测「异常被吞」不算通过。
    """
    from sqlalchemy import text

    from app.core.database import (
        activate_request_session,
        async_db_session,
        async_db_session_fresh,
        deactivate_request_session,
    )
    from app.plugin.module_ai.query.policy.audit import write_access_log
    from app.plugin.module_ai.query.policy.model import ensure_policy_tables

    ds = "t_audit_reqscope"

    async def _cleanup():
        async with async_db_session_fresh() as s:
            async with s.begin():
                await s.execute(
                    text("DELETE FROM ai_query_access_log WHERE datasource=:d"), {"d": ds}
                )

    async def _count() -> int:
        async with async_db_session_fresh() as s:
            n = (
                await s.execute(
                    text("SELECT count(*) FROM ai_query_access_log WHERE datasource=:d"),
                    {"d": ds},
                )
            ).scalar()
        return int(n or 0)

    async def _go():
        await ensure_policy_tables()
        await _cleanup()
        try:
            async with async_db_session() as outer:
                # 让请求会话进入事务（中间件/鉴权链路真实的起点）
                await outer.execute(text("SELECT 1"))
                assert outer.in_transaction(), "前置条件：请求会话必须已有事务"
                token = activate_request_session(outer)
                try:
                    await write_access_log(
                        principal=None,
                        entry="ask",
                        datasource=ds,
                        sql="select * from t where phone='13800138000'",
                        decision="permit",
                        reason="",
                        policy_ids=[],
                        rewrite=[],
                        elapsed_ms=1,
                    )
                finally:
                    deactivate_request_session(token)
                # 审计必须独立提交：请求会话这边的后续状态不影响它
                assert outer.in_transaction(), "审计写入不能把请求事务提前结束"
            return await _count()
        finally:
            await _cleanup()

    assert db_run(_go()) == 1, "请求会话已有事务时，审计必须真的落库（不能被吞成 warning）"
