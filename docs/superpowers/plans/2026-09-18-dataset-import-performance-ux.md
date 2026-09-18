# 数据集列表性能与导入体验 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax.

**Goal:** 消除数据集列表 N+1/读时写、把 750MB 级 x-anylabeling 导入改为带进度的后台任务、并收纳操作列与导入入口。

**Architecture:** 后端列表改单次聚合只读查询；导入改为进程内 job 注册表 + `asyncio.create_task` 后台处理，导入器直接从 zip 字节分批并发上传（含缩略图）并分事务落库；前端操作列改「主操作+更多」，导入入口下沉到行内并展示进度。

**Tech Stack:** FastAPI、SQLAlchemy async、boto3、Pillow、Vue3 + Element Plus、pytest、Playwright。

## Global Constraints

- 中文注释与中文提交信息（`feat(annotation): ...`）。
- 提交前跑：`uv run ruff check`（新增文件无新错误）、`uv run pytest`（全绿）、`pnpm run type-check`（annotation 无新错误）。
- 前端新组件单根；布局用 el-row/el-col。
- 导入不接受非 zip；大小上限 `ANNOTATION_IMPORT_MAX_MB=1024`。
- 后台任务必须先物化上传字节（`await file.read()`），不得依赖请求结束后的 `UploadFile`。
- 缩略图 key 约定：`datasets/{datasetId}/thumbnails/{uuid}.jpg`；导入原图 key 沿用 `annotations/dataset_{datasetId}/{uuid}{ext}`。

---

### Task 1: 导入相关配置项

**Files:** Modify `backend/app/config/setting.py`

- [ ] 在标注媒体配置块后新增：

```python
    # 单次 x-anylabeling 导入 ZIP 大小上限（MB）
    ANNOTATION_IMPORT_MAX_MB: int = 1024
    # 导入时图片处理（PIL+缩略图+S3）并发度
    ANNOTATION_IMPORT_CONCURRENCY: int = 8
    # 导入每批处理数量（每批一个 DB 事务）
    ANNOTATION_IMPORT_BATCH_SIZE: int = 50
```

- [ ] 验证：`uv run python -c "from app.config.setting import settings; print(settings.ANNOTATION_IMPORT_BATCH_SIZE)"` → `50`
- [ ] Commit：`git commit -m "feat(annotation): 新增导入任务配置项"`

---

### Task 2: 数据集列表聚合查询（去 N+1 / 去读时写）

**Files:**
- Modify `backend/app/api/v1/module_annotation/dataset/controller.py`（删除逐条循环）
- Modify `backend/app/api/v1/module_annotation/dataset/service.py`（新增 `enrich_dataset_list`）
- Test `backend/tests/test_dataset_list_progress.py`

**Interfaces:**
- Produces: `DatasetService.enrich_dataset_list(db, items: list[dict]) -> None`（就地填充 `task_count` 与 `tasks`，每个任务 `{id,name,task_type,status,progress}`）

- [ ] **Step 1: 写失败测试**

```python
"""数据集列表进度聚合测试。"""
from uuid import uuid4

_FAKE_PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 64


def test_list_progress_uses_aggregate(test_client, auth_headers, monkeypatch):
    monkeypatch.setattr("app.utils.s3_client.s3_client.ensure_bucket", lambda *a, **k: None)
    monkeypatch.setattr("app.utils.s3_client.s3_client.upload_fileobj", lambda *a, **k: None)
    name = f"agg-{uuid4().hex[:8]}"
    ds = test_client.post("/api/v1/annotation/dataset/create",
                          json={"name": name}, headers=auth_headers).json()["data"]
    ds_id = ds["id"]
    test_client.post(
        f"/api/v1/annotation/dataset/{ds_id}/upload",
        files={"files": ("a.png", _FAKE_PNG, "image/png")}, headers=auth_headers)
    task = test_client.post("/api/v1/annotation/task/create",
                            json={"dataset_id": ds_id, "name": "t", "task_type": "detection"},
                            headers=auth_headers).json()["data"]
    # 保存一个非空标注
    items = test_client.get(
        f"/api/v1/annotation/dataset/{ds_id}/images", headers=auth_headers
    ).json()["data"]["items"]
    test_client.put(
        f"/api/v1/annotation/anno/image/{items[0]['id']}/annotations",
        json={"task_id": task["id"], "image_id": items[0]["id"],
              "annotation_data": [{"type": "AxisAlignedBox", "id": "x"}]},
        headers=auth_headers)

    listed = test_client.get(
        "/api/v1/annotation/dataset/list",
        params={"page_no": 1, "page_size": 100, "name": name}, headers=auth_headers,
    ).json()["data"]["items"]
    row = next(i for i in listed if i["id"] == ds_id)
    assert row["task_count"] == 1
    assert row["tasks"][0]["progress"] == 100
```

