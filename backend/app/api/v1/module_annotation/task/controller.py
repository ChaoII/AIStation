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
    page: PaginationQueryParam = Depends(),
    auth: AuthSchema = Depends(AuthPermission(["annotation:task:query"])),
) -> JSONResponse:
    from app.core.database import async_db_session

    from .crud import TaskCRUD
    crud = TaskCRUD(auth=auth)
    offset = (page.page_no - 1) * page.page_size
    result = await crud.page(
        offset=offset, limit=page.page_size, order_by=page.order_by,
        search={}, out_schema=TaskOutSchema,
    )
    # Enrich each task with per-task calculated progress and assignee names
    if result.get("items"):
        async with async_db_session() as db:
            from sqlalchemy import select

            from app.api.v1.module_system.user.model import UserModel
            for item in result["items"]:
                prog = await TaskService._calc_progress(db, item["id"], item["dataset_id"])
                item["progress"] = prog["progress"]
                # Resolve assignee IDs to display names
                aids = item.get("assignees") or []
                if aids:
                    users = await db.execute(
                        select(UserModel).where(UserModel.id.in_(aids))
                    )
                    name_map = {u.id: u.name for u in users.scalars()}
                    item["assignees"] = [name_map.get(uid, f"用户{uid}") for uid in aids]
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
    return SuccessResponse(data=result)
