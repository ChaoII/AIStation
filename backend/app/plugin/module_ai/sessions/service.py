"""AI 会话服务：会话与消息的读写。"""
from __future__ import annotations

from sqlalchemy import select

from app.core.database import async_db_session

from .model import AiMessageModel, AiSessionModel


def _session_dict(s: AiSessionModel) -> dict:
    return {
        "id": s.id,
        "app_id": s.app_id,
        "user_id": s.user_id,
        "title": s.title or "",
        "message_count": s.message_count or 0,
        "created_time": s.created_time,
        "updated_time": s.updated_time,
    }


def _message_dict(m: AiMessageModel) -> dict:
    return {
        "id": m.id,
        "session_id": m.session_id,
        "app_id": m.app_id,
        "role": m.role,
        "parts": m.parts or [],
        "created_time": m.created_time,
    }


async def persist_session_exchange(
    session_id: int | None,
    user_text: str,
    assistant_text: str,
    app_id: int | None = None,
    user_id: int | None = None,
) -> None:
    """流式结束时落会话；无 session_id、归属不符或失败仅告警，绝不中断 SSE。"""
    if not session_id:
        return
    try:
        await AiSessionService.record_exchange(
            session_id, user_text, assistant_text, app_id, user_id
        )
    except Exception as e:  # noqa: BLE001
        from app.core.logger import logger

        logger.warning(f"写入 AI 会话消息失败: {e}")


class AiSessionService:

    @classmethod
    async def list_sessions(cls, user_id: int | None = None) -> list[dict]:
        async with async_db_session() as db:
            stmt = select(AiSessionModel).where(AiSessionModel.is_deleted.is_(False))
            if user_id is not None:
                stmt = stmt.where(AiSessionModel.user_id == user_id)
            rows = (
                await db.execute(stmt.order_by(AiSessionModel.id.desc()))
            ).scalars().all()
            return [_session_dict(s) for s in rows]

    @classmethod
    async def get_session(cls, session_id: int) -> dict | None:
        async with async_db_session() as db:
            s = await db.get(AiSessionModel, session_id)
            if not s or s.is_deleted:
                return None
            return _session_dict(s)

    @classmethod
    async def get_messages(cls, session_id: int) -> list[dict]:
        async with async_db_session() as db:
            rows = (
                await db.execute(
                    select(AiMessageModel)
                    .where(
                        AiMessageModel.session_id == session_id,
                        AiMessageModel.is_deleted.is_(False),
                    )
                    .order_by(AiMessageModel.id.asc())
                )
            ).scalars().all()
            return [_message_dict(m) for m in rows]

    @classmethod
    async def create(
        cls, title: str = "", app_id: int | None = None, user_id: int | None = None
    ) -> dict:
        async with async_db_session.begin() as db:
            s = AiSessionModel(
                title=(title or "")[:255],
                app_id=app_id,
                user_id=user_id,
                message_count=0,
            )
            db.add(s)
            await db.flush()
            return _session_dict(s)

    @classmethod
    async def append_message(
        cls,
        session_id: int,
        role: str,
        parts: list[dict] | None,
        app_id: int | None = None,
    ) -> dict | None:
        async with async_db_session.begin() as db:
            s = await db.get(AiSessionModel, session_id)
            if not s or s.is_deleted:
                return None
            m = AiMessageModel(
                session_id=session_id,
                app_id=app_id if app_id is not None else s.app_id,
                role=role,
                parts=parts or [],
            )
            db.add(m)
            s.message_count = (s.message_count or 0) + 1
            await db.flush()
            return _message_dict(m)

    @classmethod
    async def record_exchange(
        cls,
        session_id: int,
        user_text: str,
        assistant_text: str,
        app_id: int | None = None,
        user_id: int | None = None,
    ) -> None:
        """落一次问答：追加 user/assistant 文本消息并累加 message_count。

        归属校验（deny-by-default）：目标会话必须归属调用方；归属缺失（历史数据）
        或归属不符时静默拒绝并记日志，避免越权写入他人会话。
        """
        if not user_text and not assistant_text:
            return
        async with async_db_session.begin() as db:
            s = await db.get(AiSessionModel, session_id)
            if not s or s.is_deleted:
                return
            if s.user_id is None or s.user_id != user_id:
                from app.core.logger import logger

                logger.warning(
                    f"拒绝写入非本人 AI 会话: session_id={session_id} "
                    f"owner={s.user_id} caller={user_id}"
                )
                return
            target_app_id = app_id if app_id is not None else s.app_id
            added = 0
            if user_text:
                db.add(
                    AiMessageModel(
                        session_id=session_id,
                        app_id=target_app_id,
                        role="user",
                        parts=[{"type": "text", "text": user_text}],
                    )
                )
                added += 1
            if assistant_text:
                db.add(
                    AiMessageModel(
                        session_id=session_id,
                        app_id=target_app_id,
                        role="assistant",
                        parts=[{"type": "text", "text": assistant_text}],
                    )
                )
                added += 1
            s.message_count = (s.message_count or 0) + added
            if added and not (s.title or "").strip():
                s.title = (user_text or assistant_text or "")[:255]
            await db.flush()

    @classmethod
    async def delete(cls, ids: list[int]) -> None:
        """物理删除会话及其消息（避免遗留孤儿消息）。"""
        async with async_db_session.begin() as db:
            for session_id in ids:
                s = await db.get(AiSessionModel, session_id)
                if not s:
                    continue
                msgs = (
                    await db.execute(
                        select(AiMessageModel).where(
                            AiMessageModel.session_id == session_id
                        )
                    )
                ).scalars().all()
                for m in msgs:
                    await db.delete(m)
                await db.delete(s)