- [ ] **Step 2: 运行确认失败**：`uv run pytest tests/test_dataset_list_progress.py -v` → 进度断言失败（当前为 0 或报错）
- [ ] **Step 3: 实现 `enrich_dataset_list`**（置于 `service.py`，用本页 id 一次聚合）

```python
    @classmethod
    async def enrich_dataset_list(cls, db, items: list[dict]) -> None:
        """为本页数据集就地填充任务列表与进度（单次聚合、只读）。"""
        if not items:
            return
        ids = [i["id"] for i in items]
        total_rows = await db.execute(
            select(AnnotationImageModel.dataset_id, func.count(AnnotationImageModel.id))
            .where(AnnotationImageModel.dataset_id.in_(ids),
                   AnnotationImageModel.is_deleted == False)  # noqa: E712
            .group_by(AnnotationImageModel.dataset_id)
        )
        totals = {d: c for d, c in total_rows.fetchall()}

        task_rows = (await db.execute(
            select(AnnotationTaskModel).where(AnnotationTaskModel.dataset_id.in_(ids))
        )).scalars().all()
        task_ids = [t.id for t in task_rows]

        ann: dict[int, int] = {}
        if task_ids:
            max_v = select(
                AnnotationRecordModel.task_id.label("task_id"),
                AnnotationRecordModel.image_id.label("image_id"),
                func.max(AnnotationRecordModel.version).label("mv"),
            ).where(AnnotationRecordModel.task_id.in_(task_ids)).group_by(
                AnnotationRecordModel.task_id, AnnotationRecordModel.image_id
            ).subquery()
            json_length = (
                func.json_array_length if settings.DATABASE_TYPE == "sqlite"
                else func.jsonb_array_length
            )
            ann_rows = await db.execute(
                select(AnnotationRecordModel.task_id, func.count())
                .select_from(AnnotationRecordModel)
                .join(max_v, and_(
                    AnnotationRecordModel.task_id == max_v.c.task_id,
                    AnnotationRecordModel.image_id == max_v.c.image_id,
                    AnnotationRecordModel.version == max_v.c.mv,
                ))
                .where(AnnotationRecordModel.annotation_data.isnot(None),
                       json_length(AnnotationRecordModel.annotation_data) > 0)
                .group_by(AnnotationRecordModel.task_id)
            )
            ann = {t: c for t, c in ann_rows.fetchall()}

        by_ds: dict[int, list] = {}
        for t in task_rows:
            by_ds.setdefault(t.dataset_id, []).append(t)

        for item in items:
            ds_tasks = by_ds.get(item["id"], [])
            total = totals.get(item["id"], 0)
            out = []
            for t in ds_tasks:
                pct = int(ann.get(t.id, 0) / total * 100) if total > 0 else 0
                out.append({
                    "id": t.id, "name": t.name, "task_type": t.task_type,
                    "status": "completed" if pct >= 100 else "in_progress" if pct > 0 else "pending",
                    "progress": pct,
                })
            item["task_count"] = len(ds_tasks)
            item["tasks"] = out
```

- [ ] **Step 4: controller 改为调用聚合**（替换 `if result.get("items"): async with ... for item ...` 整段）

```python
    if result.get("items"):
        async with async_db_session() as db:
            await DatasetService.enrich_dataset_list(db, result["items"])
```

- [ ] **Step 5: 运行测试**：`uv run pytest tests/test_dataset_list_progress.py tests/test_dataset_purge.py -q` → PASS
- [ ] **Step 6: 实测**（服务在跑时）：带 token 请求 `/annotation/dataset/list?page_size=100`，目标 < 1s
- [ ] **Step 7: Commit**：`git commit -m "perf(annotation): 数据集列表进度改单次聚合只读查询"`

---

