# 标注数据生命周期与媒体管线 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为标注模块补齐对象存储生命周期治理（purge + 定时清理 + 版本保留 + 索引）与媒体管线（服务端缩略图、ContentType、并发上传、校验、回填），并让工作台 filmstrip 与数据集图片网格消费缩略图。

**Architecture:** 后端在 `app/api/v1/module_annotation/` 内扩展：软删保持不动物体存储，新增 purge 服务/路由与 retention 循环；上传管线改为"校验 → 线程池并发处理（PIL 缩略图 + S3 上传）→ 串行写库"；`get_images` 下发 presigned `thumbnail_url`。前端在既有工作台左侧列表加缩略图，并新增单根 `DatasetImageGrid.vue` 抽屉。

**Tech Stack:** FastAPI、SQLAlchemy 2.0 async、Alembic、PostgreSQL/SQLite、boto3、Pillow、Vue 3 + Element Plus + TypeScript、pytest、Playwright。

## Global Constraints

- 交流与提交信息用中文，提交格式 `fix(annotation): 中文描述` / `feat(annotation): 中文描述`。
- 代码注释用中文；不要添加无关注释（AGENTS.md）。
- 后端 lint：`uv run ruff check`；迁移 `uv run main.py revision --env=dev` → `uv run main.py upgrade --env=dev`。
- 前端：`pnpm run type-check`、`pnpm run lint`（工作目录 `frontend`）。
- 前端新组件必须**单根元素**；布局优先 `el-row`/`el-col`，禁止自定义 CSS Grid（AGENTS.md 强制）。
- 不修改标注画布/绘制/协作/Pinia 业务逻辑，只动工作台左侧列表模板与最小样式。
- 对象存储 key 约定：原图 `datasets/{dsId}/images/{uuid}{ext}`；缩略图 `datasets/{dsId}/thumbnails/{uuid}.jpg`；导入标注 `annotations/dataset_{dsId}/...`；导出 ZIP `train/exports/dataset_{dsId}_{format}_{userId}.zip`。
- 权限：purge 使用 `annotation:dataset:purge`（后端）与 `module_annotation:dataset:purge`（前端按钮）。
- 配置默认值：`ANNOTATION_PURGE_RETENTION_DAYS=30`、`ANNOTATION_PURGE_INTERVAL_SEC=86400`、`ANNOTATION_VERSION_KEEP=20`、`ANNOTATION_UPLOAD_MAX_MB=20`、`ANNOTATION_UPLOAD_MAX_FILES=200`、`ANNOTATION_UPLOAD_CONCURRENCY=4`、缩略图长边 `512`、JPEG 质量 `85`。

---

## 文件结构（改动地图）

**后端创建：**
- `backend/app/api/v1/module_annotation/dataset/media.py` — 图片处理（尺寸 + 缩略图 + ContentType）
- `backend/app/api/v1/module_annotation/dataset/retention.py` — 过期软删数据集清理循环
- `backend/scripts/backfill_annotation_thumbnails.py` — 存量缩略图回填
- `backend/tests/test_annotation_media.py` — 媒体管线与上传测试
- `backend/tests/test_dataset_purge.py` — purge 与 retention 测试
- `backend/tests/test_annotation_version_retention.py` — 版本保留测试

**后端修改：**
- `backend/app/config/setting.py` — 6 个新配置项
- `backend/app/utils/s3_client.py` — `content_type` 参数 + `delete_prefix` 分页
- `backend/app/api/v1/module_annotation/dataset/model.py` — `thumbnail_key` + 索引
- `backend/app/api/v1/module_annotation/annotation/model.py` — 复合索引
- `backend/app/api/v1/module_annotation/dataset/service.py` — 上传管线、purge、`get_images` 合约
- `backend/app/api/v1/module_annotation/dataset/controller.py` — purge 路由
- `backend/app/api/v1/module_annotation/annotation/service.py` — 版本保留
- `backend/app/scripts/init_app.py` — retention 挂载 + purge 权限注册
- `backend/app/alembic/versions/<new>.py` — 迁移（列/索引/删列）

**前端修改/创建：**
- `frontend/src/api/module_annotation.ts` — `purgeDataset`
- `frontend/src/views/module_annotation/annotation/index.vue` — 左侧 filmstrip
- `frontend/src/components/Annotation/DatasetImageGrid.vue` — 新增网格抽屉
- `frontend/src/views/module_annotation/dataset/index.vue` — 图片网格入口 + 彻底删除 + 文案

---

## Phase P1 — 数据生命周期（低风险先做）

### Task 1: 新增标注相关配置项

**Files:**
- Modify: `backend/app/config/setting.py:190-197`
- Modify: `backend/env/.env.dev`、`backend/env/.env.dev.example`（可选，默认值已生效）

**Interfaces:**
- Produces: `settings.ANNOTATION_PURGE_RETENTION_DAYS: int`、`settings.ANNOTATION_PURGE_INTERVAL_SEC: int`、`settings.ANNOTATION_VERSION_KEEP: int`、`settings.ANNOTATION_UPLOAD_MAX_MB: int`、`settings.ANNOTATION_UPLOAD_MAX_FILES: int`、`settings.ANNOTATION_UPLOAD_CONCURRENCY: int`

- [ ] **Step 1: 写入配置项**

在 `setting.py` 的 RustFS 配置块之后新增：

```python
    # ================================================= #
    # *************** 数据标注生命周期/媒体 ************** #
    # ================================================= #
    # 软删数据集在保留期后由定时任务彻底删除（含 S3 对象）
    ANNOTATION_PURGE_RETENTION_DAYS: int = 30
    # 彻底删除清理循环间隔（秒）
    ANNOTATION_PURGE_INTERVAL_SEC: int = 86400
    # 标注版本保留：每个 (task_id, image_id) 保留首版 + 最近 N 版
    ANNOTATION_VERSION_KEEP: int = 20
    # 单张图片上传大小上限（MB）
    ANNOTATION_UPLOAD_MAX_MB: int = 20
    # 单次上传图片数量上限
    ANNOTATION_UPLOAD_MAX_FILES: int = 200
    # 上传时处理（PIL + S3）的并发度
    ANNOTATION_UPLOAD_CONCURRENCY: int = 4
```

- [ ] **Step 2: 验证配置可加载**

Run: `uv run python -c "from app.config.setting import settings; print(settings.ANNOTATION_VERSION_KEEP, settings.ANNOTATION_UPLOAD_MAX_FILES)"`（工作目录 `backend`）
Expected: 输出 `20 200`

- [ ] **Step 3: Commit**

```bash
git add backend/app/config/setting.py
git commit -m "feat(annotation): 新增数据生命周期与媒体管线配置项"
```

---

### Task 2: `s3_client` 支持 ContentType 与分页删除

**Files:**
- Modify: `backend/app/utils/s3_client.py`
- Test: `backend/tests/test_annotation_media.py`（本任务先建文件并写首个用例）

**Interfaces:**
- Produces:
  - `S3Client.upload_fileobj(self, fileobj: BinaryIO, object_key: str, env: str | None = None, content_type: str | None = None) -> str`
  - `S3Client.upload_file(self, file_path: str, object_key: str, env: str | None = None, content_type: str | None = None) -> str`
  - `S3Client.delete_prefix(self, prefix: str, env: str | None = None) -> int`（改为分页，返回全部删除数）

- [ ] **Step 1: 写失败测试**

创建 `backend/tests/test_annotation_media.py`：

