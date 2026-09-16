# Phase 1B：工作台正确性 + 导入健壮性 + 进度落库 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 修复标注工作台的三处丢稿/不可用问题（首图不加载、锁冲突仍可编辑、类编辑不标记未保存），让任务进度/状态真实落库，并加固 x-anylabeling 导入（zip-slip、同名覆盖、计数、类型推断、旋转框/分类往返）。

**Architecture:** 后端修 `TaskService.update_progress`（提交+软删过滤）与 `AnnotationService.save_annotations`（409）及导入器；前端修工作台 `annotation/index.vue` 的加载/锁/类编辑并加 Playwright 冒烟。

**Tech Stack:** FastAPI + SQLAlchemy + pytest（SQLite 文件库 `pytest_aistation.db`，可用标准库 `sqlite3` 断言持久化）；Vue3 + Playwright。

## Global Constraints

- 命令：后端 `D:\AIStation\backend`（`uv run pytest` / `uv run ruff check`，只判断新增问题）；前端 `D:\AIStation\frontend`（`pnpm run type-check` 无新增错误，`pnpm e2e` 通过）。
- 遵循现有中文 docstring/注释。不新增依赖。不改无关文件。
- 提交风格 `fix(annotation): 中文描述`；只 `git add` 本任务文件（禁 `git add -A`）。ruff `fix=true`，提交前还原被自动改动的无关文件。
- 标注坐标：工作台为**归一化 [0,1]**。
- 测试可用标准库 `sqlite3` 直连 `os.environ["DATABASE_NAME"] + ".db"` 校验落库。
- 运行中的服务：后端 8001、前端 `http://127.0.0.1:5180/web`（hash 路由）。E2E 登录 admin/123456（dev 关验证码）。

---

### Task 1: 任务进度/状态真实落库

**背景:** `TaskService.update_progress` 用 `async_db_session()`（无 commit）→ 写入被回滚，`progress`/`status`/`completed_at` 永远不更新（`task/service.py:14-23`）。`_calc_progress` 的 total 还包含软删图片（`task/service.py:36-39`）。

**Files:**
- Modify: `backend/app/api/v1/module_annotation/task/service.py`
- Test: `backend/tests/test_task_progress_persist.py`

**Interfaces:**
- `update_progress(task_id, auth=None) -> dict` —— 计算并**提交** `progress`/`status`，`progress>=100` 时写 `completed_at`；返回计算结果。

- [ ] **Step 1: Write the failing test**

```python
"""任务进度真实落库测试（sqlite 直连校验 commit）。"""
import os
import sqlite3
from uuid import uuid4

from fastapi.testclient import TestClient


def _db():
    return sqlite3.connect(os.environ["DATABASE_NAME"] + ".db")


def _make_dataset_and_task(test_client, auth_headers):
    name = f"prog-{uuid4().hex[:8]}"
    ds = test_client.post("/api/v1/annotation/dataset/create", json={"name": name}, headers=auth_headers).json()["data"]
    ds_id = ds["id"]
    # upload one image (monkeypatch S3 in the caller)
    files = {"files": ("a.png", b"\x89PNG\r\n\x1a\n" + b"0" * 32, "image/png")}
    test_client.post(f"/api/v1/annotation/dataset/{ds_id}/upload", files=files, headers=auth_headers)
    task = test_client.post(
        "/api/v1/annotation/task/create",
        json={"dataset_id": ds_id, "name": f"t-{name}", "task_type": "detection"},
        headers=auth_headers,
    ).json()["data"]
    return ds_id, task["id"]


def test_progress_persisted_after_save(test_client: TestClient, auth_headers: dict, monkeypatch):
    monkeypatch.setattr("app.utils.s3_client.s3_client.ensure_bucket", lambda *a, **k: None)
    monkeypatch.setattr("app.utils.s3_client.s3_client.upload_fileobj", lambda *a, **k: None)
    monkeypatch.setattr("app.utils.s3_client.s3_client.download_fileobj", lambda *a, **k: __import__("io").BytesIO(b"x"))

    ds_id, task_id = _make_dataset_and_task(test_client, auth_headers)

    con = _db()
    img_id = con.execute(
        "SELECT id FROM annotation_image WHERE dataset_id=? ORDER BY id LIMIT 1", (ds_id,)
    ).fetchone()[0]
    con.close()

    # annotate the only image
    put = test_client.put(
        f"/api/v1/anno/image/{img_id}/annotations",
        json={"task_id": task_id, "image_id": img_id,
              "annotation_data": [{"type": "AxisAlignedBox", "class_id": 0, "x1": 0.1, "y1": 0.1, "x2": 0.2, "y2": 0.2}]},
        headers=auth_headers,
    )
    assert put.status_code == 200, put.text

    # trigger update_progress (list endpoint calls it)
    test_client.get("/api/v1/annotation/task/list", params={"page_no": 1, "page_size": 50}, headers=auth_headers)

    con = _db()
    progress, status = con.execute(
        "SELECT progress, status FROM annotation_task WHERE id=?", (task_id,)
    ).fetchone()
    con.close()
    assert progress == 100, f"progress should be persisted, got {progress}"
    assert str(status).lower() in ("completed", "complete")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/test_task_progress_persist.py -q`
