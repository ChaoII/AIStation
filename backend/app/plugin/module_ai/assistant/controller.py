from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse, StreamingResponse

from app.api.v1.module_system.auth.schema import AuthSchema
from app.common.response import SuccessResponse
from app.core.dependencies import AuthPermission
from app.core.router_class import OperationLogRoute
from app.plugin.module_ai.overview.service import AiOverviewService

from .agno_service import run_agno_stream
from .schema import AssistantChatSchema, AssistantUIStreamSchema
from .service import run_assistant

AssistantRouter = APIRouter(
    route_class=OperationLogRoute, prefix="/assistant", tags=["AI-智能助手"]
)


@AssistantRouter.post("/chat", summary="AI 助手对话（工具调用）")
async def assistant_chat(
    data: AssistantChatSchema,
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:assistant:query"]))],
) -> JSONResponse:
    import time

    t0 = time.perf_counter()
    uid = getattr(getattr(auth, "user", None), "id", None)
    try:
        result = await run_assistant(data.message, auth, data.knowledge_ids)
    except Exception as e:
        await AiOverviewService.add_log(
            "assistant", "chat", int((time.perf_counter() - t0) * 1000), "error", str(e), user_id=uid
        )
        raise
    await AiOverviewService.add_log(
        "assistant", "chat", int((time.perf_counter() - t0) * 1000), "success", user_id=uid
    )
    return SuccessResponse(data=result, msg="成功")


@AssistantRouter.post("/stream", summary="AI 助手对话（Agno 原生事件流）")
async def assistant_stream(
    data: AssistantUIStreamSchema,
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:assistant:query"]))],
) -> StreamingResponse:

    from app.plugin.module_ai.assistant.agno_service import agno_stream_response

    async def _gen():
        try:
            uid = getattr(getattr(auth, "user", None), "id", None)
            async for item in run_agno_stream(
                messages=data.messages,
                auth=auth,
                user_id=uid,
                session_id=data.session_id,
                knowledge_ids=data.knowledge_ids,
                model_id=data.model_id,
                files=data.files,
            ):
                yield item
        except Exception:  # noqa: BLE001
            # 异常以 Agno 原生 error 帧透出，避免 SSE 悬空
            from app.plugin.module_ai.assistant.agno_service import agno_error_frame

            yield agno_error_frame("运行失败")

    return agno_stream_response(_gen())
