from typing import Dict, List, Optional, Sequence

from app.core.base_crud import CRUDBase
from .model import AlarmRuleModel, AlarmRecordModel
from .schema import AlarmRuleCreateSchema, AlarmRuleUpdateSchema
from app.api.v1.module_system.auth.schema import AuthSchema


class AlarmRuleCRUD(CRUDBase[AlarmRuleModel, AlarmRuleCreateSchema, AlarmRuleUpdateSchema]):
    def __init__(self, auth: AuthSchema) -> None:
        self.auth = auth
        super().__init__(model=AlarmRuleModel, auth=auth)

    async def get_by_id_crud(self, id: int) -> Optional[AlarmRuleModel]:
        return await self.get(id=id)

    async def get_list_crud(self, search: Optional[Dict] = None, order_by: Optional[List[Dict[str, str]]] = None) -> Sequence[AlarmRuleModel]:
        return await self.list(search=search, order_by=order_by)


class AlarmRecordCRUD(CRUDBase[AlarmRecordModel, None, None]):
    def __init__(self, auth: AuthSchema) -> None:
        self.auth = auth
        super().__init__(model=AlarmRecordModel, auth=auth)

    async def get_list_crud(self, search: Optional[Dict] = None, order_by: Optional[List[Dict[str, str]]] = None) -> Sequence[AlarmRecordModel]:
        return await self.list(search=search, order_by=order_by)
