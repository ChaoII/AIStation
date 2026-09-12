import os
import tempfile
from typing import Annotated

from fastapi import APIRouter, Body, Depends, File, Query, UploadFile

from app.api.v1.module_system.auth.schema import AuthSchema
from app.common.response import SuccessResponse
from app.core.dependencies import AuthPermission
from app.utils.s3_client import s3_client

from .eval_scheduler import start_evaluation, stop_evaluation
from .predict_executor import start_prediction, stop_prediction
from .scheduler import start_training
from .schema import (
    DatasetExportSchema,
    ModelExportSchema,
    ModelUpdateSchema,
    TrainDeployCreateSchema,
    TrainEvalCreateSchema,
    TrainModelCreateSchema,
    TrainPredictCreateSchema,
    TrainScheduleCreateSchema,
    TrainScheduleUpdateSchema,
    TrainTaskCreateSchema,
    TrainTaskUpdateSchema,
)
from .service import TrainService

router = APIRouter(tags=["模型训练"])


@router.get("/system/tempdir", summary="系统临时目录路径", include_in_schema=False)
async def get_tempdir():
    return SuccessResponse(data={"tempdir": tempfile.gettempdir().replace("\\", "/")})


@router.get("/model/list", summary="模型仓库列表")
async def list_models(
    name: str | None = Query(None),
    framework: str | None = Query(None),
    page_no: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    auth: AuthSchema = Depends(AuthPermission(["module_train:model:query"])),
):
    data, total = await TrainService.list_models({
        "name": name,
        "framework": framework,
        "page_no": page_no,
        "page_size": page_size,
    })
    return SuccessResponse(data={
        "items": data, "total": total,
        "page_no": page_no, "page_size": page_size,
        "has_next": page_no * page_size < total,
    })


@router.get("/model/repos", summary="模型仓库列表")
async def list_model_repos(
    name: str | None = Query(None),
    framework: str | None = Query(None),
    page_no: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    auth: AuthSchema = Depends(AuthPermission(["module_train:model:query"])),
):
    data, total = await TrainService.list_model_repos({
        "name": name, "framework": framework, "page_no": page_no, "page_size": page_size,
    })
    return SuccessResponse(data={
        "items": data, "total": total,
        "page_no": page_no, "page_size": page_size,
        "has_next": page_no * page_size < total,
    })


@router.post("/model/repos", summary="创建模型仓库（含首个版本）")
async def create_repo(
    data: TrainModelCreateSchema = Body(...),
    auth: AuthSchema = Depends(AuthPermission(["module_train:model:create"])),
):
    result = await TrainService.create_model_repo(data, auth)
    return SuccessResponse(data=result, msg="创建成功")


@router.delete("/model/repos", summary="删除模型仓库（级联删除版本）")
async def delete_repos(
    ids: list[int] = Body(...),
    auth: AuthSchema = Depends(AuthPermission(["module_train:model:delete"])),
):
    await TrainService.delete_model_repos(ids)
    return SuccessResponse(msg="删除成功")


@router.put("/model/repos/{repo_id}", summary="更新模型仓库")
async def update_repo(
    repo_id: int,
    data: Annotated[dict, Body()],
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_train:model:update"]))],
):
    result = await TrainService.update_model_repo(repo_id, data)
    if result:
        return SuccessResponse(data=result, msg="更新成功")
    from app.common.response import ErrorResponse
    return ErrorResponse(msg="仓库不存在")


@router.get("/model/{repo_id}/versions", summary="模型版本列表")
async def list_model_versions(repo_id: int, auth: AuthSchema = Depends(AuthPermission(["module_train:model:query"]))):
    data = await TrainService.list_model_versions(repo_id)
    return SuccessResponse(data=data)


@router.get("/model/version/{version_id}/repo", summary="版本所属仓库")
async def get_version_repo(version_id: int, auth: AuthSchema = Depends(AuthPermission(["module_train:model:query"]))):
    data = await TrainService.get_version_repo(version_id)
    if not data:
        from app.common.response import ErrorResponse
        return ErrorResponse(msg="模型版本不存在")
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


@router.put("/task/{task_id}/update", summary="编辑训练任务（仅待开始）")
async def update_task(
    task_id: int,
    data: TrainTaskUpdateSchema,
    auth: AuthSchema = Depends(AuthPermission(["module_train:task:update"])),
):
    try:
        result = await TrainService.update_task(task_id, data, auth)
        return SuccessResponse(data=result, msg="训练任务已更新")
    except ValueError as e:
        from app.common.response import ErrorResponse
        return ErrorResponse(msg=str(e))


