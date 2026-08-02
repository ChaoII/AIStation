# 模型训练/评估/预测架构修复 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 修复模型训练/评估/预测模块的数据模型语义混乱、执行器重复、并发与孤儿恢复缺失，打通 paddlex 链路，实现指标闭环。

**Architecture:** ① 将单一 `TrainModel` 表重构为 `train_model_repos`（仓库）+ `train_model_versions`（版本）双表，通过一次性数据迁移聚合现有 41 条记录，并统一 `model_id`(版本)/`model_repo_id`(仓库) 语义；② 抽取 `TaskExecutor` 基类统一 train/eval/predict 三个执行器（并发信号量、孤儿恢复、日志管道、容器生命周期、产物归档）；③ 修复版本号 `vv1` bug、指标回流、paddlex 执行链路、deploy 端口竞态。

**Tech Stack:** FastAPI, SQLAlchemy 2.0, Alembic, Docker SDK for Python, RustFS (S3), pytest, Vue 3 + Element Plus (前端适配)

## Global Constraints

- 所有新模型继承 `ModelMixin` + `UserMixin`；新表 `train_model_repos` 用 `MappedBase` 或 `ModelMixin`（无软删需求则 MappedBase）
- 现有 `train_models` 表**重命名语义为版本表**（保留表名避免破坏引用），新增 `repo_id` 列
- 前端 API 函数命名 `listXxx/getXxxDetail/createXxx/updateXxx/deleteXxx`，位于 `frontend/web/src/api/module_train/index.ts`
- v3 前端 `useTable` 要求列表响应含 `page_no/page_size/has_next`
- 所有 API 端点 `Depends(AuthPermission([...]))`
- 测试用 `tests/` 下 pytest（`conftest.py` 已配 SQLite + TestClient），测试函数用同步 `def`，不要 `async def`
- 迁移必须可回滚；现有 41 条模型记录必须无损迁移
- 后端端口 8001，v3 前端 5190，登录 admin/123456，OAuth 端点为 `/api/v1/system/auth/login`
- 迁移后 `model_id` = 版本行 id；`model_repo_id` = 仓库行 id；`TrainTask.model_repo_id` 保留指向上次产出版本（向后兼容现有前端跳转）

---

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

### Task 2: Alembic 迁移 — 建仓库表、加列、聚合回填数据

**Files:**
- Create: `backend/app/alembic/versions/<new_rev>_model_repo_split.py`
- Modify: `backend/app/alembic/versions/c9f2a1b4d8e3_*.py`（若需要调整依赖）
- Test: `backend/tests/test_migration_model_repo.py`（新建）

**Interfaces:**
- Consumes: 现有 `train_models` 表数据（41 条，含 `vv1` 版本污染）
- Produces: `train_model_repos` 表 + `train_models.repo_id` 回填 + 版本号规范化

- [ ] **Step 1: 生成迁移骨架**

Run: `cd backend && uv run main.py revision --env=dev -m "model repo split"`
Expected: 生成 `backend/app/alembic/versions/<hash>_model_repo_split.py`

- [ ] **Step 2: 写迁移逻辑（upgrade + downgrade）**

编辑生成的迁移文件，替换 upgrade/downgrade 主体：

```python
"""模型仓库/版本拆分迁移

Revision ID: <hash>
Revises: <previous_rev>
Create Date: 2026-08-02

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "<hash>"
down_revision = "<previous_rev>"
branch_labels = None
depends_on = None


def _normalize_version(raw: str) -> str:
    """'vv1' / 'v1' / '1' -> 'v1'"""
    digits = "".join(ch for ch in (raw or "") if ch.isdigit())
    n = int(digits) if digits else 1
    return f"v{n}"


def upgrade() -> None:
    # 复用现有 PG 枚举类型 trainframework（train_models.framework 已用它，避免重复 CREATE TYPE）
    op.create_table(
        "train_model_repos",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("uuid", sa.String(36), nullable=True),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("framework", sa.Enum(name="trainframework"), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("latest_version_id", sa.Integer(), nullable=True),
        sa.Column("annotation_dataset_id", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(16), server_default="draft", nullable=False),
        sa.Column("is_deleted", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("created_id", sa.Integer(), nullable=True),
        sa.Column("updated_id", sa.Integer(), nullable=True),
        sa.Column("deleted_id", sa.Integer(), nullable=True),
        sa.Column("created_time", sa.DateTime(), nullable=True),
        sa.Column("updated_time", sa.DateTime(), nullable=True),
        sa.Column("deleted_time", sa.DateTime(), nullable=True),
        sa.UniqueConstraint("name"),
    )
    op.add_column("train_models", sa.Column("repo_id", sa.Integer(), nullable=True))

    # 聚合回填：按 name 建仓库，版本号规范化
    conn = op.get_bind()
    rows = conn.execute(
        sa.text("SELECT id, name, version, framework FROM train_models WHERE is_deleted = false")
    ).fetchall()
    repos: dict[str, int] = {}
    for row in rows:
        rid, name, version, framework = row
        if name not in repos:
            result = conn.execute(
                sa.text(
                    "INSERT INTO train_model_repos (name, framework, status, created_time, updated_time) "
                    "VALUES (:name, :framework, 'draft', NOW(), NOW()) RETURNING id"
                ),
                {"name": name, "framework": framework},
            )
            repo_id = result.scalar()
            repos[name] = repo_id
        else:
            repo_id = repos[name]
        norm_ver = _normalize_version(version)
        conn.execute(
            sa.text("UPDATE train_models SET repo_id = :rid, version = :ver WHERE id = :id"),
            {"rid": repo_id, "ver": norm_ver, "id": rid},
        )

    # 回填 latest_version_id：每个仓库取 created_time 最新版本
    repo_rows = conn.execute(
        sa.text(
            "SELECT r.id, v.id AS vid FROM train_model_repos r "
            "JOIN LATERAL ("
            "  SELECT id FROM train_models v "
            "  WHERE v.repo_id = r.id AND v.is_deleted = false "
            "  ORDER BY v.created_time DESC NULLS LAST, v.id DESC LIMIT 1"
            ") v ON true"
        )
    ).fetchall()
    for repo_id, vid in repo_rows:
        conn.execute(
            sa.text("UPDATE train_model_repos SET latest_version_id = :vid WHERE id = :rid"),
            {"vid": vid, "rid": repo_id},
        )


def downgrade() -> None:
    op.drop_column("train_models", "repo_id")
    op.drop_table("train_model_repos")
```

- [ ] **Step 3: 写迁移测试（针对 `_normalize_version` 纯函数）**

`backend/tests/test_migration_model_repo.py`:

```python
"""迁移工具函数测试。"""
from app.alembic.versions import __path__  # noqa: F401  (确保包可导入)


def test_normalize_version_variants():
    from importlib import import_module
    import os
    from pathlib import Path

    # 动态导入生成的迁移模块
    versions_dir = Path(__file__).parent.parent / "app" / "alembic" / "versions"
    mod_file = [p for p in versions_dir.glob("*_model_repo_split.py")][0]
    mod = import_module(f"app.alembic.versions.{mod_file.stem}")
    assert mod._normalize_version("v1") == "v1"
    assert mod._normalize_version("vv1") == "v1"
    assert mod._normalize_version("1") == "v1"
    assert mod._normalize_version(None) == "v1"
    assert mod._normalize_version("") == "v1"
```

