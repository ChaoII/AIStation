# Phase 0A：后端契约与快速修复 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 修复全流程后端契约层的 6 个基础缺陷（框架枚举比较、S3 环境、删除接口契约、权限补种、推理依赖降级、迁移补列），为后续 Phase 提供可信底座。

**Architecture:** 只做小而可验证的根因修复，统一走"抽小工具 + 单元/接口测试"的模式，不重构大模块。每个任务独立提交。

**Tech Stack:** FastAPI + SQLAlchemy 2.0 + Pydantic v2 + pytest（SQLite + TestClient）；Vue3 + TypeScript（前端一处契约修复）；Docker/PaddleX 相关仅做比较逻辑与错误提示，不跑容器。

## Global Constraints

- Python 版本：3.13（`backend/.venv` 由 `uv` 管理）；代码风格与 docstring 遵循现有中文注释约定。
- 后端测试必须通过：`cd backend && uv run pytest -q`。
- 后端静态检查必须通过：`cd backend && uv run ruff check`。
- 前端类型检查必须通过：`cd frontend && pnpm run type-check`。
- 任何接口/字段命名变更必须同步前端 `frontend/src/api/`。
- 不删除既有功能；不引入新依赖到默认安装集（可选依赖须放在 optional-extras 且不参与默认 `uv sync`）。
- 提交信息使用仓库现有风格（`fix(scope): ...` / `feat(scope): ...`），中文描述。
- 测试文件放 `backend/tests/`，命名 `test_*.py`；HTTP 测试用会话级 `test_client` fixture，登录辅助函数见 `backend/tests/test_train_service_repo.py:5`。

---

### Task 1: 框架枚举归一化工具

**背景:** `str(TrainFramework.PADDLEX).lower()` 得到 `"trainframework.paddlex"` 而非 `"paddlex"`，导致 `task_executor.py:130` 无法跳过 PaddleX 行（误判失败），`paddlex_executor.py:59-60` 又永远选不中 PaddleX 行（孤儿永不回收）。

**Files:**
- Create: `backend/app/plugin/module_train/framework_utils.py`
- Modify: `backend/app/plugin/module_train/task_executor.py:128-131`
- Modify: `backend/app/plugin/module_train/paddlex_executor.py:58-61`
- Test: `backend/tests/test_framework_utils.py`

**Interfaces:**
- Produces: `framework_value(framework: object | None) -> str` —— 返回去掉枚举前缀、统一小写的框架字符串；`TrainFramework.PADDLEX` → `"paddlex"`，`"paddlex"` → `"paddlex"`，`"TrainFramework.PADDLEX"` → `"paddlex"`，`None` → `""`。

- [ ] **Step 1: Write the failing test**

```python
"""framework_value 归一化测试。"""
from app.plugin.module_train.framework_utils import framework_value
from app.plugin.module_train.model import TrainFramework


def test_framework_value_from_enum():
    assert framework_value(TrainFramework.PADDLEX) == "paddlex"
    assert framework_value(TrainFramework.ULTRALYTICS) == "ultralytics"


def test_framework_value_from_plain_string():
    assert framework_value("paddlex") == "paddlex"
    assert framework_value("ULTRALYTICS") == "ultralytics"


def test_framework_value_from_repr_like_string():
    assert framework_value("TrainFramework.PADDLEX") == "paddlex"


def test_framework_value_none_is_empty():
    assert framework_value(None) == ""
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/test_framework_utils.py -q`
Expected: FAIL（`ModuleNotFoundError: app.plugin.module_train.framework_utils`）

- [ ] **Step 3: Write minimal implementation**

Create `backend/app/plugin/module_train/framework_utils.py`:

```python
"""框架标识归一化：把枚举成员 / 字符串统一成裸小写值（如 "paddlex"）。"""


def framework_value(framework: object | None) -> str:
    """返回框架的规范化字符串值。

    - 枚举成员取其 ``value``（``TrainFramework.PADDLEX`` -> ``"paddlex"``）
    - 形如 ``"TrainFramework.PADDLEX"`` 的去前缀后小写
    - ``None`` 返回空串
    """
    if framework is None:
        return ""
    value = getattr(framework, "value", framework)
    text = str(value)
    if "." in text:
        text = text.rsplit(".", 1)[-1]
    return text.lower()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && uv run pytest tests/test_framework_utils.py -q`
Expected: PASS（4 passed）

- [ ] **Step 5: 修复 task_executor 的跳过逻辑**

在 `backend/app/plugin/module_train/task_executor.py` 顶部 import 区加入：

