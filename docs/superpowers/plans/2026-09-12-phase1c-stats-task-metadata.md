# Phase 1C：统计页 + 任务元数据 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 修复统计页 `page_size:999` 触发 422 导致整页空白，修正统计语义（软删/枚举键/贡献口径）；让任务的备注与类别定义真正保存，并移除"批量启用停用"死按钮。

**Architecture:** 前端修 `stats/index.vue` 的 page_size 与 `task/index.vue` 的提交载荷；后端修 `stats/service.py` 过滤与键名、给 `task/schema.py` 加 `description`。

**Tech Stack:** FastAPI + SQLAlchemy + pytest（TestClient）；Vue3。

## Global Constraints

- 后端命令 `D:\AIStation\backend`（`uv run pytest` / `uv run ruff check`，只判断新增问题）；前端 `D:\AIStation\frontend`（`pnpm run type-check` 无新增错误；`pnpm e2e` 通过）。
- 中文注释。不新增依赖。只改本任务文件。提交风格 `fix(annotation): 中文描述`；禁 `git add -A`；ruff `fix=true` 时还原无关改动。
- 后端分页上限：`page_size <= 100`（`app/core/base_params.py:14`）。
- 统计路由：`GET /api/v1/annotation/stats/overview`、`GET /api/v1/annotation/stats/dataset/{id}`。
- 测试复用 `test_client`/`auth_headers`，S3 用 monkeypatch。

---

### Task 1: 统计页 422 修复 + 后端统计语义

**背景:** `stats/index.vue:176` 传 `page_size:999` 超后端 `le=100` → 422 使 `Promise.all` 整体失败，`overview`/`datasetOptions` 都不赋值，页面全空。后端 `stats/service.py`：各计数未过滤 `is_deleted`；`tasks_by_type`/`images_by_status` 用 `str(枚举)` 得到 `"AnnotationType.DETECTION"`；`user_contributions` 计的是记录数而非标注数。

**Files:**
- Modify: `frontend/src/views/module_annotation/stats/index.vue`
- Modify: `backend/app/api/v1/module_annotation/stats/service.py`
- Test: `backend/tests/test_stats_overview.py`

**Interfaces:**
- `overview.tasks_by_type` 键为 `"detection"` 等值；`images_by_status` 键为 `"annotated"` 等值。
- 所有计数排除软删数据（`is_deleted == False`）。

- [ ] **Step 1: Write the failing test**

```python
"""统计概览语义测试。"""
from uuid import uuid4

from fastapi.testclient import TestClient


def test_overview_enum_keys_and_soft_delete(test_client: TestClient, auth_headers: dict, monkeypatch):
    monkeypatch.setattr("app.utils.s3_client.s3_client.ensure_bucket", lambda *a, **k: None)

    before = test_client.get("/api/v1/annotation/stats/overview", headers=auth_headers).json()["data"]
    base_ds = before["dataset_count"]

    ds = test_client.post(
        "/api/v1/annotation/dataset/create",
        json={"name": f"stat-{uuid4().hex[:8]}"}, headers=auth_headers,
    ).json()["data"]
    ds_id = ds["id"]
    task = test_client.post(
        "/api/v1/annotation/task/create",
        json={"dataset_id": ds_id, "name": f"t-{uuid4().hex[:6]}", "task_type": "detection"},
        headers=auth_headers,
    ).json()["data"]

    ov = test_client.get("/api/v1/annotation/stats/overview", headers=auth_headers).json()["data"]
    # 枚举键必须是值，而非 "AnnotationType.X"
    assert all(not k.startswith("AnnotationType.") for k in ov["tasks_by_type"])
    assert "detection" in ov["tasks_by_type"]
    assert all(not k.startswith("ImageStatus.") for k in ov["images_by_status"])

    # 软删数据集后，概览计数回到基线（证明过滤生效）
    deleted = test_client.request(
        "DELETE", "/api/v1/annotation/dataset/delete", json=[ds_id], headers=auth_headers
    )
    assert deleted.status_code == 200
    after = test_client.get("/api/v1/annotation/stats/overview", headers=auth_headers).json()["data"]
    assert after["dataset_count"] == base_ds, (after["dataset_count"], base_ds)
    assert task  # 任务创建成功
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/test_stats_overview.py -q`
Expected: FAIL（出现 `AnnotationType.detection` 键，或软删后计数未回到基线）。

- [ ] **Step 3: 后端实现**