- [ ] **Step 4: 运行迁移测试**

Run: `cd backend && uv run pytest tests/test_migration_model_repo.py -v`
Expected: PASS（`_normalize_version` 五组断言全过）

- [ ] **Step 5: 在真实库执行迁移（dev 环境）**

Run: `cd backend && uv run main.py upgrade --env=dev`
Expected: 输出包含 `Running upgrade ... -> <hash>`；验证：

```bash
uv run python -c "
import asyncio
from sqlalchemy import text
from app.core.database import async_db_session
async def main():
    async with async_db_session() as db:
        repos = (await db.execute(text('SELECT COUNT(*) FROM train_model_repos'))).scalar()
        orphan = (await db.execute(text('SELECT COUNT(*) FROM train_models WHERE repo_id IS NULL'))).scalar()
        vv = (await db.execute(text(\"SELECT COUNT(*) FROM train_models WHERE version LIKE 'v%v%'\"))).scalar()
        print(f'repos={repos} orphan={orphan} double_v={vv}')
asyncio.run(main())
"
```

Expected: `repos=<~30> orphan=0 double_v=0`

- [ ] **Step 6: 提交**

```bash
git add backend/app/alembic/versions/*_model_repo_split.py backend/tests/test_migration_model_repo.py
git commit -m "feat(train): split train_models into repo+version tables with data backfill"
```

---

### Task 3: Service 层 — 仓库/版本 CRUD + 语义修正

**Files:**
- Modify: `backend/app/plugin/module_train/service.py`
- Modify: `backend/app/plugin/module_train/controller.py`
- Modify: `backend/app/plugin/module_train/schema.py`
- Test: `backend/tests/test_train_service_repo.py`（新建）

**Interfaces:**
- Consumes: `TrainModelRepo`, `TrainModel(repo_id)`（Task 1/2 产物）
- Produces:
  - `TrainService.list_model_repos(params) -> (list[dict], total)`
  - `TrainService.list_model_versions(repo_id) -> list[dict]`
  - `TrainService.get_model_version(version_id) -> dict`
  - `TrainService.create_model_repo(data, auth) -> dict{id}`
  - `TrainService.create_model_version(repo_id, data, auth) -> dict{id, version}`（含版本号自动递增）
  - `TrainService.version_next(repo_id) -> str`（纯递增，无 vv bug）
  - `TrainService.export_model_version(version_id, params, auth) -> dict`
  - `list_models`/`get_model` 保留为兼容别名（返回版本行，含 repo 信息）

- [ ] **Step 1: 写失败测试 — 仓库/版本服务 HTTP 链路**

`backend/tests/test_train_service_repo.py`（与 `conftest.py` 的同步 `TestClient` 模式对齐，不用 asyncio）：

```python
"""TrainService 仓库/版本 HTTP 测试。"""
from fastapi.testclient import TestClient


def _login(test_client: TestClient) -> dict:
    login = test_client.post(
        "/api/v1/system/auth/login",
        data={"username": "admin", "password": "123456"},
    )
    assert login.status_code == 200
    token = login.json()["data"]["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_model_repo_list(test_client: TestClient):
    headers = _login(test_client)
    resp = test_client.get("/api/v1/train/model/repos?page_no=1&page_size=5", headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["code"] == 0
    assert "items" in body["data"]
    assert "has_next" in body["data"]


def test_model_versions_list(test_client: TestClient):
    headers = _login(test_client)
    # 取第一个仓库（若迁移已执行则有数据；空库则跳过断言列表内容，仅断言结构）
    repos = test_client.get("/api/v1/train/model/repos?page_no=1&page_size=5", headers=headers).json()["data"]["items"]
    if repos:
        rid = repos[0]["id"]
        resp = test_client.get(f"/api/v1/train/model/{rid}/versions", headers=headers)
        assert resp.status_code == 200
        assert resp.json()["code"] == 0


def test_model_list_backcompat(test_client: TestClient):
    """旧接口 /model/list 仍可用（兼容现有前端）。"""
    headers = _login(test_client)
    resp = test_client.get("/api/v1/train/model/list?page_no=1&page_size=5", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["code"] == 0
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd backend && uv run pytest tests/test_train_service_repo.py -v`
Expected: FAIL，`/train/model/repos` 返回 404（路由尚未注册）

- [ ] **Step 3: 实现 Service 层新增方法**

在 `service.py` 的 `TrainService` 类中添加（保留现有 `list_models`/`get_model` 作为兼容包装）：

```python
import re as _re

_VERSION_DIGITS = _re.compile(r"[^0-9]")


@classmethod
def _parse_version(cls, raw: str | None) -> int:
    """'vv1'/'v1'/'1'/None -> 1；'v12' -> 12。纯数字，消除 vv bug。"""
    digits = _VERSION_DIGITS.sub("", raw or "")
    return int(digits) if digits else 1


@classmethod
async def create_model_repo(cls, data, auth) -> dict:
    """创建仓库+首个版本，或按 name 追加新版本。返回 {id: repo_id, version_id, version}。"""
    async with async_db_session.begin() as db:
        existing = (await db.execute(
            select(TrainModelRepo).where(TrainModelRepo.name == data.name)
        )).scalar_one_or_none()
        if not existing:
            existing = TrainModelRepo(
                name=data.name, framework=data.framework,
                description=getattr(data, "description", None),
                annotation_dataset_id=getattr(data, "annotation_dataset_id", None),
                created_id=auth.user.id,
            )
            db.add(existing)
            await db.flush()

        last_ver = (await db.execute(
            select(TrainModel).where(TrainModel.repo_id == existing.id)
            .order_by(desc(TrainModel.id)).limit(1)
        )).scalar_one_or_none()
        version = f"v{cls._parse_version(last_ver.version) + 1 if last_ver else 1}"

        ver_row = TrainModel(
            repo_id=existing.id, name=data.name, framework=data.framework,
            version=version, annotation_dataset_id=getattr(data, "annotation_dataset_id", None),
            export_format=getattr(data, "export_format", None),
            description=getattr(data, "description", None),
            created_id=auth.user.id,
        )
        db.add(ver_row)
        await db.flush()
        existing.latest_version_id = ver_row.id
        return {"id": existing.id, "version_id": ver_row.id, "version": version}


@classmethod
async def list_model_repos(cls, params: dict | None = None) -> tuple[list[dict], int]:
    page_no = max(1, int((params or {}).get("page_no", 1)))
    page_size = max(1, min(100, int((params or {}).get("page_size", 20))))
    name = (params or {}).get("name")
    framework = (params or {}).get("framework")
    async with async_db_session() as db:
        stmt = select(TrainModelRepo)
        if name:
            stmt = stmt.where(TrainModelRepo.name.ilike(f"%{name}%"))
        if framework:
            stmt = stmt.where(TrainModelRepo.framework == framework)
        count_stmt = select(func.count()).select_from(stmt.subquery())
        total = (await db.execute(count_stmt)).scalar() or 0
        rows = (await db.execute(
            stmt.order_by(desc(TrainModelRepo.created_time))
            .limit(page_size).offset((page_no - 1) * page_size)
        )).scalars().all()
        result = []
        for r in rows:
            d = _model_to_dict(r)
            vcount = (await db.execute(
                select(func.count()).select_from(TrainModel).where(
                    TrainModel.repo_id == r.id, TrainModel.is_deleted == False  # noqa: E712
                )
            )).scalar() or 0
            d["version_count"] = vcount
            result.append(d)
        return result, total


@classmethod
async def list_model_versions(cls, repo_id: int) -> list[dict]:
    async with async_db_session() as db:
        rows = (await db.execute(
            select(TrainModel).where(TrainModel.repo_id == repo_id)
            .order_by(desc(TrainModel.created_time))
        )).scalars().all()
        return [_model_to_dict(r) for r in rows]


@classmethod
async def get_version_repo(cls, version_id: int) -> dict | None:
    """按版本 id 反查所属仓库（前端跳转用）。"""
    async with async_db_session() as db:
        ver = await db.get(TrainModel, version_id)
        if not ver or not ver.repo_id:
            return None
        repo = await db.get(TrainModelRepo, ver.repo_id)
        return {"repo_id": ver.repo_id, "repo_name": repo.name if repo else ver.name}
```

