import asyncio
from datetime import datetime
from typing import Any

from sqlalchemy import select, update as sa_update

from app.api.v1.module_system.auth.schema import AuthSchema
from app.api.v1.module_video.camera.model import CameraModel
from app.core.database import async_db_session
from app.core.exceptions import CustomException
from app.core.media_server import media_server

from .crud import RecordExecutionLogCRUD, RecordFileCRUD, RecordPlanCRUD
from .model import RecordExecutionLog, RecordFileModel, RecordPlanModel
from .schema import (
    RecordExecutionLogOutSchema,
    RecordFileOutSchema,
    RecordPlanCreateSchema,
    RecordPlanOutSchema,
    RecordPlanUpdateSchema,
)


class RecordService:

    @classmethod
    async def get_plan_list_service(
        cls, auth: AuthSchema, search: Any | None = None, order_by: list[dict[str, str]] | None = None
    ) -> list[dict]:
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
            await media_server.start_record(stream_id=stream_id)
            plan_ids = await cls._get_plan_ids_for_camera(camera_id)
            if plan_ids:
                for pid in plan_ids:
                    log_entry = RecordExecutionLog(
                        plan_id=pid, camera_id=camera_id, stream_id=stream_id,
                        trigger_type="MANUAL", status="RECORDING", start_time=datetime.now(),
                    )
                    async with async_db_session() as session:
                        session.add(log_entry)
                        await session.commit()
            return {"camera_id": camera_id, "stream_id": stream_id}
        except Exception as e:
            raise CustomException(msg=f"启动录制失败: {e}")

    @classmethod
    async def stop_recording_service(cls, stream_id: str, auth: AuthSchema) -> dict:
        try:
            await media_server.stop_record(stream_id=stream_id)
            await cls._complete_running_logs(stream_id)
            await asyncio.sleep(1)
            await cls._sync_recorded_files(stream_id)
            return {"stream_id": stream_id}
        except Exception as e:
            raise CustomException(msg=f"停止录制失败: {e}")

    @classmethod
    async def _sync_recorded_files(cls, stream_id: str):
        files = await media_server.get_record_files(stream_id=stream_id)
        if not files:
            return
        camera_id = None
        async with async_db_session() as session:
            result = await session.execute(
                select(CameraModel.id).where(
                    CameraModel.stream_id == stream_id,
                    CameraModel.is_deleted.is_(False),
                )
            )
            cam = result.scalar_one_or_none()
            if cam:
                camera_id = cam
        if not camera_id:
            return
        now = datetime.now()
        for f in files:
            file_name = f.get("file_name", "")
            if not file_name:
                continue
            async with async_db_session() as session:
                existing = await session.execute(
                    select(RecordFileModel.id).where(
                        RecordFileModel.file_path == file_name,
                        RecordFileModel.stream_id == stream_id,
                    )
                )
                if existing.scalar_one_or_none():
                    continue
                record_file = RecordFileModel(
                    camera_id=camera_id,
                    stream_id=stream_id,
                    file_path=file_name,
                    file_size=f.get("file_size", 0),
                    duration=f.get("duration", 0),
                    start_time=cls._parse_zlm_time(f.get("start_time")) or now,
                    end_time=cls._parse_zlm_time(f.get("time")) or now,
                    record_type="MANUAL",
                    format="mp4",
                    status="COMPLETED",
                )
                session.add(record_file)
                await session.commit()

    @staticmethod
    def _parse_zlm_time(time_str: str | None) -> datetime | None:
        if not time_str:
            return None
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"):
            try:
                return datetime.strptime(time_str, fmt)
            except ValueError:
                continue
        return None

    @classmethod
    async def _get_plan_ids_for_camera(cls, camera_id: int) -> list[int]:
        async with async_db_session() as session:
            result = await session.execute(
                select(RecordPlanModel.id).where(
                    RecordPlanModel.camera_id == camera_id,
                    RecordPlanModel.status.is_(True),
                    RecordPlanModel.is_deleted.is_(False),
                )
            )
            return [r[0] for r in result.all()]

    @classmethod
    async def _complete_running_logs(cls, stream_id: str):
        async with async_db_session() as session:
            result = await session.execute(
                select(RecordExecutionLog).where(
                    RecordExecutionLog.stream_id == stream_id,
                    RecordExecutionLog.status == "RECORDING",
                )
            )
            now = datetime.now()
            for log_entry in result.scalars().all():
                if log_entry.start_time:
                    log_entry.duration = int((now - log_entry.start_time).total_seconds())
                log_entry.end_time = now
                log_entry.status = "COMPLETED"
                log_entry.updated_at = now
            await session.commit()

    @classmethod
    async def get_record_files_service(cls, camera_id: int, auth: AuthSchema) -> list[dict]:
        search = {"camera_id": camera_id}
        files = await RecordFileCRUD(auth).get_list_crud(search=search, order_by=[{"start_time": "desc"}])
        return [RecordFileOutSchema.model_validate(f).model_dump() for f in files]

    @classmethod
    async def get_file_list_service(
        cls, auth: AuthSchema, search: Any | None = None, order_by: list[dict[str, str]] | None = None
    ) -> list[dict]:
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

    @classmethod
    async def get_file_play_url_service(cls, id: int, auth: AuthSchema) -> dict:
        file_obj = await RecordFileCRUD(auth).get(id=id)
        if not file_obj:
            raise CustomException(msg="录制文件不存在")
        # Play URL served by ZLM HTTP server at /record/{app}/{stream_id}/{file_name}
        file_name = str(file_obj.file_path).split("/")[-1]
        play_url = media_server.get_record_file_url(
            stream_id=file_obj.stream_id or "",
            file_name=file_name,
            app="record",
        )
        return {
            "id": file_obj.id,
            "camera_id": file_obj.camera_id,
            "stream_id": file_obj.stream_id,
            "file_path": file_obj.file_path,
            "play_url": play_url,
        }

    @classmethod
    async def get_execution_log_list_service(
        cls, auth: AuthSchema, search: Any | None = None, order_by: list[dict[str, str]] | None = None
    ) -> list[dict]:
        logs = await RecordExecutionLogCRUD(auth).get_list_crud(
            search=search.__dict__ if search else None,
            order_by=order_by or [{"start_time": "desc"}],
        )
        return [RecordExecutionLogOutSchema.model_validate(log).model_dump() for log in logs]

    @classmethod
    async def get_execution_log_detail_service(cls, id: int, auth: AuthSchema) -> dict:
        log_entry = await RecordExecutionLogCRUD(auth).get_by_id_crud(id=id)
        if not log_entry:
            raise CustomException(msg="执行日志不存在")
        return RecordExecutionLogOutSchema.model_validate(log_entry).model_dump()

    @classmethod
    async def handle_record_webhook(cls, data: dict) -> dict:
        stream_id = data.get("stream_id", "")
        file_path = data.get("file_path", "")
        file_name = data.get("file_name", "")
        file_size = data.get("file_size", 0)
        duration = data.get("duration", 0)
        start_time_str = data.get("start_time", "")
        end_time_str = data.get("time", "")

        camera_id = None
        if stream_id:
            async with async_db_session() as session:
                result = await session.execute(
                    select(CameraModel.id).where(
                        CameraModel.stream_id == stream_id,
                        CameraModel.is_deleted.is_(False),
                    )
                )
                cam = result.scalar_one_or_none()
                if cam:
                    camera_id = cam

        if not camera_id:
            return {"code": 1, "msg": "camera not found"}

        record_file = RecordFileModel(
            camera_id=camera_id,
            stream_id=stream_id,
            file_path=file_path or file_name,
            file_size=file_size,
            duration=duration,
            start_time=datetime.fromisoformat(start_time_str) if start_time_str else datetime.now(),
            end_time=datetime.fromisoformat(end_time_str) if end_time_str else datetime.now(),
            record_type="CONTINUOUS",
            format="mp4",
            status="COMPLETED",
        )
        async with async_db_session() as session:
            session.add(record_file)
            await session.commit()

            await session.execute(
                sa_update(RecordExecutionLog)
                .where(
                    RecordExecutionLog.stream_id == stream_id,
                    RecordExecutionLog.status == "RECORDING",
                )
                .values(
                    file_count=RecordExecutionLog.file_count + 1,
                    updated_at=datetime.now(),
                )
            )
            await session.commit()

        return {"code": 0, "msg": "ok"}