Expected: FAIL（`progress` 仍为 0 → 断言失败）。

- [ ] **Step 3: Write minimal implementation**

`task/service.py`：

```python
    @classmethod
    async def update_progress(cls, task_id: int, auth=None) -> dict:
        from datetime import datetime

        async with async_db_session.begin() as db:
            task = await db.get(AnnotationTaskModel, task_id)
            if not task:
                log.warning(f"update_progress: task {task_id} not found")
                return {}
            result = await cls._calc_progress(db, task_id, task.dataset_id)
            if result:
                task.progress = result["progress"]
                task.status = result["status"]
                if result["progress"] >= 100:
                    task.completed_at = task.completed_at or datetime.now()
                else:
                    task.completed_at = None
            return result
```

`_calc_progress` 的 total 增加软删过滤：

```python
        total = await db.scalar(
            select(func.count(AnnotationImageModel.id))
            .where(
                AnnotationImageModel.dataset_id == dataset_id,
                AnnotationImageModel.is_deleted == False,  # noqa: E712
            )
        ) or 0
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && uv run pytest tests/test_task_progress_persist.py -q`
Expected: PASS

- [ ] **Step 5: full suite + ruff + commit**

Run: `cd backend && uv run pytest -q && uv run ruff check app/api/v1/module_annotation/task/service.py`

```bash
git add backend/app/api/v1/module_annotation/task/service.py backend/tests/test_task_progress_persist.py
git commit -m "fix(annotation): 任务进度/状态真实落库并过滤软删图片"
```

---

### Task 2: 图片硬锁 + 保存冲突返回 409

**背景:** `save_annotations` 在图片被他人锁定时抛 `ValueError` → 全局映射为 400；前端 `loadImg` 仅 `ElMessage.warning` 后仍允许编辑，保存时才失败，用户体验差且可能丢稿（`annotation/service.py:44-47`，`index.vue:3192-3204`）。

**Files:**
- Modify: `backend/app/api/v1/module_annotation/annotation/service.py`
- Modify: `frontend/src/views/module_annotation/annotation/index.vue`
- Test: `backend/tests/test_annotation_lock_conflict.py`

**Interfaces:**
- `save_annotations` 在图片被**他人**锁定时抛 `CustomException(msg=..., code=409, status_code=409)`；未被任何人锁定时保持允许保存（向后兼容）。

- [ ] **Step 1: Write the failing test**

