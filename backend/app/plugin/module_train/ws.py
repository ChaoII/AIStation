from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query

WS_Train = APIRouter(prefix="/train", tags=["训练WebSocket"])

_ws_clients: dict[int, list[WebSocket]] = {}


async def broadcast_log(task_id: int, line: str):
    for ws in _ws_clients.get(task_id, [])[:]:
        try:
            await ws.send_text(line)
        except Exception:
            _ws_clients[task_id].remove(ws)


@WS_Train.websocket("/ws/train/logs")
async def train_log_ws(websocket: WebSocket, task_id: int = Query(...)):
    await websocket.accept()
    _ws_clients.setdefault(task_id, []).append(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        if task_id in _ws_clients:
            _ws_clients[task_id].remove(websocket)
            if not _ws_clients[task_id]:
                del _ws_clients[task_id]
