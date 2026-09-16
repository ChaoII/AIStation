"""标注实时协作 WebSocket（鉴权 + 在线列表 + DB 锁 + 事件转发）。

房间为进程内内存（当前单 worker 部署）；多 worker Redis 化为后续增强。
锁使用 ``AnnotationService.lock_image``（DB 持久 + 超时），避免历史 ``image_crud`` 空鉴权崩溃。
"""
import json

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect

from app.core.logger import log
from app.core.router_class import OperationLogRoute
from app.core.security import decode_access_token

from ..annotation.service import AnnotationService

CollaborationRouter = APIRouter(route_class=OperationLogRoute, prefix="/collab", tags=["数据标注-实时协作"])

# 房间: {task_id: {user_id: {"ws": WebSocket, "name": str}}}
_rooms: dict[int, dict[int, dict]] = {}


def parse_ws_user(token: str | None) -> tuple[int, str] | None:
    """校验 WS token 并返回 ``(user_id, user_name)``；无效返回 None。"""
    if not token:
        return None
    try:
        payload = decode_access_token(token)
        info = json.loads(payload.sub)
        user_id = int(info["user_id"])
        name = str(info.get("user_name") or user_id)
        return user_id, name
    except Exception:
        return None


def presence_list(task_id: int) -> list[dict]:
    """返回房间内在线的 ``[{"id", "name"}]``。"""
    return [
        {"id": uid, "name": v.get("name") or uid}
        for uid, v in _rooms.get(task_id, {}).items()
    ]


@CollaborationRouter.websocket("/ws/{task_id}")
async def collaboration_ws(ws: WebSocket, task_id: int, token: str | None = Query(None)):
    await ws.accept()
    parsed = parse_ws_user(token)
    if parsed is None:
        await ws.close(code=4001)
        return
    user_id, user_name = parsed

    try:
        _rooms.setdefault(task_id, {})[user_id] = {"ws": ws, "name": user_name}
        # 向新用户下发在线列表
        await ws.send_json({"type": "room:presence", "users": presence_list(task_id)})
        # 通知房间其他用户
        await _broadcast(
            task_id,
            {"type": "user:join", "user": {"id": user_id, "name": user_name}},
            exclude=user_id,
        )

        while True:
            data = await ws.receive_json()
            msg_type = data.get("type")
            user = {"id": user_id, "name": user_name}

            if msg_type in ("annotate:create", "annotate:update", "annotate:delete"):
                await _broadcast(
                    task_id,
                    {"type": msg_type, "user": user, "data": data.get("data")},
                    exclude=user_id,
                )

            elif msg_type == "image:focus":
                await _broadcast(
                    task_id,
                    {"type": "image:focus", "user": user, "image_id": data.get("image_id")},
                    exclude=user_id,
                )

            elif msg_type == "cursor:move":
                await _broadcast(
                    task_id,
                    {
                        "type": "cursor:move",
                        "user": user,
                        "image_id": data.get("image_id"),
                        "x": data.get("x"),
                        "y": data.get("y"),
                    },
                    exclude=user_id,
                )

            elif msg_type == "image:lock":
                image_id = data.get("image_id")
                if image_id:
                    result = await AnnotationService.lock_image(image_id, user_id)
                    if result.get("locked"):
                        await ws.send_json(
                            {
                                "type": "image:lock:denied",
                                "image_id": image_id,
                                "locked_by": result.get("locked_by"),
                            }
                        )
                    else:
                        await _broadcast(
                            task_id,
                            {"type": "image:lock", "user": user, "image_id": image_id},
                        )

            elif msg_type == "image:unlock":
                image_id = data.get("image_id")
                if image_id:
                    await AnnotationService.unlock_image(image_id, user_id)
                    await _broadcast(
                        task_id,
                        {"type": "image:unlock", "user": user, "image_id": image_id},
                    )

    except WebSocketDisconnect:
        pass
    except Exception as e:
        log.error(f"协作WS错误: {e}")
    finally:
        room = _rooms.get(task_id)
        if room and user_id in room:
            del room[user_id]
            if not room:
                _rooms.pop(task_id, None)
            await _broadcast(
                task_id,
                {"type": "user:leave", "user": {"id": user_id, "name": user_name}},
            )


async def _broadcast(task_id: int, msg: dict, exclude: int | None = None):
    room = _rooms.get(task_id)
    if not room:
        return
    for uid, info in list(room.items()):
        if uid == exclude:
            continue
        try:
            await info["ws"].send_json(msg)
        except Exception:
            pass
