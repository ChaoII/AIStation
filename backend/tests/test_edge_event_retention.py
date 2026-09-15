"""边缘事件 TTL 清理测试：只删超期行、返回删除数。

- 落库/删除针对真实测试库（SQLite 文件），同步会话造数与读回，
  异步 ``purge_old_events`` 执行删除，避免 mock 掉被测逻辑。
"""
import asyncio
from datetime import datetime, timedelta
from uuid import uuid4

import pytest

from app.core import database


@pytest.fixture(autouse=True)
def _schema(test_client):
    """确保应用生命周期已启动（建表）；删除断言读真实测试库。"""
    return test_client


@pytest.fixture
def db_session():
    """同步会话，与异步删除共用同一 SQLite 测试库。"""
    session = database.db_session()
    try:
        yield session
    finally:
        session.close()


def test_purge_removes_only_expired_events(db_session):
    """造一条超期 + 一条未超期：只删超期行，返回删除数与之匹配。"""
    from app.api.v1.module_video.edge.model import EdgeEventModel
    from app.api.v1.module_video.edge.retention import purge_old_events
    from app.api.v1.module_video.edge.store import get_event_by_event_id

    # 先清理历史遗留的过期行，使本次断言计数确定
    asyncio.run(purge_old_events(30))

    now = datetime.now()
    old_id = f"ev-old-{uuid4().hex}"
    fresh_id = f"ev-fresh-{uuid4().hex}"
    db_session.add_all(
        [
            EdgeEventModel(
                event_id=old_id, created_time=now - timedelta(days=45), matched=False
            ),
            EdgeEventModel(
                event_id=fresh_id, created_time=now - timedelta(days=1), matched=False
            ),
        ]
    )
    db_session.commit()

    deleted = asyncio.run(purge_old_events(30))

    db_session.expire_all()
    # 返回数恰为被删除的超期行数，且只有旧行消失
    assert deleted == 1
    assert get_event_by_event_id(db_session, old_id) is None
    assert get_event_by_event_id(db_session, fresh_id) is not None