### Task 3: 导入任务注册表

**Files:** Create `backend/app/api/v1/module_annotation/dataset/import_jobs.py`

**Interfaces:**
- Produces: `ImportJob`（dataclass）、`create_job(dataset_id,user_id)->ImportJob`、`get_job(job_id)->ImportJob|None`、`update_job(job_id, **fields)->None`

- [ ] **Step 1: 实现**

```python
"""x-anylabeling 导入后台任务注册表（进程内，uvicorn 单 worker 安全）。"""
import uuid
from dataclasses import dataclass, field


@dataclass
class ImportJob:
    job_id: str
    dataset_id: int
    user_id: int
    status: str = "pending"  # pending|running|done|failed
    phase: str = ""
    processed: int = 0
    total: int = 0
    imported: int = 0
    total_annotations: int = 0
    task_id: int | None = None
    task_name: str = ""
    error: str | None = None


_JOBS: dict[str, ImportJob] = {}


def create_job(dataset_id: int, user_id: int) -> ImportJob:
    job = ImportJob(job_id=uuid.uuid4().hex, dataset_id=dataset_id, user_id=user_id)
    _JOBS[job.job_id] = job
    return job


def get_job(job_id: str) -> ImportJob | None:
    return _JOBS.get(job_id)
```

- [ ] **Step 2: 验证导入**：`uv run python -c "from app.api.v1.module_annotation.dataset.import_jobs import create_job; print(create_job(1,1).job_id)"`
- [ ] **Step 3: Commit**：`git commit -m "feat(annotation): 新增导入后台任务注册表"`

---

### Task 4: 导入器改为 bytes + 分批并发 + 缩略图

**Files:**
- Modify `backend/app/api/v1/module_annotation/dataset/x_anylabeling_importer.py`
- Test `backend/tests/test_dataset_import_job.py`

**Interfaces:**
- Consumes: `media.process_image`、`media.content_type_for`、`s3_client`、`settings`
- Produces: `async def import_x_anylabeling_bytes(data: bytes, dataset_id: int, user_id: int, progress_cb=None) -> dict`（返回 `{imported,total_images,total_annotations,class_mapping,task_id,task_name}`；`progress_cb(processed:int,total:int,phase:str)` 可空）

- [ ] **Step 1: 写失败测试（含进度回调）**

```python
"""导入任务端到端（小 zip，mock S3）。"""
import io
import json
import zipfile
from uuid import uuid4


def _make_zip() -> bytes:
    from PIL import Image
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for i in range(3):
            im = io.BytesIO()
            Image.new("RGB", (40, 20), (10, 10, 10)).save(im, format="PNG")
            z.writestr(f"d/frame_{i}.png", im.getvalue())
            z.writestr(f"d/frame_{i}.json", json.dumps({
                "imageWidth": 40, "imageHeight": 20,
                "shapes": [{"label": "text", "shape_type": "rectangle",
                            "points": [[1, 1], [30, 1], [30, 15], [1, 15]]}],
            }))
    return buf.getvalue()


def test_import_bytes_end_to_end(test_client, auth_headers, monkeypatch):
    import asyncio
    monkeypatch.setattr("app.utils.s3_client.s3_client.ensure_bucket", lambda *a, **k: None)
    monkeypatch.setattr("app.utils.s3_client.s3_client.upload_fileobj", lambda *a, **k: None)
    monkeypatch.setattr("app.utils.s3_client.s3_client.presigned_url", lambda k, *a, **k2: f"http://f/{k}")

    ds = test_client.post("/api/v1/annotation/dataset/create",
                          json={"name": f"imp-{uuid4().hex[:8]}"}, headers=auth_headers).json()["data"]
    from app.api.v1.module_annotation.dataset.x_anylabeling_importer import import_x_anylabeling_bytes

    seen: list[tuple[int, int, str]] = []
    result = asyncio.run(import_x_anylabeling_bytes(
        _make_zip(), ds["id"], 1, progress_cb=lambda p, t, ph: seen.append((p, t, ph))))

    assert result["imported"] == 3
    assert result["total_annotations"] == 3
    assert result["task_id"]
    assert seen and seen[-1][0] == 3 and seen[-1][1] == 3

    items = test_client.get(
        f"/api/v1/annotation/dataset/{ds['id']}/images", headers=auth_headers
    ).json()["data"]["items"]
    assert len(items) == 3
    assert all(i["thumbnail_key"] for i in items)
```

