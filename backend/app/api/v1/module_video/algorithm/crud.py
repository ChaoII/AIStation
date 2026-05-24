from collections.abc import Sequence

from app.api.v1.module_system.auth.schema import AuthSchema
from app.core.base_crud import CRUDBase

from .model import AlgorithmModel, AlgorithmTaskModel
from .schema import (
    AlgorithmCreateSchema,
    AlgorithmTaskCreateSchema,
    AlgorithmTaskUpdateSchema,
    AlgorithmUpdateSchema,
)


class AlgorithmCRUD(CRUDBase[AlgorithmModel, AlgorithmCreateSchema, AlgorithmUpdateSchema]):
    def __init__(self, auth: AuthSchema) -> None:
        self.auth = auth
        super().__init__(model=AlgorithmModel, auth=auth)

    async def get_by_id_crud(self, id: int) -> AlgorithmModel | None:
        return await self.get(id=id)

    async def get_list_crud(self, search: dict | None = None, order_by: list[dict[str, str]] | None = None) -> Sequence[AlgorithmModel]:
        return await self.list(search=search, order_by=order_by)


class AlgorithmTaskCRUD(CRUDBase[AlgorithmTaskModel, AlgorithmTaskCreateSchema, AlgorithmTaskUpdateSchema]):
    def __init__(self, auth: AuthSchema) -> None:
        self.auth = auth
        super().__init__(model=AlgorithmTaskModel, auth=auth)

    async def get_by_id_crud(self, id: int) -> AlgorithmTaskModel | None:
        return await self.get(id=id)

    async def get_list_crud(self, search: dict | None = None, order_by: list[dict[str, str]] | None = None) -> Sequence[AlgorithmTaskModel]:
        return await self.list(search=search, order_by=order_by)
