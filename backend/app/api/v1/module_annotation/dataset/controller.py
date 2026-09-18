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


@DatasetRouter.delete("/purge", summary="彻底删除数据集（含对象存储，不可恢复）")
async def purge_dataset(
    ids: list[int],
    auth: AuthSchema = Depends(AuthPermission(["annotation:dataset:purge"])),
) -> JSONResponse:
    result = await DatasetService.purge_datasets(ids=ids)
    return SuccessResponse(data=result, msg="已彻底删除")


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


@DatasetRouter.post("/import/x-anylabeling", summary="导入 x-anylabeling 格式标注")
async def import_x_anylabeling(
    dataset_id: int,
    file: UploadFile = File(...),
    auth: AuthSchema = Depends(AuthPermission(["annotation:dataset:create"])),
) -> JSONResponse:
    from .x_anylabeling_importer import import_x_anylabeling_zip
    result = await import_x_anylabeling_zip(file.file, dataset_id, auth.user.id)
    if result.get("error"):
        return SuccessResponse(data=result, msg=result["error"])
    return SuccessResponse(
        data=result,
        msg=f"导入完成：{result['imported']} 张图片，{result['total_annotations']} 个标注"
    )
