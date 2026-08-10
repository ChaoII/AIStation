### Task 1: 数据模型 — 新增仓库表 + 版本表加 repo_id

**Files:**
- Modify: `backend/app/plugin/module_train/model.py`
- Test: `backend/tests/test_train_model_schema.py`（新建）

**Interfaces:**
- Consumes: `ModelMixin`, `UserMixin`, `TrainFramework`（已有）
- Produces: `TrainModelRepo`, `TrainModel`（增加 `repo_id`、`metrics` 已有）, `TrainModelVersionRow` 别名

- [ ] **Step 1: 写失败测试 — 断言新表存在且可创建**

`backend/tests/test_train_model_schema.py`（与 `conftest.py` 同步模式对齐，用 ORM 元数据断言，不依赖 asyncio 插件）：

```python
"""测试模型仓库/版本双表结构。"""
from app.plugin.module_train.model import TrainModel, TrainModelRepo


def test_train_model_repo_table_declared():
    assert TrainModelRepo.__tablename__ == "train_model_repos"
    assert "name" in TrainModelRepo.__table__.columns


def test_train_model_has_repo_id_column():
    assert "repo_id" in TrainModel.__table__.columns
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd backend && uv run pytest tests/test_train_model_schema.py -v`
Expected: FAIL，`TrainModelRepo` ImportError 或 `repo_id` AttributeError

- [ ] **Step 3: 在 `model.py` 新增仓库表并改造版本表**

在 `TrainModel` 类上方添加（在 `model.py` 的 `TrainModel` 定义之前）：

```python
class TrainModelRepo(ModelMixin, UserMixin):
    """模型仓库：以模型名称聚合的一组版本。"""
    __tablename__ = "train_model_repos"
    name: Mapped[str] = mapped_column(String(128), unique=True, comment="模型名称（仓库唯一）")
    framework: Mapped[TrainFramework] = mapped_column(SAEnum(TrainFramework), comment="训练框架")
    description: Mapped[str | None] = mapped_column(Text, nullable=True, comment="描述")
    latest_version_id: Mapped[int | None] = mapped_column(Integer, nullable=True, comment="最新版本ID")
    annotation_dataset_id: Mapped[int | None] = mapped_column(Integer, nullable=True, comment="来源数据集ID")
    status: Mapped[str] = mapped_column(String(16), default="draft", comment="draft/released/archived")
```

将 `TrainModel` 类改造为（改名语义为"模型版本"，字段追加 `repo_id`）：

```python
class TrainModel(ModelMixin, UserMixin):
    __tablename__ = "train_models"
    repo_id: Mapped[int | None] = mapped_column(Integer, nullable=True, comment="所属仓库ID")
    name: Mapped[str] = mapped_column(String(128), comment="模型名称")
    framework: Mapped[TrainFramework] = mapped_column(SAEnum(TrainFramework), comment="训练框架")
    version: Mapped[str] = mapped_column(String(32), comment="语义版本号")
    description: Mapped[str | None] = mapped_column(Text, nullable=True, comment="描述")
    storage_path: Mapped[str | None] = mapped_column(String(512), nullable=True, comment="RustFS 存储路径")
    format: Mapped[str | None] = mapped_column(String(32), nullable=True, comment="导出格式 ONNX/Paddle/TorchScript")
    export_format: Mapped[str | None] = mapped_column(String(32), nullable=True, comment="数据集导出格式 YOLO/PaddleX")
    metrics: Mapped[dict | None] = mapped_column(JSONB, nullable=True, comment="评估指标")
    annotation_dataset_id: Mapped[int | None] = mapped_column(Integer, nullable=True, comment="来源数据集ID")
    status: Mapped[str] = mapped_column(String(16), default="draft", comment="draft/released/archived")
```

- [ ] **Step 4: 运行测试确认通过**

Run: `cd backend && uv run pytest tests/test_train_model_schema.py -v`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add backend/app/plugin/module_train/model.py backend/tests/test_train_model_schema.py
git commit -m "feat(train): add TrainModelRepo table, add repo_id to TrainModel version table"
```

---


