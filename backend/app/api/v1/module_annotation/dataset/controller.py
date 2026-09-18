from fastapi import APIRouter, Depends, File, UploadFile
from fastapi.responses import JSONResponse

from app.api.v1.module_system.auth.schema import AuthSchema
from app.common.response import SuccessResponse
from app.core.base_params import PaginationQueryParam
from app.core.dependencies import AuthPermission
from app.core.router_class import OperationLogRoute

from .param import DatasetQueryParam
from .schema import DatasetCreateSchema, DatasetOutSchema, DatasetUpdateSchema
from .service import DatasetService

DatasetRouter = APIRouter(route_class=OperationLogRoute, prefix="/dataset", tags=["数据标注-数据集"])


@DatasetRouter.get("/list", summary="查询数据集列表")
async def get_dataset_list(
    page: PaginationQueryParam = Depends(),
    search: DatasetQueryParam = Depends(),
    auth: AuthSchema = Depends(AuthPermission(["annotation:dataset:query"])),
) -> JSONResponse:
    from app.core.database import async_db_session

    from .crud import DatasetCRUD
    crud = DatasetCRUD(auth=auth)
    offset = (page.page_no - 1) * page.page_size
    result = await crud.page(
        offset=offset, limit=page.page_size, order_by=page.order_by,
        search=search.get_conditions(), out_schema=DatasetOutSchema,
    )
    # 本页任务与进度：单次聚合查询，只读不写
    if result.get("items"):
        async with async_db_session() as db:
            await DatasetService.enrich_dataset_list(db, result["items"])
    return SuccessResponse(data=result)


@DatasetRouter.post("/create", summary="创建数据集")
async def create_dataset(
    data: DatasetCreateSchema,
    auth: AuthSchema = Depends(AuthPermission(["annotation:dataset:create"])),
) -> JSONResponse:
    dataset = await DatasetService.create_dataset(data, auth)
    return SuccessResponse(data=dataset, msg="创建成功")


@DatasetRouter.put("/update/{id}", summary="更新数据集")
async def update_dataset(
    id: int,
    data: DatasetUpdateSchema,
    auth: AuthSchema = Depends(AuthPermission(["annotation:dataset:update"])),
) -> JSONResponse:
    from .crud import DatasetCRUD
    crud = DatasetCRUD(auth=auth)
    result = await crud.update(id=id, data=data)
    return SuccessResponse(data=result, msg="更新成功")


@DatasetRouter.delete("/delete", summary="删除数据集")
async def delete_dataset(
    ids: list[int],
    auth: AuthSchema = Depends(AuthPermission(["annotation:dataset:delete"])),
) -> JSONResponse:
    await DatasetService.delete_datasets(ids=ids, auth=auth)
    return SuccessResponse(msg="删除成功")


async def _run_purge_job(job_id: str, ids: list[int]) -> None:
    """后台彻底删除数据集并更新任务进度。"""
    from app.api.v1.module_annotation.dataset.import_jobs import get_job
    from app.core.logger import log

    job = get_job(job_id)
    if not job:
        return
    job.status = "running"
    job.phase = "delete"

    def _cb(processed: int, total: int, phase: str) -> None:
        job.processed = processed
        job.total = total
        job.phase = phase
        job.touch()

    try:
        await DatasetService.purge_datasets(ids=ids, progress_cb=_cb)
        job.status, job.phase = "done", "done"
    except Exception as e:  # noqa: BLE001
        log.warning(f"[彻底删除] 失败 job={job_id}: {e}")
        job.status, job.error = "failed", str(e)
    finally:
        job.touch()


@DatasetRouter.delete("/purge", summary="彻底删除数据集（后台任务，含对象存储，不可恢复）")
async def purge_dataset(
    ids: list[int],
    auth: AuthSchema = Depends(AuthPermission(["annotation:dataset:purge"])),
) -> JSONResponse:
    import asyncio

    from app.api.v1.module_annotation.dataset.import_jobs import create_job

    if not ids:
        return SuccessResponse(data={"job_id": None}, msg="没有需要删除的数据集")
    job = create_job(ids[0], auth.user.id, kind="purge")
    asyncio.create_task(_run_purge_job(job.job_id, ids))
    return SuccessResponse(data={"job_id": job.job_id}, msg="已开始删除")