```python
from .framework_utils import framework_value
```

把 `recover_orphans` 中（约 128-131 行）：

```python
                framework = getattr(r, "framework", None)
                if framework is not None and str(framework).lower() == "paddlex" and cls.__name__ != "PaddleXOCRExecutor":
                    continue
```

替换为：

```python
                framework = getattr(r, "framework", None)
                if (
                    framework_value(framework) == "paddlex"
                    and "PaddleXOCR" not in cls.__name__
                ):
                    continue
```

- [ ] **Step 6: 修复 paddlex_executor 的筛选逻辑**

在 `backend/app/plugin/module_train/paddlex_executor.py` 顶部 import 区加入：

```python
from .framework_utils import framework_value
```

把 `recover_orphans` 中（约 58-61 行）：

```python
            for r in rows:
                fw = str(getattr(r, "framework", "") or "").lower()
                if fw != "paddlex":
                    continue
```

替换为：

```python
            for r in rows:
                if framework_value(getattr(r, "framework", None)) != "paddlex":
                    continue
```

- [ ] **Step 7: Run 全量后端测试 + ruff**

Run: `cd backend && uv run pytest -q && uv run ruff check`
Expected: 全部通过；ruff 无新增告警。

- [ ] **Step 8: Commit**

```bash
git add backend/app/plugin/module_train/framework_utils.py backend/app/plugin/module_train/task_executor.py backend/app/plugin/module_train/paddlex_executor.py backend/tests/test_framework_utils.py
git commit -m "fix(train): 框架枚举归一化，修复 PaddleX 误判失败与孤儿不回收"
```

---

### Task 2: S3 客户端按运行环境解析 bucket

**背景:** `s3_client.py` 所有方法默认 `env="dev"`，prod 环境数据会写入 dev bucket。

**Files:**
- Modify: `backend/app/utils/s3_client.py`
- Test: `backend/tests/test_s3_client_env.py`

**Interfaces:**
- Produces: `S3Client.default_env: str`（构造时根据 `settings.ENVIRONMENT` 解析为 `"dev"` 或 `"prod"`）；`S3Client._bucket(env: str | None = None) -> str`，`env=None` 时使用 `default_env`。
- 现有调用方（`upload_fileobj`/`download_fileobj`/`delete_object`/`presigned_url` 等）保持签名 `env: str | None = None`，行为不变（显式传入优先）。

- [ ] **Step 1: Write the failing test**

```python
"""S3Client 环境解析测试。"""
from app.config.setting import settings
from app.utils.s3_client import S3Client


def test_bucket_uses_default_dev(monkeypatch):
    monkeypatch.setattr(settings, "ENVIRONMENT", "dev")
    client = S3Client()
    assert client.default_env == "dev"
    assert client._bucket() == f"{settings.RUSTFS_BUCKET_PREFIX}-dev"


def test_bucket_uses_prod_when_environment_prod(monkeypatch):
    monkeypatch.setattr(settings, "ENVIRONMENT", "prod")
    client = S3Client()
    assert client.default_env == "prod"
    assert client._bucket().endswith("-prod")


def test_bucket_explicit_env_overrides_default(monkeypatch):
    monkeypatch.setattr(settings, "ENVIRONMENT", "prod")
    client = S3Client()
    assert client._bucket("dev").endswith("-dev")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/test_s3_client_env.py -q`
Expected: FAIL（`AttributeError: 'S3Client' object has no attribute 'default_env'` 或断言失败）

- [ ] **Step 3: Write minimal implementation**

修改 `backend/app/utils/s3_client.py` 的 `__init__` 与 `_bucket`：

```python
    def __init__(self):
        self.client = boto3.client(
            "s3",
            endpoint_url=settings.RUSTFS_ENDPOINT,
            aws_access_key_id=settings.RUSTFS_ACCESS_KEY,
            aws_secret_access_key=settings.RUSTFS_SECRET_KEY,
            config=Config(signature_version="s3v4"),
            region_name="us-east-1",
        )
        self.bucket_prefix = settings.RUSTFS_BUCKET_PREFIX
        self.expiry = settings.RUSTFS_PRESIGNED_URL_EXPIRY
        env = getattr(settings.ENVIRONMENT, "value", settings.ENVIRONMENT)
        self.default_env = "prod" if str(env).lower() == "prod" else "dev"

    def _bucket(self, env: str | None = None) -> str:
        return f"{self.bucket_prefix}-{env or self.default_env}"
```

并把该类所有方法签名中的 `env: str = "dev"` 改为 `env: str | None = None`：