```python
"""保存冲突返回 409 测试。"""
import os
import sqlite3
from uuid import uuid4

from fastapi.testclient import TestClient


def test_save_conflict_returns_409(test_client: TestClient, auth_headers: dict, monkeypatch):
    monkeypatch.setattr("app.utils.s3_client.s3_client.ensure_bucket", lambda *a, **k: None)
    monkeypatch.setattr("app.utils.s3_client.s3_client.upload_fileobj", lambda *a, **k: None)

    ds = test_client.post("/api/v1/annotation/dataset/create", json={"name": f"lock-{uuid4().hex[:8]}"}, headers=auth_headers).json()["data"]
    ds_id = ds["id"]
    files = {"files": ("a.png", b"\x89PNG\r\n\x1a\n" + b"0" * 32, "image/png")}
    test_client.post(f"/api/v1/annotation/dataset/{ds_id}/upload", files=files, headers=auth_headers)
    task = test_client.post(
        "/api/v1/annotation/task/create",
        json={"dataset_id": ds_id, "name": f"t-{uuid4().hex[:6]}", "task_type": "detection"},
        headers=auth_headers,
    ).json()["data"]

    db = sqlite3.connect(os.environ["DATABASE_NAME"] + ".db")
    img_id = db.execute("SELECT id FROM annotation_image WHERE dataset_id=? ORDER BY id LIMIT 1", (ds_id,)).fetchone()[0]
    # 模拟“被他人锁定”
    db.execute("UPDATE annotation_image SET locked_by=987654 WHERE id=?", (img_id,))
    db.commit()
    db.close()

    resp = test_client.put(
        f"/api/v1/anno/image/{img_id}/annotations",
        json={"task_id": task["id"], "image_id": img_id, "annotation_data": []},
        headers=auth_headers,
    )
    assert resp.status_code == 409, resp.text
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/test_annotation_lock_conflict.py -q`
Expected: FAIL（当前返回 400）。

- [ ] **Step 3: 后端实现 409**

`annotation/service.py` 顶部：

```python
from app.core.exceptions import CustomException
```

把：

```python
            if img and img.locked_by and img.locked_by != auth.user.id:
                raise ValueError("图片已被其他用户锁定")
```

改为：

```python
            if img and img.locked_by and img.locked_by != auth.user.id:
                raise CustomException(msg="图片已被其他用户锁定，无法保存", code=409, status_code=409)
```

- [ ] **Step 4: 前端锁定只读**

在 `annotation/index.vue` `loadImg` 的 lock 回调中（`d?.locked` 分支）：设置只读状态并显示横幅，且在关闭时清除。新增状态（`<script setup>` 内）：

```ts
const lockedByOther = ref(false);
const lockedByUser = ref<number | null>(null);
```

回调改为：

```ts
        if (d?.locked) {
          lockedByOther.value = true;
          lockedByUser.value = d.locked_by ?? null;
          ElMessage.warning(`该图片已被 ${d.locked_by || "其他用户"} 锁定，只读`);
        } else {
          lockedByOther.value = false;
          lockedByUser.value = null;
        }
```

在 `loadImg` 开头（`store.annotations = []` 附近）重置：

```ts
  lockedByOther.value = false;
  lockedByUser.value = null;
```

在页面模板顶部加只读横幅（放在 `.ann-page` 内）：**先阅读模板找到主容器 class（`.ann-page`）**，插入：

```html
    <el-alert
      v-if="lockedByOther"
      type="warning"
      :closable="false"
      show-icon
      title="该图片已被其他用户锁定，当前为只读模式"
      class="ann-lock-banner"
    />
```

在每个会修改 `store.annotations` 的入口（绘制开始、拖拽开始、删除/复制等）加守卫 `if (lockedByOther.value) return;`。实现者需 grep 找到这些入口函数（如处理 `mousedown`/`dblclick` 的绘制函数、`markUnsaved` 前的变更点），并在报告中列出所加守卫的位置。至少保证：只读时无法开始新绘制、无法拖动已有标注。

- [ ] **Step 5: 运行后端测试 + 前端类型检查**

Run: `cd backend && uv run pytest tests/test_annotation_lock_conflict.py -q && uv run pytest -q`
Run: `cd frontend && pnpm run type-check`
Expected: 后端 PASS；前端无新增错误。

- [ ] **Step 6: Commit**

```bash
git add backend/app/api/v1/module_annotation/annotation/service.py backend/tests/test_annotation_lock_conflict.py frontend/src/views/module_annotation/annotation/index.vue
git commit -m "fix(annotation): 锁冲突保存返回 409，前端只读模式防止丢稿"
```

---

### Task 3: 首图自动加载 + 类编辑未保存/错误不吞

**背景:** `index.vue:3588` 在赋值 `store.images` 后判断 `!store.currentImage`（此时已为真）→ 首图永不加载；`removeClass`（1752-1767）改动标注但不 `markUnsaved/pushHistory` → 刷新丢失；`saveClassesToTask`（1768-1773）`catch {}` 吞错。