- [ ] **Step 2: 运行确认失败**：`uv run pytest tests/test_dataset_import_job.py -v` → `ImportError`
- [ ] **Step 3: 实现**

在 `x_anylabeling_importer.py` 顶部补充 import：

```python
import asyncio
import io
import posixpath

from app.api.v1.module_annotation.dataset.media import content_type_for, process_image
from app.config.setting import settings
```

新增：

```python
async def import_x_anylabeling_bytes(data: bytes, dataset_id: int, user_id: int,
                                     progress_cb=None) -> dict:
    """从 ZIP 字节导入（流式读成员，分批并发上传 + 缩略图，分事务落库）。"""
    image_extensions = {".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff", ".webp"}
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        json_files: dict[tuple[str, str], str] = {}
        entries: list[dict] = []
        for info in zf.infolist():
            if info.is_dir():
                continue
            name = info.filename.replace("\\", "/")
            reldir, base = posixpath.split(name)
            stem, ext = posixpath.splitext(base)
            el = ext.lower()
            if el == ".json":
                json_files[(reldir, stem)] = name
            elif el in image_extensions:
                entries.append({"zip_name": name, "reldir": reldir, "stem": stem,
                                "ext": ext, "basename": base})

        if not entries:
            return {"imported": 0, "total_images": 0, "total_annotations": 0,
                    "class_mapping": {}, "task_id": None,
                    "error": "ZIP 中未找到图片文件"}

        # filename 消歧（沿用既有规则）
        basename_counts = Counter(e["basename"] for e in entries)
        used: set[str] = set()
        for e in entries:
            if basename_counts[e["basename"]] == 1:
                cand = e["basename"]
            else:
                prefix = e["reldir"].replace("/", "__")
                cand = f"{prefix}__{e['basename']}" if prefix else e["basename"]
            final, idx = cand, 1
            while final in used:
                s, x = os.path.splitext(cand)
                idx += 1
                final = f"{s}_{idx}{x}"
            used.add(final)
            e["filename"] = final

        # 扫描 JSON：类映射 + 形状集合
        all_labels: set[str] = set()
        all_shapes: list[dict] = []
        jsons_cache: dict[str, dict] = {}
        for key, zname in json_files.items():
            try:
                meta = json.loads(zf.read(zname).decode("utf-8"))
            except Exception:
                continue
            jsons_cache[zname] = meta
            shapes = meta.get("shapes") or []
            all_shapes.extend(shapes)
            for s in shapes:
                lb = (s.get("label") or "").strip()
                if lb:
                    all_labels.add(lb)
            for nm in _classification_names(meta.get("flags")):
                all_labels.add(nm)

        class_mapping = {l: i for i, l in enumerate(sorted(all_labels))}
        task_type = AnnotationType(_infer_task_type(all_shapes))
        total = len(entries)

        async with async_db_session.begin() as db:
            ds = await db.get(DatasetModel, dataset_id)
            ann_task = AnnotationTaskModel(
                dataset_id=dataset_id,
                name=f"[导入] {ds.name if ds else 'dataset_' + str(dataset_id)} - x-anylabeling",
                task_type=task_type, status=TaskStatus.COMPLETED,
                classes=[{"id": cid, "name": lb, "color": _class_color(cid)}
                         for lb, cid in sorted(class_mapping.items(), key=lambda x: x[1])],
                progress=100, completed_at=datetime.now(), created_id=user_id,
            )
            db.add(ann_task)
            await db.flush()
            task_id = ann_task.id
            task_name = ann_task.name

        sem = asyncio.Semaphore(max(1, settings.ANNOTATION_IMPORT_CONCURRENCY))
        batch_size = max(1, settings.ANNOTATION_IMPORT_BATCH_SIZE)
        imported = 0
        total_annotations = 0

        for start in range(0, total, batch_size):
            batch = entries[start:start + batch_size]
            prepared = []
            for e in batch:
                img_bytes = zf.read(e["zip_name"])
                meta = jsons_cache.get(json_files.get((e["reldir"], e["stem"]), ""))
                prepared.append((e, img_bytes, meta))

            async def _proc(e, img_bytes):
                async with sem:
                    w, h, thumb = await asyncio.to_thread(process_image, img_bytes)
                    token = uuid.uuid4().hex
                    key = f"annotations/dataset_{dataset_id}/{token}{e['ext']}"
                    await asyncio.to_thread(
                        s3_client.upload_fileobj, io.BytesIO(img_bytes), key,
                        None, content_type_for(e["ext"]))
                    tkey = None
                    if thumb:
                        tkey = f"datasets/{dataset_id}/thumbnails/{token}.jpg"
                        await asyncio.to_thread(
                            s3_client.upload_fileobj, io.BytesIO(thumb), tkey,
                            None, "image/jpeg")
                    return {"key": key, "tkey": tkey, "w": w, "h": h}

            results = await asyncio.gather(*[_proc(e, b) for e, b, _ in prepared])

            async with async_db_session.begin() as db:
                for (e, _, meta), r in zip(prepared, results):
                    mw = (meta or {}).get("imageWidth") or 0
                    mh = (meta or {}).get("imageHeight") or 0
                    img_rec = AnnotationImageModel(
                        dataset_id=dataset_id, filename=e["filename"], object_key=r["key"],
                        thumbnail_key=r["tkey"], status=ImageStatus.ANNOTATED,
                        width=mw or r["w"], height=mh or r["h"], created_id=user_id,
                    )
                    db.add(img_rec)
                    await db.flush()
                    anns = []
                    for shape in ((meta or {}).get("shapes") or []):
                        ann = _shape_to_annotation(shape, class_mapping,
                                                   mw or r["w"], mh or r["h"])
                        if ann:
                            anns.append(ann)
                    names = _classification_names((meta or {}).get("flags"))
                    cids = [class_mapping[n] for n in names if n in class_mapping]
                    if cids:
                        anns.append({"id": uuid.uuid4().hex, "type": "Classification",
                                     "class_id": cids[0], "class_ids": cids,
                                     "label": names[0]})
                    if anns:
                        total_annotations += len(anns)
                        db.add(AnnotationRecordModel(
                            task_id=task_id, image_id=img_rec.id,
                            annotation_data=anns, version=1, created_id=user_id))
                    imported += 1

            if progress_cb:
                progress_cb(imported, total, "import")

        # 收尾：重算计数
        async with async_db_session.begin() as db:
            ds = await db.get(DatasetModel, dataset_id)
            if ds:
                ds.image_count = await db.scalar(
                    select(func.count(AnnotationImageModel.id)).where(
                        AnnotationImageModel.dataset_id == dataset_id,
                        AnnotationImageModel.is_deleted == False)  # noqa: E712
                ) or 0
                ds.annotated_count = await db.scalar(
                    select(func.count(func.distinct(AnnotationRecordModel.image_id)))
                    .select_from(AnnotationRecordModel)
                    .join(AnnotationImageModel, AnnotationImageModel.id == AnnotationRecordModel.image_id)
                    .where(AnnotationImageModel.dataset_id == dataset_id,
                           AnnotationImageModel.is_deleted == False,
                           AnnotationRecordModel.is_deleted == False)  # noqa: E712
                ) or 0

        if task_id:
            from app.api.v1.module_annotation.task.service import TaskService
            try:
                await TaskService.update_progress(task_id)
            except Exception as e:
                log.warning(f"update_progress failed: {e}")

    return {"imported": imported, "total_images": total,
            "total_annotations": total_annotations, "class_mapping": class_mapping,
            "task_id": task_id, "task_name": task_name}
```

