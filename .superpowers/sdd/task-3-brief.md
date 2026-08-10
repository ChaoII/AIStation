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


