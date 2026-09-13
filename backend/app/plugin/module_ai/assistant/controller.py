from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse, StreamingResponse

from app.api.v1.module_system.auth.schema import AuthSchema
from app.common.response import SuccessResponse
from app.core.dependencies import AuthPermission
from app.core.router_class import OperationLogRoute
from app.plugin.module_ai.overview.service import AiOverviewService

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
    import time

    t0 = time.perf_counter()
    uid = getattr(getattr(auth, "user", None), "id", None)
    try:
        result = await run_assistant(data.message, auth)
    except Exception as e:
        await AiOverviewService.add_log(
            "assistant", "chat", int((time.perf_counter() - t0) * 1000), "error", str(e), user_id=uid
        )
        raise
    await AiOverviewService.add_log(
        "assistant", "chat", int((time.perf_counter() - t0) * 1000), "success", user_id=uid
    )
    return SuccessResponse(data=result, msg="成功")


@AssistantRouter.post("/stream", summary="AI 助手对话（SSE 流式）")
async def assistant_stream(
    data: AssistantChatSchema,
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:assistant:query"]))],
) -> StreamingResponse:
    import time

    uid = getattr(getattr(auth, "user", None), "id", None)

    async def _gen():
        t0 = time.perf_counter()
        ok, err = True, None
        try:
            async for item in run_assistant_stream(data.message, auth):
                if isinstance(item, str) and "event: error" in item:
                    ok = False
                yield item
        except Exception as e:  # noqa: BLE001
            ok, err = False, str(e)
            raise
        finally:
            await AiOverviewService.add_log(
                "assistant",
                "chat",
                int((time.perf_counter() - t0) * 1000),
                "success" if ok else "error",
                err,
                user_id=uid,
            )

    return StreamingResponse(
        _gen(), media_type="text/event-stream", headers={"Cache-Control": "no-cache"}
    )
