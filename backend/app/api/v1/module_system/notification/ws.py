from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect

from app.core.dependencies import get_current_user_ws

NotificationWSRouter = APIRouter(prefix="/system/ws", tags=["通知WebSocket"])

_notification_ws_clients: dict[int, list[WebSocket]] = {}


async def push_notification_ws(user_id: int, payload: dict):
    import json
    for ws in _notification_ws_clients.get(user_id, [])[:]:
        try:
            await ws.send_text(json.dumps(payload, ensure_ascii=False))
        except Exception:
            _notification_ws_clients[user_id].remove(ws)


@NotificationWSRouter.websocket("/ws/notification")
async def notification_ws(websocket: WebSocket, token: str = Query(...)):
    user = await get_current_user_ws(token)
    if not user:
        await websocket.close(code=4001)
        return
    await websocket.accept()
    user_id = user.id
    _notification_ws_clients.setdefault(user_id, []).append(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        if user_id in _notification_ws_clients:
            _notification_ws_clients[user_id].remove(websocket)
            if not _notification_ws_clients[user_id]:
                del _notification_ws_clients[user_id]