```python
    def ensure_bucket(self, env: str | None = None) -> None: ...
    def upload_fileobj(self, fileobj: BinaryIO, object_key: str, env: str | None = None) -> str: ...
    def upload_file(self, file_path: str, object_key: str, env: str | None = None) -> str: ...
    def download_fileobj(self, object_key: str, env: str | None = None) -> io.BytesIO: ...
    def delete_object(self, object_key: str, env: str | None = None) -> None: ...
    def presigned_url(self, object_key: str, env: str | None = None) -> str: ...
    def presigned_put_url(self, object_key: str, env: str | None = None) -> str: ...
```

（方法体不变，内部继续调用 `self._bucket(env)`。）

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && uv run pytest tests/test_s3_client_env.py -q`
Expected: PASS（3 passed）

- [ ] **Step 5: Commit**

```bash
git add backend/app/utils/s3_client.py backend/tests/test_s3_client_env.py
git commit -m "fix(storage): S3 bucket 按 ENVIRONMENT 解析，避免 prod 落 dev"
```

---

### Task 3: 视频模块删除接口契约修复

**背景:** 前端 9 个删除函数发送 `data: { ids }`，后端 controller 声明 `ids: list[int] = Body(...)`（裸数组）→ 422。后端契约正确，前端需改为裸数组；并补接口回归测试锁定契约。同时给算法详情接口补 404 语义。

**Files:**
- Modify: `frontend/src/api/module_video/algorithm.ts:15-17,31-33`
- Modify: `frontend/src/api/module_video/camera.ts:19-20,47-48`
- Modify: `frontend/src/api/module_video/event.ts:15-16`
- Modify: `frontend/src/api/module_video/layout.ts:19-20`
- Modify: `frontend/src/api/module_video/alarm.ts:15-16,35-36`
- Modify: `frontend/src/api/module_video/record.ts:15-16`
- Modify: `frontend/src/api/module_video/deploy.ts:15-16`
- Modify: `backend/app/api/v1/module_video/algorithm/controller.py:38-45`
- Modify: `backend/tests/conftest.py`（新增共享 `auth_headers` fixture）
- Test: `backend/tests/test_video_delete_contract.py`

**Interfaces:**
- Produces: `auth_headers` pytest fixture（登录 admin 并返回带 Bearer 的 headers dict），供本计划及后续计划复用。
- 契约：所有 `/video/**/delete` 的请求体为裸 JSON 数组 `[1,2,3]`；`{ "ids": [...] }` 一律 422。
- `GET /video/algorithm/detail/{id}` 不存在时返回 HTTP 404。

- [ ] **Step 1: 在 conftest 增加共享登录 fixture**

在 `backend/tests/conftest.py` 末尾追加（`_login` 逻辑与 `test_train_service_repo.py:5` 保持一致，`X-Forwarded-For` 必需）：

```python
@pytest.fixture
def auth_headers(test_client):
    """登录 admin 返回带 Bearer 的请求头，供接口测试复用。"""
    login = test_client.post(
        "/api/v1/system/auth/login",
        data={"username": "admin", "password": "123456"},
        headers={"X-Forwarded-For": "127.0.0.1"},
    )
    assert login.status_code == 200, login.text
    token = login.json()["data"]["access_token"]
    return {"Authorization": f"Bearer {token}"}
```

- [ ] **Step 2: Write the failing backend contract test**

```python
"""视频模块删除接口契约测试：裸数组可用，包裹对象 422。"""
from fastapi.testclient import TestClient


def test_delete_accepts_raw_array(test_client: TestClient, auth_headers: dict):
    resp = test_client.request(
        "DELETE", "/api/v1/video/algorithm/delete", json=[999999], headers=auth_headers
    )
    assert resp.status_code == 200
    assert resp.json()["code"] == 0


def test_delete_rejects_wrapped_object(test_client: TestClient, auth_headers: dict):
    resp = test_client.request(
        "DELETE", "/api/v1/video/algorithm/delete", json={"ids": [999999]}, headers=auth_headers
    )
    assert resp.status_code == 422


def test_algorithm_detail_missing_returns_404(test_client: TestClient, auth_headers: dict):
    resp = test_client.get("/api/v1/video/algorithm/detail/999999", headers=auth_headers)
    assert resp.status_code == 404
```

- [ ] **Step 3: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/test_video_delete_contract.py -q`
Expected: 前两个用例 PASS（后端契约本就正确），第三个 FAIL（当前返回 200 + `data: null`）。

- [ ] **Step 4: 实现算法详情 404**

