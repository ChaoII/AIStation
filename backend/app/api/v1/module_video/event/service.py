from typing import Any

from app.api.v1.module_system.auth.schema import AuthSchema
from app.core.exceptions import CustomException

from .crud import EventCRUD
from .schema import EventCreateSchema, EventOutSchema, EventUpdateSchema


class EventService:

    @classmethod
    async def get_event_list_service(cls, auth: AuthSchema, search: Any | None = None, order_by: list[dict[str, str]] | None = None) -> list[dict]:
        items = await EventCRUD(auth).get_list_crud(
            search=search.__dict__ if search else None,
            order_by=order_by
        )
        return [EventOutSchema.model_validate(item).model_dump() for item in items]

    @classmethod
    async def create_event_service(cls, data: EventCreateSchema, auth: AuthSchema) -> dict:
        item = await EventCRUD(auth).create(data=data)
        return EventOutSchema.model_validate(item).model_dump()

    @classmethod
    async def update_event_service(cls, id: int, data: EventUpdateSchema, auth: AuthSchema) -> dict:
        item = await EventCRUD(auth).get_by_id_crud(id=id)
        if not item:
            raise CustomException(msg="事件联动不存在")
        updated = await EventCRUD(auth).update(id=id, data=data)
        return EventOutSchema.model_validate(updated).model_dump()

    @classmethod
    async def delete_event_service(cls, ids: list[int], auth: AuthSchema) -> None:
        await EventCRUD(auth).delete(ids=ids)