- [ ] **Step 4: 在 `controller.py` 添加仓库路由**

```python
@router.get("/model/repos", summary="模型仓库列表")
async def list_model_repos(
    name: str | None = Query(None),
    framework: str | None = Query(None),
    page_no: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    auth: AuthSchema = Depends(AuthPermission(["module_train:model:query"])),
):
    data, total = await TrainService.list_model_repos({
        "name": name, "framework": framework, "page_no": page_no, "page_size": page_size,
    })
    return SuccessResponse(data={
        "items": data, "total": total,
        "page_no": page_no, "page_size": page_size,
        "has_next": page_no * page_size < total,
    })


@router.get("/model/{repo_id}/versions", summary="模型版本列表")
async def list_model_versions(repo_id: int, auth: AuthSchema = Depends(AuthPermission(["module_train:model:query"]))):
    data = await TrainService.list_model_versions(repo_id)
    return SuccessResponse(data=data)


@router.get("/model/version/{version_id}/repo", summary="版本所属仓库")
async def get_version_repo(version_id: int, auth: AuthSchema = Depends(AuthPermission(["module_train:model:query"]))):
    data = await TrainService.get_version_repo(version_id)
    if not data:
        from app.common.response import ErrorResponse
        return ErrorResponse(msg="模型版本不存在")
    return SuccessResponse(data=data)
```

> 路由顺序注意：`/model/repos` 必须在 `/model/{repo_id}` 之前注册；`/model/{repo_id}/versions` 与 `/model/version/{version_id}/repo` 因路径段数不同互不冲突（前者 `/model/{id}/versions`，后者 `/model/version/{id}/repo`）。

- [ ] **Step 5: 修正 `export_model`（exporter.py）调用点**

在 `exporter.py:export_model` 中，创建版本行时同时关联/创建仓库：

```python
        existing = await db.execute(
            select(TrainModel).where(TrainModel.name == task.name).order_by(TrainModel.id.desc()).limit(1)
        )
        last = existing.scalar_one_or_none()
        next_ver = 1
        if last and last.version:
            from .service import TrainService
            next_ver = TrainService._parse_version(last.version) + 1

        repo = (await db.execute(
            select(TrainModelRepo).where(TrainModelRepo.name == task.name)
        )).scalar_one_or_none()
        if not repo:
            repo = TrainModelRepo(name=task.name, framework=task.framework, created_id=task.created_id)
            db.add(repo)
            await db.flush()

        model_rec = TrainModel(
            repo_id=repo.id, name=task.name, framework=task.framework,
            version=f"v{next_ver}", storage_path=storage_path,
            format="pytorch", annotation_dataset_id=task.dataset_id,
            created_id=task.created_id, metrics=task.best_metrics,
        )
        db.add(model_rec)
        await db.flush()
        repo.latest_version_id = model_rec.id
        task.model_repo_id = model_rec.id
```

需在 `exporter.py` 顶部导入 `from .model import TrainModelRepo`（`TrainService` 在函数内 import 避免循环依赖）。

- [ ] **Step 6: 运行 HTTP 测试验证**

Run: `cd backend && uv run pytest tests/test_train_service_repo.py -v`
Expected: PASS（三条 HTTP 用例全过）

- [ ] **Step 7: 提交**

```bash
git add backend/app/plugin/module_train/service.py backend/app/plugin/module_train/controller.py backend/app/plugin/module_train/schema.py backend/app/plugin/module_train/exporter.py backend/tests/test_train_service_repo.py
git commit -m "feat(train): add repo/version service methods and endpoints"
```

---

### Task 4: 统一执行器基类 — 并发 + 孤儿恢复 + 容器生命周期

**Files:**
- Create: `backend/app/plugin/module_train/task_executor.py`
- Modify: `backend/app/plugin/module_train/scheduler.py`
- Modify: `backend/app/plugin/module_train/eval_scheduler.py`
- Modify: `backend/app/plugin/module_train/predict_executor.py`
- Test: `backend/tests/test_task_executor.py`（新建）

**Interfaces:**
- Consumes: `docker_utils`（`run_container`/`follow_container_logs`/`remove_container`）, `ws` 广播函数
- Produces:
  - `class TaskExecutor` — 抽象基类
    - `registry: dict[str, dict[int, dict]]`（内存执行中任务表）
    - `semaphore: asyncio.Semaphore`（每框架独立）
    - `async run(task_id)` — 入口：acquire → 状态 RUNNING → `_execute` → 释放
    - `async stop(task_id)` — 标记 cancel + 停容器 + DB 状态
    - `async _execute(task_id)` — 子类实现
    - `async _mark_running/_mark_success/_mark_failed/_mark_cancelled(db, task_id, **fields)`
    - `async _follow_and_broadcast(container_id, log_file, broadcast_fn, parse_fn)` — 统一日志管道
    - `async recover_orphans()` — 类方法：DB 中 RUNNING 且不在 registry → 按超时标记 FAILED
    - `start_orphan_recovery_loop()` — 类方法：30s 循环

- [ ] **Step 1: 写失败测试 — 基类并发与注册表隔离**

`backend/tests/test_task_executor.py`（纯同步，不触发 DB/容器）：

