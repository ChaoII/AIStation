from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect, Query
from typing import Dict
from app.common.response import SuccessResponse
from app.core.dependencies import AuthPermission
from app.api.v1.module_system.auth.schema import AuthSchema
from .schema import TrainModelCreateSchema, TrainTaskCreateSchema, TrainEvalCreateSchema
from .service import TrainService

router = APIRouter(prefix="/train", tags=["模型训练"])

_ws_clients: Dict[int, list[WebSocket]] = {}


async def broadcast_log(task_id: int, line: str):
    for ws in _ws_clients.get(task_id, [])[:]:
        try:
            await ws.send_text(line)
        except Exception:
            _ws_clients[task_id].remove(ws)


@router.websocket("/ws/train/logs")
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


@router.get("/model/list", summary="模型仓库列表")
async def list_models(auth: AuthSchema = Depends(AuthPermission(["module_train:model:query"]))):
    data = await TrainService.list_models()
    return SuccessResponse(data=data)


@router.get("/model/detail/{model_id}", summary="模型详情")
async def get_model(model_id: int, auth: AuthSchema = Depends(AuthPermission(["module_train:model:query"]))):
    data = await TrainService.get_model(model_id)
    return SuccessResponse(data=data)


@router.post("/model/create", summary="创建模型记录")
async def create_model(data: TrainModelCreateSchema, auth: AuthSchema = Depends(AuthPermission(["module_train:model:create"]))):
    result = await TrainService.create_model(data, auth)
    return SuccessResponse(data=result)


@router.post("/task/create", summary="创建训练任务")
async def create_task(data: TrainTaskCreateSchema, auth: AuthSchema = Depends(AuthPermission(["module_train:task:create"]))):
    result = await TrainService.create_task(data, auth)
    return SuccessResponse(data=result, msg="训练任务已创建")


@router.get("/task/list", summary="训练任务列表")
async def list_tasks(auth: AuthSchema = Depends(AuthPermission(["module_train:task:query"]))):
    data = await TrainService.list_tasks()
    return SuccessResponse(data=data)


@router.get("/task/{task_id}/detail", summary="训练任务详情")
async def get_task(task_id: int, auth: AuthSchema = Depends(AuthPermission(["module_train:task:query"]))):
    data = await TrainService.get_task(task_id)
    return SuccessResponse(data=data)


@router.post("/task/{task_id}/stop", summary="停止训练")
async def stop_task(task_id: int, auth: AuthSchema = Depends(AuthPermission(["module_train:task:update"]))):
    result = await TrainService.stop_task(task_id)
    return SuccessResponse(data=result, msg="训练已停止")


@router.post("/eval/create", summary="创建评估任务")
async def create_eval(data: TrainEvalCreateSchema, auth: AuthSchema = Depends(AuthPermission(["module_train:eval:create"]))):
    result = await TrainService.create_eval(data, auth)
    return SuccessResponse(data=result, msg="评估任务已创建")


@router.get("/eval/list", summary="评估记录列表")
async def list_evals(model_repo_id: int, auth: AuthSchema = Depends(AuthPermission(["module_train:eval:query"]))):
    data = await TrainService.list_evals(model_repo_id)
    return SuccessResponse(data=data)
