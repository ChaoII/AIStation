from typing import Any

from app.api.v1.module_system.auth.schema import AuthSchema
from app.core.exceptions import CustomException
from app.core.media_server import media_server

from .crud import RecordFileCRUD, RecordPlanCRUD
from .schema import (
    RecordFileOutSchema,
    RecordPlanCreateSchema,
    RecordPlanOutSchema,
    RecordPlanUpdateSchema,
)


class RecordService:

    @classmethod
    async def get_plan_list_service(cls, auth: AuthSchema, search: Any | None = None, order_by: list[dict[str, str]] | None = None) -> list[dict]:
        plans = await RecordPlanCRUD(auth).get_list_crud(
            search=search.__dict__ if search else None,
            order_by=order_by
        )
        return [RecordPlanOutSchema.model_validate(p).model_dump() for p in plans]

    @classmethod
    async def create_plan_service(cls, data: RecordPlanCreateSchema, auth: AuthSchema) -> dict:
        new_plan = await RecordPlanCRUD(auth).create(data=data)
        return RecordPlanOutSchema.model_validate(new_plan).model_dump()

    @classmethod
    async def update_plan_service(cls, id: int, data: RecordPlanUpdateSchema, auth: AuthSchema) -> dict:
        plan = await RecordPlanCRUD(auth).get_by_id_crud(id=id)
        if not plan:
            raise CustomException(msg="录制计划不存在")
        updated = await RecordPlanCRUD(auth).update(id=id, data=data)
        return RecordPlanOutSchema.model_validate(updated).model_dump()

    @classmethod
    async def delete_plan_service(cls, ids: list[int], auth: AuthSchema) -> None:
        await RecordPlanCRUD(auth).delete(ids=ids)

    @classmethod
    async def start_recording_service(cls, camera_id: int, stream_id: str, auth: AuthSchema) -> dict:
        try:
            result = await media_server.start_record(stream_id=stream_id)
            return {"camera_id": camera_id, "stream_id": stream_id, "zlm_result": result}
        except Exception as e:
            raise CustomException(msg=f"启动录制失败: {e}")

    @classmethod
    async def stop_recording_service(cls, stream_id: str, auth: AuthSchema) -> dict:
        try:
            result = await media_server.stop_record(stream_id=stream_id)
            return {"stream_id": stream_id, "zlm_result": result}
        except Exception as e:
            raise CustomException(msg=f"停止录制失败: {e}")

    @classmethod
    async def get_record_files_service(cls, camera_id: int, auth: AuthSchema) -> list[dict]:
        search = {"camera_id": camera_id}
        files = await RecordFileCRUD(auth).get_list_crud(search=search, order_by=[{"start_time": "desc"}])
        return [RecordFileOutSchema.model_validate(f).model_dump() for f in files]

    @classmethod
    async def get_file_list_service(cls, auth: AuthSchema, search: Any | None = None, order_by: list[dict[str, str]] | None = None) -> list[dict]:
        files = await RecordFileCRUD(auth).get_list_crud(
            search=search.__dict__ if search else None,
            order_by=order_by
        )
        return [RecordFileOutSchema.model_validate(f).model_dump() for f in files]

    @classmethod
    async def get_file_detail_service(cls, id: int, auth: AuthSchema) -> dict:
        file_obj = await RecordFileCRUD(auth).get(id=id)
        if not file_obj:
            raise CustomException(msg="录制文件不存在")
        return RecordFileOutSchema.model_validate(file_obj).model_dump()

    @classmethod
    async def delete_file_service(cls, ids: list[int], auth: AuthSchema) -> None:
        await RecordFileCRUD(auth).delete(ids=ids)