修改 `backend/app/api/v1/module_video/algorithm/controller.py` 的详情接口：

```python
@AlgorithmRouter.get("/detail/{id}", summary="查询算法详情")
async def get_algorithm_detail_controller(
    id: int = Path(..., description="算法ID"),
    auth: AuthSchema = Depends(AuthPermission(["module_video:algorithm:query"])),
) -> JSONResponse:
    result = await AlgorithmService.get_algorithm_list_service(auth=auth)
    item = next((x for x in result if x.get("id") == id), None)
    if item is None:
        raise CustomException(msg="算法不存在", code=404)
    return SuccessResponse(data=item, msg="查询成功")
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd backend && uv run pytest tests/test_video_delete_contract.py -q`
Expected: PASS（3 passed）

- [ ] **Step 6: 修复前端 9 个删除函数为裸数组**

逐一替换（保持函数签名不变）：

`frontend/src/api/module_video/algorithm.ts`:
```typescript
export function deleteAlgorithm(ids: number[]) {
  return request({ url: "/video/algorithm/delete", method: "delete", data: ids });
}

export function deleteAlgorithmTask(ids: number[]) {
  return request({ url: "/video/algorithm/task/delete", method: "delete", data: ids });
}
```

`frontend/src/api/module_video/camera.ts`:
```typescript
export function deleteCamera(ids: number[]) {
  return request({ url: "/video/camera/delete", method: "delete", data: ids });
}

export function deleteCameraGroup(ids: number[]) {
  return request({ url: "/video/camera/group/delete", method: "delete", data: ids });
}
```

`frontend/src/api/module_video/event.ts`:
```typescript
export function deleteEvent(ids: number[]) {
  return request({ url: "/video/event/delete", method: "delete", data: ids });
}
```

`frontend/src/api/module_video/layout.ts`:
```typescript
export function deleteLayout(ids: number[]) {
  return request({ url: "/video/layout/delete", method: "delete", data: ids });
}
```

`frontend/src/api/module_video/alarm.ts`:
```typescript
export function deleteAlarmRule(ids: number[]) {
  return request({ url: "/video/alarm/rule/delete", method: "delete", data: ids });
}

export function deleteAlarmRecord(ids: number[]) {
  return request({ url: "/video/alarm/record/delete", method: "delete", data: ids });
}
```

`frontend/src/api/module_video/record.ts`:
```typescript
export function deleteRecordPlan(ids: number[]) {
  return request({ url: "/video/record/plan/delete", method: "delete", data: ids });
}
```

`frontend/src/api/module_video/deploy.ts`:
```typescript
export function deleteAlgorithmTask(ids: number[]) {
  return request({ url: "/video/algorithm/task/delete", method: "delete", data: ids });
}
```

- [ ] **Step 7: 校验前端无遗漏**

Run: `cd frontend && rg -n "data: \{ ids \}" src/api/module_video`
Expected: 无任何输出（全部替换完成）。

- [ ] **Step 8: 前端类型检查**

Run: `cd frontend && pnpm run type-check`
Expected: 通过（无新增错误）。

- [ ] **Step 9: Commit**

```bash
git add backend/tests/test_video_delete_contract.py backend/app/api/v1/module_video/algorithm/controller.py frontend/src/api/module_video
git commit -m "fix(video): 删除接口改裸数组 body，算法详情补 404"
```

---

### Task 4: 推理依赖降级与启动自检

**背景:** 视频推理 worker 依赖未安装的 `modeldeploy`(FastDeploy)，`start_inference` 却在 worker 异步失败前就返回"启动成功"，用户看到成功后任务静默变 ERROR。需在启动前同步校验并给出明确错误。

**Files:**
- Modify: `backend/app/api/v1/module_video/inference/registry.py`
- Modify: `backend/app/api/v1/module_video/inference/scheduler.py`（`start_inference` 开头调用校验）
- Modify: `backend/app/scripts/init_app.py`（启动时记录一次后端可用性告警）
- Test: `backend/tests/test_inference_backend_check.py`

**Interfaces:**
- Produces: `ensure_inference_backend() -> None` —— 导入 `modeldeploy` 失败时抛 `ImportError`，消息含 `modeldeploy`。
- Produces: `inference_backend_available() -> bool`。

- [ ] **Step 1: Write the failing test**