- [ ] **Step 4: 运行测试**：`uv run pytest tests/test_dataset_import_job.py -v` → PASS
- [ ] **Step 5: Commit**：`git commit -m "feat(annotation): 导入器改为字节流式分批并发并生成缩略图"`

---

### Task 5: 导入路由改为后台任务 + 进度查询

**Files:**
- Modify `backend/app/api/v1/module_annotation/dataset/controller.py`
- Test `backend/tests/test_dataset_import_job.py`（追加）

**Interfaces:**
- `POST /annotation/dataset/{id}/import/x-anylabeling` → `{job_id}`
- `GET /annotation/dataset/import/{job_id}` → job 快照

- [ ] **Step 1: 写失败测试（追加）**

```python
def test_import_endpoint_returns_job_and_progress(test_client, auth_headers, monkeypatch):
    monkeypatch.setattr("app.utils.s3_client.s3_client.ensure_bucket", lambda *a, **k: None)
    monkeypatch.setattr("app.utils.s3_client.s3_client.upload_fileobj", lambda *a, **k: None)
    ds = test_client.post("/api/v1/annotation/dataset/create",
                          json={"name": f"job-{uuid4().hex[:8]}"}, headers=auth_headers).json()["data"]
    r = test_client.post(
        f"/api/v1/annotation/dataset/{ds['id']}/import/x-anylabeling",
        files={"file": ("d.zip", _make_zip(), "application/zip")}, headers=auth_headers)
    assert r.status_code == 200, r.text
    job_id = r.json()["data"]["job_id"]
    assert job_id
    # 注：TestClient 下后台任务会在事件循环内推进，轮询至少能取到 job
    j = test_client.get(f"/api/v1/annotation/dataset/import/{job_id}", headers=auth_headers)
    assert j.status_code == 200
    assert j.json()["data"]["job_id"] == job_id
    assert test_client.get("/api/v1/annotation/dataset/import/nope", headers=auth_headers).status_code == 404
```

