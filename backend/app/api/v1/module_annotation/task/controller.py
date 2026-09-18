from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from app.api.v1.module_system.auth.schema import AuthSchema
from app.common.response import SuccessResponse
from app.core.base_params import PaginationQueryParam
from app.core.dependencies import AuthPermission
from app.core.router_class import OperationLogRoute

from .schema import TaskCreateSchema, TaskOutSchema, TaskUpdateSchema
from .service import TaskService

TaskRouter = APIRouter(route_class=OperationLogRoute, prefix="/task", tags=["数据标注-任务"])


@TaskRouter.get("/list", summary="查询任务列表")
async def get_task_list(
    name: str | None = None,
    annotation_type: str | None = None,
    status: str | None = None,
    page: PaginationQueryParam = Depends(),
    auth: AuthSchema = Depends(AuthPermission(["annotation:task:query"])),
) -> JSONResponse:
    from app.core.database import async_db_session

    from .crud import TaskCRUD
    crud = TaskCRUD(auth=auth)
    offset = (page.page_no - 1) * page.page_size
    search: dict = {}
    if name:
        search["name"] = ("like", name)
    if annotation_type:
        search["task_type"] = annotation_type
    if status:
        search["status"] = status
    result = await crud.page(
        offset=offset, limit=page.page_size, order_by=page.order_by,
        search=search, out_schema=TaskOutSchema,
    )
    # 本页任务：单次聚合算进度/状态，一次查询用户与数据集名（只读不写，避免 N+1）
    items = result.get("items")
    if items:
        async with async_db_session() as db:
            from sqlalchemy import select

            from app.api.v1.module_annotation.dataset.model import DatasetModel
            from app.api.v1.module_system.user.model import UserModel

            prog_map = await TaskService._calc_progress_bulk(db, items)

            # 一次查询本页所有 assignees 用户 → id→name 映射
            all_aids = {uid for it in items for uid in (it.get("assignees") or [])}
            name_map: dict[int, str] = {}
            if all_aids:
                users = await db.execute(
                    select(UserModel.id, UserModel.name).where(UserModel.id.in_(all_aids))
                )
                name_map = dict(users.fetchall())

            # 一次查询本页所有数据集名 → id→name 映射
            all_ds = {it["dataset_id"] for it in items}
            ds_name_map: dict[int, str] = {}
            if all_ds:
                ds_rows = await db.execute(
                    select(DatasetModel.id, DatasetModel.name)
                    .where(DatasetModel.id.in_(all_ds))
                )
                ds_name_map = dict(ds_rows.fetchall())

            for item in items:
                prog = prog_map.get(item["id"], {})
                item["progress"] = prog.get("progress", 0)
                item["status"] = prog.get("status", "pending")
                aids = item.get("assignees") or []
                item["assignees"] = [name_map.get(uid, f"用户{uid}") for uid in aids]
                item["dataset_name"] = ds_name_map.get(
                    item["dataset_id"], f"数据集#{item['dataset_id']}"
                )
    return SuccessResponse(data=result)


@TaskRouter.post("/create", summary="创建任务")
async def create_task(
    data: TaskCreateSchema,
    auth: AuthSchema = Depends(AuthPermission(["annotation:task:create"])),
) -> JSONResponse:
    from .crud import TaskCRUD
    crud = TaskCRUD(auth=auth)
    task = await crud.create(data=data)
    if data.assignees:
        await TaskService.ensure_annotation_access(data.assignees)
    return SuccessResponse(data=task, msg="创建成功")


@TaskRouter.put("/update/{id}", summary="更新任务")
async def update_task(
    id: int,
    data: TaskUpdateSchema,
    auth: AuthSchema = Depends(AuthPermission(["annotation:task:update"])),
) -> JSONResponse:
    from .crud import TaskCRUD
    crud = TaskCRUD(auth=auth)
    result = await crud.update(id=id, data=data)
    if data.assignees:
        await TaskService.ensure_annotation_access(data.assignees)
    return SuccessResponse(data=result, msg="更新成功")


@TaskRouter.delete("/delete", summary="删除任务")
async def delete_task(
    ids: list[int],
    auth: AuthSchema = Depends(AuthPermission(["annotation:task:delete"])),
) -> JSONResponse:
    from datetime import datetime

    from sqlalchemy import update

    from app.api.v1.module_annotation.annotation.model import AnnotationRecordModel
    from app.core.database import async_db_session

    # CRUDBase.delete 仅软删任务行，这里补级联软删该任务下的标注记录
    actor_id = getattr(getattr(auth, "user", None), "id", None)
    async with async_db_session.begin() as db:
        await db.execute(
            update(AnnotationRecordModel)
            .where(AnnotationRecordModel.task_id.in_(ids))
            .values(is_deleted=True, deleted_time=datetime.now(), deleted_id=actor_id)
        )

    from .crud import TaskCRUD
    crud = TaskCRUD(auth=auth)
    await crud.delete(ids=ids)
    return SuccessResponse(msg="删除成功")


@TaskRouter.get("/{id}/progress", summary="任务进度")
async def get_task_progress(
    id: int,
    auth: AuthSchema = Depends(AuthPermission(["annotation:task:query"])),
) -> JSONResponse:
    progress = await TaskService.get_task_progress(id, auth)
    return SuccessResponse(data=progress)


@TaskRouter.get("/{id}/detail", summary="任务详情")
async def get_task_detail(
    id: int,
    auth: AuthSchema = Depends(AuthPermission(["annotation:task:query"])),
) -> JSONResponse:
    from .crud import TaskCRUD
    crud = TaskCRUD(auth=auth)
    result = await crud.get(id=id)
    if result:
        from app.core.database import async_db_session
        async with async_db_session() as db:
            prog = await TaskService._calc_progress(db, result.id, result.dataset_id)
            d = {c.name: getattr(result, c.name) for c in result.__table__.columns}
            d["progress"] = prog["progress"]
            d["status"] = prog["status"]
            from app.api.v1.module_annotation.dataset.model import DatasetModel
            ds = await db.get(DatasetModel, result.dataset_id)
            d["dataset_name"] = ds.name if ds else f"数据集#{result.dataset_id}"
        return SuccessResponse(data=d)
    return SuccessResponse(data=None)