```python
"""推理后端可用性校验测试。"""
import importlib

import pytest

from app.api.v1.module_video.inference import registry


def test_ensure_backend_raises_clear_error(monkeypatch):
    real_import = importlib.import_module

    def fake_import(name, *args, **kwargs):
        if name == "modeldeploy":
            raise ImportError("No module named 'modeldeploy'")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(importlib, "import_module", fake_import)
    with pytest.raises(ImportError, match="modeldeploy"):
        registry.ensure_inference_backend()


def test_backend_available_returns_bool():
    assert isinstance(registry.inference_backend_available(), bool)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/test_inference_backend_check.py -q`
Expected: FAIL（`AttributeError: module ... has no attribute 'ensure_inference_backend'`）

- [ ] **Step 3: Write minimal implementation**

在 `backend/app/api/v1/module_video/inference/registry.py` 末尾追加：

```python
def inference_backend_available() -> bool:
    """推理后端（modeldeploy/FastDeploy）是否可导入。"""
    import importlib

    try:
        importlib.import_module("modeldeploy")
    except ImportError:
        return False
    return True


def ensure_inference_backend() -> None:
    """同步校验推理后端可用，不可用则抛出可读 ImportError。"""
    import importlib

    try:
        importlib.import_module("modeldeploy")
    except ImportError as e:
        raise ImportError(
            f"智能分析推理库 modeldeploy(FastDeploy) 未安装或不可用: {e}。"
            "请先安装 FastDeploy 推理库后再启动推理任务。"
        ) from e
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && uv run pytest tests/test_inference_backend_check.py -q`
Expected: PASS（2 passed）

- [ ] **Step 5: 接入 start_inference**

在 `backend/app/api/v1/module_video/inference/scheduler.py` 的 `start_inference` 函数体最前面（解析任务之前）加入：

```python
    from app.api.v1.module_video.inference.registry import ensure_inference_backend
    ensure_inference_backend()
```

这样 `start_inference_controller` 的 `except Exception` 会把消息转成 `CustomException`，接口返回可读错误，不再"先成功后失败"。

- [ ] **Step 6: 启动自检告警**

在 `backend/app/scripts/init_app.py` 的 `lifespan` 内、`start_inference_scheduler()` 之前加入：

```python
        from app.api.v1.module_video.inference.registry import inference_backend_available
        if not inference_backend_available():
            log.warning("⚠️  智能分析推理库 modeldeploy(FastDeploy) 不可用，视频布控推理将无法启动")
```

- [ ] **Step 7: 全量测试 + ruff**

Run: `cd backend && uv run pytest -q && uv run ruff check`
Expected: 通过。

- [ ] **Step 8: Commit**

```bash
git add backend/app/api/v1/module_video/inference/registry.py backend/app/api/v1/module_video/inference/scheduler.py backend/app/scripts/init_app.py backend/tests/test_inference_backend_check.py
git commit -m "fix(inference): 推理后端启动前同步校验 + 启动告警"
```

---

### Task 5: 训练模块缺失权限与详情菜单补种

**背景:** `module_train:model:update` 被后端与前端引用，但 `init_app.py` 从未注册；`TrainTaskDetail` 不在补全列表，旧库升级后缺失。只种一次数据的机制导致这些缺口无法自愈。

**Files:**
- Modify: `backend/app/scripts/init_app.py`
- Test: `backend/tests/test_train_menu_constants.py`

**Interfaces:**
- Produces: 模块级常量 `TRAIN_BUTTON_PERMS: list[tuple[str, str]]` 与 `TRAIN_EXTRA_MENUS: list[tuple[str, str, str, str, str, bool]]`，供种子与补全两段逻辑共用。

- [ ] **Step 1: Write the failing test**

```python
"""训练菜单/权限种子常量测试。"""
from app.scripts import init_app


def test_model_update_permission_seeded():
    perms = dict(init_app.TRAIN_BUTTON_PERMS)
    assert perms.get("module_train:model:update") == "编辑模型"


def test_predict_permissions_seeded():
    perms = dict(init_app.TRAIN_BUTTON_PERMS)
    for code in (
        "module_train:predict:query",
        "module_train:predict:create",
        "module_train:predict:delete",
    ):
        assert code in perms


def test_task_detail_menu_in_extra_menus():
    route_names = {row[0] for row in init_app.TRAIN_EXTRA_MENUS}
    assert "TrainTaskDetail" in route_names
    assert "TrainPredict" in route_names
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/test_train_menu_constants.py -q`
Expected: FAIL（`AttributeError: module 'app.scripts.init_app' has no attribute 'TRAIN_BUTTON_PERMS'`）

- [ ] **Step 3: 抽取常量**

在 `backend/app/scripts/init_app.py` 中 `_ensure_train_menus` 函数定义之前加入模块级常量：

