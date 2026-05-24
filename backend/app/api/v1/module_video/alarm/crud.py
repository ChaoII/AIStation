from collections.abc import Sequence

from app.api.v1.module_system.auth.schema import AuthSchema
from app.core.base_crud import CRUDBase

from .model import AlarmRecordModel, AlarmRuleModel
from .schema import AlarmRuleCreateSchema, AlarmRuleUpdateSchema


class AlarmRuleCRUD(CRUDBase[AlarmRuleModel, AlarmRuleCreateSchema, AlarmRuleUpdateSchema]):
    def __init__(self, auth: AuthSchema) -> None:
        self.auth = auth
        super().__init__(model=AlarmRuleModel, auth=auth)

    async def get_by_id_crud(self, id: int) -> AlarmRuleModel | None:
        return await self.get(id=id)

    async def get_list_crud(self, search: dict | None = None, order_by: list[dict[str, str]] | None = None) -> Sequence[AlarmRuleModel]:
        return await self.list(search=search, order_by=order_by)


class AlarmRecordCRUD(CRUDBase[AlarmRecordModel, None, None]):
    def __init__(self, auth: AuthSchema) -> None:
        self.auth = auth
        super().__init__(model=AlarmRecordModel, auth=auth)

    async def get_list_crud(self, search: dict | None = None, order_by: list[dict[str, str]] | None = None) -> Sequence[AlarmRecordModel]:
        return await self.list(search=search, order_by=order_by)