- [ ] **Step 2: 运行确认失败**：`uv run pytest tests/test_dataset_import_job.py -k endpoint -v` → FAIL（仍返回旧结构/无 GET）
- [ ] **Step 3: 实现路由**

替换 `import_x_anylabeling`：

```python
@DatasetRouter.post("/{id}/import/x-anylabeling", summary="导入 x-anylabeling 标注（后台任务）")
async def import_x_anylabeling(
    id: int,
    file: UploadFile = File(...),
    auth: AuthSchema = Depends(AuthPermission(["annotation:dataset:create"])),
) -> JSONResponse:
    import asyncio
    from app.api.v1.module_annotation.dataset.import_jobs import create_job
    from app.config.setting import settings
    from app.core.exceptions import CustomException

    name = file.filename or ""
    if not name.lower().endswith(".zip"):
        raise CustomException(msg="仅支持 .zip 文件", code=400, status_code=400)
    data = await file.read()
    max_bytes = settings.ANNOTATION_IMPORT_MAX_MB * 1024 * 1024
    if len(data) > max_bytes:
        raise CustomException(
            msg=f"文件过大（>{settings.ANNOTATION_IMPORT_MAX_MB}MB）", code=400, status_code=400)
    job = create_job(id, auth.user.id)
    asyncio.create_task(_run_import_job(job.job_id, data, id, auth.user.id))
    return SuccessResponse(data={"job_id": job.job_id}, msg="已开始导入")


@DatasetRouter.get("/import/{job_id}", summary="查询导入任务进度")
async def get_import_job(
    job_id: str,
    auth: AuthSchema = Depends(AuthPermission(["annotation:dataset:query"])),
) -> JSONResponse:
    from dataclasses import asdict
    from app.api.v1.module_annotation.dataset.import_jobs import get_job
    job = get_job(job_id)
    if not job:
        from app.core.exceptions import CustomException
        raise CustomException(msg="导入任务不存在", code=404, status_code=404)
    return SuccessResponse(data=asdict(job))
```

并在文件内新增后台协程：

```python
async def _run_import_job(job_id: str, data: bytes, dataset_id: int, user_id: int) -> None:
    from app.api.v1.module_annotation.dataset.import_jobs import get_job
    from app.api.v1.module_annotation.dataset.x_anylabeling_importer import (
        import_x_anylabeling_bytes,
    )
    from app.core.logger import log
    job = get_job(job_id)
    if not job:
        return
    job.status = "running"
    job.phase = "scan"

    def _cb(processed: int, total: int, phase: str) -> None:
        job.processed = processed
        job.total = total
        job.phase = phase

    try:
        result = await import_x_anylabeling_bytes(data, dataset_id, user_id, progress_cb=_cb)
        job.imported = result.get("imported", 0)
        job.total_annotations = result.get("total_annotations", 0)
        job.task_id = result.get("task_id")
        job.task_name = result.get("task_name", "")
        if result.get("error"):
            job.status, job.error = "failed", result["error"]
        else:
            job.status, job.phase = "done", "done"
    except Exception as e:  # noqa: BLE001
        log.warning(f"[导入任务] 失败 job={job_id}: {e}")
        job.status, job.error = "failed", str(e)
```