@DatasetRouter.post("/{id}/upload", summary="上传图片")
async def upload_images(
    id: int,
    files: list[UploadFile] = File(...),
    auth: AuthSchema = Depends(AuthPermission(["annotation:dataset:create"])),
) -> JSONResponse:
    result = await DatasetService.upload_images(id, files, auth)
    msg = f"成功上传 {result['uploaded_count']} 张图片"
    if result["failed_count"]:
        msg += f"，{result['failed_count']} 张失败"
    return SuccessResponse(data=result, msg=msg)


@DatasetRouter.get("/{id}/images", summary="图片列表")
async def get_images(
    id: int,
    status: str | None = None,
    task_id: int | None = None,
    page_no: int = 1,
    page_size: int = 100,
    auth: AuthSchema = Depends(AuthPermission(["annotation:dataset:query"])),
) -> JSONResponse:
    images = await DatasetService.get_images(id, task_id, page_no, page_size)
    return SuccessResponse(data=images)


@DatasetRouter.get("/image/{image_id}/presigned-url", summary="获取图片访问链接")
async def get_presigned_url(
    image_id: int,
    auth: AuthSchema = Depends(AuthPermission(["annotation:workbench:query"])),
) -> JSONResponse:
    url = await DatasetService.get_presigned_url(image_id)
    return SuccessResponse(data={"url": url})


async def _run_import_job(
    job_id: str, data: bytes, dataset_id: int, user_id: int, clear_existing: bool = False
) -> None:
    """后台执行 x-anylabeling 导入并更新任务进度。"""
    from app.api.v1.module_annotation.dataset.import_jobs import get_job
    from app.api.v1.module_annotation.dataset.x_anylabeling_importer import (
        import_x_anylabeling_bytes,
    )
    from app.core.logger import log

    job = get_job(job_id)
    if not job:
        return
    job.status = "running"
    job.phase = "scan"

    def _cb(processed: int, total: int, phase: str) -> None:
        job.processed = processed
        job.total = total
        job.phase = phase
        job.touch()

    try:
        result = await import_x_anylabeling_bytes(
            data, dataset_id, user_id, progress_cb=_cb, clear_existing=clear_existing
        )
        job.imported = result.get("imported", 0)
        job.total_annotations = result.get("total_annotations", 0)
        job.task_id = result.get("task_id")
        job.task_name = result.get("task_name", "") or ""
        if result.get("error"):
            job.status, job.error = "failed", result["error"]
        else:
            job.status, job.phase = "done", "done"
    except Exception as e:  # noqa: BLE001 - 后台任务需吞掉异常并记录
        log.warning(f"[导入任务] 失败 job={job_id}: {e}")
        job.status, job.error = "failed", str(e)
    finally:
        job.touch()


@DatasetRouter.post("/{id}/import/x-anylabeling", summary="导入 x-anylabeling 标注（后台任务）")
async def import_x_anylabeling(
    id: int,
    file: UploadFile = File(...),
    clear_existing: bool = False,
    auth: AuthSchema = Depends(AuthPermission(["annotation:dataset:create"])),
) -> JSONResponse:
    import asyncio

    from app.api.v1.module_annotation.dataset.import_jobs import create_job
    from app.config.setting import settings
    from app.core.exceptions import CustomException

    filename = file.filename or ""
    if not filename.lower().endswith(".zip"):
        raise CustomException(msg="仅支持 .zip 文件", code=400, status_code=400)
    # 先物化上传字节，避免请求结束后 UploadFile 失效
    data = await file.read()
    max_bytes = settings.ANNOTATION_IMPORT_MAX_MB * 1024 * 1024
    if len(data) > max_bytes:
        raise CustomException(
            msg=f"文件过大（>{settings.ANNOTATION_IMPORT_MAX_MB}MB）",
            code=400, status_code=400,
        )
    job = create_job(id, auth.user.id, file_name=filename, file_size=len(data))
    asyncio.create_task(_run_import_job(job.job_id, data, id, auth.user.id, clear_existing))
    return SuccessResponse(data={"job_id": job.job_id}, msg="已开始导入")


@DatasetRouter.get("/import/{job_id}", summary="查询导入任务进度")
async def get_import_job(
    job_id: str,
    auth: AuthSchema = Depends(AuthPermission(["annotation:dataset:query"])),
) -> JSONResponse:
    from dataclasses import asdict

    from app.api.v1.module_annotation.dataset.import_jobs import get_job
    from app.core.exceptions import CustomException

    job = get_job(job_id)
    if not job:
        raise CustomException(msg="导入任务不存在", code=404, status_code=404)
    return SuccessResponse(data=asdict(job))
