from datetime import datetime

from sqlalchemy import delete as sa_delete
from sqlalchemy import func, select
from sqlalchemy import update as sa_update

from app.api.v1.module_system.auth.schema import AuthSchema
from app.core.exceptions import CustomException
from app.core.media_server import media_server
from app.utils.common_util import traversal_to_tree

from .crud import CameraCRUD, CameraGroupCRUD
from .model import CameraGroupModel
from .param import CameraQueryParam
from .schema import (
    CameraCreateSchema,
    CameraGroupCreateSchema,
    CameraGroupOutSchema,
    CameraGroupUpdateSchema,
    CameraOutSchema,
    CameraUpdateSchema,
)


class CameraService:

    @classmethod
    async def get_detail_by_id_service(cls, auth: AuthSchema, id: int) -> dict:
        camera = await CameraCRUD(auth).get_by_id_crud(id=id)
        if not camera:
            raise CustomException(msg="摄像机不存在")
        result = CameraOutSchema.model_validate(camera).model_dump()
        result["play_urls"] = None
        result["stream_source"] = None
        if camera.stream_id:
            result["play_urls"] = media_server.get_play_urls(camera.stream_id)
            result["stream_source"] = "EXTERNAL" if not camera.stream_id.startswith("camera_") else "SYSTEM"
            result["stream_status"] = "PUSHING" if camera.reachable else "IDLE"
        return result

    @classmethod
    async def get_camera_list_service(cls, auth: AuthSchema, search: CameraQueryParam | None = None, order_by: list[dict[str, str]] | None = None) -> list[dict]:
        camera_list = await CameraCRUD(auth).get_list_crud(
            search=search.__dict__ if search else None,
            order_by=order_by
        )
        result = []
        for camera in camera_list:
            d = CameraOutSchema.model_validate(camera).model_dump()
            d["play_urls"] = None
            d["stream_source"] = None
            if camera.stream_id:
                d["play_urls"] = media_server.get_play_urls(camera.stream_id)
                d["stream_source"] = "EXTERNAL" if not camera.stream_id.startswith("camera_") else "SYSTEM"
                d["stream_status"] = "PUSHING" if camera.reachable else "IDLE"
            result.append(d)
        return result

    @classmethod
    async def create_camera_service(cls, data: CameraCreateSchema, auth: AuthSchema) -> dict:
        new_camera = await CameraCRUD(auth).create_crud(data=data)
        return CameraOutSchema.model_validate(new_camera).model_dump()

    @classmethod
    async def update_camera_service(cls, id: int, data: CameraUpdateSchema, auth: AuthSchema) -> dict:
        camera = await CameraCRUD(auth).get_by_id_crud(id=id)
        if not camera:
            raise CustomException(msg="摄像机不存在")
        updated = await CameraCRUD(auth).update_crud(id=id, data=data)
        return CameraOutSchema.model_validate(updated).model_dump()

    @classmethod
    async def delete_camera_service(cls, ids: list[int], auth: AuthSchema) -> None:
        from app.api.v1.module_video.alarm.model import AlarmRecordModel, AlarmRuleModel
        from app.api.v1.module_video.algorithm.model import AlgorithmTaskModel
        from app.api.v1.module_video.record.model import (
            RecordExecutionLog,
            RecordFileModel,
            RecordPlanModel,
        )

        for id in ids:
            camera = await CameraCRUD(auth).get_by_id_crud(id=id)
            if not camera:
                raise CustomException(msg=f"摄像机ID {id} 不存在")
            if camera.stream_id:
                try:
                    await media_server.close_stream(camera.stream_id)
                except Exception:
                    pass

        # 相机是软删（CameraModel 含 is_deleted），DB 永远收不到 DELETE，
        # 子表的 ON DELETE CASCADE 因此永不触发（H4）。此处显式处理子表：
        # 支持软删的子表置 is_deleted；不支持软删的子表物理删除（与 FK 语义一致）。
        now = datetime.now()
        deleted_by = auth.user.id if auth.user else None
        for model in (AlgorithmTaskModel, AlarmRuleModel, RecordPlanModel):
            values: dict = {"is_deleted": True, "deleted_time": now}
            if deleted_by is not None:
                values["deleted_id"] = deleted_by
            await auth.db.execute(
                sa_update(model).where(model.camera_id.in_(ids)).values(**values)
            )
        for model in (AlarmRecordModel, RecordFileModel, RecordExecutionLog):
            await auth.db.execute(sa_delete(model).where(model.camera_id.in_(ids)))
        await auth.db.flush()

        await CameraCRUD(auth).delete_crud(ids=ids)

    @classmethod
    async def start_stream_service(cls, id: int, auth: AuthSchema) -> dict:
        camera = await CameraCRUD(auth).get_by_id_crud(id=id)
        if not camera:
            raise CustomException(msg="摄像机不存在")
        stream_id = f"camera_{camera.id}"

        if camera.stream_id == stream_id:
            try:
                online = await media_server.is_media_online(stream_id)
                if online:
                    return {"stream_id": stream_id, "play_urls": media_server.get_play_urls(stream_id)}
            except Exception:
                pass

        rtsp_url = camera.rtsp_url_main if camera.stream_type == "MAIN" else camera.rtsp_url_sub
        if not rtsp_url:
            raise CustomException(msg=f"摄像机 {camera.name} 未配置RTSP地址")
        try:
            await media_server.add_stream_proxy(url=rtsp_url, stream_id=stream_id)
        except Exception as e:
            msg = str(e)
            if "already exists" in msg:
                await CameraCRUD(auth).update_crud(id=id, data={
                    "stream_id": stream_id, "stream_status": "PUSHING", "status": "ONLINE"
                })
                return {"stream_id": stream_id, "play_urls": media_server.get_play_urls(stream_id)}
            raise CustomException(msg=f"启动推流失败: {e}")
        await CameraCRUD(auth).update_crud(id=id, data={
            "stream_id": stream_id, "stream_status": "PUSHING", "status": "ONLINE"
        })
        return {"stream_id": stream_id, "play_urls": media_server.get_play_urls(stream_id)}

    @classmethod
    async def stop_stream_service(cls, id: int, auth: AuthSchema) -> None:
        camera = await CameraCRUD(auth).get_by_id_crud(id=id)
        if not camera:
            raise CustomException(msg="摄像机不存在")
        if camera.stream_id:
            try:
                await media_server.close_stream(camera.stream_id)
            except Exception:
                pass
        await CameraCRUD(auth).update_crud(id=id, data={
            "stream_id": None, "stream_status": "IDLE", "status": "OFFLINE"
        })

    @classmethod
    async def get_stream_urls_service(cls, id: int, auth: AuthSchema) -> dict:
        camera = await CameraCRUD(auth).get_by_id_crud(id=id)
        if not camera:
            raise CustomException(msg="摄像机不存在")
        if not camera.stream_id:
            raise CustomException(msg="摄像机未启动推流，请先点击「推流」按钮")
        return {"stream_id": camera.stream_id, "play_urls": media_server.get_play_urls(camera.stream_id)}

    @classmethod
    async def check_stream_online_service(cls, id: int, auth: AuthSchema) -> bool:
        camera = await CameraCRUD(auth).get_by_id_crud(id=id)
        if not camera:
            raise CustomException(msg="摄像机不存在")
        if not camera.stream_id:
            return False
        try:
            return await media_server.is_media_online(camera.stream_id)
        except Exception:
            return False

    @classmethod
    async def get_group_list_service(cls, auth: AuthSchema) -> list[dict]:
        items = await CameraGroupCRUD(auth).get_list_crud(order_by=[{"sort_order": "asc"}])
        dict_list = [CameraGroupOutSchema.model_validate(item).model_dump() for item in items]
        return traversal_to_tree(dict_list)

    @classmethod
    async def create_group_service(cls, data: CameraGroupCreateSchema, auth: AuthSchema) -> dict:
        item = await CameraGroupCRUD(auth).create_crud(data=data)
        return CameraGroupOutSchema.model_validate(item).model_dump()

    @classmethod
    async def update_group_service(cls, id: int, data: CameraGroupUpdateSchema, auth: AuthSchema) -> dict:
        item = await CameraGroupCRUD(auth).get_list_crud(search={"id": id})
        if not item:
            raise CustomException(msg="分组不存在")
        updated = await CameraGroupCRUD(auth).update_crud(id=id, data=data)
        return CameraGroupOutSchema.model_validate(updated).model_dump()

    @classmethod
    async def delete_group_service(cls, ids: list[int], auth: AuthSchema) -> None:
        """删除相机分组：存在子分组或告警规则引用时拒绝（H3）。

        ``group_id`` 外键为 ``ON DELETE SET NULL``，直接删除会让组规则的
        ``camera_id``/``group_id`` 同时为空（双空作用域），规则既不触发也无法编辑。
        故在删除前显式校验引用。
        """
        from app.api.v1.module_video.alarm.model import AlarmRuleModel

        child_count = (
            await auth.db.execute(
                select(func.count())
                .select_from(CameraGroupModel)
                .where(CameraGroupModel.parent_id.in_(ids))
            )
        ).scalar() or 0
        if child_count > 0:
            raise CustomException(
                msg="分组下存在子分组，请先删除或迁移子分组",
                code=400,
                status_code=400,
            )

        rule_count = (
            await auth.db.execute(
                select(func.count())
                .select_from(AlarmRuleModel)
                .where(
                    AlarmRuleModel.group_id.in_(ids),
                    AlarmRuleModel.is_deleted.is_(False),
                )
            )
        ).scalar() or 0
        if rule_count > 0:
            raise CustomException(
                msg="分组下存在告警规则，请先删除或改绑规则",
                code=400,
                status_code=400,
            )

        await CameraGroupCRUD(auth).delete_crud(ids=ids)
