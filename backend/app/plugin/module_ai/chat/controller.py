from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from app.api.v1.module_system.auth.schema import AuthSchema
from app.common.response import ResponseSchema, SuccessResponse
from app.core.dependencies import AuthPermission
from app.core.logger import log
from app.core.router_class import OperationLogRoute

from .schema import AiChatRequestSchema, AiChatResponseSchema
from .service import ChatService

ChatRouter = APIRouter(route_class=OperationLogRoute, prefix="/chat", tags=["AI聊天会话管理"])


@ChatRouter.post(
    "/ai-chat",
    summary="AI 对话（非流式）",
    description="AI 对话接口，用于 AiAssistant 组件，返回完整响应。会话管理统一走 /sessions。",
    response_model=ResponseSchema[AiChatResponseSchema],
)
async def ai_chat_controller(
    data: AiChatRequestSchema,
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:chat:query"]))],
) -> JSONResponse:
    """AI 对话（非流式）"""
    result = await ChatService.chat_non_stream(
        message=data.message,
        session_id=data.session_id,
        auth=auth,
    )
    log.info(f"AI 对话成功 {result.get('session_id')}")
    return SuccessResponse(
        data=AiChatResponseSchema(
            response=result["response"],
            session_id=result["session_id"],
            function_calls=result.get("function_calls"),
            action=result.get("action"),
        ),
        msg="对话成功",
    )
