from fastapi import APIRouter, Depends, Query

from app.common.response import SuccessResponse
from app.core.dependencies import AuthPermission

from .service import NotificationService

NotificationRouter = APIRouter(prefix="/notification", tags=["通知中心"])


@NotificationRouter.get("/list", summary="我的通知列表")
async def list_notifications(
    page_no: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    auth=Depends(AuthPermission()),
):
    data = await NotificationService.list_notifications(auth.user.id, page_no, page_size)
    return SuccessResponse(data=data)


@NotificationRouter.get("/unread-count", summary="未读通知数")
async def unread_count(
    auth=Depends(AuthPermission()),
):
    count = await NotificationService.unread_count(auth.user.id)
    return SuccessResponse(data={"count": count})


@NotificationRouter.patch("/{notification_id}/read", summary="标记已读")
async def mark_read(
    notification_id: int,
    auth=Depends(AuthPermission()),
):
    ok = await NotificationService.mark_read(notification_id, auth.user.id)
    if ok:
        return SuccessResponse(msg="已标记已读")
    from app.common.response import ErrorResponse
    return ErrorResponse(msg="通知不存在")


@NotificationRouter.post("/read-all", summary="全部标记已读")
async def mark_all_read(
    auth=Depends(AuthPermission()),
):
    count = await NotificationService.mark_all_read(auth.user.id)
    return SuccessResponse(data={"count": count}, msg=f"已标记 {count} 条为已读")
