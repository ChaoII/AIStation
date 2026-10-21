"""会话归属校验回归（越权读/删/写他人问数历史）。

修复前 `list_messages` / `delete_session` 只按 id 查：任何拿到
`module_ai:query:ask` 的用户枚举 id 就能读到、删掉**别人的**会话历史。

后续（P1-3）补齐了**写入面**的同类缺口：

- `list_sessions` 不按用户过滤 → 能看到所有人的会话标题，点进去却报「会话不存在」；
- `get_or_create_session` 命中已有会话时不校验归属 → `ask`/`ask_stream`
  能把消息写进他人会话；
- `feedback` / `promote_message_to_metric` 只按 `message_id` 取行 →
  能改他人反馈、把他人消息沉淀成自己的指标。
"""

import asyncio
from types import SimpleNamespace

import pytest

from app.core.exceptions import CustomException
from app.plugin.module_ai.query.model import (
    AiQueryMessageModel,
    AiQuerySessionModel,
)
from app.plugin.module_ai.query.service import AiQueryService as S


def _auth(uid: int | None):
    if uid is None:
        return None
    return SimpleNamespace(user=SimpleNamespace(id=uid))


def test_owner_can_access() -> None:
    S._ensure_session_owner(SimpleNamespace(user_id=7), _auth(7))  # 不应抛


def test_other_user_is_denied_and_existence_hidden() -> None:
    """拒绝时必须用「不存在」文案，避免泄露 id 是否存在。"""
    with pytest.raises(CustomException) as exc:
        S._ensure_session_owner(SimpleNamespace(user_id=7), _auth(8))
    assert "不存在" in str(exc.value)
    assert "权限" not in str(exc.value)


def test_legacy_session_without_owner_stays_accessible() -> None:
    S._ensure_session_owner(SimpleNamespace(user_id=None), _auth(9))  # 遗留数据不回归


def test_missing_session_is_denied() -> None:
    with pytest.raises(CustomException):
        S._ensure_session_owner(None, _auth(1))


def test_internal_call_without_auth_skips_check() -> None:
    """内部调用（如问句重写读历史）没有 HTTP 用户上下文，放行。"""
    S._ensure_session_owner(SimpleNamespace(user_id=7), None)


# ---------------------------------------------------------------------------
# 以下用例需要真实数据库（应用启动时建表 + 播种），PYTEST_NO_APP=1 时自动跳过
# ---------------------------------------------------------------------------
def _mk_session(user_id: int | None, title: str) -> int:
    async def _go() -> int:
        from app.core.database import async_db_session

        async with async_db_session.begin() as db:
            s = AiQuerySessionModel(
                user_id=user_id, tenant_id=None, title=title, datasource="system")
            db.add(s)
            await db.flush()
            return int(s.id)

    return asyncio.run(_go())


def _mk_message(session_id: int, question: str = "他人问句", sql: str = "") -> int:
    async def _go() -> int:
        from app.core.database import async_db_session

        async with async_db_session.begin() as db:
            m = AiQueryMessageModel(
                session_id=session_id, question=question, path="fast",
                datasource="system", sql=sql)
            db.add(m)
            await db.flush()
            return int(m.id)

    return asyncio.run(_go())


def _read_message(message_id: int):
    async def _go():
        from app.core.database import async_db_session

        async with async_db_session() as db:
            return await db.get(AiQueryMessageModel, message_id)

    return asyncio.run(_go())


def test_list_sessions_returns_only_mine_and_legacy(test_client) -> None:
    """列表必须与详情同口径：本人 + 历史遗留（user_id IS NULL）。"""
    _mk_session(7, "会话-本人可见")
    _mk_session(8, "会话-他人不可见")
    _mk_session(None, "会话-历史遗留")

    rows = asyncio.run(S.list_sessions(_auth(7)))
    titles = {r["title"] for r in rows}

    assert "会话-本人可见" in titles
    assert "会话-历史遗留" in titles, "无归属的历史数据不能因本次修复而不可见"
    assert "会话-他人不可见" not in titles, "不得泄露他人会话标题"


def test_get_or_create_session_rejects_foreign_session(test_client) -> None:
    """传他人 session_id 时必须拒绝，否则 ask 能往别人会话里写消息。"""
    foreign = _mk_session(8, "会话-他人写入")

    with pytest.raises(CustomException) as exc:
        asyncio.run(S.get_or_create_session(foreign, "偷偷写", _auth(7)))

    assert "不存在" in str(exc.value)


def test_get_or_create_session_reuses_own_session(test_client) -> None:
    """归属本人时照旧复用（修复不能把合法写入也挡掉）。"""
    mine = _mk_session(7, "会话-本人复用")

    r = asyncio.run(S.get_or_create_session(mine, "改标题", _auth(7)))

    assert r["id"] == mine and r["title"] == "会话-本人复用"


def test_feedback_rejects_foreign_message(test_client) -> None:
    """按 message_id 改反馈前必须先确认会话归属。"""
    foreign = _mk_session(8, "会话-他人反馈")
    mid = _mk_message(foreign)

    with pytest.raises(CustomException) as exc:
        asyncio.run(S.feedback(mid, "up", None, _auth(7)))

    assert "不存在" in str(exc.value)
    assert not (_read_message(mid).feedback or ""), "越权请求不得留下任何写入"


def test_promote_rejects_foreign_message(test_client) -> None:
    """沉淀指标同样要先确认消息归属，否则能把他人问答变成自己的指标。"""
    foreign = _mk_session(8, "会话-他人指标")
    mid = _mk_message(foreign, question="上月告警数", sql="SELECT 1")

    with pytest.raises(CustomException) as exc:
        asyncio.run(S.promote_message_to_metric(
            mid, "他人指标", "foreign_metric_p1", _auth(7)))

    assert "会话不存在" in str(exc.value)
