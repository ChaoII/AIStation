from typing import Any

from sqlalchemy import update as sa_update

from app.api.v1.module_system.auth.schema import AuthSchema
from app.core.database import async_db_session
from app.core.exceptions import CustomException

from .crud import LayoutCRUD
from .model import LayoutModel
from .schema import LayoutCreateSchema, LayoutOutSchema, LayoutUpdateSchema


class LayoutService:

    @classmethod
    async def get_layout_list_service(cls, auth: AuthSchema, search: Any | None = None, order_by: list[dict[str, str]] | None = None) -> list[dict]:
        items = await LayoutCRUD(auth).get_list_crud(
            search=search.__dict__ if search else None,
            order_by=order_by
        )
        return [LayoutOutSchema.model_validate(item).model_dump() for item in items]

    @classmethod
    async def get_layout_detail_service(cls, id: int, auth: AuthSchema) -> dict:
        item = await LayoutCRUD(auth).get_by_id_crud(id=id)
        if not item:
            raise CustomException(msg="布局不存在")
        return LayoutOutSchema.model_validate(item).model_dump()

    @classmethod
    async def create_layout_service(cls, data: LayoutCreateSchema, auth: AuthSchema) -> dict:
        if data.is_default:
            async with async_db_session() as session:
                await session.execute(
                    sa_update(LayoutModel)
                    .where(LayoutModel.is_deleted.is_(False))
                    .values(is_default=False)
                )
                await session.commit()
        item = await LayoutCRUD(auth).create(data=data)
        return LayoutOutSchema.model_validate(item).model_dump()

    @classmethod
    async def update_layout_service(cls, id: int, data: LayoutUpdateSchema, auth: AuthSchema) -> dict:
        item = await LayoutCRUD(auth).get_by_id_crud(id=id)
        if not item:
            raise CustomException(msg="布局不存在")
        # If setting as default, unset all other defaults first
        if hasattr(data, 'is_default') and data.is_default:
            async with async_db_session() as session:
                await session.execute(
                    sa_update(LayoutModel)
                    .where(
                        LayoutModel.id != id,
                        LayoutModel.is_deleted.is_(False),
                    )
                    .values(is_default=False)
                )
                await session.commit()
        updated = await LayoutCRUD(auth).update(id=id, data=data)
        return LayoutOutSchema.model_validate(updated).model_dump()

    @classmethod
    async def delete_layout_service(cls, ids: list[int], auth: AuthSchema) -> None:
        await LayoutCRUD(auth).delete(ids=ids)
