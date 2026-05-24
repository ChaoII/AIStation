from typing import Any

from app.api.v1.module_system.auth.schema import AuthSchema
from app.core.exceptions import CustomException

from .crud import AlgorithmCRUD, AlgorithmTaskCRUD
from .schema import (
    AlgorithmCreateSchema,
    AlgorithmOutSchema,
    AlgorithmTaskCreateSchema,
    AlgorithmTaskOutSchema,
    AlgorithmTaskUpdateSchema,
    AlgorithmUpdateSchema,
)


class AlgorithmService:

    @classmethod
    async def get_algorithm_list_service(cls, auth: AuthSchema, search: Any | None = None, order_by: list[dict[str, str]] | None = None) -> list[dict]:
        items = await AlgorithmCRUD(auth).get_list_crud(
            search=search.__dict__ if search else None,
            order_by=order_by
        )
        return [AlgorithmOutSchema.model_validate(item).model_dump() for item in items]

    @classmethod
    async def create_algorithm_service(cls, data: AlgorithmCreateSchema, auth: AuthSchema) -> dict:
        item = await AlgorithmCRUD(auth).create(data=data)
        return AlgorithmOutSchema.model_validate(item).model_dump()

    @classmethod
    async def update_algorithm_service(cls, id: int, data: AlgorithmUpdateSchema, auth: AuthSchema) -> dict:
        item = await AlgorithmCRUD(auth).get_by_id_crud(id=id)
        if not item:
            raise CustomException(msg="算法不存在")
        updated = await AlgorithmCRUD(auth).update(id=id, data=data)
        return AlgorithmOutSchema.model_validate(updated).model_dump()

    @classmethod
    async def delete_algorithm_service(cls, ids: list[int], auth: AuthSchema) -> None:
        await AlgorithmCRUD(auth).delete(ids=ids)

    @classmethod
    async def get_task_list_service(cls, auth: AuthSchema, search: Any | None = None, order_by: list[dict[str, str]] | None = None) -> list[dict]:
        items = await AlgorithmTaskCRUD(auth).get_list_crud(
            search=search.__dict__ if search else None,
            order_by=order_by
        )
        return [AlgorithmTaskOutSchema.model_validate(item).model_dump() for item in items]

    @classmethod
    async def create_task_service(cls, data: AlgorithmTaskCreateSchema, auth: AuthSchema) -> dict:
        item = await AlgorithmTaskCRUD(auth).create(data=data)
        return AlgorithmTaskOutSchema.model_validate(item).model_dump()

    @classmethod
    async def update_task_service(cls, id: int, data: AlgorithmTaskUpdateSchema, auth: AuthSchema) -> dict:
        item = await AlgorithmTaskCRUD(auth).get_by_id_crud(id=id)
        if not item:
            raise CustomException(msg="算法任务不存在")
        updated = await AlgorithmTaskCRUD(auth).update(id=id, data=data)
        return AlgorithmTaskOutSchema.model_validate(updated).model_dump()

    @classmethod
    async def delete_task_service(cls, ids: list[int], auth: AuthSchema) -> None:
        await AlgorithmTaskCRUD(auth).delete(ids=ids)
