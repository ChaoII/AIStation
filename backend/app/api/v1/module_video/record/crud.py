from collections.abc import Sequence

from app.api.v1.module_system.auth.schema import AuthSchema
from app.core.base_crud import CRUDBase

from .model import RecordFileModel, RecordPlanModel
from .schema import RecordPlanCreateSchema, RecordPlanUpdateSchema


class RecordPlanCRUD(CRUDBase[RecordPlanModel, RecordPlanCreateSchema, RecordPlanUpdateSchema]):
    def __init__(self, auth: AuthSchema) -> None:
        self.auth = auth
        super().__init__(model=RecordPlanModel, auth=auth)

    async def get_by_id_crud(self, id: int) -> RecordPlanModel | None:
        return await self.get(id=id)

    async def get_list_crud(self, search: dict | None = None, order_by: list[dict[str, str]] | None = None) -> Sequence[RecordPlanModel]:
        return await self.list(search=search, order_by=order_by)


class RecordFileCRUD(CRUDBase[RecordFileModel, None, None]):
    def __init__(self, auth: AuthSchema) -> None:
        self.auth = auth
        super().__init__(model=RecordFileModel, auth=auth)

    async def get_list_crud(self, search: dict | None = None, order_by: list[dict[str, str]] | None = None) -> Sequence[RecordFileModel]:
        return await self.list(search=search, order_by=order_by)
