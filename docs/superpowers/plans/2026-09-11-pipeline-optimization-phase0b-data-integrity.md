# Phase 0B：数据一致性（审计字段 + 级联删除）Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让 `module_train` 与标注图片的审计字段（`created_id`/`updated_id`/`deleted_id`）真正写入，并让删除数据集时级联软删其图片与标注记录，消除孤儿数据。

**Architecture:** 抽一个 `app/core/audit.py` 小工具统一设置审计字段（不重构各 service 的写入路径）；数据集删除改为 service 方法，逐表软删后软删数据集本身；图片列表查询补上 `is_deleted` 过滤。

**Tech Stack:** FastAPI + SQLAlchemy 2.0 + Pydantic v2 + pytest（SQLite + 内存 Redis + TestClient）。

## Global Constraints

- Python 3.13 via `uv`；命令在 `D:\AIStation\backend` 下执行：`uv run pytest`、`uv run ruff check`。
- 只判断**新增** ruff 问题（仓库存在既有 277 条 ruff 既有告警）；改动文件不应新增告警。
- 遵循现有中文 docstring/注释风格。不新增依赖。不改动无关文件。
- 提交信息风格 `fix(scope): 中文描述`；只 `git add` 本任务文件（禁止 `git add -A`）。
- ruff 配置 `fix = true`：提交前 `git status`，若 ruff 自动改了无关文件则 `git checkout -- <file>` 还原。
- 复用 `backend/tests/conftest.py` 已有的 `test_client`（session）与 `auth_headers` fixture。

---

### Task 1: 审计字段写入工具并接入训练与图片上传

**背景:** `docs/issues.md` #1/#2：`module_train/service.py` 与 `DatasetService.upload_images()` 裸构造函数写入，`updated_id` 永不写入；`created_id` 也缺失。抽工具统一补齐。

**Files:**
- Create: `backend/app/core/audit.py`
- Modify: `backend/app/plugin/module_train/service.py`（各 `create_*` 方法）
- Modify: `backend/app/api/v1/module_annotation/dataset/service.py`（`upload_images`）
- Test: `backend/tests/test_audit_helpers.py`
- Test: `backend/tests/test_audit_persisted.py`

**Interfaces:**
- Produces: `set_create_audit(obj, auth) -> None`（设置 `created_id` 与 `updated_id`）与 `set_update_audit(obj, auth) -> None`（设置 `updated_id`）。二者对 `auth`/`auth.user` 缺失安全，且仅在对象具备对应属性时赋值。

- [ ] **Step 1: Write the failing unit test**

```python
"""审计字段工具单元测试。"""
from types import SimpleNamespace

from app.core.audit import set_create_audit, set_update_audit


class _Obj:
    def __init__(self):
        self.created_id = None
        self.updated_id = None


def _auth(uid):
    return SimpleNamespace(user=SimpleNamespace(id=uid))


def test_set_create_audit_sets_both():
    obj = _Obj()
    set_create_audit(obj, _auth(7))
    assert obj.created_id == 7
    assert obj.updated_id == 7


def test_set_update_audit_sets_only_updated():
    obj = _Obj()
    obj.created_id = 3
    set_update_audit(obj, _auth(9))
    assert obj.updated_id == 9
    assert obj.created_id == 3


def test_audit_helpers_tolerate_missing_auth():
    obj = _Obj()
    set_create_audit(obj, None)
    set_update_audit(obj, SimpleNamespace(user=None))
    assert obj.created_id is None
    assert obj.updated_id is None


def test_audit_helpers_skip_objects_without_fields():
    obj = SimpleNamespace(no_audit=1)
    set_create_audit(obj, _auth(5))  # must not raise
    assert not hasattr(obj, "created_id")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/test_audit_helpers.py -q`
Expected: FAIL（`ModuleNotFoundError: app.core.audit`）

- [ ] **Step 3: Write minimal implementation**

Create `backend/app/core/audit.py`:

