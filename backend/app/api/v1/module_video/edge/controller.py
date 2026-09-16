import asyncio
import json
import logging
from typing import Annotated

from fastapi import APIRouter, Body, Depends, Path, Query, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse, Response

from app.api.v1.module_system.auth.schema import AuthSchema
from app.common.request import PaginationService
from app.common.response import SuccessResponse
from app.config.setting import settings
from app.core.base_params import PaginationQueryParam
from app.core.dependencies import AuthPermission
from app.core.exceptions import CustomException
from app.core.router_class import OperationLogRoute
from app.core.validator import DateTimeStr

from . import event_bus
from .param import EdgeQueryParam
from .schema import EdgeDeviceCreateSchema, EdgeDeviceUpdateSchema
from .service import EdgeService

log = logging.getLogger(__name__)

EdgeRouter = APIRouter(route_class=OperationLogRoute, prefix="/edge", tags=["边缘设备"])


def edge_event_query_param(
    camera_id: Annotated[int | None, Query(description="相机ID")] = None,
    task_id: Annotated[int | None, Query(description="布控任务ID")] = None,
    algorithm_type: Annotated[str | None, Query(description="场景码")] = None,
    matched: Annotated[bool | None, Query(description="是否命中规则")] = None,
    start_time: Annotated[DateTimeStr | None, Query(description="事件起始时间（含）")] = None,
    end_time: Annotated[DateTimeStr | None, Query(description="事件结束时间（含）")] = None,
    keyword: Annotated[str | None, Query(description="目标 label/文本模糊")] = None,
) -> dict:
    """边缘事件列表查询参数（独立依赖，与设备查询参数区分语义）。"""
    return {
        "camera_id": camera_id,
        "task_id": task_id,
        "algorithm_type": algorithm_type,
        "matched": matched,
        "start_time": start_time,
        "end_time": end_time,
        "keyword": keyword,
    }


@EdgeRouter.get("/list", summary="查询边缘设备列表")
async def get_edge_list_controller(
    page: PaginationQueryParam = Depends(),
    search: EdgeQueryParam = Depends(),
    auth: AuthSchema = Depends(AuthPermission(["module_video:edge:query"])),
) -> JSONResponse:
    result_list = await EdgeService.get_edge_list_service(search=search, auth=auth, order_by=page.order_by)
    result = await PaginationService.paginate(data_list=result_list, page_no=page.page_no, page_size=page.page_size)
    return SuccessResponse(data=result, msg="查询成功")


@EdgeRouter.get("/detail/{id}", summary="查询边缘设备详情")
async def get_edge_detail_controller(
    id: int = Path(..., description="边缘设备ID"),
    auth: AuthSchema = Depends(AuthPermission(["module_video:edge:query"])),
) -> JSONResponse:
    result = await EdgeService.get_edge_detail_service(id=id, auth=auth)
    return SuccessResponse(data=result, msg="查询成功")


@EdgeRouter.get("/event/list", summary="查询边缘事件列表")
async def get_edge_event_list_controller(
    page: Annotated[PaginationQueryParam, Depends()],
    search: Annotated[dict, Depends(edge_event_query_param)],
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_video:edge:query"]))],
) -> JSONResponse:
    result = await EdgeService.get_edge_event_page_service(
        auth=auth,
        page_no=page.page_no,
        page_size=page.page_size,
        order_by=page.order_by,
        **search,
    )
    return SuccessResponse(data=result, msg="查询成功")


@EdgeRouter.get("/event/detail/{id}", summary="查询边缘事件详情")
async def get_edge_event_detail_controller(
    id: Annotated[int, Path(description="边缘事件ID")],
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_video:edge:query"]))],
) -> JSONResponse:
    result = await EdgeService.get_edge_event_detail_service(id=id, auth=auth)
    return SuccessResponse(data=result, msg="查询成功")


@EdgeRouter.post("/create", summary="创建边缘设备")
async def create_edge_controller(
    data: EdgeDeviceCreateSchema,
    auth: AuthSchema = Depends(AuthPermission(["module_video:edge:create"])),
) -> JSONResponse:
    result = await EdgeService.create_edge_service(data=data, auth=auth)
    return SuccessResponse(data=result, msg="创建成功")


@EdgeRouter.put("/update/{id}", summary="修改边缘设备")
async def update_edge_controller(
    data: EdgeDeviceUpdateSchema,
    id: int = Path(..., description="边缘设备ID"),
    auth: AuthSchema = Depends(AuthPermission(["module_video:edge:update"])),
) -> JSONResponse:
    result = await EdgeService.update_edge_service(id=id, data=data, auth=auth)
    return SuccessResponse(data=result, msg="修改成功")


@EdgeRouter.delete("/delete", summary="删除边缘设备")
async def delete_edge_controller(
    ids: list[int] = Body(..., description="ID列表"),
    auth: AuthSchema = Depends(AuthPermission(["module_video:edge:delete"])),
) -> JSONResponse:
    await EdgeService.delete_edge_service(ids=ids, auth=auth)
    return SuccessResponse(msg="删除成功")


@EdgeRouter.post("/heartbeat", summary="边缘设备心跳/能力上报")
async def edge_heartbeat_controller(
    body: dict = Body(..., description="心跳/能力上报"),
) -> JSONResponse:
    # fail-closed：未配置共享密钥时拒绝心跳，避免任意伪造设备上报（凭据为空同样拒绝）
    token = (settings.EDGE_CONTROL_TOKEN or "").strip()
    if not token:
        raise CustomException(msg="边缘心跳未配置共享密钥，已拒绝", code=403, status_code=403)
    if body.get("token") != token:
        raise CustomException(msg="无效的设备凭证", code=403, status_code=403)
    await EdgeService.heartbeat(body)
    return SuccessResponse(msg="ok")