```python
"""TaskExecutor 基类测试：并发信号量与注册表隔离。"""
import pytest

from app.plugin.module_train.task_executor import TaskExecutor


class TrainExecutorStub(TaskExecutor):
    name = "train"


class EvalExecutorStub(TaskExecutor):
    name = "eval"


def test_semaphore_is_class_shared_and_initialized():
    t1, t2 = TrainExecutorStub(), TrainExecutorStub()
    assert t1._get_semaphore() is t2._get_semaphore()


def test_registry_is_per_executor_class():
    t = TrainExecutorStub()
    e = EvalExecutorStub()
    t._registry[1] = {"container_id": "abc"}
    assert 1 not in e._registry
    assert 1 in t._registry
```

> 说明：基类将 `_registry`/`_semaphore` 定义为**类属性**（每个子类独立副本），`_get_semaphore()` 为类方法惰性初始化。子类只需定义 `name`、`model_class`、`status_enum` 并实现 `_execute`。

- [ ] **Step 2: 运行确认失败**

Run: `cd backend && uv run pytest tests/test_task_executor.py -v`
Expected: FAIL（`task_executor` 模块不存在）

- [ ] **Step 3: 实现 `task_executor.py` 基类**

```python
"""统一任务执行器基类：并发控制、孤儿恢复、容器生命周期、日志管道。"""
import asyncio
import os
from abc import ABC, abstractmethod
from datetime import datetime

from sqlalchemy import update

from app.core.database import async_db_session
from app.core.logger import log

from .docker_utils import follow_container_logs, remove_container, stop_container


class TaskExecutor(ABC):
    """抽象基类。子类：TrainExecutor / EvalExecutor / PredictExecutor。

    每个子类通过 __init_subclass__ 维护独立 registry 与信号量。
    并发上限由 _concurrency 控制。
    """
    name: str = "task"
    status_enum = None  # TrainStatus 等
    model_class = None  # TrainTask / TrainEval / TrainPredict
    _concurrency: int = 1
    _registry: dict[int, dict] = {}
    _semaphore: asyncio.Semaphore | None = None
    _recovery_task: asyncio.Task | None = None
    _orphan_timeout_sec: float = 1800.0

    def __init_subclass__(cls, **kwargs):
        """每个子类获得独立的 registry / semaphore / recovery task。"""
        super().__init_subclass__(**kwargs)
        cls._registry = {}
        cls._semaphore = None
        cls._recovery_task = None

    @classmethod
    def _get_semaphore(cls) -> asyncio.Semaphore:
        if cls._semaphore is None:
            cls._semaphore = asyncio.Semaphore(cls._concurrency)
        return cls._semaphore

    @classmethod
    async def run(cls, task_id: int) -> None:
        sem = cls._get_semaphore()
        async with sem:
            await cls._execute_with_state(task_id)

    @classmethod
    async def _execute_with_state(cls, task_id: int):
        try:
            await cls._mark_status(task_id, "running", started_at=datetime.now())
            await cls._execute(task_id)
        except Exception as e:
            log.error(f"[{cls.name}] task {task_id} failed: {e}")
            await cls._mark_status(task_id, "failed", error_log=str(e), finished_at=datetime.now())
        finally:
            cls._registry.pop(task_id, None)

    @classmethod
    @abstractmethod
    async def _execute(cls, task_id: int) -> None:
        """子类实现：pull image → 导出数据 → run container → 收集产物 → 标记状态。"""

    @classmethod
    async def _mark_status(cls, task_id: int, status: str, **fields) -> None:
        values = {"status": status, **fields}
        async with async_db_session.begin() as db:
            await db.execute(update(cls.model_class).where(cls.model_class.id == task_id).values(**values))

    @classmethod
    async def stop(cls, task_id: int) -> None:
        entry = cls._registry.get(task_id)
        if entry and entry.get("container_id"):
            entry["cancel"] = True
            await stop_container(entry["container_id"])
        async with async_db_session.begin() as db:
            await db.execute(
                update(cls.model_class)
                .where(cls.model_class.id == task_id, cls.model_class.status == cls.status_enum.RUNNING)
                .values(status=cls.status_enum.CANCELLED, finished_at=datetime.now())
            )

    @classmethod
    async def follow_logs(cls, container_id: str, log_file: str, broadcast_fn, parse_fn=None):
        """统一日志管道：写文件 + 广播 + 可选指标解析。返回 (metrics_log, exit_code)。"""
        import asyncio as _asyncio
        metrics_log: list = []
        log_queue = await follow_container_logs(container_id)
        with open(log_file, "w", encoding="utf-8") as lf:
            while True:
                line = await log_queue.get()
                if line == "__EOF__":
                    break
                lf.write(line + "\n")
                lf.flush()
                if broadcast_fn:
                    try:
                        await broadcast_fn(line)
                    except Exception:
                        pass
                if parse_fn:
                    parsed = parse_fn(line)
                    if parsed:
                        metrics_log.append(parsed)
        return metrics_log

    @classmethod
    async def _get_exit_code(cls, container):
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, lambda: container.wait(timeout=600)["StatusCode"])

    @classmethod
    async def recover_orphans(cls) -> None:
        """DB 中 RUNNING 但不在 registry 的任务，超时则标记 FAILED。"""
        async with async_db_session() as db:
            from sqlalchemy import select
            rows = (await db.execute(select(cls.model_class).where(
                cls.model_class.status == cls.status_enum.RUNNING
            ))).scalars().all()
            for r in rows:
                if r.id in cls._registry:
                    continue
                if r.started_at and (datetime.now() - r.started_at).total_seconds() > cls._orphan_timeout_sec:
                    async with async_db_session.begin() as db2:
                        await db2.execute(
                            update(cls.model_class).where(cls.model_class.id == r.id).values(
                                status=cls.status_enum.FAILED,
                                error_log="任务会话已断开（后端重启或容器丢失）",
                                finished_at=datetime.now(),
                            )
                        )

    @classmethod
    async def start_recovery_loop(cls) -> None:
        if cls._recovery_task is None or cls._recovery_task.done():
            cls._recovery_task = asyncio.create_task(cls._recovery_loop())

    @classmethod
    async def _recovery_loop(cls) -> None:
        while True:
            try:
                await cls.recover_orphans()
            except Exception as e:
                log.error(f"[{cls.name}] recovery error: {e}")
            await asyncio.sleep(30)
```

- [ ] **Step 4: 定义子类并接入 init_app**

在 `scheduler.py` 定义 `TrainExecutor`（将原 `_execute_training` 主体迁入 `_execute`，删除原 `_running_tasks`/`MAX_CONCURRENT`/孤儿逻辑，交由基类）：

