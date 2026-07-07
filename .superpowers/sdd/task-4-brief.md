# Task 4: Controller — 新增预测端点 + 增强评估端点

## 要修改的文件
- `backend/app/plugin/module_train/controller.py`

## 要求

### 1. 更新 imports

将第 1 行 `from fastapi import APIRouter, Depends, Body` 改为：
```python
from fastapi import APIRouter, Depends, Body, UploadFile, File
```

将第 5 行 schema import 改为：
```python
from .schema import (
    TrainModelCreateSchema, TrainTaskCreateSchema,
    TrainEvalCreateSchema, TrainPredictCreateSchema, DatasetExportSchema
)
```

将第 7 行改为：
```python
from .scheduler import start_training
from .eval_scheduler import start_evaluation, stop_evaluation
from .predict_executor import start_prediction, stop_prediction
```

### 2. 增强评估端点

在第 75 行（create_eval 结尾）之后、第 78 行（dataset/export）之前添加：
```python
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
```

### 3. 新增预测端点

在文件末尾（delete_eval 之后）添加：
```python
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
```

## 现有文件
- `backend/app/plugin/module_train/controller.py`（104 行）
- 所有依赖都已存在：`TrainService.get_eval`（Task 3）、`start_evaluation/stop_evaluation`（Task 5）、`start_prediction/stop_prediction`（Task 6）

## 提交信息
```bash
git add backend/app/plugin/module_train/controller.py
git commit -m "feat(train): add predict API endpoints, enhance eval endpoints"
```