- [ ] **Step 4: 运行测试**：`uv run pytest tests/test_dataset_import_job.py -v` → PASS
- [ ] **Step 5: 路由顺序检查**：`GET /import/{job_id}` 必须放在 `GET /{id}/images` 等之前或路径不冲突；确认 `/dataset/import/{job_id}` 不被 `/dataset/{id}` 类路由吞掉（当前 controller 无 `GET /{id}`，安全）。
- [ ] **Step 6: Commit**：`git commit -m "feat(annotation): 导入改为后台任务并提供进度查询"`

---

### Task 6: 前端操作列收纳 + 导入入口下沉 + 进度弹窗

**Files:**
- Modify `frontend/src/api/module_annotation.ts`
- Modify `frontend/src/views/module_annotation/dataset/index.vue`

**Interfaces:**
- Consumes: `POST /dataset/{id}/import/x-anylabeling`、`GET /dataset/import/{job_id}`

- [ ] **Step 1: API 层**

`importXAnyLabeling` 保持 multipart 但超时调大；新增：

```ts
  getImportJob(jobId: string) {
    return request<ApiResponse<any>>({
      url: `${API_PATH}/dataset/import/${jobId}`,
      method: "get",
    });
  },
```

- [ ] **Step 2: 操作列改「主操作 + 更多」**
  - 保留按钮：图片、上传、编辑。
  - 新增 `el-dropdown`「更多」：导入标注 / 导出 / 导出历史 / 数据清洗 / 去训练 / `divided` 删除 / 彻底删除。
  - 删除原工具栏「X-AnyLabeling 导入」按钮与 `openImportDialog`、`loadDatasetOptions`、`datasetOptions`、`importDatasetId`。
  - 列 `min-width` 调到可一行容纳（如 260）。

- [ ] **Step 3: 导入弹窗改造**
  - 打开方式：`handleOpenImport(row)` 记录 `importDatasetId/importDatasetName`，重置进度态。
  - 标题：`导入标注到「${importDatasetName}」`；移除目标数据集下拉。
  - 文件选择后回显 `文件名（大小 MB）`，提示 `≤ ${max}MB`。
  - 提交后：`POST` 拿 `job_id`，`setInterval` 1s 轮询 `getImportJob`，渲染 `el-progress` + 阶段 + `processed/total`；`done` 显示结果与「去任务」；`failed` 显示错误；关闭/卸载清除定时器。

- [ ] **Step 3b: 文案统一**：`x-anylabeling` → `X-AnyLabeling`。

- [ ] **Step 4: 校验**：`pnpm run type-check`（annotation 无新错误）；`pnpm exec eslint src/views/module_annotation/dataset/index.vue src/api/module_annotation.ts`（无新增）。
- [ ] **Step 5: Commit**：`git commit -m "feat(annotation): 操作列收纳并将导入入口下沉到行内带进度"`

---

### Task 7: 回归与真实验证

- [ ] **Step 1: 后端全量**：`uv run pytest tests/ -q` → 全绿
- [ ] **Step 2: ruff**：`uv run ruff check --no-fix app/api/v1/module_annotation app/config/setting.py`（无新错误）
- [ ] **Step 3: 前端**：`pnpm run type-check`（annotation 无新错误）
- [ ] **Step 4: 真实导入 21代县车号数据集**（服务重启后，用 API 或 UI）：
  - 上传 750MB zip → 立即拿到 job_id
  - 轮询至 100%，期间 `/dataset/list` 保持 < 1s
  - 断言 936 图片、1019 标注、数据集计数正确、缩略图非空
- [ ] **Step 5: 截图复核操作列一行 + 导入弹窗进度**（Playwright）
- [ ] **Step 6: Commit**（若有收尾改动）：`git commit -m "test(annotation): 数据集列表与导入优化回归"`

## Self-Review

- Spec 覆盖：A→Task2、B→Task3/5、C→Task4、D→Task1/6、E→Task6、F→Task7。
- 无占位符；类型一致：`import_x_anylabeling_bytes(data, dataset_id, user_id, progress_cb)`、`enrich_dataset_list(db, items)`、`create_job/get_job`。
- 已知取舍：导入字节常驻内存（上限 1GB）；job 表进程内（重启丢失）。
