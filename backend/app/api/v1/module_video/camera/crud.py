from typing import Dict, List, Optional, Sequence

from app.core.base_crud import CRUDBase
from .model import CameraModel
from .schema import CameraCreateSchema, CameraUpdateSchema
from app.api.v1.module_system.auth.schema import AuthSchema


class CameraCRUD(CRUDBase[CameraModel, CameraCreateSchema, CameraUpdateSchema]):
    def __init__(self, auth: AuthSchema) -> None:
        self.auth = auth
        super().__init__(model=CameraModel, auth=auth)

    async def get_by_id_crud(self, id: int) -> Optional[CameraModel]:
        return await self.get(id=id)

    async def get_list_crud(self, search: Optional[Dict] = None, order_by: Optional[List[Dict[str, str]]] = None) -> Sequence[CameraModel]:
        return await self.list(search=search, order_by=order_by)

    async def create_crud(self, data: CameraCreateSchema) -> CameraModel:
        return await self.create(data=data)

    async def update_crud(self, id: int, data: CameraUpdateSchema) -> CameraModel:
        return await self.update(id=id, data=data)

    async def delete_crud(self, ids: List[int]) -> None:
        await self.delete(ids=ids)

    async def set_available_crud(self, ids: List[int], status: bool) -> None:
        await self.set(ids=ids, status=status)
