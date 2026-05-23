from typing import Any, Dict, List, Optional

from app.core.exceptions import CustomException
from app.core.media_server import media_server
from app.api.v1.module_system.auth.schema import AuthSchema
from .crud import RecordPlanCRUD, RecordFileCRUD
from .schema import RecordPlanCreateSchema, RecordPlanUpdateSchema, RecordPlanOutSchema


class RecordService:

    @classmethod
    async def get_plan_list_service(cls, auth: AuthSchema, search: Optional[Any] = None, order_by: Optional[List[Dict[str, str]]] = None) -> List[Dict]:
        plans = await RecordPlanCRUD(auth).get_list_crud(
            search=search.__dict__ if search else None,
            order_by=order_by
        )
        return [RecordPlanOutSchema.model_validate(p).model_dump() for p in plans]

    @classmethod
    async def create_plan_service(cls, data: RecordPlanCreateSchema, auth: AuthSchema) -> Dict:
        new_plan = await RecordPlanCRUD(auth).create(data=data)
        return RecordPlanOutSchema.model_validate(new_plan).model_dump()

    @classmethod
    async def update_plan_service(cls, id: int, data: RecordPlanUpdateSchema, auth: AuthSchema) -> Dict:
        plan = await RecordPlanCRUD(auth).get_by_id_crud(id=id)
        if not plan:
            raise CustomException(msg="录制计划不存在")
        updated = await RecordPlanCRUD(auth).update(id=id, data=data)
        return RecordPlanOutSchema.model_validate(updated).model_dump()

    @classmethod
    async def delete_plan_service(cls, ids: List[int], auth: AuthSchema) -> None:
        await RecordPlanCRUD(auth).delete(ids=ids)

    @classmethod
    async def start_recording_service(cls, camera_id: int, stream_id: str, auth: AuthSchema) -> Dict:
        try:
            result = await media_server.start_record(stream_id=stream_id)
            return {"camera_id": camera_id, "stream_id": stream_id, "zlm_result": result}
        except Exception as e:
            raise CustomException(msg=f"启动录制失败: {e}")

    @classmethod
    async def stop_recording_service(cls, stream_id: str, auth: AuthSchema) -> Dict:
        try:
            result = await media_server.stop_record(stream_id=stream_id)
            return {"stream_id": stream_id, "zlm_result": result}
        except Exception as e:
            raise CustomException(msg=f"停止录制失败: {e}")

    @classmethod
    async def get_record_files_service(cls, camera_id: int, auth: AuthSchema) -> List[Dict]:
        search = {"camera_id": camera_id}
        files = await RecordFileCRUD(auth).get_list_crud(search=search, order_by=[{"start_time": "desc"}])
        return [RecordPlanOutSchema.model_validate(f).model_dump() for f in files]
