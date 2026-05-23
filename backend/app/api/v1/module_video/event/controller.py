from fastapi import APIRouter, Depends

from app.core.dependencies import AuthPermission
from app.api.v1.module_system.auth.schema import AuthSchema
from app.common.response import SuccessResponse as Success

EventRouter = APIRouter(prefix="/event", tags=["事件联动"])


@EventRouter.get("/list")
async def get_event_list(
    page: int = 1,
    page_size: int = 20,
    auth: AuthSchema = Depends(AuthPermission(["module_video:event:query"])),
):
    return Success(data={"items": [], "total": 0, "page": page, "page_size": page_size})


@EventRouter.get("/detail/{id}")
async def get_event_detail(
    id: int,
    auth: AuthSchema = Depends(AuthPermission(["module_video:event:query"])),
):
    return Success(data={})


@EventRouter.post("/create")
async def create_event(
    auth: AuthSchema = Depends(AuthPermission(["module_video:event:create"])),
):
    return Success()


@EventRouter.put("/update/{id}")
async def update_event(
    id: int,
    auth: AuthSchema = Depends(AuthPermission(["module_video:event:update"])),
):
    return Success()


@EventRouter.delete("/delete")
async def delete_event(
    auth: AuthSchema = Depends(AuthPermission(["module_video:event:delete"])),
):
    return Success()