`stats/service.py` 顶部加 `from app.core.base_params` 不需要；在 `get_overview`：

```python
            from sqlalchemy import and_
            not_deleted = lambda m: getattr(m, "is_deleted") == False  # noqa: E731
            dataset_count = await db.scalar(select(func.count(DatasetModel.id)).where(not_deleted(DatasetModel)))
            task_count = await db.scalar(select(func.count(AnnotationTaskModel.id)).where(not_deleted(AnnotationTaskModel)))
            image_count = await db.scalar(select(func.count(AnnotationImageModel.id)).where(not_deleted(AnnotationImageModel))) or 0
            annotated_count = await db.scalar(
                select(func.count(func.distinct(AnnotationRecordModel.image_id)))
                .where(not_deleted(AnnotationRecordModel))
            ) or 0
```

枚举键改为值：

```python
            tasks_by_type = {getattr(r[0], "value", r[0]): r[1] for r in type_rows}
            images_by_status = {getattr(r[0], "value", r[0]): r[1] for r in img_status_rows}
```

`get_dataset_stats` 的 unannotated/in_progress/annotated 三处 `where` 增加 `AnnotationImageModel.is_deleted == False`；`user_contributions` 改为按**标注条目数**统计：

```python
                    if isinstance(ann_data, list):
                        for item in ann_data:
                            cid = item.get("class_id") if isinstance(item, dict) else None
                            if cid is not None:
                                class_counter[cid] = class_counter.get(cid, 0) + 1
                                total_annotations += 1
                        if created_id:
                            user_counter[created_id] = user_counter.get(created_id, 0) + len(ann_data)
```

（即把原 `if created_id:` 的 `+1` 移到列表分支内按 `len(ann_data)` 累加；非 list 记录不计数。）

- [ ] **Step 4: 前端 page_size 修复**

`stats/index.vue:176`：`page_size: 999` → `page_size: 100`。

- [ ] **Step 5: Run test + type-check**

Run: `cd backend && uv run pytest tests/test_stats_overview.py -q && uv run pytest -q`
Run: `cd frontend && pnpm run type-check`
Expected: 通过。

- [ ] **Step 6: Playwright 统计页冒烟（可选但建议）**

在 `frontend/e2e/` 新增 `stats.spec.ts`：登录后（复用 storageState）访问 `/#/annotation/stats`，断言 4 张指标卡渲染且页面无「请求处理失败」。若指标卡选择器难以定位，至少断言 `.annotation-stats-page` 可见。

- [ ] **Step 7: Commit**

```bash
git add backend/app/api/v1/module_annotation/stats/service.py backend/tests/test_stats_overview.py frontend/src/views/module_annotation/stats/index.vue
git commit -m "fix(annotation): 统计页 page_size 合法化 + 排除软删/枚举键/贡献口径"
```

---

### Task 2: 任务备注 + 类别定义保存 + 移除死批量按钮

**背景:** `task/index.vue` 表单有"备注"字段但提交时未发送，且 `TaskCreateSchema`/`TaskUpdateSchema` 无 `description`（模型经 `ModelMixin` 已有该列）；创建任务固定 `classes: []`，无法在创建时定义类别；工具栏 `:perm-patch` 渲染"批量启用/停用"但无 `@more` 处理 → 点击无效（任务状态由进度推导，无启用/停用语义）。

**Files:**
- Modify: `backend/app/api/v1/module_annotation/task/schema.py`
- Modify: `frontend/src/views/module_annotation/task/index.vue`
- Test: `backend/tests/test_task_metadata.py`

**Interfaces:**
- `TaskCreateSchema`/`TaskUpdateSchema` 接受 `description: str | None = None` 与 `classes: list[dict] | None`（create 默认 `[]`）。

- [ ] **Step 1: Write the failing test**

