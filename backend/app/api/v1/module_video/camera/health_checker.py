import asyncio

from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy import update as sa_update

from app.api.v1.module_video.camera.model import CameraModel
from app.config.setting import settings
from app.core.database import async_db_session
from app.core.logger import logger

_CHECK_INTERVAL = 30
_FLV_TIMEOUT = 3.0


async def _check_stream_healthy(flv_url: str) -> bool:
    """Check if a FLV stream is actually producing data."""
    if not flv_url:
        return False
    try:
        async with AsyncClient(timeout=_FLV_TIMEOUT) as client:
            async with client.stream("GET", flv_url) as resp:
                if resp.status_code != 200:
                    return False
                chunk = b""
                async for data in resp.aiter_bytes():
                    chunk += data
                    if len(chunk) >= 16384:
                        break
                return len(chunk) >= 1024
    except Exception:
        return False


async def _check_one(camera: CameraModel) -> tuple[int, bool | None]:
    """Check a single camera's health. Returns (camera_id, reachable)."""
    if not camera.stream_id:
        return camera.id, None

    # Build FLV URL from ZLM
    flv_url = (
        f"{settings.ZLM_BASE_URL}/live/{camera.stream_id}.live.flv"
        if settings.ZLM_BASE_URL else ""
    )
    if not flv_url:
        return camera.id, None

    healthy = await _check_stream_healthy(flv_url)
    return camera.id, healthy


async def _run_health_check():
    """Check all cameras that have a stream_id and update reachable in DB."""
    try:
        async with async_db_session() as session:
            result = await session.execute(
                select(CameraModel).where(
                    CameraModel.stream_id.isnot(None),
                    CameraModel.is_deleted.is_(False),
                )
            )
            cameras = list(result.scalars().all())

        if not cameras:
            return

        results = await asyncio.gather(*[_check_one(c) for c in cameras], return_exceptions=True)

        async with async_db_session.begin() as session:
            for cam, res in zip(cameras, results, strict=False):
                if isinstance(res, Exception):
                    logger.warning(f"[健康检查] camera={cam.id} error: {res}")
                    continue
                cam_id, reachable = res
                await session.execute(
                    sa_update(CameraModel)
                    .where(CameraModel.id == cam_id)
                    .values(reachable=reachable)
                )

        logger.debug(f"[健康检查] 完成: {len(cameras)} 个摄像头")

    except Exception as e:
        logger.error(f"[健康检查] 异常: {e}")


_health_task: asyncio.Task | None = None


async def start_camera_health_checker():
    global _health_task
    _health_task = asyncio.current_task()
    await asyncio.sleep(10)  # Warmup
    logger.info(f"[健康检查] 启动，间隔 {_CHECK_INTERVAL}s")
    while True:
        await _run_health_check()
        await asyncio.sleep(_CHECK_INTERVAL)


async def stop_camera_health_checker():
    global _health_task
    if _health_task:
        _health_task.cancel()
        _health_task = None
        logger.info("[健康检查] 已停止")