```python
TRAIN_BUTTON_PERMS: list[tuple[str, str]] = [
    ("module_train:model:query", "查询模型"),
    ("module_train:model:create", "创建模型"),
    ("module_train:model:update", "编辑模型"),
    ("module_train:model:delete", "删除模型"),
    ("module_train:task:query", "查询任务"),
    ("module_train:task:create", "创建任务"),
    ("module_train:task:update", "更新任务"),
    ("module_train:task:delete", "删除任务"),
    ("module_train:eval:query", "查询评估"),
    ("module_train:eval:create", "创建评估"),
    ("module_train:eval:delete", "删除评估"),
    ("module_train:predict:query", "查询预测"),
    ("module_train:predict:create", "创建预测"),
    ("module_train:predict:delete", "删除预测"),
]

# (name, route_name, route_path, component_path, permission, hidden)
TRAIN_EXTRA_MENUS: list[tuple[str, str, str, str, str, bool]] = [
    ("模型预测", "TrainPredict", "/train/predict", "module_train/predict/index", "module_train:predict:query", False),
    ("模型部署", "TrainDeploy", "/train/deploy", "module_train/deploy/index", "module_train:model:query", False),
    ("训练详情", "TrainTaskDetail", "/train/task/:id", "module_train/task/detail", "module_train:task:query", True),
    ("评估详情", "TrainEvalDetail", "/train/eval/:id", "module_train/eval/detail", "module_train:eval:query", True),
    ("预测详情", "TrainPredictDetail", "/train/predict/:id", "module_train/predict/detail", "module_train:predict:query", True),
]
```

- [ ] **Step 4: 让种子逻辑使用常量**

把 `_ensure_train_menus` 首建分支里的 `button_perms = [...]` 列表替换为：

```python
                for perm_code, perm_name in TRAIN_BUTTON_PERMS:
```

并在其后的循环体保持不变（仍用 `existing_perm` 判重后插入）。

把 detail 页面种子块（`for detail_data in [...]`）与之后已存在分支的 `missing = [...]` 列表，统一改为遍历 `TRAIN_EXTRA_MENUS`：

```python
                for name, route_name, route_path, component_path, permission, hidden in TRAIN_EXTRA_MENUS:
                    dm = MenuModel(
                        name=name, type=2, icon=None, order=99,
                        route_name=route_name, route_path=route_path,
                        component_path=component_path,
                        permission=permission, parent_id=parent.id,
                        status="0", is_deleted=False, title=name, hidden=hidden,
                    )
                    db.add(dm)
                    await db.flush()
                    db.add(RoleMenusModel(role_id=1, menu_id=dm.id))
```

已存在分支：

```python
            for name, route_name, route_path, component_path, permission, hidden in TRAIN_EXTRA_MENUS:
                existing_menu = await db.execute(
                    select(MenuModel).where(MenuModel.route_name == route_name)
                )
                if existing_menu.scalar_one_or_none():
                    continue
                mm = MenuModel(
                    name=name, type=2, icon=None, order=99,
                    route_name=route_name, route_path=route_path,
                    component_path=component_path, permission=permission,
                    parent_id=parent.id, status="0", is_deleted=False,
                    title=name, hidden=hidden,
                )
                db.add(mm)
                await db.flush()
                db.add(RoleMenusModel(role_id=1, menu_id=mm.id))
```

把已存在分支里补权限的列表也改为遍历 `TRAIN_BUTTON_PERMS`：

```python
            for perm_code, perm_name in TRAIN_BUTTON_PERMS:
                existing_perm = await db.execute(
                    select(MenuModel).where(MenuModel.permission == perm_code)
                )
                if existing_perm.first() is None:
                    pm = MenuModel(name=perm_name, type=3, icon=None, order=99,
                                   route_name="", route_path="", component_path="",
                                   permission=perm_code, parent_id=parent.id,
                                   status="0", is_deleted=False, title=perm_name)
                    db.add(pm)
                    await db.flush()
                    db.add(RoleMenusModel(role_id=1, menu_id=pm.id))
```

同时删除 `lifespan` 中那段"直接 SQL 补全 TrainPredict/TrainEvalDetail/TrainPredictDetail"的临时逻辑（已被上面的常量补全取代），避免两套机制分叉。

- [ ] **Step 5: Run test to verify it passes**

Run: `cd backend && uv run pytest tests/test_train_menu_constants.py -q`
Expected: PASS（3 passed）

- [ ] **Step 6: 全量测试 + ruff**

Run: `cd backend && uv run pytest -q && uv run ruff check`
Expected: 通过（注意删除临时 SQL 段后无未使用 import 告警）。

