from typing import Dict

from app.core.exceptions import CustomException
from app.core.media_server import media_server
from ..camera.crud import CameraCRUD
from ..camera.schema import CameraOutSchema
from app.api.v1.module_system.auth.schema import AuthSchema


class PreviewService:

    @classmethod
    async def get_play_urls_service(cls, camera_id: int, auth: AuthSchema) -> Dict:
        camera = await CameraCRUD(auth).get_by_id_crud(id=camera_id)
        if not camera:
            raise CustomException(msg="摄像机不存在")
        stream_id = camera.stream_id
        if not stream_id:
            raise CustomException(msg=f"摄像机 {camera.name} 未启动推流，请先启动推流")
        return media_server.get_play_urls(stream_id)

    @classmethod
    async def get_snap_service(cls, camera_id: int, auth: AuthSchema) -> bytes:
        camera = await CameraCRUD(auth).get_by_id_crud(id=camera_id)
        if not camera:
            raise CustomException(msg="摄像机不存在")
        if not camera.stream_id:
            raise CustomException(msg="摄像机未启动推流")
        try:
            return await media_server.get_snap(stream_id=camera.stream_id)
        except Exception as e:
            raise CustomException(msg=f"获取截图失败: {e}")
