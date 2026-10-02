"""数据落地（抽帧/清洗）控制器：视频 → 图片、批量图片 → 清洗入库，均后台任务。

复用 ``annotation:dataset:create``（上传类）与 ``annotation:dataset:query``（查看任务）
两个既有权限，无需新增菜单/权限项。
"""
import asyncio
import os
import tempfile
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, File, Query, UploadFile
from fastapi.responses import JSONResponse

from app.api.v1.module_system.auth.schema import AuthSchema
from app.common.response import SuccessResponse
from app.core.dependencies import AuthPermission
from app.core.router_class import OperationLogRoute

from . import jobs
from .config import CleaningConfig, ExtractConfig
from .service import PreprocessService

PreprocessRouter = APIRouter(
    route_class=OperationLogRoute,
    prefix="/dataset/preprocess",
    tags=["数据标注-数据落地"],
)

_VIDEO_MAX_BYTES = 1024 * 1024 * 1024  # 视频 1GB 兜底
_VIDEO_EXTENSIONS = {".mp4", ".mov", ".mkv", ".avi", ".webm", ".flv", ".wmv", ".ts", ".m4v"}


@PreprocessRouter.post("/video", summary="视频抽帧+清洗入库（后台任务）")
async def preprocess_video(
    dataset_id: Annotated[int, Query(description="目标数据集")],
    interval: Annotated[float, Query(description="抽帧间隔（秒）")] = 1.0,
    max_frames: Annotated[int, Query(description="最多抽帧数，0 不限")] = 0,
    scene_change: Annotated[bool, Query(description="是否按场景变化额外取帧")] = False,
    scene_threshold: Annotated[float, Query(description="场景变化阈值")] = 25.0,
    min_side: Annotated[int, Query(description="短边最小像素，0 禁用")] = 320,
    blur: Annotated[float, Query(description="模糊阈值（Laplacian 方差），0 禁用")] = 30.0,
    brightness_min: Annotated[float, Query(description="过暗阈值，0 禁用")] = 20.0,
    brightness_max: Annotated[float, Query(description="过曝阈值，0 禁用")] = 240.0,
    phash: Annotated[int, Query(description="近重复汉明阈值，0 禁用")] = 6,
    video: UploadFile = File(...),
    auth: AuthSchema = Depends(AuthPermission(["annotation:dataset:create"])),
) -> JSONResponse:
    from app.core.exceptions import CustomException

    filename = video.filename or "unnamed"
    ext = Path(filename).suffix.lower()
    if ext not in _VIDEO_EXTENSIONS:
        raise CustomException(msg=f"不支持的视频格式: {filename}", code=400, status_code=400)

    extract_cfg = ExtractConfig.from_params(
        interval=interval, max_frames=max_frames,
        scene_change=scene_change, scene_threshold=scene_threshold,
    )
    clean_cfg = CleaningConfig.from_params(
        min_side=min_side, blur=blur,
        brightness_min=brightness_min, brightness_max=brightness_max, phash=phash,
    )

    # 先把上传视频流式写到临时文件，避免整段读入内存
    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(suffix=ext or ".mp4", delete=False) as tmp:
            tmp_path = tmp.name
            written = 0
            while True:
                chunk = await video.read(1024 * 1024)
                if not chunk:
                    break
                written += len(chunk)
                if written > _VIDEO_MAX_BYTES:
                    raise CustomException(
                        msg=f"文件过大: {filename}", code=400, status_code=400
                    )
                tmp.write(chunk)
    except Exception:
        if tmp_path and os.path.exists(tmp_path):
            os.unlink(tmp_path)
        raise

    job = jobs.create_job(dataset_id, auth.user.id, source="video", source_name=filename)
    asyncio.create_task(
        PreprocessService.run_video_job(
            job.job_id, dataset_id, auth.user.id,
            tmp_path, filename, extract_cfg, clean_cfg, auth,
        )
    )
    return SuccessResponse(data={"job_id": job.job_id}, msg="已开始抽帧入库")


@PreprocessRouter.post("/images", summary="批量图片清洗+入库（后台任务）")
async def preprocess_images(
    dataset_id: Annotated[int, Query(description="目标数据集")],
    min_side: Annotated[int, Query(description="短边最小像素，0 禁用")] = 320,
    blur: Annotated[float, Query(description="模糊阈值（Laplacian 方差），0 禁用")] = 30.0,
    brightness_min: Annotated[float, Query(description="过暗阈值，0 禁用")] = 20.0,
    brightness_max: Annotated[float, Query(description="过曝阈值，0 禁用")] = 240.0,
    phash: Annotated[int, Query(description="近重复汉明阈值，0 禁用")] = 6,
    files: list[UploadFile] = File(...),
    auth: AuthSchema = Depends(AuthPermission(["annotation:dataset:create"])),
) -> JSONResponse:
    from app.api.v1.module_annotation.dataset.media import ALLOWED_IMAGE_EXTENSIONS
    from app.config.setting import settings
    from app.core.exceptions import CustomException

    if not files:
        raise CustomException(msg="至少上传一张图片", code=400, status_code=400)

    max_bytes = settings.ANNOTATION_UPLOAD_MAX_MB * 1024 * 1024
    clean_cfg = CleaningConfig.from_params(
        min_side=min_side, blur=blur,
        brightness_min=brightness_min, brightness_max=brightness_max, phash=phash,
    )

    items: list[tuple[str, bytes]] = []
    for f in files:
        name = f.filename or "unnamed"
        ext = Path(name).suffix.lower()
        if ext not in ALLOWED_IMAGE_EXTENSIONS:
            raise CustomException(msg=f"不支持的图片格式: {name}", code=400, status_code=400)
        content = await f.read()
        if len(content) > max_bytes:
            raise CustomException(
                msg=f"文件过大（>{settings.ANNOTATION_UPLOAD_MAX_MB}MB）: {name}",
                code=400, status_code=400,
            )
        items.append((name, content))

    job = jobs.create_job(dataset_id, auth.user.id, source="images",
                          source_name=f"{len(items)} 张图片")
    asyncio.create_task(
        PreprocessService.run_images_job(job.job_id, dataset_id, auth.user.id, items, clean_cfg, auth)
    )
    return SuccessResponse(data={"job_id": job.job_id}, msg="已开始清洗入库")


@PreprocessRouter.get("/{job_id}", summary="查询数据落地任务进度")
async def get_preprocess_job(
    job_id: str,
    auth: AuthSchema = Depends(AuthPermission(["annotation:dataset:query"])),
):
    job = jobs.get_job(job_id)
    if job is None:
        from app.common.response import ErrorResponse
        return ErrorResponse(msg="任务不存在或已过期")
    return SuccessResponse(data=jobs.job_snapshot(job))