@EdgeRouter.get("/{device_id}/tasks/{task_id}/snapshot", summary="边缘任务快照预览")
async def get_edge_task_snapshot_controller(
    device_id: int = Path(..., description="边缘设备ID"),
    task_id: int = Path(..., description="布控任务ID"),
    auth: AuthSchema = Depends(AuthPermission(["module_video:algorithm:query"])),
) -> Response:
    content = await EdgeService.get_task_snapshot_service(device_id=device_id, task_id=task_id, auth=auth)
    return Response(content=content, media_type="image/jpeg", headers={"Cache-Control": "no-store"})


async def verify_edge_event_ws_token(token: str | None, websocket: WebSocket) -> bool:
    """严格校验边缘事件 WS token，与 HTTP 路径同强度（fail-closed）。

    校验内容：非空 → JWT 签名 + 过期时间（exp 必填）+ 签发者（iss）→
    非 refresh token → Redis 在线会话 → 用户存在且未停用。
    任一环节失败或 Redis 不可用均返回 False（拒绝连接），不做弱化放行。
    """
    if not token or not token.strip():
        return False

    redis = getattr(websocket.app.state, "redis", None)
    if redis is None:
        # 无法校验在线会话 → 直接拒绝，避免仅凭签名放行
        return False

    from app.core.database import async_db_session
    from app.core.dependencies import _verify_token

    try:
        async with async_db_session() as db:
            await _verify_token(token.strip(), db, redis)
        return True
    except Exception:  # noqa: BLE001 - 任何校验失败都视为未通过鉴权
        return False


async def _forward_pubsub(websocket: WebSocket, pubsub) -> None:
    """把 Redis 频道消息（``{"type":"event","data":...}``）转发给前端。"""
    async for message in pubsub.listen():
        if message.get("type") != "message":
            continue
        data = message.get("data")
        if isinstance(data, (bytes, bytearray)):
            data = data.decode("utf-8", errors="ignore")
        try:
            payload = json.loads(data) if isinstance(data, str) else data
        except (ValueError, TypeError):
            continue
        if isinstance(payload, dict):
            await websocket.send_json(payload)
        elif data is not None:
            await websocket.send_text(str(data))


async def _forward_queue(websocket: WebSocket, queue: asyncio.Queue) -> None:
    """把进程内降级队列消息转发给前端。"""
    while True:
        await websocket.send_json(await queue.get())


async def _detect_disconnect(websocket: WebSocket) -> None:
    """感知客户端断开：纯推送连接不主动收消息，用 receive 任务兜底。

    循环读取以忽略客户端上行报文（如 ping），仅在真正 disconnect 时返回。
    """
    while True:
        message = await websocket.receive()
        if message.get("type") == "websocket.disconnect":
            return


async def edge_event_ws_controller(websocket: WebSocket) -> None:
    """边缘事件实时推送：query token 鉴权，失败以 4401 关闭。

    浏览器 WS 无法携带自定义头，故 token 走 query 参数。连接后订阅 Redis 频道
    ``ai:edge:event``（Redis 不可用降级进程内广播），把落库事件详情原样转发。
    """
    token = websocket.query_params.get("token")
    if not await verify_edge_event_ws_token(token, websocket):
        await websocket.close(code=4401)
        return

    # 复用应用级 Redis 连接（多进程安全）；Redis 不可用时降级进程内队列
    app_redis = getattr(websocket.app.state, "redis", None)
    if app_redis is not None:
        event_bus.set_redis(app_redis)
    redis = await event_bus.get_redis()

    pubsub = None
    queue = None
    if redis is not None:
        pubsub = redis.pubsub()
        await pubsub.subscribe(event_bus.EDGE_EVENT_CHANNEL)
    else:
        queue = event_bus.subscribe_local()

    # 先订阅再 accept：客户端握手成功即代表订阅就绪，避免漏掉首条事件
    await websocket.accept()

    forward = asyncio.create_task(
        _forward_pubsub(websocket, pubsub)
        if pubsub is not None
        else _forward_queue(websocket, queue)
    )
    disconnected = asyncio.create_task(_detect_disconnect(websocket))

    try:
        done, pending = await asyncio.wait(
            {forward, disconnected}, return_when=asyncio.FIRST_COMPLETED
        )
        for task in pending:
            task.cancel()
        # 等待取消落地，避免悬挂任务
        await asyncio.gather(*pending, return_exceptions=True)
        for task in done:
            if task.cancelled():
                continue
            exc = task.exception()
            if exc is not None and not isinstance(exc, WebSocketDisconnect):
                log.warning(f"边缘事件 WS 转发异常: {exc}")
    finally:
        for task in (forward, disconnected):
            if not task.done():
                task.cancel()
        # 注销订阅，禁止泄漏
        if queue is not None:
            event_bus.unsubscribe_local(queue)
        if pubsub is not None:
            try:
                await pubsub.unsubscribe(event_bus.EDGE_EVENT_CHANNEL)
                await pubsub.aclose()
            except Exception:  # noqa: BLE001 - 清理失败不影响连接关闭
                pass


# 注册为 Starlette 原生 WS 路由：video_router 的 HTTP 限流依赖（RateLimiter 需要 Request）
# 在 WS 作用域解析会失败，而原生 WebSocketRoute 在 include_router 时不继承该依赖。
# 代价是原生路由不烘焙 APIRouter 前缀，故这里按最终挂载路径写全（root_path 为 /api/v1）。
def _register_edge_event_ws() -> None:
    from app.api.v1.module_video import video_router

    video_router.add_websocket_route(
        f"{video_router.prefix}/edge/event/ws",
        edge_event_ws_controller,
        name="edge_event_ws",
    )


_register_edge_event_ws()