**Files:**
- Modify: `frontend/src/views/module_annotation/annotation/index.vue`
- Test: `frontend/e2e/workbench.spec.ts`（新增）

**Interfaces:**
- 进入工作台后首图自动加载渲染；类删除标记未保存并可持久化；类保存失败有提示。

- [ ] **Step 1: 修首图加载**

把 `index.vue:3588` 的：

```ts
        if (imgs.length > 0 && !store.currentImage) loadImg(imgs[0].id);
```

改为：

```ts
        if (imgs.length > 0 && store.currentImageIndex >= 0 && store.currentImageIndex < imgs.length) {
          loadImg(imgs[store.currentImageIndex].id);
        } else if (imgs.length > 0) {
          store.currentImageIndex = 0;
          loadImg(imgs[0].id);
        }
```

- [ ] **Step 2: 修类编辑未保存与错误吞没**

`removeClass` 在改动 `store.annotations` 后加入 `markUnsaved(); pushHistory();`（放在过滤之后、`saveClassesToTask()` 之前）：

```ts
  store.annotations = store.annotations.filter(
    (a: any) => a.class_id !== -1 && !(a.type === "Classification" && !a.class_ids?.length)
  );
  markUnsaved();
  pushHistory();
  if (selectedClassId.value === id) selectedClassId.value = taskClasses.value[0]?.id ?? 0;
  saveClassesToTask();
```

`saveClassesToTask` 不再吞错：

```ts
async function saveClassesToTask() {
  if (!task.value?.id) return;
  try {
    await AnnotationAPI.updateTask(task.value.id, { classes: taskClasses.value });
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.msg || e?.msg || "类别保存失败，请重试");
  }
}
```

- [ ] **Step 3: Write the failing Playwright test**

创建 `frontend/e2e/workbench.spec.ts`：

```ts
import { test, expect } from "@playwright/test";

const API = process.env.E2E_API_URL || "http://127.0.0.1:8001/api/v1";
const PNG = Buffer.from(
  "89504e470d0a1a0a0000000d4948445200000010000000100806000000" +
  "1ff3ff610000001d4944415478da63fccfc0f01f8a1930e2d4a8016206" +
  "8c38b5e8d40300b7c02f9c1b3b5c0000000049454e44ae426082",
  "hex"
);

test("工作台首图自动加载", async ({ page, request }) => {
  const login = await request.post(`${API}/system/auth/login`, {
    form: { username: "admin", password: "123456" },
    headers: { "X-Forwarded-For": "127.0.0.1" },
  });
  const token = (await login.json()).data.access_token;
  const auth = { Authorization: `Bearer ${token}` };

  const name = `wb-${Date.now()}`;
  const ds = await (await request.post(`${API}/annotation/dataset/create`, { data: { name }, headers: auth })).json();
  const dsId = ds.data.id;
  await request.post(`${API}/annotation/dataset/${dsId}/upload`, {
    headers: auth,
    multipart: { files: { name: "a.png", mimeType: "image/png", buffer: PNG } },
  });
  const task = await (await request.post(`${API}/annotation/task/create`, {
    data: { dataset_id: dsId, name: `t-${name}`, task_type: "detection" }, headers: auth,
  })).json();
  const taskId = task.data.id;

  await page.goto(`/#/annotation/workbench/${taskId}`, { waitUntil: "domcontentloaded" });
  // 首图应自动加载：不出现 “No image loaded”，且 SVG 画布可见
  await expect(page.locator("text=No image loaded")).toHaveCount(0);
  await expect(page.locator(".ann-svg").first()).toBeVisible({ timeout: 15_000 });
  await expect(page.locator("img.ann-img").first()).toBeVisible({ timeout: 15_000 });
});
```

（若真实 DOM 的图片/画布选择器不同，按实际调整并在报告记录；断言意图保持：首图自动加载渲染。）

- [ ] **Step 4: 运行 E2E + 类型检查**

Run: `cd frontend && pnpm run type-check && pnpm e2e`
Expected: `workbench.spec.ts` 通过；其余用例不回归。

- [ ] **Step 5: Commit**

```bash
git add frontend/src/views/module_annotation/annotation/index.vue frontend/e2e/workbench.spec.ts
git commit -m "fix(annotation): 工作台首图自动加载 + 类编辑标记未保存/错误提示"
```

---

### Task 4: x-anylabeling 导入健壮性

**背景:** `x_anylabeling_importer.py`：`zf.extractall` 有 zip-slip（47-48）；图片/JSON 按 stem 键控导致同名跨目录/跨扩展名互相覆盖（59-70）；`object_key` 用 stem → 重复导入覆盖（119）；`image_count/annotated_count` 用 `+=` 累加 → 重复导入 double count（183-184）；任务类型恒为 DETECTION（95-96）；不识别 `rotation`/分类 flags（204-256）；类无 color。

**Files:**
- Modify: `backend/app/api/v1/module_annotation/dataset/x_anylabeling_importer.py`
- Test: `backend/tests/test_xanylabeling_importer.py`

**Interfaces:**
- Produces: `_safe_extract(zf, dest) -> None`（拒绝越界成员）。
- Produces: `_infer_task_type(shapes_all: list[dict]) -> str`（含 rotation→rotated_detection；仅 point→keypoint；仅 polygon→segmentation；否则 detection）。
- `_shape_to_annotation` 支持 `shape_type == "rotation"`（4 点 → RotatedBox，归一化）。

- [ ] **Step 1: Write the failing tests**

```python
"""x-anylabeling 导入健壮性单元测试。"""
import io
import zipfile

