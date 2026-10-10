"""请求作用域会话：同任务复用、跨任务隔离、无上下文新建。"""
import asyncio

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

            assert seen["ambient"] is None  # 子任务不得看到请求会话
            assert seen["child_session"] is not outer

    asyncio.run(_run())


def test_ambient_session_begin_is_nested_when_transaction_active():
    """请求内二次 begin() 不得抛 InvalidRequestError（登录后写操作日志即此场景）。"""
    async def _run():
        from sqlalchemy import text

        async with async_db_session() as s:
            token = activate_request_session(s)
            try:
                await s.execute(text("SELECT 1"))  # 请求会话已有事务
                assert s.in_transaction()
                async with async_db_session() as db:
                    async with db.begin():  # 旧行为：InvalidRequestError
                        await db.execute(text("SELECT 1"))
            finally:
                deactivate_request_session(token)

    asyncio.run(_run())


def test_ambient_begin_commits_at_block_exit():
    """请求内 `async with async_db_session.begin()` 也必须「退出即提交」（及时释放写锁）。

    否则块内写入会一直持有写锁，另一条连接（如操作日志 / 后台任务）会撞上
    SQLite 的 ``database is locked``（实测视频检测回调 + 操作日志即命中）。
    """
    async def _run():
        from sqlalchemy import text

        async with async_db_session() as s:
            token = activate_request_session(s)
            try:
                async with async_db_session.begin() as db:
                    await db.execute(text("CREATE TABLE IF NOT EXISTS _amb_probe (v int)"))
                    await db.execute(text("DELETE FROM _amb_probe"))
                    await db.execute(text("INSERT INTO _amb_probe VALUES (1)"))

                # 另一任务 → 另一条连接：能立即读到，说明块退出已提交
                async def _read():
                    async with async_db_session() as other:
                        rows = (await other.execute(text("SELECT v FROM _amb_probe"))).fetchall()
                        return [r[0] for r in rows]

                assert await asyncio.create_task(_read()) == [1]
            finally:
                deactivate_request_session(token)

    asyncio.run(_run())


def test_fresh_session_bypasses_ambient():
    """async_db_session_fresh() 必须新建会话（供必须独立提交的写入使用）。"""
    async def _run():
        from app.core.database import async_db_session_fresh

        async with async_db_session() as outer:
            token = activate_request_session(outer)
            try:
                async with async_db_session_fresh() as s:
                    assert s is not outer
            finally:
                deactivate_request_session(token)

    asyncio.run(_run())


def test_db_getter_commits_but_does_not_close_ambient_session():
    async def _run():
        from sqlalchemy import text

        from app.core.dependencies import db_getter

        async with async_db_session() as outer:
            token = activate_request_session(outer)
            try:
                await outer.execute(text("SELECT 1"))  # 先开启事务
                assert outer.in_transaction()

                agen = db_getter()
                got = await agen.__anext__()
                assert got is outer
                try:
                    await agen.__anext__()
                except StopAsyncIteration:
                    pass

                # 提交仍发生在依赖收尾（早于路由处理器写操作日志），但**不关闭**会话
                assert outer.in_transaction() is False
                assert (await outer.execute(text("SELECT 1"))) is not None
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
