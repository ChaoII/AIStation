from fastapi import APIRouter, Depends, Body, UploadFile, File
from app.common.response import SuccessResponse
from app.core.dependencies import AuthPermission
from app.api.v1.module_system.auth.schema import AuthSchema
from .schema import (
    TrainModelCreateSchema, TrainTaskCreateSchema,
    TrainEvalCreateSchema, TrainPredictCreateSchema, DatasetExportSchema
)
from .service import TrainService
from .scheduler import start_training
from .eval_scheduler import start_evaluation, stop_evaluation
from .predict_executor import start_prediction, stop_prediction

router = APIRouter(tags=["模型训练"])


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


@router.post("/task/{task_id}/start", summary="开始训练")
async def start_task(task_id: int, auth: AuthSchema = Depends(AuthPermission(["module_train:task:update"]))):
    try:
        await start_training(task_id)
        return SuccessResponse(data={"id": task_id}, msg="训练已开始")
    except Exception as e:
        from app.common.response import ErrorResponse
        return ErrorResponse(msg=str(e))


@router.delete("/task/delete", summary="删除训练任务")
async def delete_task(ids: list[int] = Body(...), auth: AuthSchema = Depends(AuthPermission(["module_train:task:delete"]))):
    await TrainService.delete_tasks(ids)
    return SuccessResponse(msg="删除成功")


@router.post("/eval/create", summary="创建评估任务")
async def create_eval(data: TrainEvalCreateSchema, auth: AuthSchema = Depends(AuthPermission(["module_train:eval:create"]))):
    result = await TrainService.create_eval(data, auth)
    return SuccessResponse(data=result, msg="评估任务已创建")


@router.get("/eval/{eval_id}/detail", summary="评估详情")
async def get_eval(eval_id: int, auth: AuthSchema = Depends(AuthPermission(["module_train:eval:query"]))):
    data = await TrainService.get_eval(eval_id)
    return SuccessResponse(data=data)


@router.post("/eval/{eval_id}/start", summary="开始评估")
async def start_eval(eval_id: int, auth: AuthSchema = Depends(AuthPermission(["module_train:eval:create"]))):
    await start_evaluation(eval_id)
    return SuccessResponse(data={"id": eval_id}, msg="评估已开始")


@router.post("/eval/{eval_id}/stop", summary="停止评估")
async def stop_eval(eval_id: int, auth: AuthSchema = Depends(AuthPermission(["module_train:eval:create"]))):
    await stop_evaluation(eval_id)
    return SuccessResponse(data={"id": eval_id}, msg="评估已停止")


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


@router.post("/predict/create", summary="创建预测任务")
async def create_predict(data: TrainPredictCreateSchema, auth: AuthSchema = Depends(AuthPermission(["module_train:predict:create"]))):
    result = await TrainService.create_predict(data, auth)
    return SuccessResponse(data=result, msg="预测任务已创建")


@router.get("/predict/list", summary="预测任务列表")
async def list_predicts(auth: AuthSchema = Depends(AuthPermission(["module_train:predict:query"]))):
    data = await TrainService.list_predicts()
    return SuccessResponse(data=data)


@router.get("/predict/{predict_id}/detail", summary="预测详情")
async def get_predict(predict_id: int, auth: AuthSchema = Depends(AuthPermission(["module_train:predict:query"]))):
    data = await TrainService.get_predict(predict_id)
    return SuccessResponse(data=data)


@router.post("/predict/{predict_id}/start", summary="开始预测")
async def start_predict(predict_id: int, auth: AuthSchema = Depends(AuthPermission(["module_train:predict:create"]))):
    await start_prediction(predict_id)
    return SuccessResponse(data={"id": predict_id}, msg="预测已开始")


@router.post("/predict/{predict_id}/stop", summary="停止预测")
async def stop_predict(predict_id: int, auth: AuthSchema = Depends(AuthPermission(["module_train:predict:create"]))):
    await stop_prediction(predict_id)
    return SuccessResponse(data={"id": predict_id}, msg="预测已停止")


@router.delete("/predict/delete", summary="删除预测任务")
async def delete_predict(ids: list[int] = Body(...), auth: AuthSchema = Depends(AuthPermission(["module_train:predict:delete"]))):
    await TrainService.delete_predicts(ids)
    return SuccessResponse(msg="删除成功")


@router.post("/predict/upload", summary="上传预测图片")
async def upload_predict_images(files: list[UploadFile] = File(...), auth: AuthSchema = Depends(AuthPermission(["module_train:predict:create"]))):
    urls = await TrainService.upload_predict_images(files, auth)
    return SuccessResponse(data=urls, msg="上传成功")