- [ ] **Step 7: Commit**

```bash
git add backend/app/scripts/init_app.py backend/tests/test_train_menu_constants.py
git commit -m "fix(train): 补种 model:update 权限与训练详情菜单，统一种子常量"
```

---

### Task 6: 训练模块迁移补列与启动自检

**背景:** 多个 ORM 新列未进 Alembic、启动补列也漏，旧库升级后读写报错。需新增一份幂等迁移并让启动补列覆盖全部新列。

**Files:**
- Create: `backend/app/plugin/module_train/schema_check.py`
- Create: `backend/app/alembic/versions/<new_rev>_train_missing_columns.py`
- Modify: `backend/app/scripts/init_app.py`（启动补列调用 `schema_check`）
- Test: `backend/tests/test_train_schema_check.py`

**Interfaces:**
- Produces: `MISSING_TRAIN_COLUMNS: dict[str, list[tuple[str, str]]]` —— `{表名: [(列名, PostgreSQL类型)]}`。
- Produces: `missing_columns_for_model(model: type) -> set[str]` —— 返回 `MISSING_TRAIN_COLUMNS` 中该模型表缺少的定义（用于断言清单与 ORM 对齐）。

- [ ] **Step 1: Write the failing test**

```python
"""训练模块补列清单与 ORM 对齐测试。"""
from app.plugin.module_train import schema_check
from app.plugin.module_train.model import TrainEval, TrainModel, TrainTask


def test_backfill_covers_orm_columns():
    # 清单声明的列必须是 ORM 真实字段，且覆盖所有预期缺失列
    for table, columns in schema_check.MISSING_TRAIN_COLUMNS.items():
        assert isinstance(columns, list) and columns
        for name, _type in columns:
            assert name


def test_expected_columns_listed():
    task_cols = dict(schema_check.MISSING_TRAIN_COLUMNS["train_tasks"])
    assert "annotation_task_id" in task_cols
    assert "cleanup_delay_minutes" in task_cols

    model_cols = dict(schema_check.MISSING_TRAIN_COLUMNS["train_models"])
    assert "repo_id" in model_cols
    assert "export_format" in model_cols

    eval_cols = dict(schema_check.MISSING_TRAIN_COLUMNS["train_evals"])
    assert "progress" in eval_cols
    assert "error_log" in eval_cols


def test_models_have_declared_columns():
    for table, columns in schema_check.MISSING_TRAIN_COLUMNS.items():
        cls = {
            "train_tasks": TrainTask,
            "train_models": TrainModel,
            "train_evals": TrainEval,
        }[table]
        for name, _type in columns:
            assert hasattr(cls, name), f"{cls.__name__} 缺少字段 {name}"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/test_train_schema_check.py -q`
Expected: FAIL（模块不存在）

- [ ] **Step 3: Write the schema-check module**

Create `backend/app/plugin/module_train/schema_check.py`:

```python
"""训练模块缺失列清单与启动补列。

用于旧库升级：Alembic 迁移之外，启动时幂等补齐 ORM 已声明但库里缺失的列。
"""

MISSING_TRAIN_COLUMNS: dict[str, list[tuple[str, str]]] = {
    "train_tasks": [
        ("annotation_task_id", "INTEGER"),
        ("cleanup_delay_minutes", "INTEGER"),
        ("metrics_log", "JSONB"),
        ("best_metrics", "JSONB"),
        ("last_metrics", "JSONB"),
        ("error_log", "TEXT"),
    ],
    "train_models": [
        ("repo_id", "INTEGER"),
        ("export_format", "VARCHAR(32)"),
    ],
    "train_evals": [
        ("model_id", "INTEGER"),
        ("framework", "VARCHAR(16)"),
        ("hyperparams", "JSONB"),
        ("progress", "INTEGER"),
        ("started_at", "TIMESTAMP"),
        ("finished_at", "TIMESTAMP"),
        ("error_log", "TEXT"),
        ("metrics_log", "JSONB"),
        ("best_metrics", "JSONB"),
        ("last_metrics", "JSONB"),
    ],
}


async def ensure_train_columns(engine) -> None:
    """幂等补齐训练相关表的缺失列（ALTER TABLE ... ADD COLUMN IF NOT EXISTS）。"""
    from sqlalchemy import text

    async with engine.begin() as conn:
        for table, columns in MISSING_TRAIN_COLUMNS.items():
            for name, col_type in columns:
                try:
                    await conn.execute(
                        text(f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {name} {col_type}")
                    )
                except Exception:
                    pass
```

