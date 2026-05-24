from collections.abc import Sequence

from app.api.v1.module_system.auth.schema import AuthSchema
from app.core.base_crud import CRUDBase

from .model import CameraGroupModel, CameraModel
from .schema import (
    CameraCreateSchema,
    CameraGroupCreateSchema,
    CameraGroupUpdateSchema,
    CameraUpdateSchema,
)


class CameraCRUD(CRUDBase[CameraModel, CameraCreateSchema, CameraUpdateSchema]):
    def __init__(self, auth: AuthSchema) -> None:
        self.auth = auth
        super().__init__(model=CameraModel, auth=auth)

    async def get_by_id_crud(self, id: int) -> CameraModel | None:
        return await self.get(id=id)

    async def get_list_crud(self, search: dict | None = None, order_by: list[dict[str, str]] | None = None) -> Sequence[CameraModel]:
        return await self.list(search=search, order_by=order_by)

    async def create_crud(self, data: CameraCreateSchema) -> CameraModel:
        return await self.create(data=data)

    async def update_crud(self, id: int, data: CameraUpdateSchema) -> CameraModel:
        return await self.update(id=id, data=data)

    async def delete_crud(self, ids: list[int]) -> None:
        await self.delete(ids=ids)

    async def set_available_crud(self, ids: list[int], status: bool) -> None:
        await self.set(ids=ids, status=status)


class CameraGroupCRUD(CRUDBase[CameraGroupModel, CameraGroupCreateSchema, CameraGroupUpdateSchema]):
    def __init__(self, auth: AuthSchema) -> None:
        self.auth = auth
        super().__init__(model=CameraGroupModel, auth=auth)

    async def get_list_crud(self, search: dict | None = None, order_by: list[dict[str, str]] | None = None) -> Sequence[CameraGroupModel]:
        return await self.list(search=search, order_by=order_by)

    async def create_crud(self, data: CameraGroupCreateSchema) -> CameraGroupModel:
        return await self.create(data=data)

    async def update_crud(self, id: int, data: CameraGroupUpdateSchema) -> CameraGroupModel:
        return await self.update(id=id, data=data)

    async def delete_crud(self, ids: list[int]) -> None:
        await self.delete(ids=ids)
