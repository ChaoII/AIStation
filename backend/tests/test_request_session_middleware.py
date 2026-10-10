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
        # 先独立建表并提交，使被测请求只负责插入（否则建表也会被一起回滚，
        # SQLite 下后续查询会因表不存在而报错，测不出回滚语义）。
        async with async_db_session.begin() as db:
            await db.execute(text("CREATE TABLE IF NOT EXISTS _mw_probe2 (v int)"))
            await db.execute(text("DELETE FROM _mw_probe2"))

        async def inner(scope, receive, send):
            # 直接用请求会话写入（不经 begin() 块 → 不自行提交），
            # 由中间件在异常时回滚，才能检验中间件的回滚语义。
            async with async_db_session() as db:
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
        assert not session.in_transaction()  # 已收尾，无悬挂事务

    asyncio.run(_run())
