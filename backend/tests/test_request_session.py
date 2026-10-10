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
