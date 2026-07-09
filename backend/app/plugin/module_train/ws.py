from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect

WS_Train = APIRouter(prefix="/train", tags=["训练WebSocket"])

# Train logs
_train_ws_clients: dict[int, list[WebSocket]] = {}


async def broadcast_log(task_id: int, line: str):
    for ws in _train_ws_clients.get(task_id, [])[:]:
        try:
            await ws.send_text(line)
        except Exception:
            _train_ws_clients[task_id].remove(ws)


@WS_Train.websocket("/ws/train/logs")
async def train_log_ws(websocket: WebSocket, task_id: int = Query(...)):
    await websocket.accept()
    _train_ws_clients.setdefault(task_id, []).append(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        if task_id in _train_ws_clients:
            _train_ws_clients[task_id].remove(websocket)
            if not _train_ws_clients[task_id]:
                del _train_ws_clients[task_id]


# Eval logs
_eval_ws_clients: dict[int, list[WebSocket]] = {}


async def broadcast_eval_log(eval_id: int, line: str):
    for ws in _eval_ws_clients.get(eval_id, [])[:]:
        try:
            await ws.send_text(line)
        except Exception:
            _eval_ws_clients[eval_id].remove(ws)


@WS_Train.websocket("/ws/eval/logs")
async def eval_log_ws(websocket: WebSocket, eval_id: int = Query(...)):
    await websocket.accept()
    _eval_ws_clients.setdefault(eval_id, []).append(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        if eval_id in _eval_ws_clients:
            _eval_ws_clients[eval_id].remove(websocket)
            if not _eval_ws_clients[eval_id]:
                del _eval_ws_clients[eval_id]


# Predict logs
_predict_ws_clients: dict[int, list[WebSocket]] = {}


async def broadcast_predict_log(predict_id: int, line: str):
    for ws in _predict_ws_clients.get(predict_id, [])[:]:
        try:
            await ws.send_text(line)
        except Exception:
            _predict_ws_clients[predict_id].remove(ws)


@WS_Train.websocket("/ws/predict/logs")
async def predict_log_ws(websocket: WebSocket, predict_id: int = Query(...)):
    await websocket.accept()
    _predict_ws_clients.setdefault(predict_id, []).append(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        if predict_id in _predict_ws_clients:
            _predict_ws_clients[predict_id].remove(websocket)
            if not _predict_ws_clients[predict_id]:
                del _predict_ws_clients[predict_id]
