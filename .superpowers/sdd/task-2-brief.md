# Task 2: Schema — 新增预测 + 增强评估

## 要修改的文件
- `backend/app/plugin/module_train/schema.py`（修改）

## 要求

### 1. 替换现有 `TrainEvalCreateSchema` 和 `TrainEvalOutSchema`

现有代码：
```python
class TrainEvalCreateSchema(BaseModel):
    model_repo_id: int
    eval_dataset_id: int


class TrainEvalOutSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    model_repo_id: int
    eval_dataset_id: int
    metrics: dict | None
    status: str
    log: str | None
    created_time: datetime | None
```

替换为：
```python
class TrainEvalCreateSchema(BaseModel):
    model_repo_id: int
    model_id: int | None = None
    eval_dataset_id: int
    hyperparams: dict = Field(default_factory=dict)


class TrainEvalOutSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    model_repo_id: int
    model_id: int | None
    eval_dataset_id: int
    framework: str
    hyperparams: dict | None
    metrics: dict | None
    status: str
    log: str | None
    started_at: datetime | None
    finished_at: datetime | None
    created_id: int | None
    created_time: datetime | None
```

### 2. 在 `DatasetExportSchema` 之前新增预测 Schema

```python
class TrainPredictCreateSchema(BaseModel):
    model_repo_id: int
    model_id: int
    source_type: str = Field(pattern=r"^(dataset|upload)$")
    source_dataset_id: int | None = None
    source_images: list[str] | None = None
    hyperparams: dict = Field(default_factory=dict)


class TrainPredictOutSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    model_repo_id: int
    model_id: int
    framework: str
    source_type: str
    source_dataset_id: int | None
    source_images: list | None
    result_images: list | None
    result_zip_path: str | None
    hyperparams: dict | None
    status: str
    started_at: datetime | None
    finished_at: datetime | None
    log: str | None
    created_id: int | None
    created_time: datetime | None
```

## 现有文件参考
- 文件路径：`backend/app/plugin/module_train/schema.py`
- 现有 import：`from datetime import datetime` 和 `from pydantic import BaseModel, ConfigDict, Field`
- 结构：TrainModelCreateSchema → TrainModelOutSchema → TrainTaskCreateSchema → TrainTaskOutSchema → TrainEvalCreateSchema → TrainEvalOutSchema → DatasetExportSchema

## 提交信息
```bash
git add backend/app/plugin/module_train/schema.py
git commit -m "feat(train): add predict schemas, enhance eval schemas"
```
