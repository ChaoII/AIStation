# Task 3: Service — 评估服务增强 + 预测服务

## 要修改的文件
- `backend/app/plugin/module_train/service.py`（修改）

## 要求

### 1. 更新 import（第 3 行）
将：
```python
from .model import TrainModel, TrainTask, TrainEval
```
改为：
```python
from .model import TrainModel, TrainTask, TrainEval, TrainPredict
```

### 2. 增强 `create_eval` 方法（约第 93-99 行）
现有：
```python
@classmethod
async def create_eval(cls, data, auth) -> dict:
    async with async_db_session.begin() as db:
        e = TrainEval(model_repo_id=data.model_repo_id, eval_dataset_id=data.eval_dataset_id, created_id=auth.user.id)
        db.add(e)
        await db.flush()
        return {"id": e.id}
```
改为支持 `model_id` 和 `hyperparams`：
```python
@classmethod
async def create_eval(cls, data, auth) -> dict:
    async with async_db_session.begin() as db:
        e = TrainEval(
            model_repo_id=data.model_repo_id,
            model_id=data.model_id,
            eval_dataset_id=data.eval_dataset_id,
            hyperparams=data.hyperparams,
            created_id=auth.user.id,
        )
        db.add(e)
        await db.flush()
        return {"id": e.id}
```

### 3. 在 `delete_evals`（约第 109 行）之后新增 `get_eval` 方法
```python
@classmethod
async def get_eval(cls, eval_id: int) -> dict | None:
    async with async_db_session() as db:
        e = await db.get(TrainEval, eval_id)
        return dict(e.__dict__) if e else None
```

### 4. 新增预测 CRUD 方法（在 `get_eval` 之后）
```python
@classmethod
async def create_predict(cls, data, auth) -> dict:
    async with async_db_session.begin() as db:
        p = TrainPredict(
            model_repo_id=data.model_repo_id,
            model_id=data.model_id,
            source_type=data.source_type,
            source_dataset_id=data.source_dataset_id,
            source_images=data.source_images,
            hyperparams=data.hyperparams,
            created_id=auth.user.id,
        )
        db.add(p)
        await db.flush()
        return {"id": p.id}


@classmethod
async def get_predict(cls, predict_id: int) -> dict | None:
    async with async_db_session() as db:
        p = await db.get(TrainPredict, predict_id)
        return dict(p.__dict__) if p else None


@classmethod
async def list_predicts(cls) -> list[dict]:
    async with async_db_session() as db:
        result = await db.execute(select(TrainPredict).order_by(desc(TrainPredict.created_time)))
        return [dict(r.__dict__) for r in result.scalars().all()]


@classmethod
async def delete_predicts(cls, ids: list[int]) -> None:
    async with async_db_session.begin() as db:
        for pid in ids:
            p = await db.get(TrainPredict, pid)
            if p:
                await db.delete(p)


@classmethod
async def upload_predict_images(cls, files: list, auth) -> list[str]:
    import uuid
    import tempfile, os
    from app.utils.s3_client import s3_client

    urls = []
    for f in files:
        content = await f.read()
        ext = f.filename.rsplit(".", 1)[-1] if "." in f.filename else "jpg"
        key = f"train/predict/upload/{auth.user.id}/{uuid.uuid4()}.{ext}"
        s3_client.upload_fileobj(content, key)
        urls.append(s3_client.presigned_url(key))
    return urls
```

## 现有文件结构
- 文件路径：`backend/app/plugin/module_train/service.py`
- `s3_client` 模式和 `export_dataset` 方法已有（参考第 137-144 行）
- 所有现有方法使用 `@classmethod` 和 `async with async_db_session`/`async_db_session.begin()`

## 提交信息
```bash
git add backend/app/plugin/module_train/service.py
git commit -m "feat(train): add predict service, enhance eval service"
```