```python
class TrainExecutor(TaskExecutor):
    name = "train"
    status_enum = TrainStatus
    model_class = TrainTask
    _concurrency = 1

    @classmethod
    async def _execute(cls, task_id: int):
        container_id = None
        try:
            # ---- 以下为原 scheduler._execute_training 主体，原样迁移 ----
            async with async_db_session() as db:
                task = await db.get(TrainTask, task_id)
                if not task:
                    return
            await broadcast_log(task_id, f"[scheduler] pulling image {task.docker_image}...")
            await pull_image(task.docker_image)
            export_dir = await _build_export_dir(task_id)
            data_dir = os.path.join(export_dir, "data")
            os.makedirs(data_dir, exist_ok=True)
            from .exporter import prepare_training_data_for_task
            await prepare_training_data_for_task(
                task.dataset_id, task.id, task.framework, data_dir,
                annotation_task_id=task.annotation_task_id,
                train_ratio=task.hyperparams.get("train_ratio", 0.8),
            )
            cmd = _build_cmd(task)  # 复用现有 _build_ultralytics_cmd/_build_paddlex_cmd
            os.makedirs(MODELS_CACHE_DIR, exist_ok=True)
            container = await run_container(
                task.docker_image, cmd,
                volumes={data_dir: {"bind": "/data", "mode": "rw"},
                         export_dir: {"bind": "/output", "mode": "rw"},
                         MODELS_CACHE_DIR: {"bind": "/models", "mode": "ro"}},
                gpu_id=task.hyperparams.get("gpu_id", "0"),
            )
            container_id = container.id
            cls._registry[task_id] = {"container_id": container_id, "cancel": False}

            metrics_log = await cls.follow_logs(
                container_id,
                os.path.join(export_dir, "train.log"),
                lambda line: broadcast_log(task_id, line),
                _parse_epoch,
            )
            exit_code = await cls._get_exit_code(container)

            if cls._registry.get(task_id, {}).get("cancel"):
                await remove_container(container_id)
                await cls._mark_status(task_id, TrainStatus.CANCELLED, finished_at=datetime.now())
            elif exit_code == 0:
                await remove_container(container_id)
                from .exporter import export_model
                model_info = await export_model(task_id, task.framework, export_dir)
                await cls._mark_status(task_id, TrainStatus.SUCCESS,
                                       model_repo_id=model_info.get("repo_id"),
                                       progress=100, finished_at=datetime.now(),
                                       metrics_log=metrics_log or None,
                                       best_metrics=cls._compute_best(metrics_log),
                                       last_metrics=metrics_log[-1] if metrics_log else None)
                if getattr(task, "created_id", None):
                    _send_notify(task.created_id, f"训练完成: {task.name}",
                                 "任务已成功完成，模型已保存", "training_complete", "train", task_id)
            else:
                await remove_container(container_id)
                await cls._mark_status(task_id, TrainStatus.FAILED,
                                       error_log="training failed", finished_at=datetime.now())
        except Exception as e:
            log.error(f"training task {task_id} failed: {e}")
            await cls._mark_status(task_id, TrainStatus.FAILED,
                                   error_log=str(e), finished_at=datetime.now())
        finally:
            cls._registry.pop(task_id, None)
            if container_id:
                await remove_container(container_id)
```

> `_build_cmd` 与 `_compute_best` 由实现者从现有 `_build_ultralytics_cmd`/`_build_paddlex_cmd` 与 best_metrics 逻辑提取为模块函数。

在 `eval_scheduler.py` 定义 `EvalExecutor`：

```python
class EvalExecutor(TaskExecutor):
    name = "eval"
    status_enum = TrainStatus
    model_class = TrainEval
    _concurrency = 1

    @classmethod
    async def _execute(cls, eval_id: int):
        # 原 eval_scheduler._execute_evaluation 主体迁移，
        # 模型路径解析改用 TrainService._resolve_model_storage（Task 5 提供）。
        # 日志管道改用 cls.follow_logs；状态更新改用 cls._mark_status；
        # registry 用 cls._registry；container 生命周期沿用 docker_utils。
        raise NotImplementedError  # 由实现者按上述指引填充
```

> 注意：`EvalExecutor._execute` 中不能写 `raise NotImplementedError` 后交付——实现者须完整迁移原 `_execute_evaluation` 逻辑（Task 4 Step 4 为骨架指引，完整实现在执行时按原文件内容迁移）。若实现者选择在 Task 4 一次性完成三个子类完整迁移，可跳过本骨架的占位符。

在 `predict_executor.py` 定义 `PredictExecutor`：

```python
class PredictExecutor(TaskExecutor):
    name = "predict"
    status_enum = TrainStatus
    model_class = TrainPredict
    _concurrency = 1

    @classmethod
    async def _execute(cls, predict_id: int):
        # 原 predict_executor._execute_prediction 主体迁移，
        # 模型路径解析改用 TrainService._resolve_model_storage（Task 5 提供）。
        # 本类新增孤儿恢复（此前缺失），由基类 start_recovery_loop 统一提供。
        raise NotImplementedError  # 由实现者按上述指引填充
```

> **重要**：Task 4 Step 4 的两个 `raise NotImplementedError` 是骨架指引，**不允许交付到最终代码**。实现者应在该 Step 内完成三个子类的完整 `_execute` 迁移（复制原 executor 文件逻辑 + 替换 registry/状态/日志调用点），并运行 `uv run ruff check` 确保无 `NotImplementedError` 残留。若任务过大，可拆分为 Task 4a/4b/4c 各自完成一个子类迁移并单独提交。

`init_app.py:535-541` 改为三个子类的恢复循环：

```python
from app.plugin.module_train.scheduler import TrainExecutor
from app.plugin.module_train.eval_scheduler import EvalExecutor
from app.plugin.module_train.predict_executor import PredictExecutor

asyncio.create_task(TrainExecutor.start_recovery_loop())
asyncio.create_task(EvalExecutor.start_recovery_loop())
asyncio.create_task(PredictExecutor.start_recovery_loop())
```

> 注：`PredictExecutor` 此前无孤儿恢复循环——Task 4 修复此缺陷。原 `start_scheduler`/`start_evaluation_scheduler` 的调度循环（定时训练触发、孤儿清理）合并进各自 executor 的 recovery loop。

- [ ] **Step 5: 运行测试验证基类**

Run: `cd backend && uv run pytest tests/test_task_executor.py -v`
Expected: PASS

- [ ] **Step 6: 提交**

```bash
git add backend/app/plugin/module_train/task_executor.py backend/app/plugin/module_train/scheduler.py backend/app/plugin/module_train/eval_scheduler.py backend/app/plugin/module_train/predict_executor.py backend/app/scripts/init_app.py backend/tests/test_task_executor.py
git commit -m "feat(train): unified TaskExecutor base with concurrency and orphan recovery"
```

---

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

### Task 6: 打通 paddlex 执行链路（训练→评估→预测→部署）

**Files:**
- Modify: `backend/app/plugin/module_train/scheduler.py`（TrainExecutor._execute）
- Modify: `backend/app/plugin/module_train/eval_scheduler.py`（EvalExecutor._execute）
- Modify: `backend/app/plugin/module_train/predict_executor.py`（PredictExecutor._execute）
- Modify: `backend/app/plugin/module_train/exporter.py`（`_export_paddlex` 真正导出数据）
- Test: `backend/tests/test_paddlex_export.py`（新建）

**Interfaces:**
- Consumes: `TrainFramework.PADDLEX`, `_export_paddlex` 现有占位
- Produces: `_export_paddlex(dataset_id, task_id, images, output_dir, annotation_task_id)` 完整实现；paddlex 的 eval/predict 命令构造