@router.get("/task/list", summary="训练任务列表")
async def list_tasks(
    name: str | None = Query(None),
    framework: str | None = Query(None),
    status: str | None = Query(None),
    page_no: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    auth: AuthSchema = Depends(AuthPermission(["module_train:task:query"])),
):
    data, total = await TrainService.list_tasks({
        "name": name,
        "framework": framework,
        "status": status,
        "page_no": page_no,
        "page_size": page_size,
    })
    return SuccessResponse(data={
        "items": data, "total": total,
        "page_no": page_no, "page_size": page_size,
        "has_next": page_no * page_size < total,
    })


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


@router.get("/eval/{eval_id}/logs", summary="获取评估日志")
async def get_eval_logs(eval_id: int, auth: AuthSchema = Depends(AuthPermission(["module_train:eval:query"]))):
    import tempfile
    log_path = os.path.join(tempfile.gettempdir(), "eval_output", str(eval_id), "eval.log")
    if not os.path.exists(log_path):
        eval_rec = await TrainService.get_eval(eval_id)
        log_content = eval_rec.get("log", "") if eval_rec else ""
        return SuccessResponse(data={"logs": log_content, "path": log_path})
    with open(log_path, encoding="utf-8", errors="replace") as f:
        content = f.read()
    return SuccessResponse(data={"logs": content[-500000:]})


@router.post("/eval/{eval_id}/start", summary="开始评估")
async def start_eval(eval_id: int, auth: AuthSchema = Depends(AuthPermission(["module_train:eval:create"]))):
    try:
        await start_evaluation(eval_id)
        return SuccessResponse(data={"id": eval_id}, msg="评估已开始")
    except Exception as e:
        from app.common.response import ErrorResponse
        return ErrorResponse(msg=str(e))


@router.post("/eval/{eval_id}/stop", summary="停止评估")
async def stop_eval(eval_id: int, auth: AuthSchema = Depends(AuthPermission(["module_train:eval:create"]))):
    await stop_evaluation(eval_id)
    return SuccessResponse(data={"id": eval_id}, msg="评估已停止")


@router.post("/dataset/export", summary="导出标注数据集")
async def export_dataset(data: DatasetExportSchema, auth: AuthSchema = Depends(AuthPermission(["annotation:dataset:query"]))):
    try:
        result = await TrainService.export_dataset(data, auth)
        return SuccessResponse(data=result, msg="数据集导出成功")
    except Exception as e:
        from app.common.response import ErrorResponse
        return ErrorResponse(msg=str(e))


@router.get("/eval/list", summary="评估记录列表")
async def list_evals(
    model_repo_id: int | None = Query(None),
    name: str | None = Query(None),
    framework: str | None = Query(None),
    status: str | None = Query(None),
    page_no: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    auth: AuthSchema = Depends(AuthPermission(["module_train:eval:query"])),
):
    data, total = await TrainService.list_evals({
        "model_repo_id": model_repo_id,
        "name": name,
        "framework": framework,
        "status": status,
        "page_no": page_no,
        "page_size": page_size,
    })
    return SuccessResponse(data={
        "items": data, "total": total,
        "page_no": page_no, "page_size": page_size,
        "has_next": page_no * page_size < total,
    })


@router.get("/task/{task_id}/logs", summary="获取训练日志")
async def get_task_logs(task_id: int, auth: AuthSchema = Depends(AuthPermission(["module_train:task:query"]))):
    import tempfile
    log_path = os.path.join(tempfile.gettempdir(), "train_output", str(task_id), "train.log")
    if not os.path.exists(log_path):
        return SuccessResponse(data={"logs": "", "path": log_path})
    with open(log_path, encoding="utf-8", errors="replace") as f:
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
async def list_predicts(
    model_repo_id: int | None = Query(None),
    name: str | None = Query(None),
    framework: str | None = Query(None),
    status: str | None = Query(None),
    page_no: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    auth: AuthSchema = Depends(AuthPermission(["module_train:predict:query"])),
):
    data, total = await TrainService.list_predicts({
        "model_repo_id": model_repo_id,
        "name": name,
        "framework": framework,
        "status": status,
        "page_no": page_no,
        "page_size": page_size,
    })
    return SuccessResponse(data={
        "items": data, "total": total,
        "page_no": page_no, "page_size": page_size,
        "has_next": page_no * page_size < total,
    })


