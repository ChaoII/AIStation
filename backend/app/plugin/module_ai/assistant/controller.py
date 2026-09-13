from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse, StreamingResponse

from app.api.v1.module_system.auth.schema import AuthSchema
from app.common.response import SuccessResponse
from app.core.dependencies import AuthPermission
from app.core.router_class import OperationLogRoute

from .schema import AssistantChatSchema
from .service import run_assistant, run_assistant_stream

AssistantRouter = APIRouter(
    route_class=OperationLogRoute, prefix="/assistant", tags=["AI-智能助手"]
)


@AssistantRouter.post("/chat", summary="AI 助手对话（工具调用）")
async def assistant_chat(
    data: AssistantChatSchema,
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:assistant:query"]))],
) -> JSONResponse:
    result = await run_assistant(data.message, auth)
    return SuccessResponse(data=result, msg="成功")


@AssistantRouter.post("/stream", summary="AI 助手对话（SSE 流式）")
async def assistant_stream(
    data: AssistantChatSchema,
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:assistant:query"]))],
) -> StreamingResponse:
    return StreamingResponse(
        run_assistant_stream(data.message, auth),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
