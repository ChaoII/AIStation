from fastapi import APIRouter, Depends, Body, HTTPException
from app.common.response import SuccessResponse
from app.core.dependencies import AuthPermission
from app.api.v1.module_system.auth.schema import AuthSchema
from .schema import TrainModelCreateSchema, TrainTaskCreateSchema, TrainEvalCreateSchema, DatasetExportSchema
from .service import TrainService

router = APIRouter(tags=["模型训练"])

from .ws import broadcast_log


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


@router.delete("/model/delete", summary="删除模型")
async def delete_model(ids: list[int] = Body(...), auth: AuthSchema = Depends(AuthPermission(["module_train:model:delete"]))):
    await TrainService.delete_models(ids)
    return SuccessResponse(msg="删除成功")


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


@router.delete("/task/delete", summary="删除训练任务")
async def delete_task(ids: list[int] = Body(...), auth: AuthSchema = Depends(AuthPermission(["module_train:task:delete"]))):
    await TrainService.delete_tasks(ids)
    return SuccessResponse(msg="删除成功")


@router.post("/eval/create", summary="创建评估任务")
async def create_eval(data: TrainEvalCreateSchema, auth: AuthSchema = Depends(AuthPermission(["module_train:eval:create"]))):
    result = await TrainService.create_eval(data, auth)
    return SuccessResponse(data=result, msg="评估任务已创建")


@router.post("/dataset/export", summary="导出标注数据集")
async def export_dataset(data: DatasetExportSchema, auth: AuthSchema = Depends(AuthPermission(["annotation:dataset:query"]))):
    result = await TrainService.export_dataset(data, auth)
    return SuccessResponse(data=result, msg="数据集导出成功")


@router.get("/eval/list", summary="评估记录列表")
async def list_evals(model_repo_id: int, auth: AuthSchema = Depends(AuthPermission(["module_train:eval:query"]))):
    data = await TrainService.list_evals(model_repo_id)
    return SuccessResponse(data=data)


@router.get("/task/{task_id}/logs", summary="获取训练日志")
async def get_task_logs(task_id: int, auth: AuthSchema = Depends(AuthPermission(["module_train:task:query"]))):
    import os, tempfile
    log_path = os.path.join(tempfile.gettempdir(), "train_output", str(task_id), "train.log")
    if not os.path.exists(log_path):
        return SuccessResponse(data={"logs": "", "path": log_path})
    with open(log_path, "r", encoding="utf-8", errors="replace") as f:
        content = f.read()
    return SuccessResponse(data={"logs": content[-500000:]})


@router.delete("/eval/delete", summary="删除评估记录")
async def delete_eval(ids: list[int] = Body(...), auth: AuthSchema = Depends(AuthPermission(["module_train:eval:delete"]))):
    await TrainService.delete_evals(ids)
    return SuccessResponse(msg="删除成功")