@router.get("/predict/{predict_id}/detail", summary="预测详情")
async def get_predict(predict_id: int, auth: AuthSchema = Depends(AuthPermission(["module_train:predict:query"]))):
    data = await TrainService.get_predict(predict_id)
    return SuccessResponse(data=data)


@router.get("/predict/{predict_id}/logs", summary="获取预测日志")
async def get_predict_logs(predict_id: int, auth: AuthSchema = Depends(AuthPermission(["module_train:predict:query"]))):
    import tempfile
    log_path = os.path.join(tempfile.gettempdir(), "predict_output", str(predict_id), "predict.log")
    if not os.path.exists(log_path):
        pred_rec = await TrainService.get_predict(predict_id)
        log_content = pred_rec.get("log", "") if pred_rec else ""
        return SuccessResponse(data={"logs": log_content, "path": log_path})
    with open(log_path, encoding="utf-8", errors="replace") as f:
        content = f.read()
    return SuccessResponse(data={"logs": content[-500000:]})


@router.post("/predict/{predict_id}/start", summary="开始预测")
async def start_predict(predict_id: int, auth: AuthSchema = Depends(AuthPermission(["module_train:predict:create"]))):
    try:
        await start_prediction(predict_id)
        return SuccessResponse(data={"id": predict_id}, msg="预测已开始")
    except Exception as e:
        from app.common.response import ErrorResponse
        return ErrorResponse(msg=str(e))


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


@router.post("/schedule/create", summary="创建定时训练计划")
async def create_schedule(
    data: TrainScheduleCreateSchema = Body(...),
    auth: AuthSchema = Depends(AuthPermission(["module_train:task:create"])),
):
    from .schedule_service import ScheduleService
    result = await ScheduleService.create_schedule(data, auth)
    return SuccessResponse(data=result, msg="创建成功")


@router.get("/schedule/list", summary="定时训练计划列表")
async def list_schedules(auth: AuthSchema = Depends(AuthPermission(["module_train:task:query"]))):
    from .schedule_service import ScheduleService
    data = await ScheduleService.list_schedules()
    return SuccessResponse(data=data)


@router.put("/schedule/update/{schedule_id}", summary="更新定时训练计划")
async def update_schedule(
    schedule_id: int,
    data: TrainScheduleUpdateSchema = Body(...),
    auth: AuthSchema = Depends(AuthPermission(["module_train:task:update"])),
):
    from .schedule_service import ScheduleService
    result = await ScheduleService.update_schedule(schedule_id, data)
    if result:
        return SuccessResponse(data=result, msg="更新成功")
    from app.common.response import ErrorResponse
    return ErrorResponse(msg="计划不存在")


@router.delete("/schedule/delete", summary="删除定时训练计划")
async def delete_schedule(
    ids: list[int] = Body(...),
    auth: AuthSchema = Depends(AuthPermission(["module_train:task:delete"])),
):
    from .schedule_service import ScheduleService
    await ScheduleService.delete_schedules(ids)
    return SuccessResponse(msg="删除成功")


@router.post("/model/{model_id}/export", summary="导出模型（格式转换）")
async def export_model(
    model_id: int,
    data: ModelExportSchema = Body(...),
    auth: AuthSchema = Depends(AuthPermission(["module_train:model:query"])),
):
    from .export_service import export_model_to_format
    from .service import TrainService

    model = await TrainService.get_model(model_id)
    if not model:
        print(f"[export] model_id={model_id} not found in DB", flush=True)
        from app.common.response import ErrorResponse
        return ErrorResponse(msg="模型不存在")

    try:
        result = await export_model_to_format(
            model_id=model_id,
            storage_path=model.get("storage_path", ""),
            export_params=data.model_dump(),
            model_name=model.get("name", ""),
            created_id=auth.user.id,
            dataset_id=model.get("annotation_dataset_id"),
            framework=model.get("framework"),
        )
        return SuccessResponse(data=result, msg="模型导出成功")
    except Exception as e:
        from app.common.response import ErrorResponse
        return ErrorResponse(msg=f"导出失败: {e}")


@router.get("/model/{model_id}/download", summary="下载模型文件")
async def download_model(
    model_id: int,
    auth: AuthSchema = Depends(AuthPermission(["module_train:model:query"])),
):
    from .export_service import resolve_download_target
    from .service import TrainService
    model = await TrainService.get_model(model_id)
    if not model or not model.get("storage_path"):
        from app.common.response import ErrorResponse
        return ErrorResponse(msg="模型或文件不存在")

    key, fmt = resolve_download_target(model, s3_client.object_exists)
    url = s3_client.presigned_url(key)
    return SuccessResponse(data={"download_url": url, "format": fmt})


