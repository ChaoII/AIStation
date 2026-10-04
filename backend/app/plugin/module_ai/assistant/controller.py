from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse, StreamingResponse

from app.api.v1.module_system.auth.schema import AuthSchema
from app.common.response import SuccessResponse
from app.core.dependencies import AuthPermission
from app.core.router_class import OperationLogRoute
from app.plugin.module_ai.overview.service import AiOverviewService

from .schema import AssistantChatSchema, AssistantUIStreamSchema
from .service import run_assistant, run_assistant_ui_stream

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


@AssistantRouter.post("/stream", summary="AI 助手对话（AI SDK UI Message Stream）")
async def assistant_stream(
    data: AssistantUIStreamSchema,
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:assistant:query"]))],
) -> StreamingResponse:

    from app.plugin.module_ai.streaming import ui_stream_response

    async def _gen():
        try:
            async for item in run_assistant_ui_stream(
                data.messages, auth, data.session_id, data.knowledge_ids, data.model_id
            ):
                yield item
        except Exception:  # noqa: BLE001
            # 日志已在 run_assistant_ui_stream 的 finally 落库，这里仅透传异常
            raise

    return ui_stream_response(_gen())