```python
"""任务备注与类别保存测试。"""
from uuid import uuid4

from fastapi.testclient import TestClient


def test_create_task_persists_description_and_classes(test_client: TestClient, auth_headers: dict, monkeypatch):
    monkeypatch.setattr("app.utils.s3_client.s3_client.ensure_bucket", lambda *a, **k: None)
    ds = test_client.post(
        "/api/v1/annotation/dataset/create", json={"name": f"meta-{uuid4().hex[:8]}"}, headers=auth_headers
    ).json()["data"]
    ds_id = ds["id"]
    classes = [{"id": 0, "name": "person", "color": "#409eff"}]
    resp = test_client.post(
        "/api/v1/annotation/task/create",
        json={"dataset_id": ds_id, "name": f"t-{uuid4().hex[:6]}", "task_type": "detection",
              "description": "hello-desc", "classes": classes},
        headers=auth_headers,
    )
    assert resp.status_code == 200, resp.text
    task_id = resp.json()["data"]["id"]

    detail = test_client.get(f"/api/v1/annotation/task/{task_id}/detail", headers=auth_headers).json()["data"]
    assert detail["description"] == "hello-desc"
    assert detail["classes"][0]["name"] == "person"

    # update description
    upd = test_client.put(
        f"/api/v1/annotation/task/update/{task_id}",
        json={"description": "changed"}, headers=auth_headers,
    )
    assert upd.status_code == 200, upd.text
    detail2 = test_client.get(f"/api/v1/annotation/task/{task_id}/detail", headers=auth_headers).json()["data"]
    assert detail2["description"] == "changed"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/test_task_metadata.py -q`
Expected: FAIL（`description` 未被持久化 / schema 忽略该字段）。

- [ ] **Step 3: 后端 schema**

`task/schema.py`：

```python
class TaskCreateSchema(BaseModel):
    dataset_id: int
    name: str = Field(max_length=128)
    task_type: AnnotationType
    assignees: list[int] = Field(default_factory=list)
    classes: list[dict] = Field(default_factory=list)
    classification_mode: str | None = None
    description: str | None = None


class TaskUpdateSchema(BaseModel):
    name: str | None = Field(None, max_length=128)
    assignees: list[int] | None = None
    classes: list[dict] | None = None
    classification_mode: str | None = None
    description: str | None = None
```

（`AnnotationTaskModel` 经 `ModelMixin` 已有 `description` 列，无需迁移；`TaskOutSchema` 可加 `description: str | None = None` 以便列表返回。）

- [ ] **Step 4: 前端提交备注 + 类别**

`task/index.vue`：
- `handleSubmit` 的 update 载荷加入 `description: formData.description`；create 载荷加入 `description: formData.description`。
- 新增类别编辑器：在对话框加一个表单项（`el-form-item label="类别"`），用一个可增删的简单列表绑定 `formData.classes`（`reactive<{id:number;name:string;color:string}[]>`）。创建时用 `formData.classes`，编辑时从 `item.classes` 载入（`formData.classes = item.classes || []`）。
  - 简单实现：一个 `el-input` + "添加"按钮，下面是 `el-tag`（可关闭）列出已加类别；`id` 按 `max+1` 递增，`color` 从固定调色板循环分配。
- 提交载荷 create：`classes: formData.classes`（替换写死的 `[]`）。
- 移除死批量按钮：删除 `:perm-patch="['module_annotation:task:patch']"` 这一绑定（任务无启用/停用语义，避免误导）。若希望保留批量能力，改为真实动作（如批量删除）并在报告中说明。

- [ ] **Step 5: Run tests + type-check + e2e**

Run: `cd backend && uv run pytest tests/test_task_metadata.py -q && uv run pytest -q`
Run: `cd frontend && pnpm run type-check && pnpm e2e`
Expected: 通过；`e2e` 不回归。

- [ ] **Step 6: Commit**

```bash
git add backend/app/api/v1/module_annotation/task/schema.py backend/tests/test_task_metadata.py frontend/src/views/module_annotation/task/index.vue
git commit -m "fix(annotation): 任务备注/类别定义可保存，移除无效批量按钮"
```

---

## Self-Review

**Spec coverage（对照 Phase 1 spec 组件 E、F）:**
- 统计页 422 与语义 → Task 1 ✅
- 任务类定义 / 备注 / 批量接线 → Task 2 ✅（批量按钮按"任务无启用停用语义"移除，而非伪造状态）

**Placeholder scan:** 无 TBD；Task 2 的前端类别编辑器给了明确实现要点与数据结构。

**Type consistency:** `TaskCreateSchema.description`、`formData.classes`、统计键 `"detection"` 在使用处一致。

**风险:** 统计测试的基线 `base_ds` 依赖其它用例不并发改动数据集；pytest 串行执行，且用"软删后回到基线"断言，稳健。Task 2 编辑对话框需同时载入 `classes`，注意 `handleOpenDialog` 的 `item.classes` 可能是对象而非数组（后端 `classes` 列默认 `dict`），前端需容错（`Array.isArray(item.classes) ? item.classes : []`）。