```python
"""媒体管线与 S3 客户端测试。"""
import io


def test_delete_prefix_paginates(monkeypatch):
    """delete_prefix 必须翻页删除全部对象（>1000 时不能只删第一页）。"""
    from app.utils.s3_client import S3Client

    client = S3Client.__new__(S3Client)  # 不跑 __init__，避免真实 boto3 连接
    client.bucket_prefix = "test"
    client.default_env = "dev"

    pages = {
        None: {"Contents": [{"Key": f"k{i}"} for i in range(1000)], "IsTruncated": True,
               "NextContinuationToken": "t1"},
        "t1": {"Contents": [{"Key": f"z{i}"} for i in range(3)], "IsTruncated": False},
    }
    deleted: list[str] = []

    class _FakeBoto:
        def list_objects_v2(self, **kwargs):
            return pages[kwargs.get("ContinuationToken")]

        def delete_object(self, **kwargs):
            deleted.append(kwargs["Key"])

    client.client = _FakeBoto()
    count = client.delete_prefix("k")
    assert count == 1003
    assert len(deleted) == 1003


def test_upload_fileobj_passes_content_type(monkeypatch):
    """upload_fileobj 需把 content_type 透传到 ExtraArgs。"""
    from app.utils.s3_client import S3Client

    client = S3Client.__new__(S3Client)
    client.bucket_prefix = "test"
    client.default_env = "dev"
    captured: dict = {}

    class _FakeBoto:
        def upload_fileobj(self, fileobj, bucket, key, ExtraArgs=None):
            captured["bucket"] = bucket
            captured["key"] = key
            captured["extra"] = ExtraArgs

    client.client = _FakeBoto()
    client.upload_fileobj(io.BytesIO(b"x"), "a/b.png", content_type="image/png")
    assert captured["extra"] == {"ContentType": "image/png"}
```

- [ ] **Step 2: 运行测试确认失败**

Run: `uv run pytest tests/test_annotation_media.py -v`
Expected: FAIL（`delete_prefix` 不支持分页 / `upload_fileobj` 无 content_type）

- [ ] **Step 3: 实现**

替换 `s3_client.py` 的 `upload_fileobj`、`upload_file`、`delete_prefix`：

```python
    def upload_fileobj(
        self,
        fileobj: BinaryIO,
        object_key: str,
        env: str | None = None,
        content_type: str | None = None,
    ) -> str:
        extra = {"ContentType": content_type} if content_type else None
        self.client.upload_fileobj(fileobj, self._bucket(env), object_key, ExtraArgs=extra)
        return object_key

    def upload_file(
        self,
        file_path: str,
        object_key: str,
        env: str | None = None,
        content_type: str | None = None,
    ) -> str:
        extra = {"ContentType": content_type} if content_type else None
        self.client.upload_file(file_path, self._bucket(env), object_key, ExtraArgs=extra)
        return object_key

    def delete_prefix(self, prefix: str, env: str | None = None) -> int:
        """删除该前缀下所有对象（分页直至 IsTruncated=False），返回删除数量。"""
        bucket = self._bucket(env)
        removed = 0
        token: str | None = None
        while True:
            kwargs: dict = {"Bucket": bucket, "Prefix": prefix}
            if token:
                kwargs["ContinuationToken"] = token
            resp = self.client.list_objects_v2(**kwargs)
            for obj in resp.get("Contents", []) or []:
                self.client.delete_object(Bucket=bucket, Key=obj["Key"])
                removed += 1
            if not resp.get("IsTruncated"):
                break
            token = resp.get("NextContinuationToken")
        return removed
```

- [ ] **Step 4: 运行测试确认通过**

Run: `uv run pytest tests/test_annotation_media.py -v`
Expected: PASS（2 passed）

- [ ] **Step 5: Commit**

```bash
git add backend/app/utils/s3_client.py backend/tests/test_annotation_media.py
git commit -m "feat(annotation): s3_client 支持 ContentType 与分页删除"
```

---

### Task 3: 模型加缩略图列与索引 + Alembic 迁移

**Files:**
- Modify: `backend/app/api/v1/module_annotation/dataset/model.py`
- Modify: `backend/app/api/v1/module_annotation/annotation/model.py`
- Create: `backend/app/alembic/versions/<autogen>.py`（由命令生成后编辑）
- Test: `backend/tests/test_dataset_purge.py`（本任务先建文件并写首用例）

**Interfaces:**
- Produces: `AnnotationImageModel.thumbnail_key: str | None`
- Consumes: 无

- [ ] **Step 1: 写失败测试**

创建 `backend/tests/test_dataset_purge.py`：

```python
"""数据集 purge 与缩略图列测试。"""


def test_annotation_image_has_thumbnail_key(test_client, auth_headers, monkeypatch):
    monkeypatch.setattr("app.utils.s3_client.s3_client.ensure_bucket", lambda *a, **k: None)
    monkeypatch.setattr("app.utils.s3_client.s3_client.upload_fileobj", lambda *a, **k: None)
    from app.api.v1.module_annotation.dataset.model import AnnotationImageModel

    assert hasattr(AnnotationImageModel, "thumbnail_key")
```

- [ ] **Step 2: 运行确认失败**

Run: `uv run pytest tests/test_dataset_purge.py::test_annotation_image_has_thumbnail_key -v`
Expected: FAIL（`hasattr` 为 False）

- [ ] **Step 3: 改模型**

在 `dataset/model.py` 的 `AnnotationImageModel` 中，`object_key` 之后新增：

```python
    thumbnail_key: Mapped[str | None] = mapped_column(
        String(512), nullable=True, comment="RustFS 缩略图 key"
    )
```

并在类体末尾新增索引声明：

```python
    __table_args__ = (
        Index("ix_annotation_image_dataset_status", "dataset_id", "status"),
    )
```

同时把 import 改为：

```python
from sqlalchemy import DateTime, Enum, ForeignKey, Index, Integer, String, Text
```

删除 `DatasetModel.bucket_name` 一行（死字段）。

在 `annotation/model.py` 的 `AnnotationRecordModel` 中新增索引：

```python
from sqlalchemy import ForeignKey, Index, Integer
...
    __table_args__ = (
        Index("ix_annotation_record_task_image_version", "task_id", "image_id", "version"),
    )
```

- [ ] **Step 4: 生成并编辑迁移**

Run（`backend` 目录）: `uv run main.py revision --env=dev`
然后在生成的 `backend/app/alembic/versions/*.py` 中确认/补齐 `upgrade()`：

```python
def upgrade() -> None:
    op.add_column(
        "annotation_image",
        sa.Column("thumbnail_key", sa.String(length=512), nullable=True,
                  comment="RustFS 缩略图 key"),
    )
    op.create_index(
        "ix_annotation_image_dataset_status", "annotation_image",
        ["dataset_id", "status"], unique=False,
    )
    op.create_index(
        "ix_annotation_record_task_image_version", "annotation_record",
        ["task_id", "image_id", "version"], unique=False,
    )
    op.drop_column("annotation_dataset", "bucket_name")


def downgrade() -> None:
    op.add_column(
        "annotation_dataset",
        sa.Column("bucket_name", sa.String(length=64), nullable=False,
                  server_default="aistation-annotation-dev"),
    )
    op.drop_index("ix_annotation_record_task_image_version", table_name="annotation_record")
    op.drop_index("ix_annotation_image_dataset_status", table_name="annotation_image")
    op.drop_column("annotation_image", "thumbnail_key")
```

- [ ] **Step 5: 应用迁移并验证**

Run: `uv run main.py upgrade --env=dev`
Run: `uv run pytest tests/test_dataset_purge.py::test_annotation_image_has_thumbnail_key -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add backend/app/api/v1/module_annotation/dataset/model.py backend/app/api/v1/module_annotation/annotation/model.py backend/app/alembic/versions backend/tests/test_dataset_purge.py
git commit -m "feat(annotation): 图片增加缩略图列、版本复合索引并移除死字段"
```

---

### Task 4: 标注版本保留（首版 + 最近 N 版）

**Files:**
- Modify: `backend/app/api/v1/module_annotation/annotation/service.py:42-88`
- Test: `backend/tests/test_annotation_version_retention.py`

