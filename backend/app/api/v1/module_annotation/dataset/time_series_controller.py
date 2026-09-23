"""时间序列接口 controller：上传/列表/详情/原始内容/锁定。

镜像 ``audio_controller.py`` 的结构与鉴权语义；上传因 ``TimeSeriesService.upload_time_series``
接受外部 ``db`` 会话（只 flush 不 commit），由控制器包裹 ``begin()`` 事务，
并在提交失败时补偿删除已上传的 RustFS 对象。
"""
from typing import Annotated

from fastapi import APIRouter, Depends, File, Query, UploadFile
from fastapi.responses import JSONResponse, Response

from app.api.v1.module_system.auth.schema import AuthSchema
from app.common.response import SuccessResponse
from app.core.database import async_db_session
from app.core.dependencies import AuthPermission
from app.core.router_class import OperationLogRoute

from .schema import (
    TimeSeriesListOutSchema,
    TimeSeriesOutSchema,
)
from .time_series_service import TimeSeriesService

TimeSeriesRouter = APIRouter(
    route_class=OperationLogRoute, prefix="/timeseries", tags=["数据标注-时间序列"]
)


@TimeSeriesRouter.post("/upload", summary="上传时间序列", response_model=TimeSeriesOutSchema)
async def upload_time_series(
    dataset_id: Annotated[int, Query(description="数据集ID")],
    file: Annotated[UploadFile, File(...)],
    auth: Annotated[AuthSchema, Depends(AuthPermission(["annotation:dataset:create"]))],
) -> JSONResponse:
    # TimeSeriesService.upload_time_series 接受外部 db 会话，内部仅 flush 不 commit；
    # 由本控制器包裹 begin() 事务，保证提交正常收口；提交失败则补偿删除对象。
    import asyncio

    from app.utils.s3_client import s3_client

    async with async_db_session() as db:
        object_key = None
        try:
            async with db.begin():
                series = await TimeSeriesService.upload_time_series(
                    db, dataset_id, file, auth
                )
                object_key = series.object_key
        except Exception:
            if object_key:
                try:
                    await asyncio.to_thread(s3_client.delete_object, object_key)
                except Exception as e2:  # noqa: BLE001
                    from app.core.logger import log
                    log.warning(f"[时间序列上传] 提交失败补偿删除对象失败: {e2}")
            raise
        return SuccessResponse(
            data=TimeSeriesService.series_out(series), msg="上传成功"
        )


@TimeSeriesRouter.get("/list", summary="查询数据集下的时间序列列表", response_model=TimeSeriesListOutSchema)
async def list_time_series(
    dataset_id: Annotated[int, Query(description="数据集ID")],
    auth: Annotated[AuthSchema, Depends(AuthPermission(["annotation:dataset:query"]))],
) -> JSONResponse:
    items = await TimeSeriesService.list_time_series(dataset_id)
    return SuccessResponse(data={"items": items})


@TimeSeriesRouter.get("/detail/{series_id}", summary="查询时间序列详情", response_model=TimeSeriesOutSchema)
async def time_series_detail(
    series_id: int,
    auth: Annotated[AuthSchema, Depends(AuthPermission(["annotation:dataset:query"]))],
) -> JSONResponse:
    series = await TimeSeriesService.get_time_series(series_id)
    return SuccessResponse(data=series)


@TimeSeriesRouter.get("/content/{series_id}", summary="获取时间序列原始 CSV 内容")
async def time_series_content(
    series_id: int,
    auth: Annotated[AuthSchema, Depends(AuthPermission(["annotation:dataset:query"]))],
) -> Response:
    content = await TimeSeriesService.get_content(series_id)
    return Response(content=content, media_type="text/csv")


@TimeSeriesRouter.post("/lock/{series_id}", summary="锁定时间序列")
async def lock_time_series(
    series_id: int,
    auth: Annotated[AuthSchema, Depends(AuthPermission(["annotation:dataset:query"]))],
) -> JSONResponse:
    result = await TimeSeriesService.lock_time_series(series_id, auth.user.id)
    return SuccessResponse(data=result)


@TimeSeriesRouter.post("/unlock/{series_id}", summary="解锁时间序列")
async def unlock_time_series(
    series_id: int,
    auth: Annotated[AuthSchema, Depends(AuthPermission(["annotation:dataset:query"]))],
) -> JSONResponse:
    await TimeSeriesService.unlock_time_series(series_id, auth.user.id)
    return SuccessResponse()