import pytest

from app.api.v1.module_annotation.dataset import x_anylabeling_importer as imp


def test_safe_extract_rejects_zip_slip(tmp_path):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("../../evil.txt", "x")
    buf.seek(0)
    with zipfile.ZipFile(buf) as zf:
        with pytest.raises(ValueError):
            imp._safe_extract(zf, str(tmp_path / "out"))


def test_infer_task_type():
    assert imp._infer_task_type([{"shape_type": "rectangle"}]) == "detection"
    assert imp._infer_task_type([{"shape_type": "polygon"}]) == "segmentation"
    assert imp._infer_task_type([{"shape_type": "point"}]) == "keypoint"
    assert imp._infer_task_type([{"shape_type": "rotation"}]) == "rotated_detection"


def test_shape_rotation_to_rotated_box():
    shape = {"label": "t", "shape_type": "rotation",
             "points": [[10, 10], [30, 10], [30, 20], [10, 20]]}
    ann = imp._shape_to_annotation(shape, {"t": 0}, 100, 100)
    assert ann["type"] == "RotatedBox"
    assert 0 <= ann["cx"] <= 1 and 0 <= ann["cy"] <= 1
    assert ann["width"] > 0 and ann["height"] > 0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && uv run pytest tests/test_xanylabeling_importer.py -q`
Expected: FAIL（`_safe_extract`/`_infer_task_type` 不存在；rotation 返回 None）。

- [ ] **Step 3: Write minimal implementation**

在 `x_anylabeling_importer.py` 增加：

```python
def _safe_extract(zf: zipfile.ZipFile, dest: str) -> None:
    """解压并拒绝任何越界的 zip 成员（zip-slip）。"""
    dest_abs = os.path.abspath(dest)
    for member in zf.namelist():
        target = os.path.abspath(os.path.join(dest, member))
        if not (target == dest_abs or target.startswith(dest_abs + os.sep)):
            raise ValueError(f"非法的压缩包路径: {member}")
    zf.extractall(dest)


def _infer_task_type(shapes_all: list[dict]) -> str:
    """按形状推断任务类型。"""
    types = {s.get("shape_type") for s in shapes_all}
    if "rotation" in types:
        return "rotated_detection"
    if types == {"point"}:
        return "keypoint"
    if types == {"polygon"}:
        return "segmentation"
    return "detection"
```

把 `zf.extractall(extract_dir)` 改为 `_safe_extract(zf, extract_dir)`。

在 `_import_from_dir` 收集完 `all_labels` 后，额外收集全部 shapes 并推断类型：

```python
    all_shapes: list[dict] = []
    for stem, jp in json_files.items():
        try:
            with open(jp, encoding="utf-8") as f:
                data = json.load(f)
            all_shapes.extend(data.get("shapes", []))
        except Exception:
            continue
    task_type = _infer_task_type(all_shapes)
