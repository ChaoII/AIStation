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
    from sqlalchemy import select

    from app.core.database import async_db_session

    from ..task.model import AnnotationTaskModel
    from .crud import DatasetCRUD
    crud = DatasetCRUD(auth=auth)
    offset = (page.page_no - 1) * page.page_size
    result = await crud.page(
        offset=offset, limit=page.page_size, order_by=page.order_by,
        search=search.get_conditions(), out_schema=DatasetOutSchema,
    )
    # Populate task_count and task list for each dataset
    if result.get("items"):
        async with async_db_session() as db:
            for item in result["items"]:
                tasks_result = await db.execute(
                    select(AnnotationTaskModel).where(AnnotationTaskModel.dataset_id == item["id"])
                )
                task_rows = tasks_result.scalars().all()
                item["task_count"] = len(task_rows)
                item["tasks"] = []
                for t in task_rows:
                    from app.api.v1.module_annotation.task.service import TaskService
                    try:
                        prog = await TaskService._calc_progress(db, t.id, t.dataset_id)
                        t.progress = prog["progress"]
                        t.status = prog["status"]
                        # Cache to DB
                        try:
                            await TaskService.update_progress(t.id)
                        except Exception:
                            pass
                    except Exception:
                        pass
                    item["tasks"].append({
                        "id": t.id, "name": t.name, "task_type": t.task_type,
                        "status": t.status, "progress": t.progress,
                    })
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
    from .crud import DatasetCRUD
    crud = DatasetCRUD(auth=auth)
    await crud.delete(ids=ids)
    return SuccessResponse(msg="删除成功")


@DatasetRouter.post("/{id}/upload", summary="上传图片")
async def upload_images(
    id: int,
    files: list[UploadFile] = File(...),
    auth: AuthSchema = Depends(AuthPermission(["annotation:dataset:create"])),
) -> JSONResponse:
    results = await DatasetService.upload_images(id, files, auth)
    return SuccessResponse(data=results, msg=f"成功上传 {len(results)} 张图片")


@DatasetRouter.get("/{id}/images", summary="图片列表")
async def get_images(
    id: int,
    status: str | None = None,
    task_id: int | None = None,
    auth: AuthSchema = Depends(AuthPermission(["annotation:dataset:query"])),
) -> JSONResponse:
    images = await DatasetService.get_images(id, task_id)
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