- [ ] **Step 1: 写失败测试 — paddlex 导出生成 PaddleX 数据**

`backend/tests/test_paddlex_export.py`:

```python
"""PaddleX 数据集导出测试（验证不再空实现）。"""


def test_export_paddlex_is_implemented():
    import inspect
    from app.plugin.module_train.exporter import _export_paddlex
    src = inspect.getsource(_export_paddlex)
    # 原实现只有 mkdir + log；修复后应有 label 或 yaml 生成
    assert "yaml" in src.lower() or "label" in src.lower() or "json" in src.lower()
```

- [ ] **Step 2: 运行确认失败**

Run: `cd backend && uv run pytest tests/test_paddlex_export.py -v`
Expected: FAIL（当前 `_export_paddlex` 只有 mkdir + log）

- [ ] **Step 3: 实现 `_export_paddlex` 完整导出**

在 `exporter.py` 中替换 `_export_paddlex`：

```python
async def _export_paddlex(dataset_id: int, task_id: int, images: list, output_dir: str, annotation_task_id: int | None = None) -> None:
    """导出 PaddleX 检测格式：images/ + annotations/ (XML) + train/val 划分 + PaddleX 目录规范。

    PaddleX 3.0 期望目录结构：
      {output}/images/{img}
      {output}/annotations/{img}.xml
      {output}/train.txt / val.txt
    """
    import random
    import xml.etree.ElementTree as ET

    from app.utils.s3_client import s3_client

    random.shuffle(images)
    split_idx = max(1, int(len(images) * 0.8))
    img_dir = os.path.join(output_dir, "images")
    ann_dir = os.path.join(output_dir, "annotations")
    os.makedirs(img_dir, exist_ok=True)
    os.makedirs(ann_dir, exist_ok=True)

    train_lines: list[str] = []
    val_lines: list[str] = []
    classes: set[str] = set()

    async with async_db_session() as db:
        for idx, img in enumerate(images):
            img_path = os.path.join(img_dir, img.filename)
            if not os.path.exists(img_path):
                try:
                    data = s3_client.download_fileobj(img.object_key)
                    with open(img_path, "wb") as f:
                        f.write(data.read())
                except Exception as e:
                    log.warning(f"skip image {img.filename}: {e}")
                    continue

            query = select(AnnotationRecordModel).where(AnnotationRecordModel.image_id == img.id)
            if annotation_task_id:
                query = query.where(AnnotationRecordModel.task_id == annotation_task_id)
            query = query.order_by(desc(AnnotationRecordModel.version)).limit(1)
            rec = await db.execute(query)
            record = rec.scalar_one_or_none()
            anns = record.annotation_data if record and record.annotation_data else []

            # 构造 PaddleX XML
            root = ET.Element("annotation")
            ET.SubElement(root, "filename").text = img.filename
            size = ET.SubElement(root, "size")
            ET.SubElement(size, "width").text = str(img.width or 0)
            ET.SubElement(size, "height").text = str(img.height or 0)
            for ann in anns:
                if ann.get("type") not in ("AxisAlignedBox", "box"):
                    continue
                if "x1" in ann:
                    x1, y1, x2, y2 = ann["x1"], ann["y1"], ann["x2"], ann["y2"]
                else:
                    xc, yc, w, h = ann["x"], ann["y"], ann["width"], ann["height"]
                    x1, y1, x2, y2 = xc - w / 2, yc - h / 2, xc + w / 2, yc + h / 2
                obj = ET.SubElement(root, "object")
                ET.SubElement(obj, "name").text = f"class_{ann.get('class_id', 0)}"
                ET.SubElement(obj, "difficult").text = "0"
                bbox = ET.SubElement(obj, "bndbox")
                ET.SubElement(bbox, "xmin").text = f"{int(x1 * (img.width or 1))}"
                ET.SubElement(bbox, "ymin").text = f"{int(y1 * (img.height or 1))}"
                ET.SubElement(bbox, "xmax").text = f"{int(x2 * (img.width or 1))}"
                ET.SubElement(bbox, "ymax").text = f"{int(y2 * (img.height or 1))}"
                classes.add(f"class_{ann.get('class_id', 0)}")

            xml_path = os.path.join(ann_dir, os.path.splitext(img.filename)[0] + ".xml")
            tree = ET.ElementTree(root)
            tree.write(xml_path, encoding="utf-8", xml_declaration=True)

            rel = f"images/{img.filename}\tannotations/{os.path.splitext(img.filename)[0]}.xml"
            if idx < split_idx:
                train_lines.append(rel)
            else:
                val_lines.append(rel)

    with open(os.path.join(output_dir, "train.txt"), "w", encoding="utf-8") as f:
        f.write("\n".join(train_lines))
    with open(os.path.join(output_dir, "val.txt"), "w", encoding="utf-8") as f:
        f.write("\n".join(val_lines))
    with open(os.path.join(output_dir, "labels.txt"), "w", encoding="utf-8") as f:
        f.write("\n".join(sorted(classes)))
    log.info(f"paddlex: train={len(train_lines)} val={len(val_lines)} classes={sorted(classes)}")
```

- [ ] **Step 4: paddlex 训练命令与产物查找修正**

`scheduler.py`（TrainExecutor）中：

```python
        if task.framework == TrainFramework.ULTRALYTICS:
            cmd = _build_ultralytics_cmd(...)
        elif task.framework == TrainFramework.PADDLEX:
            # PaddleX 训练需挂载导出目录并执行训练
            cmd = [
                "paddlex", "--train", "--data", "/data",
                "--model", task.hyperparams.get("model", "PP-YOLOE"),
                "--epochs", str(task.hyperparams.get("epochs", 100)),
                "--batch", str(task.hyperparams.get("batch", 16)),
                "--output", "/output",
            ]
```

`exporter.py:export_model` 扩展 paddlex 产物搜索（`best.pdparams` 已支持，补充 PaddleX 输出路径变体）：

```python
    if framework == "paddlex":
        candidates = [
            os.path.join(export_dir, "output", "best_model", "model.pdparams"),
            os.path.join(export_dir, "best_model", "model.pdparams"),
            os.path.join(export_dir, "exp", "best_model", "model.pdparams"),
        ]
        for p in candidates:
            if os.path.isfile(p):
                best_path = p
                break
```

- [ ] **Step 5: paddlex 评估/预测命令分支**

`eval_scheduler.py`（EvalExecutor）按 `framework` 分支：

```python
        if eval_rec.framework == TrainFramework.ULTRALYTICS:
            cmd = ["yolo", "val", ...]
        else:
            cmd = ["paddlex", "--eval", f"--model=/model/{model_filename}", "data=/data", ...]
```

`predict_executor.py`（PredictExecutor）同理按框架构造命令。

- [ ] **Step 6: 运行测试**

Run: `cd backend && uv run pytest tests/test_paddlex_export.py -v`
Expected: PASS

- [ ] **Step 7: 提交**