```python
"""审计字段写入工具：统一设置 created_id / updated_id。

用于绕过 CRUDBase 直接构造 ORM 对象的写入路径（module_train、标注图片上传等）。
"""


def _uid(auth) -> int | None:
    user = getattr(auth, "user", None)
    return getattr(user, "id", None) if user is not None else None


def set_create_audit(obj, auth) -> None:
    """为新建对象写入创建人/更新人。"""
    uid = _uid(auth)
    if uid is None:
        return
    if hasattr(obj, "created_id"):
        obj.created_id = uid
    if hasattr(obj, "updated_id"):
        obj.updated_id = uid


def set_update_audit(obj, auth) -> None:
    """为更新对象写入更新人。"""
    uid = _uid(auth)
    if uid is None:
        return
    if hasattr(obj, "updated_id"):
        obj.updated_id = uid
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && uv run pytest tests/test_audit_helpers.py -q`
Expected: PASS（4 passed）

- [ ] **Step 5: Write the failing persistence test**

```python
"""审计字段落库测试：创建训练仓库后 created_id/updated_id 非空。"""
from uuid import uuid4

from fastapi.testclient import TestClient


def test_model_repo_create_sets_audit_fields(test_client: TestClient, auth_headers: dict):
    name = f"audit-{uuid4().hex[:8]}"
    created = test_client.post(
        "/api/v1/train/model/repos",
        json={"name": name, "framework": "ultralytics"},
        headers=auth_headers,
    )
    assert created.status_code == 200, created.text

    listing = test_client.get(
        "/api/v1/train/model/list", params={"name": name, "page_no": 1, "page_size": 5},
        headers=auth_headers,
    ).json()["data"]["items"]
    assert listing, "新建的模型版本应能在 /model/list 查询到"
    row = listing[0]
    assert row["created_id"] is not None
    assert row["updated_id"] is not None
```

- [ ] **Step 6: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/test_audit_persisted.py -q`
Expected: FAIL（`updated_id` 为 `None`）——若该接口默认尚未创建版本导致用例无法取到行，改为直接调用 `TrainService.create_model_repo` 的等价路径并在报告中说明；核心断言是 `updated_id is not None`。

- [ ] **Step 7: 接入 module_train 各 create 方法**

在 `backend/app/plugin/module_train/service.py` 顶部加入：

```python
from app.core.audit import set_create_audit
```

对以下每个 `create_*` 方法，把裸构造对象后、`db.add(...)` 之前补一行 `set_create_audit(obj, auth)`（若已有 `created_id=auth.user.id` 可保留，工具会覆盖为一致值并补 `updated_id`）：

- `create_model_repo`（约 142-176 行，对象 `existing`/首个版本）
- `create_model`（约 252-279 行）
- `create_task`（约 319-333 行）
- `create_eval`（约 365-383 行）
- `create_predict`（约 447-466 行）
- `create_deploy`（约 621 行起）

示例（`create_task`）：

```python
            t = TrainTask(
                name=data.name, framework=data.framework, dataset_id=data.dataset_id,
                annotation_task_id=data.annotation_task_id,
                base_model_id=data.base_model_id, docker_image=image,
                hyperparams=data.hyperparams,
            )
            set_create_audit(t, auth)
            db.add(t)
```

- [ ] **Step 8: 接入标注图片上传**

在 `backend/app/api/v1/module_annotation/dataset/service.py` 顶部加入：

```python
from app.core.audit import set_create_audit
```

在 `upload_images` 中，`img_record = AnnotationImageModel(...)` 之后、`db.add(img_record)` 之前插入：

```python
                set_create_audit(img_record, auth)
