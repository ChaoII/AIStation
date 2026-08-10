### Task 5: 修正版本号 bug + eval/predict model_id 语义

**Files:**
- Modify: `backend/app/plugin/module_train/controller.py`
- Modify: `backend/app/plugin/module_train/service.py`
- Modify: `backend/app/plugin/module_train/eval_scheduler.py`
- Modify: `backend/app/plugin/module_train/predict_executor.py`
- Test: `backend/tests/test_version_and_model_refs.py`（新建）

**Interfaces:**
- Consumes: `TrainService._parse_version`, `TrainModelRepo`（Task 3 产物）
- Produces: `TrainEval`/`TrainPredict` 的 `model_id` 恒为版本行 id；`model_repo_id` 恒为仓库 id；`_resolve_model_storage(version_id)` 统一模型文件解析

- [ ] **Step 1: 写失败测试 — 模型文件路径回溯统一**

`backend/tests/test_version_and_model_refs.py`:

```python
"""版本号与模型引用语义测试。"""


def test_parse_version_removes_all_non_digits():
    from app.plugin.module_train.service import TrainService
    assert TrainService._parse_version("vv1") == 1
    assert TrainService._parse_version("v1") == 1
    assert TrainService._parse_version("v12") == 12
    assert TrainService._parse_version("") == 1
    assert TrainService._parse_version(None) == 1
```

- [ ] **Step 2: 运行确认失败**

Run: `cd backend && uv run pytest tests/test_version_and_model_refs.py -v`
Expected: FAIL（`_parse_version` 不存在，因为是 classmethod 且当前实现是 `int(last.version.replace("v",""))`）

- [ ] **Step 3: 统一模型文件解析 — 新增 service 方法**

在 `service.py` 添加：

```python
@classmethod
async def _resolve_model_storage(cls, version_id: int) -> str:
    """解析版本行真实模型文件路径。处理 /export/ 覆盖回溯问题。

    返回 RustFS key（best.pt）。若 storage_path 是导出产物(/export/)则回溯原始训练产物。
    """
    async with async_db_session() as db:
        ver = await db.get(TrainModel, version_id)
        if not ver or not ver.storage_path:
            raise Exception("模型版本不存在或无存储文件")
        storage_path = ver.storage_path
        if "/export/" in storage_path:
            from .model import TrainTask
            task = (await db.execute(
                select(TrainTask).where(TrainTask.model_repo_id == ver.id)
                .order_by(desc(TrainTask.id)).limit(1)
            )).scalar_one_or_none()
            if task:
                storage_path = f"train/models/task_{task.id}/best.pt"
        return storage_path
```

- [ ] **Step 4: eval/predict 改用统一解析**

`eval_scheduler.py` 中替换 `db.get(TrainModel, eval_rec.model_id or eval_rec.model_repo_id)` 与回溯逻辑：

```python
        from .service import TrainService
        storage_path = await TrainService._resolve_model_storage(eval_rec.model_id)
```

`predict_executor.py` 中对应替换：

```python
        from .service import TrainService
        storage_path = await TrainService._resolve_model_storage(pred.model_id)
```

- [ ] **Step 5: 前端 eval/predict 创建表单修正 model_id 来源**

`frontend/web/src/views/module_train/eval/index.vue` 与 `predict/index.vue`：`model_id` 改为选中的**版本行 id**（从 repo 的 `listModelVersions` 获取），`model_repo_id` 为仓库 id。`repo/index.vue` 的"去评估/去推理"跳转带 `model_repo_id=<repo_id>`，详情页再用 repo_id 拉版本列表供选择。

> 具体前端改动在 Task 8 详细展开；此处仅保证后端字段语义正确。

- [ ] **Step 6: 运行测试**

Run: `cd backend && uv run pytest tests/test_version_and_model_refs.py -v`
Expected: PASS

- [ ] **Step 7: 提交**

```bash
git add backend/app/plugin/module_train/service.py backend/app/plugin/module_train/eval_scheduler.py backend/app/plugin/module_train/predict_executor.py backend/tests/test_version_and_model_refs.py
git commit -m "fix(train): unify version parse and model storage resolution"
```

---