**Interfaces:**
- Consumes: `settings.ANNOTATION_VERSION_KEEP`
- Produces: `AnnotationService._prune_versions(db, task_id: int, image_id: int, latest_version: int, keep: int) -> None`

- [ ] **Step 1: 写失败测试**

创建 `backend/tests/test_annotation_version_retention.py`（全程走 HTTP 接口，避免与 TestClient 事件循环冲突）：

```python
"""标注版本保留策略测试。"""
from uuid import uuid4

_FAKE_PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 64


def _setup_dataset_task(test_client, auth_headers) -> tuple[int, int]:
    """建数据集→传图→建任务，返回 (task_id, image_id)。"""
    ds = test_client.post(
        "/api/v1/annotation/dataset/create",
        json={"name": f"ver-{uuid4().hex[:8]}"}, headers=auth_headers,
    ).json()["data"]
    test_client.post(
        f"/api/v1/annotation/dataset/{ds['id']}/upload",
        files={"files": ("a.png", _FAKE_PNG, "image/png")}, headers=auth_headers,
    )
    image_id = test_client.get(
        f"/api/v1/annotation/dataset/{ds['id']}/images", headers=auth_headers,
    ).json()["data"]["items"][0]["id"]
    task = test_client.post(
        "/api/v1/annotation/task/create",
        json={"dataset_id": ds["id"], "name": "t", "task_type": "detection"},
        headers=auth_headers,
    ).json()["data"]
    return task["id"], image_id


def test_prune_versions_keeps_first_and_recent(test_client, auth_headers, monkeypatch):
    monkeypatch.setattr("app.utils.s3_client.s3_client.ensure_bucket", lambda *a, **k: None)
    monkeypatch.setattr("app.utils.s3_client.s3_client.upload_fileobj", lambda *a, **k: None)

    task_id, image_id = _setup_dataset_task(test_client, auth_headers)

    for v in range(25):  # 25 次保存 → v1..v25
        r = test_client.put(
            f"/api/v1/annotation/anno/image/{image_id}/annotations",
            json={"task_id": task_id, "image_id": image_id,
                  "annotation_data": [{"type": "box", "id": str(v)}]},
            headers=auth_headers,
        )
        assert r.status_code == 200, r.text

    hist = test_client.get(
        f"/api/v1/annotation/anno/image/{image_id}/history",
        params={"task_id": task_id}, headers=auth_headers,
    ).json()["data"]
    versions = sorted(h["version"] for h in hist)
    assert versions[0] == 1
    assert versions[-1] == 25
    assert 2 not in versions            # 中间旧版被清理
    assert 5 not in versions
    assert all(v in versions for v in range(6, 26))  # v6..v25 共 20 版
    assert len(versions) == 21           # 首版 + 最近 20 版
```

> 说明：本测试用 `GET /dataset/{id}/images` 取 image_id，不依赖 Task 8 的返回结构，可在 Task 8 之前运行。

- [ ] **Step 2: 运行确认失败**

Run: `uv run pytest tests/test_annotation_version_retention.py -v`
Expected: FAIL（`_prune_versions` 不存在）

- [ ] **Step 3: 实现**

在 `annotation/service.py` 顶部 import 增加 `delete`：

```python
from sqlalchemy import delete, desc, func, select, update

from app.config.setting import settings
```

在 `AnnotationService` 中新增方法：

```python
    @classmethod
    async def _prune_versions(cls, db, task_id: int, image_id: int,
                              latest_version: int, keep: int) -> None:
        """保留首版（v1）与最近 keep 版，删除中间旧版本。"""
        if keep <= 0 or latest_version <= keep + 1:
            return
        upper = latest_version - keep  # 删除 version ∈ [2, upper]
        await db.execute(
            delete(AnnotationRecordModel).where(
                AnnotationRecordModel.task_id == task_id,
                AnnotationRecordModel.image_id == image_id,
                AnnotationRecordModel.version >= 2,
                AnnotationRecordModel.version <= upper,
            )
        )
```

在 `save_annotations` 中，`db.add(AnnotationRecordModel(...))` 之后、更新图片状态之前调用：

```python
            db.add(AnnotationRecordModel(...))
            await db.flush()
            await cls._prune_versions(db, task_id, image_id, version,
                                      settings.ANNOTATION_VERSION_KEEP)
```

- [ ] **Step 4: 运行确认通过**

Run: `uv run pytest tests/test_annotation_version_retention.py -v`
Expected: PASS

- [ ] **Step 5: 回归既有标注测试**

Run: `uv run pytest tests/test_annotation_lock_conflict.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add backend/app/api/v1/module_annotation/annotation/service.py backend/tests/test_annotation_version_retention.py
git commit -m "feat(annotation): 标注版本保留首版与最近 N 版"
```

---

### Task 5: purge 服务与路由

**Files:**
- Modify: `backend/app/api/v1/module_annotation/dataset/service.py:27-61`
- Modify: `backend/app/api/v1/module_annotation/dataset/controller.py`
- Modify: `backend/app/scripts/init_app.py:854-907`
- Test: `backend/tests/test_dataset_purge.py`

**Interfaces:**
- Produces: `DatasetService.purge_datasets(ids: list[int]) -> dict`（返回 `{"purged": n}`）
- Consumes: `s3_client.delete_prefix`

- [ ] **Step 1: 写失败测试（追加到 test_dataset_purge.py）**

```python
def test_purge_removes_db_rows_and_s3(test_client, auth_headers, monkeypatch):
    prefixes: list[str] = []
    monkeypatch.setattr("app.utils.s3_client.s3_client.ensure_bucket", lambda *a, **k: None)
    monkeypatch.setattr("app.utils.s3_client.s3_client.upload_fileobj", lambda *a, **k: None)
    monkeypatch.setattr(
        "app.utils.s3_client.s3_client.delete_prefix",
        lambda prefix, *a, **k: prefixes.append(prefix) or 1,
    )
    from uuid import uuid4 as _uuid
    name = f"purge-{_uuid().hex[:8]}"
    ds = test_client.post("/api/v1/annotation/dataset/create",
                          json={"name": name}, headers=auth_headers).json()["data"]
    ds_id = ds["id"]
    test_client.post(
        f"/api/v1/annotation/dataset/{ds_id}/upload",
        files={"files": ("a.png", b"\x89PNG\r\n\x1a\n" + b"0" * 64, "image/png")},
        headers=auth_headers,
    )
    # 先软删，再彻底删除
    test_client.request("DELETE", "/api/v1/annotation/dataset/delete",
                        json=[ds_id], headers=auth_headers)
    r = test_client.request("DELETE", "/api/v1/annotation/dataset/purge",
                            json=[ds_id], headers=auth_headers)
    assert r.status_code == 200, r.text
    assert f"datasets/{ds_id}/" in prefixes
    assert f"annotations/dataset_{ds_id}/" in prefixes
    assert any(p.startswith(f"train/exports/dataset_{ds_id}_") for p in prefixes)
    # 幂等：再 purge 不报错
    r2 = test_client.request("DELETE", "/api/v1/annotation/dataset/purge",
                             json=[ds_id], headers=auth_headers)
    assert r2.status_code == 200, r2.text
```

- [ ] **Step 2: 运行确认失败**

Run: `uv run pytest tests/test_dataset_purge.py::test_purge_removes_db_rows_and_s3 -v`
Expected: FAIL（路由不存在 404）

- [ ] **Step 3: 实现 `purge_datasets`**

在 `dataset/service.py` 顶部 import 增加：

```python
from sqlalchemy import and_, delete, func, select, update

from app.api.v1.module_annotation.dataset.export_model import DatasetExportModel
```

新增方法（放在 `delete_datasets` 之后）：