@router.put("/model/update/{model_id}", summary="更新模型信息")
async def update_model(
    model_id: int,
    data: ModelUpdateSchema = Body(...),
    auth: AuthSchema = Depends(AuthPermission(["module_train:model:update"])),
):
    from .service import TrainService
    result = await TrainService.update_model(model_id, data.model_dump(exclude_none=True), auth)
    if result:
        return SuccessResponse(data=result, msg="更新成功")
    from app.common.response import ErrorResponse
    return ErrorResponse(msg="模型不存在")


@router.post("/deploy/create", summary="创建模型部署")
async def create_deploy(
    data: TrainDeployCreateSchema = Body(...),
    auth: AuthSchema = Depends(AuthPermission(["module_train:model:query"])),
):
    from .service import TrainService
    result = await TrainService.create_deploy(data, auth)
    return SuccessResponse(data=result, msg="部署已创建")


@router.post("/deploy/{deploy_id}/start", summary="启动部署")
async def start_deploy(
    deploy_id: int,
    auth: AuthSchema = Depends(AuthPermission(["module_train:model:query"])),
):
    try:
        from .deploy_executor import start_deployment
        await start_deployment(deploy_id)
        return SuccessResponse(data={"id": deploy_id}, msg="部署已启动")
    except Exception as e:
        from app.common.response import ErrorResponse
        return ErrorResponse(msg=str(e))


@router.post("/deploy/{deploy_id}/stop", summary="停止部署")
async def stop_deploy(
    deploy_id: int,
    auth: AuthSchema = Depends(AuthPermission(["module_train:model:query"])),
):
    from .deploy_executor import stop_deployment
    await stop_deployment(deploy_id)
    return SuccessResponse(data={"id": deploy_id}, msg="部署已停止")


@router.put("/deploy/{deploy_id}/renew-key", summary="重新生成API Key")
async def renew_deploy_key(
    deploy_id: int,
    auth: AuthSchema = Depends(AuthPermission(["module_train:model:query"])),
):
    from .service import TrainService
    result = await TrainService.renew_deploy_key(deploy_id)
    if not result:
        from app.common.response import ErrorResponse
        return ErrorResponse(msg="部署不存在")
    return SuccessResponse(data=result, msg="API Key 已重新生成")


@router.get("/deploy/list", summary="部署列表")
async def list_deploys(
    status: str | None = Query(None),
    name: str | None = Query(None),
    page_no: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    auth: AuthSchema = Depends(AuthPermission(["module_train:model:query"])),
):
    from .service import TrainService
    data, total = await TrainService.list_deploys({
        "status": status,
        "name": name,
        "page_no": page_no,
        "page_size": page_size,
    })
    return SuccessResponse(data={
        "items": data, "total": total,
        "page_no": page_no, "page_size": page_size,
        "has_next": page_no * page_size < total,
    })


@router.get("/deploy/{deploy_id}/detail", summary="部署详情")
async def get_deploy(
    deploy_id: int,
    auth: AuthSchema = Depends(AuthPermission(["module_train:model:query"])),
):
    from .service import TrainService
    data = await TrainService.get_deploy(deploy_id)
    if not data:
        from app.common.response import ErrorResponse
        return ErrorResponse(msg="部署不存在")
    return SuccessResponse(data=data)


@router.get("/deploy/{deploy_id}/logs", summary="获取部署日志")
async def get_deploy_logs(
    deploy_id: int,
    auth: AuthSchema = Depends(AuthPermission(["module_train:model:query"])),
):
    import tempfile
    log_path = os.path.join(tempfile.gettempdir(), "deploy_output", str(deploy_id), "deploy.log")
    if not os.path.exists(log_path):
        return SuccessResponse(data={"logs": ""})
    with open(log_path, encoding="utf-8", errors="replace") as f:
        content = f.read()
    return SuccessResponse(data={"logs": content[-500000:]})


@router.delete("/deploy/delete", summary="删除部署")
async def delete_deploy(
    ids: list[int] = Body(...),
    auth: AuthSchema = Depends(AuthPermission(["module_train:model:delete"])),
):
    from .service import TrainService
    await TrainService.delete_deploys(ids)
    return SuccessResponse(msg="删除成功")
