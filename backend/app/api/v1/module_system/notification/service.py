
from sqlalchemy import desc, func, select, update

from app.core.database import async_db_session

from .model import UserNotificationModel
from .ws import push_notification_ws


class NotificationService:

    @classmethod
    async def create_notification(
        cls, user_id: int, title: str, content: str | None = None,
        type: str = "system", module: str = "system", module_id: int | None = None,
    ) -> dict:
        async with async_db_session.begin() as db:
            n = UserNotificationModel(
                user_id=user_id, title=title, content=content,
                type=type, module=module, module_id=module_id,
            )
            db.add(n)
            await db.flush()
            result = {
                "id": n.id,
                "user_id": n.user_id,
                "title": n.title,
                "content": n.content,
                "type": n.type,
                "module": n.module,
                "module_id": n.module_id,
                "is_read": False,
                "created_time": n.created_time.isoformat() if n.created_time else None,
            }
        await push_notification_ws(user_id, result)
        return result

    @classmethod
    async def list_notifications(
        cls, user_id: int, page_no: int = 1, page_size: int = 20
    ) -> dict:
        async with async_db_session() as db:
            total = await db.scalar(
                select(func.count(UserNotificationModel.id))
                .where(UserNotificationModel.user_id == user_id)
            ) or 0
            offset = (page_no - 1) * page_size
            result = await db.execute(
                select(UserNotificationModel)
                .where(UserNotificationModel.user_id == user_id)
                .order_by(desc(UserNotificationModel.created_time))
                .offset(offset)
                .limit(page_size)
            )
            items = [
                {
                    "id": n.id,
                    "title": n.title,
                    "content": n.content,
                    "type": n.type,
                    "module": n.module,
                    "module_id": n.module_id,
                    "is_read": n.is_read,
                    "created_time": n.created_time.isoformat() if n.created_time else None,
                }
                for n in result.scalars().all()
            ]
            return {
                "page_no": page_no,
                "page_size": page_size,
                "total": total,
                "has_next": offset + page_size < total,
                "items": items,
            }

    @classmethod
    async def mark_read(cls, notification_id: int, user_id: int) -> bool:
        async with async_db_session.begin() as db:
            result = await db.execute(
                update(UserNotificationModel)
                .where(
                    UserNotificationModel.id == notification_id,
                    UserNotificationModel.user_id == user_id,
                )
                .values(is_read=True)
            )
            return result.rowcount > 0

    @classmethod
    async def mark_all_read(cls, user_id: int) -> int:
        async with async_db_session.begin() as db:
            result = await db.execute(
                update(UserNotificationModel)
                .where(
                    UserNotificationModel.user_id == user_id,
                    ~UserNotificationModel.is_read,
                )
                .values(is_read=True)
            )
            return result.rowcount

    @classmethod
    async def unread_count(cls, user_id: int) -> int:
        async with async_db_session() as db:
            return await db.scalar(
                select(func.count(UserNotificationModel.id))
                .where(
                    UserNotificationModel.user_id == user_id,
                    ~UserNotificationModel.is_read,
                )
            ) or 0