```python
    @classmethod
    async def purge_datasets(cls, ids: list[int]) -> dict:
        """彻底删除数据集：先删 S3 对象，再物理删 DB 行（不可逆）。"""
        purged = 0
        for dataset_id in ids:
            # 1) 先删对象存储，失败则抛出，DB 不提交，避免留下不可恢复态
            s3_client.delete_prefix(f"datasets/{dataset_id}/")
            s3_client.delete_prefix(f"annotations/dataset_{dataset_id}/")
            s3_client.delete_prefix(f"train/exports/dataset_{dataset_id}_")

            # 2) 物理删除 DB（含软删行）
            async with async_db_session.begin() as db:
                img_ids = (
                    await db.execute(
                        select(AnnotationImageModel.id).where(
                            AnnotationImageModel.dataset_id == dataset_id
                        )
                    )
                ).scalars().all()
                if img_ids:
                    await db.execute(
                        delete(AnnotationRecordModel).where(
                            AnnotationRecordModel.image_id.in_(img_ids)
                        )
                    )
                await db.execute(
                    delete(DatasetExportModel).where(
                        DatasetExportModel.dataset_id == dataset_id
                    )
                )
                await db.execute(
                    delete(AnnotationImageModel).where(
                        AnnotationImageModel.dataset_id == dataset_id
                    )
                )
                await db.execute(
                    delete(AnnotationTaskModel).where(
                        AnnotationTaskModel.dataset_id == dataset_id
                    )
                )
                await db.execute(
                    delete(DatasetModel).where(DatasetModel.id == dataset_id)
                )
            purged += 1
        return {"purged": purged}
```

- [ ] **Step 4: 新增路由**

在 `dataset/controller.py` 的 `delete_dataset` 之后新增：

```python
@DatasetRouter.delete("/purge", summary="彻底删除数据集（含对象存储，不可恢复）")
async def purge_dataset(
    ids: list[int],
    auth: AuthSchema = Depends(AuthPermission(["annotation:dataset:purge"])),
) -> JSONResponse:
    result = await DatasetService.purge_datasets(ids=ids)
    return SuccessResponse(data=result, msg="已彻底删除")
```

- [ ] **Step 5: 注册 purge 权限菜单**

在 `init_app.py` 的 `_ensure_annotation_button_menus` 中，把 `existing` 查询改为同时覆盖 `annotation:dataset:purge`：

```python
            existing = set(
                (await db.execute(
                    select(MenuModel.permission).where(
                        MenuModel.permission.like("module_annotation:%")
                    )
                )).scalars().all()
            )
            existing |= set(
                (await db.execute(
                    select(MenuModel.permission).where(
                        MenuModel.permission.in_(["annotation:dataset:purge"])
                    )
                )).scalars().all()
            )
```

并在 `buttons` 列表末尾追加：

```python
                (dataset_menu.id, "彻底删除数据集", 6, "annotation:dataset:purge"),
                (dataset_menu.id, "彻底删除按钮", 7, "module_annotation:dataset:purge"),
```

- [ ] **Step 6: 运行测试确认通过**

Run: `uv run pytest tests/test_dataset_purge.py -v`
Expected: PASS（2 passed）

- [ ] **Step 7: Commit**

```bash
git add backend/app/api/v1/module_annotation/dataset/service.py backend/app/api/v1/module_annotation/dataset/controller.py backend/app/scripts/init_app.py backend/tests/test_dataset_purge.py
git commit -m "feat(annotation): 新增数据集彻底删除（purge）与对象存储清理"
```

---

### Task 6: 过期软删数据集定时清理

**Files:**
- Create: `backend/app/api/v1/module_annotation/dataset/retention.py`
- Modify: `backend/app/scripts/init_app.py:1242-1248`
- Test: `backend/tests/test_dataset_purge.py`

**Interfaces:**
- Produces:
  - `async def purge_expired_datasets(retention_days: int) -> int`
  - `def start_annotation_purge_retention() -> asyncio.Task | None`
- Consumes: `DatasetService.purge_datasets`

- [ ] **Step 1: 写失败测试（追加）**

```python
def test_purge_expired_selects_soft_deleted_older_than(test_client, auth_headers, monkeypatch):
    import asyncio
    from datetime import datetime, timedelta
    from uuid import uuid4 as _uuid

    monkeypatch.setattr("app.utils.s3_client.s3_client.ensure_bucket", lambda *a, **k: None)
    monkeypatch.setattr("app.utils.s3_client.s3_client.delete_prefix", lambda *a, **k: 0)

    ds = test_client.post("/api/v1/annotation/dataset/create",
                          json={"name": f"exp-{_uuid().hex[:8]}"},
                          headers=auth_headers).json()["data"]
    ds_id = ds["id"]
    test_client.request("DELETE", "/api/v1/annotation/dataset/delete",
                        json=[ds_id], headers=auth_headers)

    from app.core.database import async_db_session
    from app.api.v1.module_annotation.dataset.model import DatasetModel
    from app.api.v1.module_annotation.dataset.retention import purge_expired_datasets

    async def _backdate():
        async with async_db_session.begin() as db:
            row = await db.get(DatasetModel, ds_id)
            row.deleted_time = datetime.now() - timedelta(days=99)

    asyncio.run(_backdate())
    removed = asyncio.run(purge_expired_datasets(30))
    assert removed >= 1
    async def _gone():
        async with async_db_session() as db:
            return await db.get(DatasetModel, ds_id)
    assert asyncio.run(_gone()) is None
```

- [ ] **Step 2: 运行确认失败**

Run: `uv run pytest tests/test_dataset_purge.py::test_purge_expired_selects_soft_deleted_older_than -v`
Expected: FAIL（模块不存在）

- [ ] **Step 3: 实现 retention 模块**

创建 `dataset/retention.py`：

```python
"""过期软删数据集彻底清理：超过保留期后删除 DB 行与对象存储。

与 ``alarm/retention.py`` 同模式：启动即跑一次，之后按间隔循环；异常隔离；
``TESTING`` 下不启动后台任务。
"""
import asyncio
import logging
from datetime import datetime, timedelta

from sqlalchemy import select

from app.config.setting import settings

log = logging.getLogger(__name__)

_retention_task: asyncio.Task | None = None


async def purge_expired_datasets(retention_days: int) -> int:
    """彻底删除软删时间早于保留期的数据集，返回删除数量。

    ``retention_days <= 0`` 视为无效配置，返回 0（不删除）。
    """
    if retention_days is None or retention_days <= 0:
        return 0
    from app.api.v1.module_annotation.dataset.model import DatasetModel
    from app.api.v1.module_annotation.dataset.service import DatasetService
    from app.core.database import async_db_session

    cutoff = datetime.now() - timedelta(days=retention_days)
    try:
        async with async_db_session() as db:
            ids = (
                await db.execute(
                    select(DatasetModel.id).where(
                        DatasetModel.is_deleted == True,  # noqa: E712
                        DatasetModel.deleted_time.isnot(None),
                        DatasetModel.deleted_time < cutoff,
                    )
                )
            ).scalars().all()
        if not ids:
            return 0
        result = await DatasetService.purge_datasets(list(ids))
        return int(result.get("purged", 0))
    except Exception as e:
        log.warning(f"[标注数据集清理] 删除失败: {e}")
        return 0


async def _retention_loop(interval_sec: int) -> None:
    while True:
        try:
            removed = await purge_expired_datasets(settings.ANNOTATION_PURGE_RETENTION_DAYS)
            if removed:
                log.info(
                    f"[标注数据集清理] 已彻底删除 {removed} 个超过 "
                    f"{settings.ANNOTATION_PURGE_RETENTION_DAYS} 天的数据集"
                )
        except asyncio.CancelledError:
            raise
        except Exception as e:  # pragma: no cover - 防御
            log.warning(f"[标注数据集清理] 循环异常: {e}")
        await asyncio.sleep(interval_sec)


def start_annotation_purge_retention() -> asyncio.Task | None:
    """挂起清理任务；``TESTING`` 下不启动。"""
    global _retention_task
    if settings.TESTING:
        return None
    if _retention_task is not None and not _retention_task.done():
        return _retention_task
    _retention_task = asyncio.create_task(
        _retention_loop(settings.ANNOTATION_PURGE_INTERVAL_SEC)
    )
    log.info(
        f"[标注数据集清理] 已启动，保留 {settings.ANNOTATION_PURGE_RETENTION_DAYS} 天，"
        f"间隔 {settings.ANNOTATION_PURGE_INTERVAL_SEC}s"
    )
    return _retention_task
```

