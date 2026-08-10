from typing import Any

from app.api.v1.module_system.auth.schema import AuthSchema
from app.core.exceptions import CustomException

from .crud import EventCRUD
from .schema import EventCreateSchema, EventOutSchema, EventUpdateSchema


class EventService:

    @classmethod
    async def get_event_list_service(cls, auth: AuthSchema, search: Any | None = None, order_by: list[dict[str, str]] | None = None) -> list[dict]:
        items = await EventCRUD(auth).get_list_crud(
            search=search.__dict__ if search else None,
            order_by=order_by
        )
        return [EventOutSchema.model_validate(item).model_dump() for item in items]

    @classmethod
    async def create_event_service(cls, data: EventCreateSchema, auth: AuthSchema) -> dict:
        item = await EventCRUD(auth).create(data=data)
        return EventOutSchema.model_validate(item).model_dump()

    @classmethod
    async def update_event_service(cls, id: int, data: EventUpdateSchema, auth: AuthSchema) -> dict:
        item = await EventCRUD(auth).get_by_id_crud(id=id)
        if not item:
            raise CustomException(msg="事件联动不存在")
        updated = await EventCRUD(auth).update(id=id, data=data)
        return EventOutSchema.model_validate(updated).model_dump()

    @classmethod
    async def delete_event_service(cls, ids: list[int], auth: AuthSchema) -> None:
        await EventCRUD(auth).delete(ids=ids)

    @classmethod
    async def execute_linkage_actions(cls, camera_id: int, event_type: str) -> list[str]:
        """运行时执行事件联动动作（逻辑闭环：事件源 → linkage 动作）。

        在告警创建等事件发生时调用，查询启用的联动规则（trigger_event 匹配 + 摄像机匹配），
        执行 action_type：
          - RECORD: 若流在线则启动录像
          - ALERT/PUSH: 告警记录/通知已由事件源处理，此处仅记录
          - PTZ: 暂无后端，记录为跳过
        """
        from sqlalchemy import select

        from app.core.database import async_db_session

        from .model import EventLinkageModel

        executed = []
        async with async_db_session() as session:
            stmt = select(EventLinkageModel).where(
                EventLinkageModel.status.is_(True),
                EventLinkageModel.is_deleted.is_(False),
                EventLinkageModel.trigger_event == event_type,
            )
            linkages = list((await session.execute(stmt)).scalars().all())

        for ln in linkages:
            # 摄像机过滤：trigger_camera_ids 为空 → 全部；否则需包含该 camera
            cids = ln.trigger_camera_ids or []
            if cids and camera_id not in cids:
                continue
            action = ln.action_type or ""
            try:
                if action == "RECORD":
                    # 启动录像（若流在线，_start_ffmpeg_recording 内部校验）
                    from sqlalchemy import select as sa_select

                    from app.api.v1.module_video.camera.model import CameraModel
                    from app.api.v1.module_video.record.service import RecordService

                    async with async_db_session() as session:
                        cam = (await session.execute(sa_select(CameraModel).where(
                            CameraModel.id == camera_id,
                            CameraModel.is_deleted.is_(False),
                        ))).scalar_one_or_none()
                    if cam and cam.stream_id:
                        try:
                            await RecordService._start_ffmpeg_recording(camera_id, cam.stream_id, "ALARM")
                            executed.append(f"RECORD:{ln.name}")
                        except Exception as e:
                            from app.core.logger import log
                            log.warning(f"[事件联动] RECORD 失败: {ln.name} camera={camera_id} err={e}")
                else:
                    executed.append(f"{action}:{ln.name}")
            except Exception as e:
                from app.core.logger import log
                log.warning(f"[事件联动] 执行失败: {ln.name} action={action} err={e}")
        return executed