```

- [ ] **Step 9: Run tests to verify they pass**

Run: `cd backend && uv run pytest tests/test_audit_helpers.py tests/test_audit_persisted.py -q`
Expected: PASS

- [ ] **Step 10: Full suite + ruff + commit**

Run: `cd backend && uv run pytest -q && uv run ruff check app/core/audit.py app/plugin/module_train/service.py app/api/v1/module_annotation/dataset/service.py`
Expected: 全部通过；无新增 ruff 告警。

```bash
git add backend/app/core/audit.py backend/app/plugin/module_train/service.py backend/app/api/v1/module_annotation/dataset/service.py backend/tests/test_audit_helpers.py backend/tests/test_audit_persisted.py
git commit -m "fix(audit): 审计字段统一写入 module_train 与标注图片"
```

---

### Task 2: 删除数据集级联软删图片与标注记录

**背景:** 删除数据集只软删数据集行，图片、标注记录成为孤儿；且 `DatasetService.get_images` 未过滤 `is_deleted`，软删后的图片仍会出现在列表。

**Files:**
- Modify: `backend/app/api/v1/module_annotation/dataset/service.py`（新增 `delete_datasets`；`get_images` 补 `is_deleted` 过滤）
- Modify: `backend/app/api/v1/module_annotation/dataset/controller.py:86-94`
- Test: `backend/tests/test_dataset_cascade_delete.py`

**Interfaces:**
- Produces: `DatasetService.delete_datasets(ids: list[int], auth) -> None` —— 对每个数据集，先软删其 `annotation_image` 与其 `annotation_record`，再软删数据集本身。
- Consumes: `set_update_audit`（可选用）与 `CRUDBase.delete` 的软删语义。

- [ ] **Step 1: Write the failing cascade test**

```python
"""删除数据集级联软删图片测试。"""
from uuid import uuid4

from fastapi.testclient import TestClient

_FAKE_PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 64


def _create_dataset_with_image(test_client: TestClient, auth_headers: dict) -> int:
    name = f"cascade-{uuid4().hex[:8]}"
    created = test_client.post(
        "/api/v1/annotation/dataset/create", json={"name": name}, headers=auth_headers
    )
    assert created.status_code == 200, created.text
    data = created.json()["data"]
    dataset_id = data["id"] if isinstance(data, dict) and "id" in data else None
    if dataset_id is None:
        items = test_client.get(
            "/api/v1/annotation/dataset/list",
            params={"page_no": 1, "page_size": 5},
            headers=auth_headers,
        ).json()["data"]["items"]
        dataset_id = next(i["id"] for i in items if i["name"] == name)
    files = {"files": ("a.png", _FAKE_PNG, "image/png")}
    up = test_client.post(
        f"/api/v1/annotation/dataset/{dataset_id}/upload", files=files, headers=auth_headers
    )
    assert up.status_code == 200, up.text
    return dataset_id


def test_dataset_delete_cascades_images(
    test_client: TestClient, auth_headers: dict, monkeypatch
):
    # 上传需要对象存储：屏蔽真实 S3 调用
    monkeypatch.setattr(
        "app.utils.s3_client.s3_client.ensure_bucket", lambda *a, **k: None
    )
    monkeypatch.setattr(
        "app.utils.s3_client.s3_client.upload_fileobj", lambda *a, **k: None
    )

    dataset_id = _create_dataset_with_image(test_client, auth_headers)
    before = test_client.get(
        f"/api/v1/annotation/dataset/{dataset_id}/images", headers=auth_headers
    ).json()["data"]
    assert before["total"] == 1

    deleted = test_client.request(
        "DELETE", "/api/v1/annotation/dataset/delete", json=[dataset_id], headers=auth_headers
    )
    assert deleted.status_code == 200, deleted.text

    after = test_client.get(
        f"/api/v1/annotation/dataset/{dataset_id}/images", headers=auth_headers
    ).json()["data"]
    assert after["total"] == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/test_dataset_cascade_delete.py -q`
Expected: FAIL（删除后 `total` 仍为 1，因为图片未级联且 `get_images` 未过滤软删）。

- [ ] **Step 3: 实现级联软删**

在 `backend/app/api/v1/module_annotation/dataset/service.py` 顶部补充 import：

```python
from sqlalchemy import update

