
from app.api.v1.module_system.auth.schema import AuthSchema
from app.core.exceptions import CustomException
from app.core.media_server import media_server
from app.utils.common_util import traversal_to_tree

from .crud import CameraCRUD, CameraGroupCRUD
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
            try:
                online = await media_server.is_media_online(camera.stream_id)
                result["status"] = "ONLINE" if online else "OFFLINE"
                result["stream_status"] = "PUSHING" if online else "IDLE"
            except Exception:
                pass
        else:
            result["status"] = "OFFLINE"
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
                try:
                    online = await media_server.is_media_online(camera.stream_id)
                    d["status"] = "ONLINE" if online else "OFFLINE"
                    d["stream_status"] = "PUSHING" if online else "IDLE"
                except Exception:
                    pass
            else:
                d["status"] = "OFFLINE"
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
        for id in ids:
            camera = await CameraCRUD(auth).get_by_id_crud(id=id)
            if not camera:
                raise CustomException(msg=f"摄像机ID {id} 不存在")
            if camera.stream_id:
                try:
                    await media_server.close_stream(camera.stream_id)
                except Exception:
                    pass
        await CameraCRUD(auth).delete_crud(ids=ids)

    @classmethod
    async def start_stream_service(cls, id: int, auth: AuthSchema) -> dict:
        camera = await CameraCRUD(auth).get_by_id_crud(id=id)
        if not camera:
            raise CustomException(msg="摄像机不存在")
        rtsp_url = camera.rtsp_url_main if camera.stream_type == "MAIN" else camera.rtsp_url_sub
        if not rtsp_url:
            raise CustomException(msg=f"摄像机 {camera.name} 未配置RTSP地址")
        stream_id = f"camera_{camera.id}"
        try:
            await media_server.add_stream_proxy(url=rtsp_url, stream_id=stream_id)
        except Exception as e:
            raise CustomException(msg=f"启动推流失败: {e}")
        await CameraCRUD(auth).update_crud(id=id, data=CameraUpdateSchema(
            stream_id=stream_id, stream_status="PUSHING"
        ))
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
            try:
                still_online = await media_server.is_media_online(camera.stream_id)
                if still_online:
                    await CameraCRUD(auth).update_crud(id=id, data=CameraUpdateSchema(
                        stream_status="PUSHING"
                    ))
                    return
            except Exception:
                pass
        await CameraCRUD(auth).update_crud(id=id, data=CameraUpdateSchema(
            stream_id=None, stream_status="IDLE"
        ))

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
        await CameraGroupCRUD(auth).delete_crud(ids=ids)
