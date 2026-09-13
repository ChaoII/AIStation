from typing import Annotated

from fastapi import APIRouter, Body, Depends, status
from fastapi.responses import JSONResponse

from app.api.v1.module_system.auth.schema import AuthSchema
from app.common.response import ErrorResponse, SuccessResponse
from app.core.dependencies import AuthPermission
from app.core.exceptions import CustomException
from app.core.router_class import OperationLogRoute

from .schema import AiSessionCreateSchema
from .service import AiSessionService

AiSessionRouter = APIRouter(route_class=OperationLogRoute, prefix="/sessions", tags=["AI-会话"])


def _ensure_session_owner(session: dict, auth: AuthSchema) -> None:
    """会话归属校验：user_id 已设置且非当前用户时按“不存在”拒绝（防 IDOR）。"""
    uid = getattr(getattr(auth, "user", None), "id", None)
    owner = session.get("user_id")
    if owner is not None and owner != uid:
        raise CustomException(msg="会话不存在", status_code=status.HTTP_404_NOT_FOUND)


@AiSessionRouter.get("/list", summary="会话列表")
async def list_sessions(
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:assistant:query"]))],
) -> JSONResponse:
    uid = getattr(getattr(auth, "user", None), "id", None)
    return SuccessResponse(data=await AiSessionService.list_sessions(uid), msg="查询成功")


@AiSessionRouter.get("/detail/{session_id}", summary="会话详情（含消息）")
async def get_session(
    session_id: int,
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:assistant:query"]))],
) -> JSONResponse:
    session = await AiSessionService.get_session(session_id)
    if not session:
        return ErrorResponse(msg="会话不存在")
    _ensure_session_owner(session, auth)
    session["messages"] = await AiSessionService.get_messages(session_id)
    return SuccessResponse(data=session, msg="查询成功")


@AiSessionRouter.post("/create", summary="新建会话")
async def create_session(
    data: AiSessionCreateSchema,
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:assistant:query"]))],
) -> JSONResponse:
    uid = getattr(getattr(auth, "user", None), "id", None)
    result = await AiSessionService.create(data.title, data.app_id, uid)
    return SuccessResponse(data=result, msg="创建成功")


@AiSessionRouter.delete("/delete", summary="删除会话")
async def delete_sessions(
    ids: Annotated[list[int], Body(description="ID列表")],
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:assistant:query"]))],
) -> JSONResponse:
    # 归属校验：任一 id 不属于当前用户即整体拒绝，避免越权删除
    for session_id in ids:
        session = await AiSessionService.get_session(session_id)
        if session:
            _ensure_session_owner(session, auth)
    await AiSessionService.delete(ids)
    return SuccessResponse(msg="删除成功")