```

并把原来 `task_type = AnnotationType.DETECTION` 替换为上面的推断结果（注意 `task_type` 需要是 `AnnotationType` 值；`_infer_task_type` 返回字符串，赋给 `AnnotationTaskModel(task_type=...)` 时 SAEnum 绑定字符串即可；若不行则用 `AnnotationType(task_type_str)` 转换）。

在 `_shape_to_annotation` 增加 rotation 分支：

```python
    elif shape_type == "rotation" and len(points) >= 4:
        import math
        xs = [p[0] / img_w if img_w else 0 for p in points[:4]]
        ys = [p[1] / img_h if img_h else 0 for p in points[:4]]
        cx = sum(xs) / 4
        cy = sum(ys) / 4
        # 以第 1、2 点估算宽与角度
        dx = (points[1][0] - points[0][0]) / img_w if img_w else 0
        dy = (points[1][1] - points[0][1]) / img_h if img_h else 0
        width = math.hypot(dx, dy)
        # 高由第 2、3 点估算
        ex = (points[2][0] - points[1][0]) / img_w if img_w else 0
        ey = (points[2][1] - points[1][1]) / img_h if img_h else 0
        height = math.hypot(ex, ey)
        angle = math.atan2(dy, dx)
        return {
            "id": uuid.uuid4().hex, "type": "RotatedBox", "class_id": class_id,
            "label": label, "cx": cx, "cy": cy, "width": width, "height": height, "angle": angle,
        }
```

其余修复：
- 键控改为 `(相对目录, stem)`：把 `json_files`/`image_files` 的 key 由 `stem` 改为 `os.path.relpath(path, src_dir)` 的文件名 stem（含父目录），并在取用侧相应调整（sidecar 匹配仍按同目录同 stem）。
- `object_key` 用 `uuid.uuid4().hex` 前缀避免重复导入覆盖：`f"annotations/dataset_{dataset_id}/{uuid.uuid4().hex}{ext}"`。
- 计数改为**重算**：导入后 `ds.image_count = count(images where dataset_id and not is_deleted)`、`ds.annotated_count = count(distinct image_id in records)`，不再 `+=`。
- 类定义补 `color`：按调色板循环分配。
- 支持分类 flags：若 sidecar `flags` 含 `classification`，生成 `{"type": "Classification", "class_ids": [...], "label": ...}` 标注（class_mapping 需包含这些名）。

（本步改动较大，按上述要点完成，测试覆盖 `_safe_extract`/`_infer_task_type`/rotation 三个纯函数即可，其余以代码审查 + 一个内存 zip 集成测试验证。）

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && uv run pytest tests/test_xanylabeling_importer.py -q`
Expected: PASS

- [ ] **Step 5: full suite + ruff + commit**

Run: `cd backend && uv run pytest -q && uv run ruff check app/api/v1/module_annotation/dataset/x_anylabeling_importer.py`

```bash
git add backend/app/api/v1/module_annotation/dataset/x_anylabeling_importer.py backend/tests/test_xanylabeling_importer.py
git commit -m "fix(annotation): x-anylabeling 导入防 zip-slip/同名覆盖、重算计数、类型推断"
```

---

## Self-Review

**Spec coverage（对照 Phase 1 spec 组件 B、D、A）:**
- 首图自动加载 / 类编辑未保存 / 错误不吞 → Task 3 ✅
- 硬锁 + 409 不丢稿 → Task 2 ✅
- 进度/状态落库 → Task 1 ✅
- 导入健壮性（zip-slip/计数/类型/旋转/分类/颜色）→ Task 4 ✅

**Placeholder scan:** 无 TBD；Task 2/4 涉及模板/多处入口的部分给了明确模式与"实现者需 grep 定位"的说明（非占位，而是要求按真实代码落地并列报告）。

**Type consistency:** `lockedByOther`/`lockedByUser`、`_safe_extract`、`_infer_task_type` 在定义与使用处一致。

**风险:** Task 3 Step 1 的选择器需与真实 DOM 对齐（已给调整指引）；Task 4 的键控从 stem 改为相对路径 stem 会影响 sidecar 匹配逻辑，需整体一致改动，若不慎会漏配对——以集成 zip 测试兜底。