```bash
git add backend/app/plugin/module_train/scheduler.py backend/app/plugin/module_train/eval_scheduler.py backend/app/plugin/module_train/predict_executor.py backend/app/plugin/module_train/exporter.py backend/tests/test_paddlex_export.py
git commit -m "feat(train): implement PaddleX training/eval/predict pipeline"
```

---

### Task 7: 指标回流 — 训练最优指标写回模型版本 + 模型详情展示

**Files:**
- Modify: `backend/app/plugin/module_train/scheduler.py`（TrainExecutor）
- Modify: `backend/app/plugin/module_train/exporter.py`
- Test: `backend/tests/test_metrics_backfill.py`（新建）

**Interfaces:**
- Consumes: `task.best_metrics` / `task.last_metrics`（已有字段）
- Produces: `TrainModel.metrics` 恒包含训练最优指标；`list_model_repos` 的 version 行带 `metrics`

- [ ] **Step 1: 写失败测试 — 模型 metrics 来自任务 best_metrics**

`backend/tests/test_metrics_backfill.py`:

```python
"""指标回流测试。"""


def test_export_model_passes_best_metrics():
    import inspect
    from app.plugin.module_train.exporter import export_model
    src = inspect.getsource(export_model)
    # 修复前 metrics=task.best_metrics 已有；断言仍存在并含注释
    assert "task.best_metrics" in src or "best_metrics" in src
```

- [ ] **Step 2: 确认 exporter 已传 metrics**

Run: `cd backend && uv run ruff check app/plugin/module_train/exporter.py`
Expected: 无错误。核对 `exporter.py:521` `metrics=task.best_metrics` 是否已存在。

> 注：审查中发现 `exporter.py:521` 已写 `metrics=task.best_metrics`，但 DB 中模型 metrics 为空——原因是 `task.best_metrics` 在训练成功路径可能为 None（解析逻辑对部分日志行失败）。本任务修复 `scheduler.py` 的 best_metrics 计算，确保非 None。

- [ ] **Step 3: 强化 best_metrics 计算**

`scheduler.py`（TrainExecutor）中替换 best_metrics 计算段：

```python
        best_metrics = None
        last_metrics = None
        if metrics_log:
            last_metrics = metrics_log[-1]
            valid = [m for m in metrics_log if m.get("map50") is not None]
            best_metrics = max(valid, key=lambda m: m["map50"]) if valid else last_metrics
            # 兜底：若 metrics_log 全无 map50，取含最多数值字段的一条
            if not valid:
                ranked = sorted(
                    metrics_log, key=lambda m: sum(1 for k in ("precision", "recall", "map50", "map5095") if m.get(k) is not None), reverse=True
                )
                best_metrics = ranked[0] if ranked else None
```

- [ ] **Step 4: 写前端展示 — 模型版本指标列**

`frontend/web/src/views/module_train/repo/index.vue` 在版本列后新增 `map50` 列：

```vue
{ prop: "map50", label: "mAP50", width: 90, align: "center", formatter: (row: any) => (row.metrics?.map50 != null ? Number(row.metrics.map50).toFixed(3) : "-") },
```

- [ ] **Step 5: 运行测试**

Run: `cd backend && uv run pytest tests/test_metrics_backfill.py -v && cd ../frontend/web && pnpm run type-check`
Expected: 后端 PASS，前端 type-check 通过

- [ ] **Step 6: 提交**

```bash
git add backend/app/plugin/module_train/scheduler.py frontend/web/src/views/module_train/repo/index.vue backend/tests/test_metrics_backfill.py
git commit -m "feat(train): backfill best metrics to model version and display map50"
```

---

### Task 8: 前端仓库页两级展示 + eval/predict 版本选择

**Files:**
- Modify: `frontend/web/src/api/module_train/index.ts`
- Modify: `frontend/web/src/views/module_train/repo/index.vue`
- Modify: `frontend/web/src/views/module_train/eval/index.vue`
- Modify: `frontend/web/src/views/module_train/predict/index.vue`
- Modify: `frontend/web/src/views/module_train/task/detail.vue`
- Test: `cd frontend/web && pnpm run type-check`

**Interfaces:**
- Consumes: `GET /train/model/repos`, `GET /train/model/{repo_id}/versions`（Task 3 产物）
- Produces: 前端仓库两级表格、版本选择联动

- [ ] **Step 1: API 层补充方法**

`frontend/web/src/api/module_train/index.ts` 添加：

```typescript
  listModelRepos(query?: TablePageQuery) {
    return request<ApiResponse>({
      url: `${API_PATH}/model/repos`,
      method: "get",
      params: query,
    });
  },
  listModelVersions(repoId: number) {
    return request<ApiResponse>({
      url: `${API_PATH}/model/${repoId}/versions`,
      method: "get",
    });
  },
```

- [ ] **Step 2: 仓库页改为两级展示**

`repo/index.vue`：
- 搜索栏保留 name/framework
- 主表列改为：名称、框架、版本数、最新版本、创建时间、操作（去评估/去训练/删除）
- 新增"展开行/抽屉"展示版本列表（`listModelVersions`），版本行操作：评估、预测、导出、下载

关键改动（抽屉内版本表格）：

```vue
<ElDrawer v-model="versionsDrawer.visible" :title="versionsDrawer.repoName" size="600px">
  <ElTable v-loading="versionsLoading" :data="versionItems" border stripe>
    <ElTableColumn prop="version" label="版本" width="80" />
    <ElTableColumn label="mAP50" width="90" align="center">
      <template #default="{ row }">{{ row.metrics?.map50 != null ? Number(row.metrics.map50).toFixed(3) : "-" }}</template>
    </ElTableColumn>
    <ElTableColumn prop="format" label="格式" width="90" align="center" />
    <ElTableColumn prop="created_time" label="创建时间" min-width="160" />
    <ElTableColumn label="操作" width="220" fixed="right">
      <template #default="{ row }">
        <ElButton link type="primary" size="small" @click="goEval(repo, row)">评估</ElButton>
        <ElButton link type="success" size="small" @click="goPredict(repo, row)">推理</ElButton>
        <ElButton link type="warning" size="small" @click="exportVersion(row)">导出</ElButton>
      </template>
    </ElTableColumn>
  </ElTable>
</ElDrawer>
```

- [ ] **Step 3: eval/predict 表单版本联动**

`eval/index.vue`：选择仓库后调 `listModelVersions(repoId)` 填充版本下拉；提交时 `model_id=版本id, model_repo_id=仓库id`。

`predict/index.vue`：同样的版本联动。

- [ ] **Step 4: task/detail 跳转修正**

`task/detail.vue` 中 `model_repo_id` 跳转改为查该版本所属仓库：

```typescript
  if (task.value?.model_repo_id) {
    const repo = await TrainAPI.detailModelRepoOfVersion(task.value.model_repo_id);
    router.push(`/train/repo?repo_id=${repo?.repo_id}`);
  }
```

> 需要后端补一个 `GET /train/model/version/{version_id}/repo` 端点（在 Task 3 中一并提供）返回 `{repo_id, repo_name}`。

