from typing import Any, Dict, List, Optional

from app.core.exceptions import CustomException
from app.core.media_server import media_server
from app.api.v1.module_system.auth.schema import AuthSchema
from .crud import CameraCRUD
from .schema import CameraCreateSchema, CameraUpdateSchema, CameraOutSchema
from .param import CameraQueryParam


class CameraService:

    @classmethod
    async def get_detail_by_id_service(cls, auth: AuthSchema, id: int) -> Dict:
        camera = await CameraCRUD(auth).get_by_id_crud(id=id)
        if not camera:
            raise CustomException(msg="摄像机不存在")
        result = CameraOutSchema.model_validate(camera).model_dump()
        if camera.stream_id:
            result["play_urls"] = media_server.get_play_urls(camera.stream_id)
        return result

    @classmethod
    async def get_camera_list_service(cls, auth: AuthSchema, search: Optional[CameraQueryParam] = None, order_by: Optional[List[Dict[str, str]]] = None) -> List[Dict]:
        camera_list = await CameraCRUD(auth).get_list_crud(
            search=search.__dict__ if search else None,
            order_by=order_by
        )
        result = []
        for camera in camera_list:
            d = CameraOutSchema.model_validate(camera).model_dump()
            if camera.stream_id:
                d["play_urls"] = media_server.get_play_urls(camera.stream_id)
            result.append(d)
        return result

    @classmethod
    async def create_camera_service(cls, data: CameraCreateSchema, auth: AuthSchema) -> Dict:
        new_camera = await CameraCRUD(auth).create_crud(data=data)
        return CameraOutSchema.model_validate(new_camera).model_dump()

    @classmethod
    async def update_camera_service(cls, id: int, data: CameraUpdateSchema, auth: AuthSchema) -> Dict:
        camera = await CameraCRUD(auth).get_by_id_crud(id=id)
        if not camera:
            raise CustomException(msg="摄像机不存在")
        updated = await CameraCRUD(auth).update_crud(id=id, data=data)
        return CameraOutSchema.model_validate(updated).model_dump()

    @classmethod
    async def delete_camera_service(cls, ids: List[int], auth: AuthSchema) -> None:
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
    async def start_stream_service(cls, id: int, auth: AuthSchema) -> Dict:
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
        await CameraCRUD(auth).update_crud(id=id, data=CameraUpdateSchema(
            stream_id=None, stream_status="IDLE"
        ))
