import json
import logging

from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect
from starlette.websockets import WebSocketState

from app.api.v1.module_system.auth.schema import AuthSchema
from app.core.dependencies import get_current_user_ws

log = logging.getLogger(__name__)

AlarmWSRouter = APIRouter(prefix="/alarm", tags=["告警WebSocket"])


class AlarmWSManager:
    def __init__(self):
        self._connections: set[WebSocket] = set()

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        self._connections.add(ws)
        log.info("Alarm WS connected: %s (total: %d)", ws.client, len(self._connections))

    def disconnect(self, ws: WebSocket) -> None:
        self._connections.discard(ws)
        log.info("Alarm WS disconnected (total: %d)", len(self._connections))

    async def broadcast(self, data: dict) -> None:
        dead: list[WebSocket] = []
        for ws in self._connections:
            try:
                if ws.client_state == WebSocketState.CONNECTED:
                    await ws.send_json(data)
                else:
                    dead.append(ws)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self._connections.discard(ws)

    @property
    def count(self) -> int:
        return len(self._connections)


alarm_manager = AlarmWSManager()


@AlarmWSRouter.websocket("/ws")
async def alarm_ws_endpoint(
    websocket: WebSocket,
    auth: AuthSchema = Depends(get_current_user_ws),
):
    await alarm_manager.connect(websocket)
    try:
        while True:
            data = await websocket.receive_text()
            try:
                msg = json.loads(data)
                if msg.get("type") == "ping":
                    await websocket.send_json({"type": "pong"})
            except json.JSONDecodeError:
                await websocket.send_json({"type": "error", "message": "invalid json"})
    except WebSocketDisconnect:
        pass
    except Exception as e:
        log.warning("Alarm WS error: %s", e)
    finally:
        alarm_manager.disconnect(websocket)
