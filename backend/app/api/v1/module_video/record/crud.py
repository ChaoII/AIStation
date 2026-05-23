from typing import Dict, List, Optional, Sequence

from app.core.base_crud import CRUDBase
from .model import RecordPlanModel, RecordFileModel
from .schema import RecordPlanCreateSchema, RecordPlanUpdateSchema
from app.api.v1.module_system.auth.schema import AuthSchema


class RecordPlanCRUD(CRUDBase[RecordPlanModel, RecordPlanCreateSchema, RecordPlanUpdateSchema]):
    def __init__(self, auth: AuthSchema) -> None:
        self.auth = auth
        super().__init__(model=RecordPlanModel, auth=auth)

    async def get_by_id_crud(self, id: int) -> Optional[RecordPlanModel]:
        return await self.get(id=id)

    async def get_list_crud(self, search: Optional[Dict] = None, order_by: Optional[List[Dict[str, str]]] = None) -> Sequence[RecordPlanModel]:
        return await self.list(search=search, order_by=order_by)


class RecordFileCRUD(CRUDBase[RecordFileModel, None, None]):
    def __init__(self, auth: AuthSchema) -> None:
        self.auth = auth
        super().__init__(model=RecordFileModel, auth=auth)

    async def get_list_crud(self, search: Optional[Dict] = None, order_by: Optional[List[Dict[str, str]]] = None) -> Sequence[RecordFileModel]:
        return await self.list(search=search, order_by=order_by)