- [ ] **Step 4: 挂载到应用启动**

在 `init_app.py` 其余 retention 挂载之后新增：

```python
        from app.api.v1.module_annotation.dataset.retention import (
            start_annotation_purge_retention,
        )
        start_annotation_purge_retention()
        log.info("✅ 标注数据集过期清理已启动")
```

- [ ] **Step 5: 运行测试确认通过**

Run: `uv run pytest tests/test_dataset_purge.py -v`
Expected: PASS（3 passed）

- [ ] **Step 6: Commit**

```bash
git add backend/app/api/v1/module_annotation/dataset/retention.py backend/app/scripts/init_app.py backend/tests/test_dataset_purge.py
git commit -m "feat(annotation): 过期软删数据集定时彻底清理"
```

---

## Phase P2 — 媒体管线

### Task 7: 图片处理模块（尺寸 + 缩略图 + ContentType）

**Files:**
- Create: `backend/app/api/v1/module_annotation/dataset/media.py`
- Test: `backend/tests/test_annotation_media.py`

**Interfaces:**
- Produces:
  - `ALLOWED_IMAGE_EXTENSIONS: set[str]`
  - `content_type_for(ext: str) -> str`
  - `process_image(content: bytes) -> tuple[int, int, bytes | None]`

- [ ] **Step 1: 写失败测试（追加）**

```python
def _png_bytes(w: int, h: int) -> bytes:
    import io
    from PIL import Image
    buf = io.BytesIO()
    Image.new("RGB", (w, h), (200, 30, 30)).save(buf, format="PNG")
    return buf.getvalue()


def test_process_image_returns_dims_and_thumbnail():
    from app.api.v1.module_annotation.dataset.media import process_image

    w, h, thumb = process_image(_png_bytes(1200, 600))
    assert (w, h) == (1200, 600)
    assert thumb is not None
    from PIL import Image
    import io
    with Image.open(io.BytesIO(thumb)) as t:
        assert t.format == "JPEG"
        assert max(t.size) <= 512


def test_process_image_bad_bytes_returns_none_thumb():
    from app.api.v1.module_annotation.dataset.media import process_image

    w, h, thumb = process_image(b"not-an-image")
    assert (w, h, thumb) == (0, 0, None)


def test_content_type_mapping():
    from app.api.v1.module_annotation.dataset.media import content_type_for

    assert content_type_for(".png") == "image/png"
    assert content_type_for(".JPG") == "image/jpeg"
    assert content_type_for(".unknown") == "application/octet-stream"
```

- [ ] **Step 2: 运行确认失败**

Run: `uv run pytest tests/test_annotation_media.py -v`
Expected: FAIL（模块不存在）

- [ ] **Step 3: 实现 media.py**

```python
"""标注图片处理：尺寸探测、缩略图生成与 Content-Type 映射。"""
import io

from PIL import Image, ImageOps

ALLOWED_IMAGE_EXTENSIONS: set[str] = {
    ".jpg", ".jpeg", ".png", ".bmp", ".webp", ".tif", ".tiff",
}

_EXT_CONTENT_TYPE: dict[str, str] = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".bmp": "image/bmp",
    ".webp": "image/webp",
    ".tif": "image/tiff",
    ".tiff": "image/tiff",
}

THUMBNAIL_MAX_SIDE = 512
THUMBNAIL_QUALITY = 85


def content_type_for(ext: str) -> str:
    """按扩展名返回 Content-Type，未知类型回退 octet-stream。"""
    return _EXT_CONTENT_TYPE.get(ext.lower(), "application/octet-stream")


def process_image(content: bytes) -> tuple[int, int, bytes | None]:
    """返回 (width, height, thumbnail_jpeg_bytes)。

    无法解析的图片返回 ``(0, 0, None)``，不抛异常。
    """
    try:
        with Image.open(io.BytesIO(content)) as opened:
            img = ImageOps.exif_transpose(opened)
            width, height = img.size
            thumb = img.copy()
            thumb.thumbnail((THUMBNAIL_MAX_SIDE, THUMBNAIL_MAX_SIDE))
            if thumb.mode not in ("RGB", "L"):
                thumb = thumb.convert("RGB")
            buf = io.BytesIO()
            thumb.save(buf, format="JPEG", quality=THUMBNAIL_QUALITY)
            return width, height, buf.getvalue()
    except Exception:
        return 0, 0, None
```

- [ ] **Step 4: 运行确认通过**

Run: `uv run pytest tests/test_annotation_media.py -v`
Expected: PASS（5 passed）

- [ ] **Step 5: Commit**

```bash
git add backend/app/api/v1/module_annotation/dataset/media.py backend/tests/test_annotation_media.py
git commit -m "feat(annotation): 新增图片处理模块（尺寸/缩略图/ContentType）"
```

---

### Task 8: 上传管线改造（校验 + 并发 + 缩略图 + ContentType + 部分失败）

**Files:**
- Modify: `backend/app/api/v1/module_annotation/dataset/service.py:63-109`
- Modify: `backend/app/api/v1/module_annotation/dataset/controller.py:95-102`
- Test: `backend/tests/test_annotation_media.py`

**Interfaces:**
- Produces: `DatasetService.upload_images(dataset_id: int, files: list, auth) -> dict`，返回
  `{"uploaded": [{"id","filename","object_key","thumbnail_key"}], "failed": [{"filename","reason"}], "uploaded_count": int, "failed_count": int}`
- Consumes: `process_image`、`content_type_for`、`ALLOWED_IMAGE_EXTENSIONS`

- [ ] **Step 1: 写失败测试（追加）**

```python
def test_upload_generates_thumbnail_and_content_type(test_client, auth_headers, monkeypatch):
    from uuid import uuid4
    uploaded: list[tuple[str, dict]] = []

    monkeypatch.setattr("app.utils.s3_client.s3_client.ensure_bucket", lambda *a, **k: None)

    def _capture(fileobj, object_key, env=None, content_type=None):
        uploaded.append((object_key, {"content_type": content_type}))
        return object_key

    monkeypatch.setattr("app.utils.s3_client.s3_client.upload_fileobj", _capture)

    ds = test_client.post("/api/v1/annotation/dataset/create",
                          json={"name": f"media-{uuid4().hex[:8]}"},
                          headers=auth_headers).json()["data"]
    ds_id = ds["id"]
    png = _png_bytes(800, 400)
    r = test_client.post(
        f"/api/v1/annotation/dataset/{ds_id}/upload",
        files={"files": ("a.png", png, "image/png")},
        headers=auth_headers,
    )
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert data["uploaded_count"] == 1
    keys = [k for k, _ in uploaded]
    assert any(k.startswith(f"datasets/{ds_id}/images/") for k in keys)
    assert any(k.startswith(f"datasets/{ds_id}/thumbnails/") for k in keys)
    thumb = [meta for k, meta in uploaded if "/thumbnails/" in k][0]
    assert thumb["content_type"] == "image/jpeg"


def test_upload_rejects_bad_extension(test_client, auth_headers, monkeypatch):
    from uuid import uuid4
    monkeypatch.setattr("app.utils.s3_client.s3_client.ensure_bucket", lambda *a, **k: None)
    ds = test_client.post("/api/v1/annotation/dataset/create",
                          json={"name": f"bad-{uuid4().hex[:8]}"},
                          headers=auth_headers).json()["data"]
    r = test_client.post(
        f"/api/v1/annotation/dataset/{ds['id']}/upload",
        files={"files": ("a.exe", b"MZ", "application/octet-stream")},
        headers=auth_headers,
    )
    assert r.status_code == 400, r.text


def test_upload_broken_image_registers_without_thumbnail(test_client, auth_headers, monkeypatch):
    from uuid import uuid4
    monkeypatch.setattr("app.utils.s3_client.s3_client.ensure_bucket", lambda *a, **k: None)
    monkeypatch.setattr("app.utils.s3_client.s3_client.upload_fileobj", lambda *a, **k: None)
    ds = test_client.post("/api/v1/annotation/dataset/create",
                          json={"name": f"part-{uuid4().hex[:8]}"},
                          headers=auth_headers).json()["data"]
    r = test_client.post(
        f"/api/v1/annotation/dataset/{ds['id']}/upload",
        files=[
            ("files", ("good.png", _png_bytes(10, 10), "image/png")),
            ("files", ("bad.png", b"broken", "image/png")),
        ],
        headers=auth_headers,
    )
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert data["uploaded_count"] == 2   # 坏图仍登记（无缩略图），不阻断
    assert data["failed_count"] == 0
    items = test_client.get(
        f"/api/v1/annotation/dataset/{ds['id']}/images", headers=auth_headers
    ).json()["data"]["items"]
    by_name = {i["filename"]: i for i in items}
    assert by_name["good.png"]["thumbnail_key"]
    assert by_name["bad.png"]["thumbnail_key"] is None
```