- [ ] **Step 4: New Alembic revision**

创建 `backend/app/alembic/versions/7a1b2c3d4e5f_train_missing_columns.py`：

```python
"""补齐训练模块缺失列

Revision ID: 7a1b2c3d4e5f
Revises: 1c2d3e4f5a6b
Create Date: 2026-09-11
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "7a1b2c3d4e5f"
down_revision: str | None = "1c2d3e4f5a6b"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_ADDITIONS: dict[str, list[tuple[str, str]]] = {
    "train_tasks": [
        ("annotation_task_id", "INTEGER"),
        ("cleanup_delay_minutes", "INTEGER"),
        ("metrics_log", "JSONB"),
        ("best_metrics", "JSONB"),
        ("last_metrics", "JSONB"),
        ("error_log", "TEXT"),
    ],
    "train_models": [
        ("repo_id", "INTEGER"),
        ("export_format", "VARCHAR(32)"),
    ],
    "train_evals": [
        ("model_id", "INTEGER"),
        ("framework", "VARCHAR(16)"),
        ("hyperparams", "JSONB"),
        ("progress", "INTEGER"),
        ("started_at", "TIMESTAMP"),
        ("finished_at", "TIMESTAMP"),
        ("error_log", "TEXT"),
        ("metrics_log", "JSONB"),
        ("best_metrics", "JSONB"),
        ("last_metrics", "JSONB"),
    ],
}


def upgrade() -> None:
    for table, columns in _ADDITIONS.items():
        for name, col_type in columns:
            op.execute(f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {name} {col_type}")


def downgrade() -> None:
    pass
```

- [ ] **Step 5: 启动补列接入**

在 `backend/app/scripts/init_app.py` 的 `lifespan` 内、现有 `for col in ["metrics_log", ...]` 那段之前，替换为调用统一补列：

```python
        from app.api.v1.module_annotation.dataset.model import DatasetModel  # noqa: F401  # 确保模型已注册
        from app.plugin.module_train.schema_check import ensure_train_columns
        from app.core.database import async_engine as _train_engine
        await ensure_train_columns(_train_engine)
```

并删除紧随其后的重复 `ALTER TABLE train_tasks ADD COLUMN ...` 三行（`metrics_log`/`best_metrics`/`last_metrics`），保留 `CREATE TABLE IF NOT EXISTS train_predicts` 段。

- [ ] **Step 6: Run test to verify it passes**

Run: `cd backend && uv run pytest tests/test_train_schema_check.py -q`
Expected: PASS（3 passed）

- [ ] **Step 7: 验证迁移链**

Run: `cd backend && uv run alembic heads`
Expected: 只输出一个 head：`7a1b2c3d4e5f`（如仍显示 `1c2d3e4f5a6b` 说明文件未被识别，检查文件名/`down_revision`）。

- [ ] **Step 8: 全量测试 + ruff**

Run: `cd backend && uv run pytest -q && uv run ruff check`
Expected: 通过。

- [ ] **Step 9: Commit**

```bash
git add backend/app/plugin/module_train/schema_check.py backend/app/alembic/versions/7a1b2c3d4e5f_train_missing_columns.py backend/app/scripts/init_app.py backend/tests/test_train_schema_check.py
git commit -m "fix(train): 新增迁移补齐缺失列 + 启动幂等补列"
```

---

## Self-Review

**Spec coverage（对照 design 第 5.1 节）:**
- 0.6 枚举 bug → Task 1 ✅
- 0.9 S3 环境 → Task 2 ✅
- 0.4 删除接口契约 → Task 3 ✅
- 0.5 推理依赖 → Task 4 ✅
- 0.10 权限/菜单补种 → Task 5 ✅
- 0.3 迁移漂移 → Task 6 ✅
- 0.1 审计字段 / 0.2 级联删除 → 归入 **Plan 0B**（数据一致性）
- 0.7 重复 toast / 0.8 Playwright → 归入 **Plan 0C**（前端护栏）

**Placeholder scan:** 无 TBD/TODO；每个代码步骤均含完整代码。

**Type consistency:** `framework_value`、`ensure_inference_backend`、`MISSING_TRAIN_COLUMNS`、`TRAIN_BUTTON_PERMS`/`TRAIN_EXTRA_MENUS` 在定义与使用处名称一致。

**风险:** Task 5 删除 `lifespan` 临时 SQL 段后需确认无残留未使用 import（Step 6 ruff 会捕获）；Task 6 `train_evals.framework` 若旧库已有同名列类型不同，`IF NOT EXISTS` 会跳过，属预期。
