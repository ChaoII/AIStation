from collections.abc import Sequence

from app.api.v1.module_system.auth.schema import AuthSchema
from app.core.base_crud import CRUDBase

from .model import EventLinkageModel
from .schema import EventCreateSchema, EventUpdateSchema


class EventCRUD(CRUDBase[EventLinkageModel, EventCreateSchema, EventUpdateSchema]):
    def __init__(self, auth: AuthSchema) -> None:
        self.auth = auth
        super().__init__(model=EventLinkageModel, auth=auth)

    async def get_by_id_crud(self, id: int) -> EventLinkageModel | None:
        return await self.get(id=id)

    async def get_list_crud(self, search: dict | None = None, order_by: list[dict[str, str]] | None = None) -> Sequence[EventLinkageModel]:
        return await self.list(search=search, order_by=order_by)