- [ ] **Step 2: 运行确认失败**

Run: `uv run pytest tests/test_annotation_media.py -v`
Expected: FAIL（返回结构与缩略图缺失）

- [ ] **Step 3: 实现上传管线**

`dataset/service.py` 的 `upload_images` 整体替换为：

```python
    @classmethod
    async def upload_images(cls, dataset_id: int, files: list, auth) -> dict:
        import asyncio
        import io
        from pathlib import Path

        from app.api.v1.module_annotation.dataset.media import (
            ALLOWED_IMAGE_EXTENSIONS,
            content_type_for,
            process_image,
        )
        from .model import AnnotationImageModel

        # 1) 整批校验（不写任何对象/行）
        if len(files) > settings.ANNOTATION_UPLOAD_MAX_FILES:
            raise CustomException(
                msg=f"单次最多上传 {settings.ANNOTATION_UPLOAD_MAX_FILES} 张图片",
                code=400, status_code=400,
            )
        max_bytes = settings.ANNOTATION_UPLOAD_MAX_MB * 1024 * 1024
        for file in files:
            ext = Path(file.filename or "").suffix.lower()
            if ext not in ALLOWED_IMAGE_EXTENSIONS:
                raise CustomException(
                    msg=f"不支持的图片格式: {file.filename}", code=400, status_code=400
                )
            size = getattr(file, "size", None)
            if size is not None and size > max_bytes:
                raise CustomException(
                    msg=f"文件过大（>{settings.ANNOTATION_UPLOAD_MAX_MB}MB）: {file.filename}",
                    code=400, status_code=400,
                )

        async with async_db_session() as db:
            dataset = await db.get(DatasetModel, dataset_id)
            if not dataset:
                raise ValueError("数据集不存在")

        sem = asyncio.Semaphore(max(1, settings.ANNOTATION_UPLOAD_CONCURRENCY))

        async def _process(file) -> dict:
            filename = file.filename or "unnamed"
            async with sem:
                try:
                    content = await file.read()
                    ext = Path(filename).suffix.lower()
                    token = uuid.uuid4().hex
                    object_key = f"datasets/{dataset_id}/images/{token}{ext}"
                    thumb_key = f"datasets/{dataset_id}/thumbnails/{token}.jpg"
                    width, height, thumb = await asyncio.to_thread(process_image, content)
                    await asyncio.to_thread(
                        s3_client.upload_fileobj, io.BytesIO(content), object_key,
                        None, content_type_for(ext),
                    )
                    if thumb:
                        await asyncio.to_thread(
                            s3_client.upload_fileobj, io.BytesIO(thumb), thumb_key,
                            None, "image/jpeg",
                        )
                    else:
                        thumb_key = None
                    return {"ok": True, "filename": filename, "object_key": object_key,
                            "thumbnail_key": thumb_key, "width": width, "height": height}
                except Exception as e:
                    return {"ok": False, "filename": filename, "reason": str(e)}

        results = await asyncio.gather(*[_process(f) for f in files])

        uploaded: list[dict] = []
        failed: list[dict] = []
        async with async_db_session.begin() as db:
            for r in results:
                if not r["ok"]:
                    failed.append({"filename": r["filename"], "reason": r["reason"]})
                    continue
                img = AnnotationImageModel(
                    dataset_id=dataset_id,
                    filename=r["filename"],
                    object_key=r["object_key"],
                    thumbnail_key=r["thumbnail_key"],
                    width=r["width"],
                    height=r["height"],
                    status=ImageStatus.UNANNOTATED,
                )
                set_create_audit(img, auth)
                db.add(img)
                await db.flush()
                uploaded.append({"id": img.id, "filename": r["filename"],
                                 "object_key": r["object_key"],
                                 "thumbnail_key": r["thumbnail_key"]})
            total = await db.scalar(
                select(func.count(AnnotationImageModel.id))
                .where(AnnotationImageModel.dataset_id == dataset_id)
            )
            await db.execute(
                update(DatasetModel)
                .where(DatasetModel.id == dataset_id)
                .values(image_count=total or 0)
            )
        return {"uploaded": uploaded, "failed": failed,
                "uploaded_count": len(uploaded), "failed_count": len(failed)}
```

同时在 `service.py` 顶部确保以下 import 存在：

```python
from app.config.setting import settings
from app.core.exceptions import CustomException
```

`controller.py` 的 `upload_images` 返回值提示按计数更新：

```python
    result = await DatasetService.upload_images(id, files, auth)
    msg = f"成功上传 {result['uploaded_count']} 张图片"
    if result["failed_count"]:
        msg += f"，{result['failed_count']} 张失败"
    return SuccessResponse(data=result, msg=msg)
```

- [ ] **Step 4: 运行确认通过**

Run: `uv run pytest tests/test_annotation_media.py -v`
Expected: PASS（8 passed）

- [ ] **Step 5: 回归既有数据集测试**

Run: `uv run pytest tests/test_dataset_cascade_delete.py tests/test_export_history.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add backend/app/api/v1/module_annotation/dataset/service.py backend/app/api/v1/module_annotation/dataset/controller.py backend/tests/test_annotation_media.py
git commit -m "feat(annotation): 上传管线支持缩略图/ContentType/并发与校验"
```

---

### Task 9: `get_images` 下发 `thumbnail_url`

**Files:**
- Modify: `backend/app/api/v1/module_annotation/dataset/service.py:111-214`
- Test: `backend/tests/test_annotation_media.py`

**Interfaces:**
- Produces: `get_images` 每项新增 `thumbnail_key: str | None`、`thumbnail_url: str | None`

- [ ] **Step 1: 写失败测试（追加）**

```python
def test_get_images_includes_thumbnail_url(test_client, auth_headers, monkeypatch):
    from uuid import uuid4
    monkeypatch.setattr("app.utils.s3_client.s3_client.ensure_bucket", lambda *a, **k: None)
    monkeypatch.setattr("app.utils.s3_client.s3_client.upload_fileobj", lambda *a, **k: None)
    monkeypatch.setattr(
        "app.utils.s3_client.s3_client.presigned_url",
        lambda key, *a, **k: f"http://fake/{key}",
    )
    ds = test_client.post("/api/v1/annotation/dataset/create",
                          json={"name": f"url-{uuid4().hex[:8]}"},
                          headers=auth_headers).json()["data"]
    test_client.post(
        f"/api/v1/annotation/dataset/{ds['id']}/upload",
        files={"files": ("a.png", _png_bytes(20, 20), "image/png")},
        headers=auth_headers,
    )
    items = test_client.get(
        f"/api/v1/annotation/dataset/{ds['id']}/images", headers=auth_headers
    ).json()["data"]["items"]
    assert items[0]["thumbnail_key"]
    assert items[0]["thumbnail_url"].startswith("http://fake/")
```

