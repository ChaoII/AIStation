
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.core.logger import log
from app.core.router_class import OperationLogRoute

from ..dataset.crud import image_crud

CollaborationRouter = APIRouter(route_class=OperationLogRoute, prefix="/collab", tags=["数据标注-实时协作"])

# 房间管理: {task_id: {user_id: WebSocket}}
_rooms: dict[int, dict[int, WebSocket]] = {}
# 图片锁: {image_id: user_id}
_image_locks: dict[int, int] = {}


@CollaborationRouter.websocket("/ws/{task_id}")
async def collaboration_ws(ws: WebSocket, task_id: int):
    await ws.accept()
    user_id = None
    try:
        data = await ws.receive_json()
        user_id = data.get("user_id")
        if not user_id:
            await ws.close(code=4000)
            return

        if task_id not in _rooms:
            _rooms[task_id] = {}
        _rooms[task_id][user_id] = ws

        # 通知房间其他用户
        await _broadcast(task_id, {"type": "user:join", "user": {"id": user_id}}, exclude=user_id)

        while True:
            data = await ws.receive_json()
            msg_type = data.get("type")

            if msg_type == "annotate:create":
                await _broadcast(task_id, {
                    "type": "annotate:create",
                    "user": {"id": user_id},
                    "data": data.get("data"),
                }, exclude=user_id)

            elif msg_type == "annotate:update":
                await _broadcast(task_id, {
                    "type": "annotate:update",
                    "user": {"id": user_id},
                    "data": data.get("data"),
                }, exclude=user_id)

            elif msg_type == "annotate:delete":
                await _broadcast(task_id, {
                    "type": "annotate:delete",
                    "user": {"id": user_id},
                    "data": data.get("data"),
                }, exclude=user_id)

            elif msg_type == "image:lock":
                image_id = data.get("image_id")
                if image_id and image_id not in _image_locks:
                    _image_locks[image_id] = user_id
                    await image_crud.update(id=image_id, data={"locked_by": user_id})
                    await _broadcast(task_id, {
                        "type": "image:lock",
                        "user": {"id": user_id},
                        "image_id": image_id,
                    })
                elif image_id and _image_locks.get(image_id) == user_id:
                    pass
                else:
                    await ws.send_json({
                        "type": "image:lock:denied",
                        "image_id": image_id,
                        "locked_by": _image_locks.get(image_id),
                    })

            elif msg_type == "image:unlock":
                image_id = data.get("image_id")
                if image_id and _image_locks.get(image_id) == user_id:
                    _image_locks.pop(image_id, None)
                    await image_crud.update(id=image_id, data={"locked_by": None, "locked_at": None})
                    await _broadcast(task_id, {
                        "type": "image:unlock",
                        "user": {"id": user_id},
                        "image_id": image_id,
                    })

            elif msg_type == "image:focus":
                await _broadcast(task_id, {
                    "type": "image:focus",
                    "user": {"id": user_id},
                    "image_id": data.get("image_id"),
                }, exclude=user_id)

    except WebSocketDisconnect:
        pass
    except Exception as e:
        log.error(f"协作WS错误: {e}")
    finally:
        if task_id in _rooms and user_id in _rooms[task_id]:
            del _rooms[task_id][user_id]
            await _broadcast(task_id, {"type": "user:leave", "user": {"id": user_id}})
            # 释放该用户的所有锁
            for img_id, uid in list(_image_locks.items()):
                if uid == user_id:
                    _image_locks.pop(img_id, None)
                    await image_crud.update(id=img_id, data={"locked_by": None, "locked_at": None})


async def _broadcast(task_id: int, msg: dict, exclude: int | None = None):
    if task_id not in _rooms:
        return
    for uid, ws in list(_rooms[task_id].items()):
        if uid == exclude:
            continue
        try:
            await ws.send_json(msg)
        except Exception:
            pass