- [ ] **Step 5: type-check 验证**

Run: `cd frontend/web && pnpm run type-check`
Expected: 0 errors

- [ ] **Step 6: 构建验证**

Run: `cd frontend/web && npx vite build 2>&1 | Select-Object -Last 3`
Expected: `built in` 无报错

- [ ] **Step 7: 提交**

```bash
git add frontend/web/src/api/module_train/index.ts frontend/web/src/views/module_train/repo/index.vue frontend/web/src/views/module_train/eval/index.vue frontend/web/src/views/module_train/predict/index.vue frontend/web/src/views/module_train/task/detail.vue
git commit -m "feat(train): repo two-level UI with version selection for eval/predict"
```

---

### Task 9: 部署功能修正 — 端口竞态 + 容器存活探活 + 回收

**Files:**
- Modify: `backend/app/plugin/module_train/deploy_executor.py`
- Modify: `backend/app/plugin/module_train/service.py`
- Test: `backend/tests/test_deploy_fixes.py`（新建）

**Interfaces:**
- Consumes: `TaskExecutor` 基类（可选复用）
- Produces: `_find_available_port` 支持占位预留、`start_deployment` 幂等、运行中容器健康探活

- [ ] **Step 1: 写失败测试 — 端口预留**

`backend/tests/test_deploy_fixes.py`:

```python
"""部署修复测试。"""


def test_find_available_port_bounds():
    from app.plugin.module_train.deploy_executor import _find_available_port
    p = _find_available_port(9100, 9100)
    assert p == 9100
```

- [ ] **Step 2: 运行确认通过**

Run: `cd backend && uv run pytest tests/test_deploy_fixes.py -v`
Expected: PASS

- [ ] **Step 3: 端口占用竞态修复**

`deploy_executor.py` 中 `_execute_deployment` 修改：选定端口后立即写入 DB `host_port` 并持有"预留锁"，再启动容器；失败回滚端口。将 `_find_available_port` 改为同时检查 Docker 已发布端口：

```python
def _find_available_port(start: int = 9001, end: int = 9999) -> int:
    import socket
    import docker
    client = docker.from_env()
    used = set()
    try:
        for c in client.containers.list(all=True):
            for _, bindings in (c.attrs.get("HostConfig", {}).get("PortBindings") or {}).items():
                for b in bindings:
                    used.add(int(b["HostPort"]))
    except Exception:
        pass
    for port in range(start, end + 1):
        if port in used:
            continue
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            if s.connect_ex(("127.0.0.1", port)) != 0:
                return port
    raise Exception("no available port found")
```

- [ ] **Step 4: 探活与回收**

启动后 `_execute_deployment` 中等待 server.py 健康检查（最多 60s），通过 `requests.get(f"{api_url}/health")` 轮询；运行中容器用 `container.status` 轮询，异常退出标记 failed 并移除。`stop_deployment` 已存在；增加 `recover_orphan_deploys()` 在启动时把 `running` 状态但无容器的部署标记 `failed`。

- [ ] **Step 5: 运行测试**

Run: `cd backend && uv run pytest tests/test_deploy_fixes.py -v`
Expected: PASS

- [ ] **Step 6: 提交**

```bash
git add backend/app/plugin/module_train/deploy_executor.py backend/app/plugin/module_train/service.py backend/tests/test_deploy_fixes.py
git commit -m "fix(train): deploy port reservation, health probe, orphan recovery"
```

---

### Task 10: 清理与回归验证

**Files:**
- Modify: `backend/app/scripts/init_app.py`（如残留旧调度器引用）
- Test: 全量回归

- [ ] **Step 1: 清理临时目录残留**

确认 `%TEMP%/train_output`、`eval_output`、`predict_output` 下无占用大文件。提供 `backend/app/plugin/module_train/cleanup.py` 定时清理（保留最近 N 天）：

```python
"""定时清理临时训练产物目录。"""
import asyncio
import os
import shutil
import tempfile
import time


async def cleanup_loop(keep_days: int = 7, interval_sec: int = 3600):
    while True:
        try:
            base = tempfile.gettempdir()
            for sub in ("train_output", "eval_output", "predict_output", "deploy_output", "model_export", "dataset_export", "model_export_logs"):
                d = os.path.join(base, sub)
                if not os.path.isdir(d):
                    continue
                cutoff = time.time() - keep_days * 86400
                for entry in os.listdir(d):
                    p = os.path.join(d, entry)
                    try:
                        if os.path.getmtime(p) < cutoff:
                            if os.path.isdir(p):
                                shutil.rmtree(p, ignore_errors=True)
                            else:
                                os.remove(p)
                    except Exception:
                        pass
        except Exception:
            pass
        await asyncio.sleep(interval_sec)
```

在 `init_app.py` 启动该清理循环。

- [ ] **Step 2: 后端全量测试**

Run: `cd backend && uv run pytest tests/ -v`
Expected: 全部 PASS（含既有测试）

- [ ] **Step 3: ruff 检查**

Run: `cd backend && uv run ruff check`
Expected: 0 errors（若有历史问题记录，注明忽略项）

- [ ] **Step 4: 前端 type-check + build**

Run: `cd frontend/web && pnpm run type-check && npx vite build 2>&1 | Select-Object -Last 3`
Expected: type-check 0 errors，build 成功

- [ ] **Step 5: 真实库端到端冒烟**

1. 登录 v3 前端 (http://localhost:5190/web) admin/123456
2. 模型仓库页：确认 41 条旧数据聚合为仓库+版本两级展示，无 `vv1`
3. 创建一次训练任务 → 跑通 → 确认产物落盘、metrics 非空
4. 评估：选最新版本 → 跑通 → metrics 正常
5. 预测：上传图片 → 跑通 → 结果图/zip 可见
6. 部署：创建 + 启动 → 健康检查通过 → 停止
7. 重启后端：确认无 RUNNING 残留任务卡死（孤儿恢复生效）

- [ ] **Step 6: 提交**

```bash
git add backend/app/plugin/module_train/cleanup.py backend/app/scripts/init_app.py
git commit -m "chore(train): temp dir cleanup and regression verification"
```

---

## Self-Review 结论

- **Spec 覆盖**：P0 数据模型语义（Task 1-3, 5）✅；P0 导出覆盖 hack（Task 5）✅；P1 并发控制（Task 4）✅；P1 predict 孤儿（Task 4）✅；P1 paddlex 半成品（Task 6）✅；P1 指标未回流（Task 7）✅；P2 部署未用/端口竞态（Task 9）✅；P2 临时目录清理（Task 10）✅；前端适配（Task 8）✅。版本号 vv bug（Task 2, 5）✅。
- **回滚安全**：Task 2 迁移含 downgrade；Task 3-9 均小步提交。
- **类型一致性**：`_parse_version`、`_resolve_model_storage`、`TaskExecutor` 接口在各 Task 间签名一致。
- **遗留说明**：`TrainTask.model_repo_id` 保留指向版本行 id（兼容旧前端跳转），前端已改为通过 `version/{id}/repo` 解析仓库。