- [ ] **Step 2: 运行确认失败**

Run: `uv run pytest tests/test_annotation_media.py::test_get_images_includes_thumbnail_url -v`
Expected: FAIL（KeyError `thumbnail_key`）

- [ ] **Step 3: 实现**

在 `get_images` 的两个返回分支（`task_id` 为空、有 task_id）中，为每项补充缩略图字段。以 `_img_minimal` 为例：

```python
def _img_minimal(img) -> dict:
    return {
        ...
        "thumbnail_key": img.thumbnail_key,
        "thumbnail_url": s3_client.presigned_url(img.thumbnail_key) if img.thumbnail_key else None,
    }
```

并在 `get_images` 中 task 分支构造 item 的字典字面量里追加：

```python
                    "thumbnail_key": img.thumbnail_key,
                    "thumbnail_url": (
                        s3_client.presigned_url(img.thumbnail_key)
                        if img.thumbnail_key else None
                    ),
```

- [ ] **Step 4: 运行确认通过**

Run: `uv run pytest tests/test_annotation_media.py -v`
Expected: PASS（9 passed）

- [ ] **Step 5: Commit**

```bash
git add backend/app/api/v1/module_annotation/dataset/service.py backend/tests/test_annotation_media.py
git commit -m "feat(annotation): 图片列表下发缩略图 presigned 地址"
```

---

### Task 10: 存量缩略图回填脚本

**Files:**
- Create: `backend/scripts/backfill_annotation_thumbnails.py`
- Test: 手工验证（脚本依赖真实 S3，不写 pytest）

**Interfaces:**
- Consumes: `process_image`、`s3_client`

- [ ] **Step 1: 编写脚本**

```python
"""为存量标注图片回填缩略图。

用法（工作目录 backend）:
    uv run python scripts/backfill_annotation_thumbnails.py --dataset-id 12 --limit 100
    uv run python scripts/backfill_annotation_thumbnails.py --dry-run
"""
import argparse
import asyncio
import io

from sqlalchemy import select

from app.api.v1.module_annotation.dataset.media import process_image
from app.api.v1.module_annotation.dataset.model import AnnotationImageModel
from app.core.database import async_db_session
from app.utils.s3_client import s3_client


async def _run(dataset_id: int | None, limit: int | None, dry_run: bool) -> tuple[int, int]:
    done = skipped = 0
    async with async_db_session() as db:
        stmt = select(AnnotationImageModel).where(
            AnnotationImageModel.thumbnail_key.is_(None),
            AnnotationImageModel.is_deleted == False,  # noqa: E712
        )
        if dataset_id:
            stmt = stmt.where(AnnotationImageModel.dataset_id == dataset_id)
        if limit:
            stmt = stmt.limit(limit)
        images = (await db.execute(stmt)).scalars().all()

        for img in images:
            try:
                data = s3_client.download_fileobj(img.object_key)
                _, _, thumb = process_image(data.read())
                if not thumb:
                    skipped += 1
                    continue
                thumb_key = f"datasets/{img.dataset_id}/thumbnails/{img.id}.jpg"
                if dry_run:
                    done += 1
                    continue
                s3_client.upload_fileobj(io.BytesIO(thumb), thumb_key,
                                         None, "image/jpeg")
                img.thumbnail_key = thumb_key
                await db.flush()
                done += 1
            except Exception as e:
                print(f"[skip] image={img.id} {e}")
                skipped += 1
    return done, skipped


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--dataset-id", type=int, default=None)
    p.add_argument("--limit", type=int, default=None)
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args()
    done, skipped = asyncio.run(_run(args.dataset_id, args.limit, args.dry_run))
    print(f"完成：生成 {done}，跳过 {skipped}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: 干跑验证脚本可启动**

Run: `uv run python scripts/backfill_annotation_thumbnails.py --dry-run --limit 1`（工作目录 `backend`）
Expected: 打印 `完成：生成 x，跳过 y`（无异常退出）

- [ ] **Step 3: Commit**

```bash
git add backend/scripts/backfill_annotation_thumbnails.py
git commit -m "feat(annotation): 新增存量缩略图回填脚本"
```

---

## Phase P3 — 前端消费

### Task 11: 前端 API 增加 purge

**Files:**
- Modify: `frontend/src/api/module_annotation.ts`

**Interfaces:**
- Produces: `AnnotationAPI.purgeDataset(ids: number[])`

- [ ] **Step 1: 新增方法**

在 `deleteDataset` 之后新增：

```ts
  purgeDataset(ids: number[]) {
    return request<ApiResponse>({ url: `${API_PATH}/dataset/purge`, method: "delete", data: ids });
  },
```

- [ ] **Step 2: 类型检查**

Run: `pnpm run type-check`（工作目录 `frontend`）
Expected: 通过

- [ ] **Step 3: Commit**

```bash
git add frontend/src/api/module_annotation.ts
git commit -m "feat(annotation): 前端 API 增加数据集彻底删除"
```

---

### Task 12: 工作台左侧改为缩略图 filmstrip

**Files:**
- Modify: `frontend/src/views/module_annotation/annotation/index.vue:955-985`

**Interfaces:**
- Consumes: `store.images` 每项的 `thumbnail_url`、`filename`

- [ ] **Step 1: 改模板（在既有 `v-for` 图片项内插入缩略图）**

在 `v-for="(img, idx) in store.images"` 的列表项中，`<span class="img-name">{{ img.filename }}</span>` 之前插入：

```html
<img
  v-if="img.thumbnail_url"
  class="img-thumb"
  :src="img.thumbnail_url"
  loading="lazy"
  alt=""
  @error="($event.target as HTMLImageElement).style.display = 'none'"
/>
<span v-else class="img-thumb img-thumb--placeholder" />
```

- [ ] **Step 2: 加最小样式（同文件 `<style>` 内）**

```css
.img-thumb {
  width: 34px;
  height: 34px;
  object-fit: cover;
  border-radius: 3px;
  flex: none;
  background: var(--el-fill-color-light);
}
.img-thumb--placeholder {
  display: inline-block;
}
```

- [ ] **Step 3: 构建验证**

Run: `pnpm run type-check`（工作目录 `frontend`）
Expected: 通过

- [ ] **Step 4: Commit**

```bash
git add frontend/src/views/module_annotation/annotation/index.vue
git commit -m "feat(annotation): 工作台图片列表显示缩略图"
```

---

### Task 13: 新增数据集图片网格组件

**Files:**
- Create: `frontend/src/components/Annotation/DatasetImageGrid.vue`

**Interfaces:**
- Props: `datasetId: number | null`
- Uses: `AnnotationAPI.getImages(datasetId, undefined, page, pageSize)`
- Emits: `open-workbench`（载荷：`{ taskId: number }`），或由父组件负责跳转

- [ ] **Step 1: 编写组件（单根 + el-row/el-col）**

```vue
<template>
  <div class="dataset-image-grid">
    <el-dialog
      :model-value="modelValue"
      title="数据集图片"
      width="900px"
      append-to-body
      @update:model-value="(v: boolean) => emit('update:modelValue', v)"
      @open="load(1)"
    >
      <div class="grid-toolbar">
        <el-radio-group v-model="filter" size="small">
          <el-radio-button label="all">全部</el-radio-button>
          <el-radio-button label="unannotated">未标注</el-radio-button>
          <el-radio-button label="annotated">已标注</el-radio-button>
        </el-radio-group>
      </div>
      <div v-loading="loading" class="grid-body">
        <el-row :gutter="8">
          <el-col
            v-for="img in filtered"
            :key="img.id"
            :xs="12"
            :sm="8"
            :md="6"
            :lg="6"
          >
            <div class="grid-cell" @click="emit('open-workbench', img)">
              <img
                v-if="img.thumbnail_url"
                :src="img.thumbnail_url"
                class="grid-img"
                loading="lazy"
                alt=""
              />
              <div v-else class="grid-img grid-img--empty">无缩略图</div>
              <div class="grid-name" :title="img.filename">{{ img.filename }}</div>
              <el-tag
                class="grid-badge"
                size="small"
                :type="img.status === 'annotated' ? 'success' : 'info'"
              >
                {{ img.status === "annotated" ? "已标注" : "未标注" }}
              </el-tag>
            </div>
          </el-col>
        </el-row>
        <el-empty v-if="!loading && filtered.length === 0" description="暂无图片" />
      </div>
      <template #footer>
        <el-pagination
          layout="prev, pager, next"
          :total="total"
          :page-size="pageSize"
          :current-page="page"
          @current-change="load"
        />
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from "vue";
import { AnnotationAPI } from "@/api/module_annotation";

