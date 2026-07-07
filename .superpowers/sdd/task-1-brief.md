# Task 1: 后端数据模型 — 增强 TrainEval + 新建 TrainPredict

## 要修改的文件
- `backend/app/plugin/module_train/model.py`（修改）

## 要求

### 1. 增强 TrainEval（替换现有第 54-60 行）

```python
class TrainEval(ModelMixin, UserMixin):
    __tablename__ = "train_evals"
    model_repo_id: Mapped[int] = mapped_column(Integer, comment="模型仓库ID")
    model_id: Mapped[int | None] = mapped_column(Integer, nullable=True, comment="具体模型版本ID")
    eval_dataset_id: Mapped[int] = mapped_column(Integer, comment="评估数据集ID")
    framework: Mapped[TrainFramework] = mapped_column(SAEnum(TrainFramework), default=TrainFramework.ULTRALYTICS, comment="框架")
    hyperparams: Mapped[dict | None] = mapped_column(JSONB, nullable=True, default=dict, comment="评估参数")
    metrics: Mapped[dict | None] = mapped_column(JSONB, nullable=True, comment="评估指标")
    status: Mapped[TrainStatus] = mapped_column(SAEnum(TrainStatus), default=TrainStatus.PENDING, comment="状态")
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, comment="开始时间")
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, comment="完成时间")
    log: Mapped[str | None] = mapped_column(Text, nullable=True, comment="评估日志")
```

### 2. 新建 TrainPredict（在 TrainEval 定义之后添加）

```python
class TrainPredict(ModelMixin, UserMixin):
    __tablename__ = "train_predicts"
    model_repo_id: Mapped[int] = mapped_column(Integer, comment="模型仓库ID")
    model_id: Mapped[int] = mapped_column(Integer, comment="模型版本ID")
    framework: Mapped[TrainFramework] = mapped_column(SAEnum(TrainFramework), default=TrainFramework.ULTRALYTICS, comment="框架")
    source_type: Mapped[str] = mapped_column(String(16), comment="图片来源 dataset/upload")
    source_dataset_id: Mapped[int | None] = mapped_column(Integer, nullable=True, comment="源数据集ID")
    source_images: Mapped[list | None] = mapped_column(JSONB, nullable=True, comment="上传图片原始URL列表")
    result_images: Mapped[list | None] = mapped_column(JSONB, nullable=True, comment="结果图片URL列表")
    result_zip_path: Mapped[str | None] = mapped_column(String(512), nullable=True, comment="结果ZIP在RustFS的路径")
    hyperparams: Mapped[dict | None] = mapped_column(JSONB, nullable=True, default=dict, comment="预测参数")
    status: Mapped[TrainStatus] = mapped_column(SAEnum(TrainStatus), default=TrainStatus.PENDING, comment="状态")
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, comment="开始时间")
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, comment="完成时间")
    log: Mapped[str | None] = mapped_column(Text, nullable=True, comment="预测日志")
```

## 前置条件
- 无需 type-check 测试
- 模型继承 `ModelMixin` + `UserMixin`（已有）
- `TrainStatus`, `TrainFramework`, `TrainStatus` 枚举已有（第 9-19 行）
- `TrainEval` 已有，需要替换其全部字段
- 文件路径：`backend/app/plugin/module_train/model.py`

## 提交信息
```
git add backend/app/plugin/module_train/model.py
git commit -m "feat(train): enhance TrainEval model, add TrainPredict model"
```