from app.api.v1.module_annotation.annotation.model import AnnotationRecordModel
```

在 `DatasetService` 内新增方法：

```python
    @classmethod
    async def delete_datasets(cls, ids: list[int], auth) -> None:
        """软删数据集，并级联软删其图片与标注记录。"""
        from datetime import datetime

        actor_id = getattr(getattr(auth, "user", None), "id", None)
        async with async_db_session.begin() as db:
            for dataset_id in ids:
                img_ids = (
                    await db.execute(
                        select(AnnotationImageModel.id).where(
                            AnnotationImageModel.dataset_id == dataset_id
                        )
                    )
                ).scalars().all()
                soft = {"is_deleted": True, "deleted_time": datetime.now(), "deleted_id": actor_id}
                if img_ids:
                    await db.execute(
                        update(AnnotationRecordModel)
                        .where(AnnotationRecordModel.image_id.in_(img_ids))
                        .values(**soft)
                    )
                await db.execute(
                    update(AnnotationImageModel)
                    .where(AnnotationImageModel.dataset_id == dataset_id)
                    .values(**soft)
                )
            from .crud import DatasetCRUD
            await DatasetCRUD(auth=auth).delete(ids=ids)
```

- [ ] **Step 4: 图片列表补软删过滤**

在 `get_images` 中，把图片计数与查询都补上 `is_deleted` 过滤。将：

```python
            count_sql = select(func.count()).select_from(
                select(AnnotationImageModel).where(AnnotationImageModel.dataset_id == dataset_id).subquery()
            )
```

改为：

```python
            count_sql = select(func.count()).select_from(
                select(AnnotationImageModel)
                .where(
                    AnnotationImageModel.dataset_id == dataset_id,
                    AnnotationImageModel.is_deleted == False,  # noqa: E712
                )
                .subquery()
            )
```

并把分页查询：

```python
            sql = (select(AnnotationImageModel)
                   .where(AnnotationImageModel.dataset_id == dataset_id)
                   .order_by(AnnotationImageModel.filename)
                   .limit(page_size).offset(offset))
```

改为：

```python
            sql = (select(AnnotationImageModel)
                   .where(
                       AnnotationImageModel.dataset_id == dataset_id,
                       AnnotationImageModel.is_deleted == False,  # noqa: E712
                   )
                   .order_by(AnnotationImageModel.filename)
                   .limit(page_size).offset(offset))
```

- [ ] **Step 5: 控制器改走 service**

修改 `backend/app/api/v1/module_annotation/dataset/controller.py` 的 `delete_dataset`：

```python
@DatasetRouter.delete("/delete", summary="删除数据集")
async def delete_dataset(
    ids: list[int],
    auth: AuthSchema = Depends(AuthPermission(["annotation:dataset:delete"])),
) -> JSONResponse:
    await DatasetService.delete_datasets(ids=ids, auth=auth)
    return SuccessResponse(msg="删除成功")
```

- [ ] **Step 6: Run test to verify it passes**

Run: `cd backend && uv run pytest tests/test_dataset_cascade_delete.py -q`
Expected: PASS

- [ ] **Step 7: Full suite + ruff + commit**

Run: `cd backend && uv run pytest -q && uv run ruff check app/api/v1/module_annotation/dataset/service.py app/api/v1/module_annotation/dataset/controller.py`
Expected: 通过。

```bash
git add backend/app/api/v1/module_annotation/dataset/service.py backend/app/api/v1/module_annotation/dataset/controller.py backend/tests/test_dataset_cascade_delete.py
git commit -m "fix(annotation): 删除数据集级联软删图片与标注记录"
```

---

## Self-Review

**Spec coverage（对照 design 第 5.1 节）:**
- 0.1 审计字段统一 → Task 1 ✅
- 0.2 删除级联 → Task 2 ✅（另附带修复 `get_images` 的软删过滤，属同一致性问题）

**Placeholder scan:** 无 TBD/TODO；每个代码步骤含完整代码。

**Type consistency:** `set_create_audit`/`set_update_audit`、`DatasetService.delete_datasets` 命名在定义与使用处一致。

**风险:** Task 1 Step 6 的落库断言依赖 `/train/model/repos` 默认创建版本行；若接口行为不同，按 Step 6 说明改用等价路径，核心断言保持 `updated_id is not None`。Task 2 的 `crud.delete` 对 `DatasetModel` 走软删（模型含 `is_deleted`）。