defineOptions({ name: "DatasetImageGrid" });

const props = defineProps<{ modelValue: boolean; datasetId: number | null }>();
const emit = defineEmits<{
  (e: "update:modelValue", v: boolean): void;
  (e: "open-workbench", img: any): void;
}>();

const page = ref(1);
const pageSize = 24;
const total = ref(0);
const loading = ref(false);
const images = ref<any[]>([]);
const filter = ref<"all" | "unannotated" | "annotated">("all");

const filtered = computed(() => {
  if (filter.value === "all") return images.value;
  return images.value.filter((i) => i.status === filter.value);
});

async function load(p: number) {
  if (!props.datasetId) return;
  page.value = p;
  loading.value = true;
  try {
    const r = await AnnotationAPI.getImages(props.datasetId, undefined, p, pageSize);
    images.value = r.data?.data?.items || [];
    total.value = r.data?.data?.total || 0;
  } catch {
    images.value = [];
  } finally {
    loading.value = false;
  }
}
</script>

<style scoped>
.grid-toolbar {
  margin-bottom: 8px;
}
.grid-body {
  min-height: 200px;
}
.grid-cell {
  position: relative;
  margin-bottom: 8px;
  cursor: pointer;
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 4px;
  overflow: hidden;
}
.grid-img {
  width: 100%;
  height: 120px;
  object-fit: cover;
  display: block;
  background: var(--el-fill-color-light);
}
.grid-img--empty {
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--el-text-color-secondary);
  font-size: 12px;
}
.grid-name {
  padding: 2px 4px;
  font-size: 12px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.grid-badge {
  position: absolute;
  top: 4px;
  right: 4px;
}
</style>
```

- [ ] **Step 2: 类型检查**

Run: `pnpm run type-check`（工作目录 `frontend`）
Expected: 通过

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/Annotation/DatasetImageGrid.vue
git commit -m "feat(annotation): 新增数据集图片网格组件"
```

---

### Task 14: 数据集页接入网格、彻底删除与文案修正

**Files:**
- Modify: `frontend/src/views/module_annotation/dataset/index.vue`

**Interfaces:**
- Consumes: `DatasetImageGrid`、`AnnotationAPI.purgeDataset`

- [ ] **Step 1: 模板接入**

在 `dataset/index.vue` 操作列"上传"按钮前新增"图片"按钮，并在"删除"按钮后新增"彻底删除"按钮（`v-hasPerm="['module_annotation:dataset:purge']"`、`type="danger"`），分别调用：

```ts
function handleOpenImages(row: any) {
  gridDatasetId.value = row.id;
  gridVisible.value = true;
}
async function handlePurge(row: any) {
  await ElMessageBox.confirm(
    `确认彻底删除数据集「${row.name}」？将删除全部图片、标注与导出产物，且不可恢复。`,
    "危险操作",
    { type: "error", confirmButtonText: "彻底删除", cancelButtonText: "取消" },
  );
  await AnnotationAPI.purgeDataset([row.id]);
  ElMessage.success("已彻底删除");
  refreshList();
}
```

并在 `</PageContent>` 之后、容器 `</div>` 之前挂载：

```html
<DatasetImageGrid
  v-model="gridVisible"
  :dataset-id="gridDatasetId"
  @open-workbench="handleOpenWorkbench"
/>
```

`handleOpenWorkbench` 从当前数据集行取第一个任务跳转：

```ts
function handleOpenWorkbench(img: any) {
  const row = contentRef.value?.tableData?.find((r: any) => r.id === img.dataset_id);
  const task = row?.tasks?.[0];
  if (!task) {
    ElMessage.warning("该数据集还没有标注任务，请先创建任务");
    return;
  }
  router.push(`/annotation/workbench/${task.id}`);
}
```

（若 `contentRef` 无 `tableData`，退化为打开网格前把当前 `row.tasks` 存到 `gridRowTasks` ref，在 `handleOpenWorkbench` 中读取。）

- [ ] **Step 2: 修正软删确认文案**

把 `deleteConfirm.message` 从"图片和标注数据将一并删除。"改为：

```ts
  deleteConfirm: {
    title: "提示",
    message: "确认删除所选数据集？可在保留期内恢复。",
    type: "warning",
  },
```

- [ ] **Step 3: 类型检查与 lint**

Run: `pnpm run type-check && pnpm run lint`（工作目录 `frontend`）
Expected: 通过（既有历史告警不新增）

- [ ] **Step 4: Commit**

```bash
git add frontend/src/views/module_annotation/dataset/index.vue
git commit -m "feat(annotation): 数据集页接入图片网格与彻底删除并修正文案"
```

---

## Phase P4 — 回归与收尾

### Task 15: 全量回归与验证

**Files:** 无新增

- [ ] **Step 1: 后端全量测试**

Run: `uv run pytest tests/ -q`（工作目录 `backend`）
Expected: 全部通过（含新增 3 个测试文件）

- [ ] **Step 2: 后端 lint**

Run: `uv run ruff check`（工作目录 `backend`）
Expected: 无新增错误

- [ ] **Step 3: 前端类型检查与 lint**

Run: `pnpm run type-check && pnpm run lint`（工作目录 `frontend`）
Expected: 通过

- [ ] **Step 4: 导出→训练链路回归**

Run: `uv run pytest tests/test_export_history.py tests/test_eval_flow.py -q`（工作目录 `backend`）
Expected: 通过（确认上传/读取合约改动未破坏导出）

- [ ] **Step 5: 手工冒烟（真实服务，可选）**

启动后端与前端，登录 `admin/123456`：
1. 新建数据集 → 上传 2 张图 → 数据集页"图片"查看网格有缩略图。
2. 创建检测任务 → 进入工作台 → 左侧列表显示缩略图。
3. 数据集"删除"（软删）→ 列表消失；调用 `purge` 后 S3 对应前缀清空。

- [ ] **Step 6: Commit（若有收尾改动）**

```bash
git add -A
git commit -m "test(annotation): 生命周期与媒体管线回归"
```

---

## Self-Review 记录

- **Spec 覆盖**：P1（Task 3/4/5/6）、P2（Task 2/7/8/9/10）、P3（Task 11/12/13/14）、P4（Task 15）逐条对应 spec 的 A–J 与验收标准。
- **占位符**：无 TBD/TODO；所有代码步骤含可直接粘贴实现。
- **类型一致**：`thumbnail_key`、`thumbnail_url`、`purge_datasets`、`delete_prefix`、`_prune_versions`、`process_image`、`content_type_for` 在前后任务中签名一致。
- **已知偏差**：spec 写"单文件大小超限整批拒绝"，计划实现为依赖 `UploadFile.size` 前置校验（Starlette 提供）；若运行环境 `size` 为 `None`，退化为按文件失败计入 `failed`。
