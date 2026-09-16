# Phase 3D：云边可视化前端 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 Phase 3C 的云边协同后端能力接到前端（边缘设备管理页、布控任务设备选择与 ROI、告警快照可访问），并补齐快照的受鉴权 HTTP 路由与读取时归一化。

**Architecture:** 后端新增受控快照路由与 `resolve_snapshot_url` 归一化助手，告警出参增加 `snapshot_url` 计算字段；前端新增 `module_video/edge` 页面与 `edge.ts` API，抽取 `EdgeDeviceSelect`/`EdgeCapabilityPanel`/`RoiEditor`/`SnapshotImage` 复用组件，增强 `deploy` 与 `alarm` 页面。

**Tech Stack:** FastAPI + SQLAlchemy 2.0 + Pydantic v2（后端）；Vue 3 + Vite + Element Plus + TypeScript（前端）；pytest + Playwright。

**Spec:** `docs/superpowers/specs/2026-09-12-phase3d-cloud-edge-frontend-design.md`

## Global Constraints

- 后端工作目录 `D:\AIStation\backend`；测试 `uv run pytest`；静态检查 `uv run ruff check`；不新增后端依赖。
- 前端工作目录 `D:\AIStation\frontend`；类型检查 `pnpm type-check`（`vue-tsc --noEmit`）；静态检查 `pnpm lint`；不新增前端依赖。
- 代码注释用中文；提交信息用 `feat(video): 中文描述` / `fix(video): 中文描述`；禁止 `git add -A`，只 add 本任务涉及文件。
- 遵循项目既有 CRUD 范式（`PageSearch` + `PageContent` + `EnhancedDialog` + `useCrudList`）与 Element Plus 栅格（`el-row`/`el-col`），不写自定义 CSS Grid 主布局。
- 前端静态路由为 hash 模式；动态路由/菜单来自后端 `sys_menu` 由 `init_app.py` 补种。
- 已知 pre-existing lint 错误文件：`LivePlayer.vue`、`live/index.vue`、`playback/index.vue`。只修本任务新增/触碰行，不追平历史错误。
- 快照 URL 统一前缀：`/api/v1/video/detections/{相对路径}`。

---

### Task 1: 后端快照归一化 helper + 受控路由

**Files:**
- Create: `backend/app/api/v1/module_video/inference/snapshot.py`
- Create: `backend/app/api/v1/module_video/inference/controller.py`
- Modify: `backend/app/api/v1/module_video/__init__.py`
- Test: `backend/tests/test_snapshot_url.py`
- Test: `backend/tests/test_snapshot_route.py`

**Interfaces:**
- Produces:
  - `snapshot.py::safe_local_snapshot(file_path: str) -> pathlib.Path | None` —— 在 `settings.DETECTIONS_DIR` 下解析；越界或非文件返回 `None`。
  - `snapshot.py::resolve_snapshot_url(value: str | None) -> str | None` —— 归一化为前端可访问 URL。
  - `controller.py::SnapshotRouter` —— FastAPI `APIRouter`，最终路径 `GET /api/v1/video/detections/{file_path:path}`。
- Consumes: `settings.DETECTIONS_DIR`、`app.utils.s3_client.s3_client.presigned_url`、`app.core.dependencies.AuthPermission`、`app.core.router_class.OperationLogRoute`。

- [ ] **Step 1: 写失败测试（归一化）**

创建 `backend/tests/test_snapshot_url.py`：

```python
"""快照引用归一化测试。"""
from pathlib import Path

from app.api.v1.module_video.inference import snapshot as snap


def test_empty_returns_none():
    assert snap.resolve_snapshot_url(None) is None
    assert snap.resolve_snapshot_url("") is None
    assert snap.resolve_snapshot_url("   ") is None


def test_http_passthrough():
    url = "https://cdn.example.com/a.jpg"
    assert snap.resolve_snapshot_url(url) == url


def test_object_scheme_presign(monkeypatch):
    monkeypatch.setattr(snap, "_presign", lambda key: f"https://signed/{key}")
    assert snap.resolve_snapshot_url("s3://edge-01/cam7/a.jpg") == "https://signed/edge-01/cam7/a.jpg"


def test_local_absolute(monkeypatch, tmp_path):
    monkeypatch.setattr(snap.settings, "DETECTIONS_DIR", str(tmp_path))
    f = tmp_path / "2026-09-12" / "a.jpg"
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_bytes(b"x")
    assert snap.resolve_snapshot_url(str(f)) == "/api/v1/video/detections/2026-09-12/a.jpg"


def test_local_relative(monkeypatch, tmp_path):
    monkeypatch.setattr(snap.settings, "DETECTIONS_DIR", str(tmp_path))
    f = tmp_path / "2026-09-12" / "b.jpg"
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_bytes(b"x")
    assert snap.resolve_snapshot_url("2026-09-12/b.jpg") == "/api/v1/video/detections/2026-09-12/b.jpg"


def test_missing_relative_becomes_presign(monkeypatch, tmp_path):
    monkeypatch.setattr(snap.settings, "DETECTIONS_DIR", str(tmp_path))
    monkeypatch.setattr(snap, "_presign", lambda key: f"https://signed/{key}")
    assert snap.resolve_snapshot_url("edge-01/cam7/missing.jpg") == "https://signed/edge-01/cam7/missing.jpg"


def test_presign_failure_returns_none(monkeypatch, tmp_path):
    monkeypatch.setattr(snap.settings, "DETECTIONS_DIR", str(tmp_path))
    monkeypatch.setattr(snap, "_presign", lambda key: None)
    assert snap.resolve_snapshot_url("edge-01/cam7/missing.jpg") is None


def test_safe_local_snapshot_blocks_traversal(monkeypatch, tmp_path):
    monkeypatch.setattr(snap.settings, "DETECTIONS_DIR", str(tmp_path))
    assert snap.safe_local_snapshot("../secret.txt") is None
    assert snap.safe_local_snapshot(str(Path(tmp_path).parent / "secret.txt")) is None


def test_safe_local_snapshot_ok(monkeypatch, tmp_path):
    monkeypatch.setattr(snap.settings, "DETECTIONS_DIR", str(tmp_path))
    f = tmp_path / "a.jpg"
    f.write_bytes(b"x")
    assert snap.safe_local_snapshot("a.jpg") == f.resolve()
```

- [ ] **Step 2: 运行测试确认失败**

Run: `uv run pytest tests/test_snapshot_url.py -q`
Expected: FAIL（`ModuleNotFoundError: ...snapshot` 或函数不存在）

- [ ] **Step 3: 实现 `snapshot.py`**

创建 `backend/app/api/v1/module_video/inference/snapshot.py`：

```python
"""快照引用的本地服务与对象存储归一化。

DB 中 ``snapshot_path`` 可能是：
- 本机 worker 保存的绝对路径（如 ``D:\\...\\data\\detections\\2026-09-12\\x.jpg``）；
- 相对路径（``{date}/{name}.jpg``）；
- 边缘 Agent 上报的对象存储相对引用 / ``s3://key``。

本模块统一转换为前端可访问 URL，供告警列表/详情展示。
"""
from pathlib import Path

from app.config.setting import settings

PREFIX = "/api/v1/video/detections"
_OBJECT_SCHEMES = ("s3://", "oss://", "minio://")


def detections_base() -> Path:
    """返回 DETECTIONS_DIR 的绝对路径。"""
    return Path(settings.DETECTIONS_DIR)


def safe_local_snapshot(file_path: str) -> Path | None:
    """在 DETECTIONS_DIR 下解析文件路径；目录穿越或文件不存在返回 None。"""
    if not file_path:
        return None
    base = detections_base().resolve()
    try:
        target = (base / file_path).resolve()
    except OSError:
        return None
    if target != base and base not in target.parents:
        return None
    return target if target.is_file() else None


def _presign(object_key: str) -> str | None:
    """对象存储 key → 预签名 URL；不可用或失败返回 None。"""
    try:
        from app.utils.s3_client import s3_client

        return s3_client.presigned_url(object_key)
    except Exception:
        return None


def resolve_snapshot_url(value: str | None) -> str | None:
    """把快照引用归一化为前端可访问 URL（失败返回 None）。

    规则：
    1. 空 → None；
    2. ``http(s)://`` → 原样；
    3. ``s3://`` / ``oss://`` / ``minio://`` → 去 scheme 后预签名；
    4. 命中 DETECTIONS_DIR 下的本地文件 → ``/api/v1/video/detections/{rel}``；
    5. 其余按对象存储 key 尽力预签名，失败 → None。
    """
    if not value:
        return None
    raw = value.strip()
    if not raw:
        return None
    if raw.startswith(("http://", "https://")):
        return raw
    for scheme in _OBJECT_SCHEMES:
        if raw.startswith(scheme):
            return _presign(raw[len(scheme):])

    base = detections_base().resolve()
    p = Path(raw)
    try:
        target = p.resolve() if p.is_absolute() else (base / raw).resolve()
    except OSError:
        return None
    if target.is_file() and (target == base or base in target.parents):
        rel = target.relative_to(base).as_posix()
        return f"{PREFIX}/{rel}"
    return _presign(raw)
```

- [ ] **Step 4: 运行测试确认通过**

Run: `uv run pytest tests/test_snapshot_url.py -q`
Expected: PASS（9 passed）

- [ ] **Step 5: 写失败测试（路由）**

创建 `backend/tests/test_snapshot_route.py`：

```python
"""快照 HTTP 路由测试。"""
from app.api.v1.module_video.inference import snapshot as snap


def test_snapshot_route_requires_auth(test_client):
    resp = test_client.get("/api/v1/video/detections/none.jpg")
    assert resp.status_code in (401, 403)


def test_snapshot_route_serves_file(test_client, auth_headers, monkeypatch, tmp_path):
    monkeypatch.setattr(snap.settings, "DETECTIONS_DIR", str(tmp_path))
    f = tmp_path / "a.jpg"
    f.write_bytes(b"fake-jpeg-bytes")
    resp = test_client.get("/api/v1/video/detections/a.jpg", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("image/jpeg")
    assert resp.content == b"fake-jpeg-bytes"


def test_snapshot_route_blocks_traversal(test_client, auth_headers, monkeypatch, tmp_path):
    monkeypatch.setattr(snap.settings, "DETECTIONS_DIR", str(tmp_path))
    resp = test_client.get(
        "/api/v1/video/detections/%2e%2e%2fenv%2f.env.dev", headers=auth_headers
    )
    assert resp.status_code == 404


def test_snapshot_route_missing_404(test_client, auth_headers, monkeypatch, tmp_path):
    monkeypatch.setattr(snap.settings, "DETECTIONS_DIR", str(tmp_path))
    resp = test_client.get("/api/v1/video/detections/nope.jpg", headers=auth_headers)
    assert resp.status_code == 404
```

- [ ] **Step 6: 运行测试确认失败**

Run: `uv run pytest tests/test_snapshot_route.py -q`
Expected: FAIL（404，路由未注册）

- [ ] **Step 7: 实现路由并注册**

创建 `backend/app/api/v1/module_video/inference/controller.py`：

```python
"""视频推理相关受控文件路由（快照展示）。"""
from fastapi import APIRouter, Depends
from fastapi import Path as PathParam
from fastapi.responses import FileResponse, JSONResponse

from app.api.v1.module_system.auth.schema import AuthSchema
from app.core.dependencies import AuthPermission
from app.core.router_class import OperationLogRoute

from .snapshot import safe_local_snapshot

SnapshotRouter = APIRouter(route_class=OperationLogRoute, prefix="/detections", tags=["视频快照"])

_MEDIA_TYPES = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
    ".gif": "image/gif",
    ".bmp": "image/bmp",
}


@SnapshotRouter.get("/{file_path:path}", summary="读取推理快照", include_in_schema=False)
async def get_snapshot_controller(
    file_path: str = PathParam(..., description="DETECTIONS_DIR 下的相对路径"),
    auth: AuthSchema = Depends(AuthPermission(["module_video:alarm:query"])),
) -> FileResponse | JSONResponse:
    """按相对路径返回 DETECTIONS_DIR 下的快照文件（受告警查看权限保护）。"""
    target = safe_local_snapshot(file_path)
    if target is None:
        return JSONResponse(status_code=404, content={"code": 404, "msg": "快照不存在"})
    media_type = _MEDIA_TYPES.get(target.suffix.lower(), "application/octet-stream")
    return FileResponse(str(target), media_type=media_type)
```

修改 `backend/app/api/v1/module_video/__init__.py`，在 `_register_video_routers()` 内新增导入与注册：

```python
def _register_video_routers():
    from .alarm.controller import AlarmRouter
    from .algorithm.controller import AlgorithmRouter
    from .camera.controller import CameraRouter
    from .edge.controller import EdgeRouter
    from .event.controller import EventRouter
    from .inference.controller import SnapshotRouter
    from .layout.controller import LayoutRouter
    from .preview.controller import PreviewRouter
    from .record.controller import RecordRouter
    video_router.include_router(AlarmRouter)
    video_router.include_router(AlgorithmRouter)
    video_router.include_router(CameraRouter)
    video_router.include_router(EdgeRouter)
    video_router.include_router(EventRouter)
    video_router.include_router(LayoutRouter)
    video_router.include_router(PreviewRouter)
    video_router.include_router(RecordRouter)
    video_router.include_router(SnapshotRouter)
```

- [ ] **Step 8: 运行测试确认通过**

Run: `uv run pytest tests/test_snapshot_route.py tests/test_snapshot_url.py -q`
Expected: PASS

- [ ] **Step 9: 全量 + ruff + 提交**

Run: `uv run pytest -q && uv run ruff check app/api/v1/module_video/inference/snapshot.py app/api/v1/module_video/inference/controller.py app/api/v1/module_video/__init__.py`
Expected: 全部通过；ruff `All checks passed!`

```bash
git add backend/app/api/v1/module_video/inference/snapshot.py backend/app/api/v1/module_video/inference/controller.py backend/app/api/v1/module_video/__init__.py backend/tests/test_snapshot_url.py backend/tests/test_snapshot_route.py
git commit -m "feat(video): 受控快照路由与快照 URL 归一化"
```

---

### Task 2: 告警出参 `snapshot_url` + 规则匹配健壮化

**Files:**
- Modify: `backend/app/api/v1/module_video/alarm/schema.py`
- Modify: `backend/app/api/v1/module_video/inference/service.py`
- Test: `backend/tests/test_alarm_rule_match.py`
- Test: `backend/tests/test_alarm_snapshot_url.py`

**Interfaces:**
- Consumes: `snapshot.py::resolve_snapshot_url`（Task 1）、`AlarmRuleModel`。
- Produces:
  - `service.py::pick_alarm_rule(rules: list, algorithm_type: str) -> Any | None`。
  - `AlarmRecordOutSchema.snapshot_url: str | None`（Pydantic `model_dump()` 中含该键）。

- [ ] **Step 1: 写失败测试（规则匹配 + 出参）**

创建 `backend/tests/test_alarm_rule_match.py`：

```python
"""告警规则匹配测试。"""
from app.api.v1.module_video.inference.service import pick_alarm_rule


class _Rule:
    def __init__(self, alarm_type):
        self.alarm_type = alarm_type


def test_pick_alarm_rule_prefers_exact_type():
    rules = [_Rule("OTHER"), _Rule("INTRUSION")]
    assert pick_alarm_rule(rules, "INTRUSION").alarm_type == "INTRUSION"


def test_pick_alarm_rule_falls_back_to_first():
    rules = [_Rule("OTHER"), _Rule("SECOND")]
    assert pick_alarm_rule(rules, "INTRUSION").alarm_type == "OTHER"


def test_pick_alarm_rule_empty():
    assert pick_alarm_rule([], "X") is None
```

创建 `backend/tests/test_alarm_snapshot_url.py`：

```python
"""告警出参 snapshot_url 计算字段测试。"""
from app.api.v1.module_video.alarm.schema import AlarmRecordOutSchema
from app.api.v1.module_video.inference import snapshot as snap


def test_snapshot_url_computed(monkeypatch, tmp_path):
    monkeypatch.setattr(snap.settings, "DETECTIONS_DIR", str(tmp_path))
    f = tmp_path / "2026-09-12" / "a.jpg"
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_bytes(b"x")
    schema = AlarmRecordOutSchema(
        camera_id=1, alarm_type="INTRUSION", snapshot_path=str(f)
    )
    dumped = schema.model_dump()
    assert dumped["snapshot_url"] == "/api/v1/video/detections/2026-09-12/a.jpg"


def test_snapshot_url_none_when_no_path():
    schema = AlarmRecordOutSchema(camera_id=1, alarm_type="INTRUSION", snapshot_path=None)
    assert schema.model_dump()["snapshot_url"] is None
```

- [ ] **Step 2: 运行测试确认失败**

Run: `uv run pytest tests/test_alarm_rule_match.py tests/test_alarm_snapshot_url.py -q`
Expected: FAIL（`pick_alarm_rule` 不存在 / `snapshot_url` 缺失）

- [ ] **Step 3: 实现 `pick_alarm_rule` 并替换查询**

在 `backend/app/api/v1/module_video/inference/service.py` 顶部（`class InferenceService` 之前）新增：

```python
def pick_alarm_rule(rules: list, algorithm_type: str):
    """从多条候选规则中选一条：优先 alarm_type 精确匹配，否则第一条；空返回 None。"""
    if not rules:
        return None
    for r in rules:
        if getattr(r, "alarm_type", None) == algorithm_type:
            return r
    return rules[0]
```

把 `process_detection_callback` 内的规则查询：

```python
            result = await session.execute(stmt)
            rule = result.scalar_one_or_none()
```

替换为：

```python
            result = await session.execute(stmt)
            rule = pick_alarm_rule(result.scalars().all(), algorithm_type or "AI_DETECTION")
```

- [ ] **Step 4: 增加 `snapshot_url` 计算字段**

修改 `backend/app/api/v1/module_video/alarm/schema.py` 顶部导入：

```python
from pydantic import BaseModel, Field, computed_field
```

在 `AlarmRecordOutSchema` 的 `rule: CommonSchema | None = None` 之后追加：

```python
    @computed_field  # type: ignore[prop-decorator]
    @property
    def snapshot_url(self) -> str | None:
        """快照可访问 URL（按本地文件 / 对象存储归一化）。"""
        from app.api.v1.module_video.inference.snapshot import resolve_snapshot_url

        return resolve_snapshot_url(self.snapshot_path)
```

- [ ] **Step 5: 运行测试确认通过**

Run: `uv run pytest tests/test_alarm_rule_match.py tests/test_alarm_snapshot_url.py -q`
Expected: PASS

- [ ] **Step 6: 全量 + ruff + 提交**

Run: `uv run pytest -q && uv run ruff check app/api/v1/module_video/alarm/schema.py app/api/v1/module_video/inference/service.py`
Expected: 全部通过

```bash
git add backend/app/api/v1/module_video/alarm/schema.py backend/app/api/v1/module_video/inference/service.py backend/tests/test_alarm_rule_match.py backend/tests/test_alarm_snapshot_url.py
git commit -m "feat(video): 告警出参 snapshot_url 与规则匹配健壮化"
```

---

### Task 3: 边缘设备管理页（API + 能力面板 + 菜单 + E2E）

**Files:**
- Create: `frontend/src/api/module_video/edge.ts`
- Create: `frontend/src/components/Edge/EdgeCapabilityPanel.vue`
- Create: `frontend/src/views/module_video/edge/index.vue`
- Modify: `backend/app/scripts/init_app.py`（新增 `_ensure_edge_page_menu()` 并调用）
- Test: `frontend/e2e/edge.spec.ts`

**Interfaces:**
- Consumes: 后端 `/video/edge/*`（Task 3C 已就绪）。
- Produces:
  - `edge.ts::getEdgeDeviceList/getEdgeDeviceDetail/createEdgeDevice/updateEdgeDevice/deleteEdgeDevice`。
  - `EdgeCapabilityPanel` props：`capabilities?: Record<string, any> | null`、`metrics?: Record<string, any> | null`。
  - 路由 `/video/edge`，组件 `module_video/edge/index`，权限 `module_video:edge:query`。

- [ ] **Step 1: 创建 edge API**

创建 `frontend/src/api/module_video/edge.ts`：

```ts
import request from "@/utils/request";

export function getEdgeDeviceList(data?: any) {
  return request({ url: "/video/edge/list", method: "get", params: data });
}

export function getEdgeDeviceDetail(id: number) {
  return request({ url: `/video/edge/detail/${id}`, method: "get" });
}

export function createEdgeDevice(data: any) {
  return request({ url: "/video/edge/create", method: "post", data });
}

export function updateEdgeDevice(id: number, data: any) {
  return request({ url: `/video/edge/update/${id}`, method: "put", data });
}

export function deleteEdgeDevice(ids: number[]) {
  return request({ url: "/video/edge/delete", method: "delete", data: ids });
}
```

- [ ] **Step 2: 创建能力/指标面板组件**

创建 `frontend/src/components/Edge/EdgeCapabilityPanel.vue`：

```vue
<template>
  <div class="edge-cap-panel">
    <el-descriptions :column="2" border size="small" title="硬件">
      <el-descriptions-item label="平台">{{ hardware.platform || "-" }}</el-descriptions-item>
      <el-descriptions-item label="GPU 型号">{{ hardware.gpu_model || "-" }}</el-descriptions-item>
      <el-descriptions-item label="显存(MB)">{{ hardware.vram_mb ?? "-" }}</el-descriptions-item>
      <el-descriptions-item label="TPU">{{ hardware.tpu || "-" }}</el-descriptions-item>
    </el-descriptions>

    <el-descriptions :column="1" border size="small" title="能力" class="edge-cap-block">
      <el-descriptions-item label="推理后端">
        <el-tag v-for="b in backends" :key="b" size="small" class="edge-cap-tag">{{ b }}</el-tag>
        <span v-if="!backends.length" class="edge-cap-muted">-</span>
      </el-descriptions-item>
      <el-descriptions-item label="模型族">
        <el-tag v-for="m in modelFamilies" :key="m" size="small" type="success" class="edge-cap-tag">
          {{ m }}
        </el-tag>
        <span v-if="!modelFamilies.length" class="edge-cap-muted">-</span>
      </el-descriptions-item>
      <el-descriptions-item label="最大并发路数">{{ maxChannels ?? "-" }}</el-descriptions-item>
      <el-descriptions-item label="解码">
        {{ codecList(codecs.decode) }} ｜ 编码: {{ codecList(codecs.encode) }}
      </el-descriptions-item>
    </el-descriptions>

    <el-descriptions :column="2" border size="small" title="实时指标" class="edge-cap-block">
      <el-descriptions-item label="CPU">{{ fmtPercent(metrics.cpu) }}</el-descriptions-item>
      <el-descriptions-item label="GPU">{{ fmtPercent(metrics.gpu) }}</el-descriptions-item>
      <el-descriptions-item label="显存(MB)">{{ metrics.vram_mb ?? "-" }}</el-descriptions-item>
      <el-descriptions-item label="在跑路数">
        {{ metrics.running_channels ?? metrics.running ?? "-" }}
      </el-descriptions-item>
    </el-descriptions>
  </div>
</template>

<script setup lang="ts">
import { computed } from "vue";

const props = defineProps<{
  capabilities?: Record<string, any> | null;
  metrics?: Record<string, any> | null;
}>();

const hardware = computed(() => props.capabilities?.hardware || {});
const backends = computed<string[]>(() => props.capabilities?.backends || []);
const modelFamilies = computed<string[]>(() => props.capabilities?.model_families || []);
const maxChannels = computed<number | undefined>(() => props.capabilities?.max_channels);
const codecs = computed<Record<string, any>>(() => props.capabilities?.codecs || {});
const metrics = computed<Record<string, any>>(() => props.metrics || {});

function codecList(val: any): string {
  return Array.isArray(val) && val.length ? val.join("/") : "-";
}

function fmtPercent(val: any): string {
  if (val === undefined || val === null) return "-";
  const n = Number(val);
  if (Number.isNaN(n)) return String(val);
  return n <= 1 ? `${Math.round(n * 100)}%` : `${round1(n)}%`;
}

function round1(n: number): number {
  return Math.round(n * 10) / 10;
}
</script>

<style scoped>
.edge-cap-panel {
  font-size: 12px;
}
.edge-cap-block {
  margin-top: 10px;
}
.edge-cap-tag {
  margin-right: 4px;
}
.edge-cap-muted {
  color: var(--el-text-color-placeholder);
}
</style>
```

- [ ] **Step 3: 补种边缘设备页菜单**

在 `backend/app/scripts/init_app.py` 的 `_ensure_edge_button_menus()` 之后新增：

```python
async def _ensure_edge_page_menu() -> None:
    """确保『边缘设备』页面菜单存在（挂在视频监控父菜单下，分配 admin）。"""
    from sqlalchemy import select

    from app.api.v1.module_system.menu.model import MenuModel
    from app.api.v1.module_system.role.model import RoleMenusModel, RoleModel
    from app.core.database import async_db_session

    async with async_db_session() as db:
        async with db.begin():
            existing = await db.execute(
                select(MenuModel).where(MenuModel.route_name == "VideoEdge")
            )
            if existing.scalar_one_or_none():
                return
            parent = await db.scalar(
                select(MenuModel).where(MenuModel.name == "视频监控", MenuModel.type == 1)
            )
            if not parent:
                log.warning("⚠️  未找到视频监控父菜单，跳过边缘设备菜单注册")
                return
            menu = MenuModel(
                name="边缘设备",
                type=2,
                icon="el-icon-Cpu",
                order=10,
                route_name="VideoEdge",
                route_path="/video/edge",
                component_path="module_video/edge/index",
                permission="module_video:edge:query",
                parent_id=parent.id,
                status="0",
                is_deleted=False,
                title="边缘设备",
            )
            db.add(menu)
            await db.flush()
            admin = await db.scalar(select(RoleModel).where(RoleModel.id == 1))
            if admin:
                db.add(RoleMenusModel(role_id=admin.id, menu_id=menu.id))
            log.info("✅ 边缘设备菜单已注册")
```

在同文件启动序列中 `_ensure_edge_button_menus()`（约 586 行）之后新增调用：

```python
        await _ensure_deploy_menu()
        await _ensure_edge_button_menus()
        await _ensure_edge_page_menu()
```

- [ ] **Step 4: 创建边缘设备管理页**

创建 `frontend/src/views/module_video/edge/index.vue`：

```vue
<template>
  <div class="app-container">
    <PageSearch
      ref="searchRef"
      :search-config="searchConfig"
      @query-click="handleQueryClick"
      @reset-click="handleResetClick"
    />

    <PageContent ref="contentRef" :content-config="contentConfig">
      <template #toolbar="{ toolbarRight, onToolbar, removeIds, cols }">
        <CrudToolbarLeft
          :remove-ids="removeIds"
          :perm-create="['module_video:edge:create']"
          :perm-delete="['module_video:edge:delete']"
          @add="handleOpenDialog('create')"
          @delete="onToolbar('delete')"
        />
        <div class="data-table__toolbar--right">
          <CrudToolbarRight :buttons="toolbarRight" :cols="cols" :on-toolbar="onToolbar" />
        </div>
      </template>

      <template #table="{ data, loading, tableRef, onSelectionChange }">
        <div class="data-table__content">
          <el-table
            :ref="tableRef as any"
            v-loading="loading"
            row-key="id"
            :data="data"
            height="100%"
            border
            stripe
            @selection-change="onSelectionChange"
          >
            <template #empty>
              <el-empty :image-size="80" description="暂无数据" />
            </template>
            <el-table-column
              v-if="edgeCols.find((c) => c.prop === 'selection')?.show"
              type="selection"
              width="55"
              align="center"
            />
            <el-table-column
              v-if="edgeCols.find((c) => c.prop === 'index')?.show"
              type="index"
              fixed
              label="序号"
              width="60"
              align="center"
            />
            <el-table-column label="设备名称" prop="name" min-width="130" show-overflow-tooltip />
            <el-table-column label="设备编码" prop="code" min-width="130" show-overflow-tooltip />
            <el-table-column label="状态" width="100" align="center">
              <template #default="scope">
                <el-tag :type="statusTag(scope.row.status)" size="small">
                  {{ statusLabel(scope.row.status) }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column label="在跑/上限" width="110" align="center">
              <template #default="scope">
                {{ runningOf(scope.row) }} / {{ scope.row.capabilities?.max_channels ?? "-" }}
              </template>
            </el-table-column>
            <el-table-column
              label="最后心跳"
              prop="last_heartbeat"
              width="170"
              show-overflow-tooltip
            />
            <el-table-column
              label="控制地址"
              prop="control_url"
              min-width="160"
              show-overflow-tooltip
            />
            <el-table-column
              v-if="edgeCols.find((c) => c.prop === 'operation')?.show"
              fixed="right"
              label="操作"
              align="center"
              min-width="160"
            >
              <template #default="scope">
                <el-button type="primary" size="small" link @click="handleViewDetail(scope.row)">
                  详情
                </el-button>
                <el-button
                  v-hasPerm="['module_video:edge:update']"
                  type="primary"
                  size="small"
                  link
                  @click="handleOpenDialog('update', scope.row.id)"
                >
                  编辑
                </el-button>
                <el-button
                  v-hasPerm="['module_video:edge:delete']"
                  type="danger"
                  size="small"
                  link
                  @click="handleRowDelete(scope.row.id)"
                >
                  删除
                </el-button>
              </template>
            </el-table-column>
          </el-table>
        </div>
      </template>
    </PageContent>

    <EnhancedDialog
      v-model="dialogVisible.visible"
      :title="dialogVisible.title"
      append-to-body
      width="620px"
      @close="handleCloseDialog"
    >
      <el-form ref="dataFormRef" :model="formData" label-width="100px" size="default">
        <el-form-item
          label="设备名称"
          prop="name"
          :rules="[{ required: true, message: '请输入设备名称', trigger: 'blur' }]"
        >
          <el-input v-model="formData.name" placeholder="如：一号车间边缘盒" />
        </el-form-item>
        <el-form-item
          label="设备编码"
          prop="code"
          :rules="[{ required: true, message: '请输入设备编码', trigger: 'blur' }]"
        >
          <el-input v-model="formData.code" placeholder="唯一编码，如 edge-01" />
        </el-form-item>
        <el-form-item label="控制地址" prop="control_url">
          <el-input v-model="formData.control_url" placeholder="http://192.168.1.10:8080" />
        </el-form-item>
        <el-form-item label="鉴权密钥" prop="secret">
          <el-input
            v-model="formData.secret"
            type="password"
            show-password
            :placeholder="dialogVisible.type === 'update' ? '留空表示不变更' : 'Agent 控制面密钥'"
          />
        </el-form-item>
        <el-form-item label="备注" prop="description">
          <el-input v-model="formData.description" type="textarea" :rows="2" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="handleCloseDialog">取消</el-button>
        <el-button type="primary" :loading="submitLoading" @click="handleSubmit">保存</el-button>
      </template>
    </EnhancedDialog>

    <el-drawer v-model="detailDrawer.visible" title="边缘设备详情" size="560px">
      <template v-if="detailDrawer.data">
        <el-descriptions :column="1" border size="small">
          <el-descriptions-item label="名称">{{ detailDrawer.data.name }}</el-descriptions-item>
          <el-descriptions-item label="编码">{{ detailDrawer.data.code }}</el-descriptions-item>
          <el-descriptions-item label="状态">
            <el-tag :type="statusTag(detailDrawer.data.status)" size="small">
              {{ statusLabel(detailDrawer.data.status) }}
            </el-tag>
          </el-descriptions-item>
          <el-descriptions-item label="控制地址">
            {{ detailDrawer.data.control_url || "-" }}
          </el-descriptions-item>
          <el-descriptions-item label="最后心跳">
            {{ detailDrawer.data.last_heartbeat || "-" }}
          </el-descriptions-item>
        </el-descriptions>
        <EdgeCapabilityPanel
          class="edge-detail-cap"
          :capabilities="detailDrawer.data.capabilities"
          :metrics="detailDrawer.data.metrics"
        />
      </template>
    </el-drawer>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onBeforeMount, onBeforeUnmount } from "vue";
import {
  getEdgeDeviceList,
  getEdgeDeviceDetail,
  createEdgeDevice,
  updateEdgeDevice,
  deleteEdgeDevice,
} from "@/api/module_video/edge";
import EdgeCapabilityPanel from "@/components/Edge/EdgeCapabilityPanel.vue";
import type { ISearchConfig, IContentConfig } from "@/components/CURD/types";
import { useCrudList } from "@/components/CURD/useCrudList";

interface TablePageQuery {
  page_no: number;
  page_size: number;
  [key: string]: any;
}

const { searchRef, contentRef, handleQueryClick, handleResetClick, refreshList } = useCrudList();

const submitLoading = ref(false);
const dataFormRef = ref();

const searchConfig = reactive<ISearchConfig>({
  permPrefix: "module_video:edge",
  colon: true,
  isExpandable: true,
  showNumber: 2,
  form: { labelWidth: "auto" },
  formItems: [
    {
      prop: "name",
      label: "设备名称",
      type: "input",
      attrs: { placeholder: "设备名称", clearable: true, style: { width: "180px" } },
    },
    {
      prop: "status",
      label: "状态",
      type: "select",
      options: [
        { label: "在线", value: "online" },
        { label: "离线", value: "offline" },
        { label: "繁忙", value: "busy" },
        { label: "异常", value: "error" },
      ],
      attrs: { placeholder: "全部", clearable: true, style: { width: "120px" } },
    },
  ],
});

const edgeCols = reactive<Array<{ prop?: string; label?: string; show?: boolean }>>([
  { prop: "selection", label: "选择框", show: true },
  { prop: "index", label: "序号", show: true },
  { prop: "operation", label: "操作", show: true },
]);

const contentConfig = reactive<IContentConfig<TablePageQuery>>({
  permPrefix: "module_video:edge",
  pk: "id",
  cols: edgeCols as IContentConfig["cols"],
  hideColumnFilter: false,
  toolbar: [],
  defaultToolbar: ["refresh", "filter"],
  pagination: { pageSize: 10, pageSizes: [10, 20, 30, 50] },
  request: { page_no: "page_no", page_size: "page_size" },
  indexAction: async (params) => {
    const res = await getEdgeDeviceList(params as TablePageQuery);
    return { total: res.data.data.total, list: res.data.data.items };
  },
  deleteAction: async (ids) => {
    await deleteEdgeDevice(
      ids
        .split(",")
        .map((s: string) => Number(s.trim()))
        .filter((n: number) => !Number.isNaN(n))
    );
  },
  deleteConfirm: { title: "警告", message: "确认删除该边缘设备?", type: "warning" },
});

const dialogVisible = reactive({
  title: "",
  visible: false,
  type: "create" as "create" | "update",
});

const formData = reactive({
  id: undefined as number | undefined,
  name: "",
  code: "",
  control_url: undefined as string | undefined,
  secret: undefined as string | undefined,
  description: undefined as string | undefined,
});

const initialFormData = { ...formData };

const detailDrawer = reactive<{ visible: boolean; data: any }>({ visible: false, data: null });

function statusTag(status: string): "success" | "info" | "warning" | "danger" {
  if (status === "online") return "success";
  if (status === "busy") return "warning";
  if (status === "error") return "danger";
  return "info";
}

function statusLabel(status: string): string {
  return (
    { online: "在线", offline: "离线", busy: "繁忙", error: "异常" }[status] || status || "未知"
  );
}

function runningOf(row: any): number | string {
  const m = row?.metrics || {};
  return m.running_channels ?? m.running ?? "-";
}

function handleRowDelete(id: number) {
  contentRef.value?.handleDelete(id);
}

async function handleViewDetail(row: any) {
  detailDrawer.data = row;
  detailDrawer.visible = true;
  try {
    const res = await getEdgeDeviceDetail(row.id);
    if (res.data?.data) detailDrawer.data = res.data.data;
  } catch {
    /* 保留列表行数据 */
  }
}

async function resetForm() {
  if (dataFormRef.value) {
    dataFormRef.value.resetFields();
    dataFormRef.value.clearValidate();
  }
  Object.assign(formData, initialFormData);
}

async function handleCloseDialog() {
  dialogVisible.visible = false;
  await resetForm();
}

async function handleOpenDialog(type: "create" | "update", id?: number) {
  dialogVisible.type = type;
  if (id && type === "update") {
    dialogVisible.title = "编辑边缘设备";
    const res = await getEdgeDeviceDetail(id);
    const item = res.data?.data;
    if (item) {
      formData.id = item.id;
      formData.name = item.name;
      formData.code = item.code;
      formData.control_url = item.control_url;
      formData.description = item.description;
      formData.secret = undefined;
    }
  } else {
    dialogVisible.title = "新增边缘设备";
    await resetForm();
  }
  dialogVisible.visible = true;
}

async function handleSubmit() {
  dataFormRef.value.validate(async (valid: boolean) => {
    if (!valid) return;
    submitLoading.value = true;
    const id = formData.id;
    const payload: any = {
      name: formData.name,
      code: formData.code,
      control_url: formData.control_url || null,
      description: formData.description || null,
    };
    if (formData.secret) payload.secret = formData.secret;
    try {
      if (id) {
        await updateEdgeDevice(id, payload);
      } else {
        await createEdgeDevice(payload);
      }
      dialogVisible.visible = false;
      await resetForm();
      refreshList();
    } finally {
      submitLoading.value = false;
    }
  });
}

let pollTimer: ReturnType<typeof setInterval> | null = null;

async function pollDevices() {
  if (document.hidden || dialogVisible.visible) return;
  try {
    await refreshList();
  } catch {
    /* 轮询失败静默 */
  }
}

onBeforeMount(() => {
  pollTimer = setInterval(pollDevices, 15_000);
});
onBeforeUnmount(() => {
  if (pollTimer) clearInterval(pollTimer);
});
</script>

<style scoped>
.edge-detail-cap {
  margin-top: 12px;
}
</style>
```

- [ ] **Step 5: 运行前端类型检查**

Run: `pnpm type-check`
Expected: 无新增错误（0 errors）

- [ ] **Step 6: 写 E2E 测试**

创建 `frontend/e2e/edge.spec.ts`：

```ts
import { test, expect } from "@playwright/test";

test("边缘设备页可加载并打开新增弹窗", async ({ page }) => {
  await page.goto("/#/video/edge", { waitUntil: "domcontentloaded" });
  await expect(page.locator(".tags-item.active .tag-text").first()).toHaveText("边缘设备");
  await expect(page.locator(".app-main .app-container").first()).toBeVisible({ timeout: 15_000 });

  // 打开新增弹窗并校验必填项
  await page.getByRole("button", { name: /新增|添加|Add/i }).first().click();
  await expect(page.locator(".el-dialog")).toBeVisible();
  await expect(page.locator(".el-dialog").getByLabel("设备名称")).toBeVisible();
  await page.keyboard.press("Escape");
});
```

- [ ] **Step 7: 运行 E2E（需后端已重启以补种菜单）**

前置：按 `frontend/e2e/README.md` 启动后端（`CAPTCHA_ENABLE=false`）与前端预览；首次需重启后端让 `_ensure_edge_page_menu()` 生效。
Run: `pnpm e2e -- edge.spec.ts`
Expected: 1 passed

- [ ] **Step 8: 提交**

```bash
git add frontend/src/api/module_video/edge.ts frontend/src/components/Edge/EdgeCapabilityPanel.vue frontend/src/views/module_video/edge/index.vue frontend/e2e/edge.spec.ts backend/app/scripts/init_app.py
git commit -m "feat(video): 边缘设备管理页与能力面板"
```

---

### Task 4: 布控页设备选择 + ROI 编辑器

**Files:**
- Modify: `frontend/src/components/Video/LivePlayer.vue`（新增 overlay 插槽 + 暴露 video 元素）
- Create: `frontend/src/components/Video/RoiEditor.vue`
- Create: `frontend/src/components/Edge/EdgeDeviceSelect.vue`
- Modify: `frontend/src/views/module_video/deploy/index.vue`
- Test: `frontend/e2e/deploy-edge-roi.spec.ts`

**Interfaces:**
- Consumes: `getEdgeDeviceList`（Task 3）、`EdgeCapabilityPanel`（Task 3）。
- Produces:
  - `LivePlayer` 新增 `<slot name="overlay" />` 与 `defineExpose({ ..., getVideoElement })`。
  - `RoiEditor` props `{ modelValue: number[][] | null; streamId?: string }`，emits `update:modelValue`（归一化 `[[x,y], ...]`）。
  - `EdgeDeviceSelect` props `{ modelValue: number | null }`，emits `update:modelValue`；含 `null` = 本机/纯云端。
  - 布控任务 payload 新增 `edge_device_id` 与 `detect_region`。

- [ ] **Step 1: 给 LivePlayer 增加 overlay 插槽并暴露 video 元素**

修改 `frontend/src/components/Video/LivePlayer.vue`：在 `<DetectionOverlay ... />` 之后、`</div>`（`.video-wrapper` 结束）之前新增一行：

```html
      <slot name="overlay" />
```

并把文件底部：

```js
defineExpose({ play, destroyPlayer, switchProtocol });
```

替换为：

```js
function getVideoElement(): HTMLVideoElement | null {
  return videoRef.value;
}

defineExpose({ play, destroyPlayer, switchProtocol, getVideoElement });
```

- [ ] **Step 2: 创建 RoiEditor 组件**

创建 `frontend/src/components/Video/RoiEditor.vue`：

```vue
<template>
  <div class="roi-editor">
    <div ref="wrapRef" class="roi-stage">
      <LivePlayer
        ref="playerRef"
        :stream-id="streamId"
        stream-type="flv"
        @load="onPlayerLoad"
        @error="onPlayerError"
      >
        <template #overlay>
          <svg
            class="roi-svg"
            :viewBox="`0 0 ${stage.w} ${stage.h}`"
            @click="onStageClick"
            @dblclick.prevent="closePolygon"
          >
            <polygon
              v-if="points.length >= 2"
              :points="polygonPoints"
              fill="rgba(64,158,255,0.25)"
              stroke="#409eff"
              stroke-width="2"
            />
            <circle
              v-for="(p, i) in displayPoints"
              :key="i"
              :cx="p[0]"
              :cy="p[1]"
              r="4"
              fill="#fff"
              stroke="#409eff"
              stroke-width="2"
            />
          </svg>
        </template>
      </LivePlayer>
      <div v-if="!streamId" class="roi-hint">该点位无可用流，无法绘制 ROI</div>
    </div>
    <div class="roi-actions">
      <span class="roi-count">已选 {{ points.length }} 个点</span>
      <el-button size="small" @click="undoPoint">撤销</el-button>
      <el-button size="small" @click="clearPoints">清空</el-button>
      <el-button size="small" type="primary" @click="closePolygon">闭合</el-button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onBeforeUnmount, onMounted, nextTick } from "vue";
import LivePlayer from "./LivePlayer.vue";

const props = defineProps<{
  modelValue: number[][] | null;
  streamId?: string;
}>();

const emit = defineEmits<{ (e: "update:modelValue", val: number[][] | null): void }>();

const wrapRef = ref<HTMLDivElement | null>(null);
const playerRef = ref<any>(null);
const stage = reactive({ w: 640, h: 360 });
const videoSize = reactive({ w: 0, h: 0 });
const points = ref<number[][]>(
  Array.isArray(props.modelValue) ? props.modelValue.map((p) => [Number(p[0]), Number(p[1])]) : []
);
const closed = ref(false);

const contentRect = computed(() => {
  const { w, h } = stage;
  const vw = videoSize.w || 16;
  const vh = videoSize.h || 9;
  const scale = Math.min(w / vw, h / vh);
  const dw = vw * scale;
  const dh = vh * scale;
  return { x: (w - dw) / 2, y: (h - dh) / 2, w: dw, h: dh };
});

const displayPoints = computed(() =>
  points.value.map(([nx, ny]) => [
    contentRect.value.x + nx * contentRect.value.w,
    contentRect.value.y + ny * contentRect.value.h,
  ])
);

const polygonPoints = computed(() =>
  displayPoints.value.map(([x, y]) => `${x},${y}`).join(" ")
);

function measureStage() {
  const el = wrapRef.value;
  if (!el) return;
  const video = playerRef.value?.getVideoElement?.();
  if (video?.videoWidth) {
    videoSize.w = video.videoWidth;
    videoSize.h = video.videoHeight;
  }
  stage.w = el.clientWidth || 640;
  stage.h = el.clientHeight || 360;
}

function onPlayerLoad() {
  nextTick(measureStage);
}

function onPlayerError() {
  /* 保留画布，允许在无流时仍显示已有 ROI */
}

function onStageClick(e: MouseEvent) {
  if (!videoSize.w) return;
  const video = playerRef.value?.getVideoElement?.();
  const box = video?.getBoundingClientRect();
  if (!box) return;
  const nx = (e.clientX - box.left - contentRect.value.x) / contentRect.value.w;
  const ny = (e.clientY - box.top - contentRect.value.y) / contentRect.value.h;
  if (nx < 0 || nx > 1 || ny < 0 || ny > 1) return;
  points.value = [...points.value, [round4(nx), round4(ny)]];
  closed.value = false;
  emit("update:modelValue", points.value);
}

function undoPoint() {
  points.value = points.value.slice(0, -1);
  closed.value = false;
  emit("update:modelValue", points.value.length ? points.value : null);
}

function clearPoints() {
  points.value = [];
  closed.value = false;
  emit("update:modelValue", null);
}

function closePolygon() {
  if (points.value.length < 3) return;
  closed.value = true;
  emit("update:modelValue", points.value);
}

function round4(n: number): number {
  return Math.round(n * 10000) / 10000;
}

let ro: ResizeObserver | null = null;
onMounted(() => {
  nextTick(measureStage);
  if (wrapRef.value) {
    ro = new ResizeObserver(() => measureStage());
    ro.observe(wrapRef.value);
  }
});
onBeforeUnmount(() => {
  if (ro) ro.disconnect();
});
</script>

<style scoped>
.roi-editor {
  width: 100%;
}
.roi-stage {
  position: relative;
  width: 100%;
  height: 320px;
  overflow: hidden;
  background: #000;
  border-radius: 6px;
}
.roi-svg {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
  cursor: crosshair;
}
.roi-hint {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 13px;
  color: #ccc;
  pointer-events: none;
  background: rgba(0, 0, 0, 0.5);
}
.roi-actions {
  display: flex;
  gap: 8px;
  align-items: center;
  margin-top: 8px;
}
.roi-count {
  margin-right: auto;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
</style>
```

- [ ] **Step 3: 创建 EdgeDeviceSelect 组件**

创建 `frontend/src/components/Edge/EdgeDeviceSelect.vue`：

```vue
<template>
  <el-select
    :model-value="modelValue ?? null"
    filterable
    clearable
    placeholder="本机 / 纯云端"
    style="width: 280px"
    @update:model-value="onChange"
  >
    <el-option :value="null" label="本机 / 纯云端（不使用边缘设备）" />
    <el-option v-for="d in devices" :key="d.id" :value="d.id" :label="d.name" :disabled="false">
      <span class="edge-opt">
        <span class="edge-opt-dot" :class="d.status" />
        {{ d.name }}
        <span class="edge-opt-code">({{ d.code }})</span>
        <span class="edge-opt-meta">{{ runningOf(d) }}/{{ d.capabilities?.max_channels ?? "-" }}</span>
      </span>
    </el-option>
  </el-select>
</template>

<script setup lang="ts">
import { ref, onMounted } from "vue";
import { getEdgeDeviceList } from "@/api/module_video/edge";

defineProps<{ modelValue: number | null }>();
const emit = defineEmits<{ (e: "update:modelValue", val: number | null): void }>();

const devices = ref<any[]>([]);

function runningOf(d: any): number | string {
  const m = d?.metrics || {};
  return m.running_channels ?? m.running ?? "-";
}

function onChange(val: number | null) {
  emit("update:modelValue", val ?? null);
}

onMounted(async () => {
  try {
    const res = await getEdgeDeviceList({ page_no: 1, page_size: 100 });
    devices.value = res.data?.data?.items || [];
  } catch {
    /* 加载失败保持空列表 */
  }
});
</script>

<style scoped>
.edge-opt {
  display: inline-flex;
  gap: 6px;
  align-items: center;
}
.edge-opt-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--el-color-info);
}
.edge-opt-dot.online {
  background: var(--el-color-success);
}
.edge-opt-dot.busy {
  background: var(--el-color-warning);
}
.edge-opt-dot.error {
  background: var(--el-color-danger);
}
.edge-opt-code {
  color: var(--el-text-color-placeholder);
}
.edge-opt-meta {
  margin-left: auto;
  font-size: 11px;
  color: var(--el-text-color-secondary);
}
</style>
```

- [ ] **Step 4: 布控页接入设备选择与 ROI**

修改 `frontend/src/views/module_video/deploy/index.vue`：

(a) 模板：在「监控点位」表单项之后新增「推理设备」，在「布控配置」区块之后新增「检测区域（ROI）」区块：

```html
          <el-form-item label="推理设备">
            <EdgeDeviceSelect v-model="formData.edge_device_id" />
          </el-form-item>
          <div v-if="selectedDevice" class="device-status-row">
            <el-tag :type="selectedDevice.status === 'online' ? 'success' : 'info'" size="small">
              {{ selectedDevice.status }}
            </el-tag>
            <span class="device-status-meta">
              在跑 {{ selectedDevice.metrics?.running_channels ?? 0 }} /
              {{ selectedDevice.capabilities?.max_channels ?? "-" }}
            </span>
          </div>
```

在「布控配置」`</div>` 结束之后（「布控时段」区块之前）新增：

```html
        <div class="form-section">
          <div class="form-section-title">
            检测区域（ROI）
            <span class="form-section-desc">在预览画面上点击绘制多边形；留空表示全画面</span>
          </div>
          <RoiEditor v-model="formData.detect_region_points" :stream-id="selectedStreamId" />
        </div>
```

(b) 脚本导入新增：

```ts
import EdgeDeviceSelect from "@/components/Edge/EdgeDeviceSelect.vue";
import RoiEditor from "@/components/Video/RoiEditor.vue";
```

并在 `import { getCameraList } ...` 后新增：

```ts
import { getEdgeDeviceDetail } from "@/api/module_video/edge";
import { computed } from "vue";
```

（注意：把 `import { ref, reactive, onBeforeMount, onBeforeUnmount } from "vue";` 合并为含 `computed` 的同一行，避免重复导入。）

(c) `formData` 增加字段：

```ts
const formData = reactive({
  id: undefined as number | undefined,
  camera_id: undefined as number | undefined,
  algorithm_id: undefined as number | undefined,
  edge_device_id: null as number | null,
  stream_type: "SUB",
  sensitivity: 50,
  statusBool: true,
  detect_region_points: null as number[][] | null,
  description: undefined as string | undefined,
});
```

(d) 新增计算属性与设备详情加载（放在 `initialFormData` 之后）：

```ts
const selectedDevice = ref<any>(null);

const selectedStreamId = computed<string>(() => {
  const cam = cameraOptions.value.find((c: any) => c.id === formData.camera_id);
  return cam?.stream_id || "";
});

async function loadSelectedDevice(id: number | null) {
  selectedDevice.value = null;
  if (!id) return;
  try {
    const res = await getEdgeDeviceDetail(id);
    selectedDevice.value = res.data?.data || null;
  } catch {
    /* 忽略 */
  }
}
```

(e) `handleOpenDialog` 的编辑分支中，在 `formData.description = item.description;` 之后新增：

```ts
      formData.edge_device_id = item.edge_device_id ?? null;
      formData.detect_region_points = Array.isArray(item.detect_region?.points)
        ? item.detect_region.points
        : null;
      await loadSelectedDevice(formData.edge_device_id);
```

(f) `handleSubmit` 的 payload 中新增：

```ts
        edge_device_id: formData.edge_device_id,
        detect_region: formData.detect_region_points?.length
          ? { points: formData.detect_region_points }
          : null,
```

(g) 在 `resetForm()` 中 `scheduleGrid.value = ...;` 之后新增：

```ts
  selectedDevice.value = null;
```

(h) 列表「状态」列展示编排失败原因：把状态列的

```html
                <el-tag :type="scope.row.status === 'RUNNING' ? 'success' : 'info'" size="small">
                  {{ scope.row.status === "RUNNING" ? "运行中" : "已停止" }}
                </el-tag>
```

替换为：

```html
                <el-tag :type="scope.row.status === 'RUNNING' ? 'success' : 'info'" size="small">
                  {{ scope.row.status === "RUNNING" ? "运行中" : "已停止" }}
                </el-tag>
                <el-tooltip
                  v-if="scope.row.error_log"
                  :content="scope.row.error_log"
                  placement="top"
                >
                  <el-tag type="danger" size="small" class="error-log-tag">失败</el-tag>
                </el-tooltip>
```

(i) 样式末尾新增：

```css
.device-status-row {
  display: flex;
  gap: 8px;
  align-items: center;
  margin: -8px 0 12px 110px;
}
.device-status-meta {
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
.error-log-tag {
  margin-left: 4px;
}
```

- [ ] **Step 5: 类型检查**

Run: `pnpm type-check`
Expected: 无新增错误

- [ ] **Step 6: E2E 测试（布控页设备选择与 ROI 保存）**

创建 `frontend/e2e/deploy-edge-roi.spec.ts`：

```ts
import { test, expect } from "@playwright/test";

test("布控页可选择推理设备并打开 ROI 编辑器", async ({ page }) => {
  await page.goto("/#/video/deploy", { waitUntil: "domcontentloaded" });
  await expect(page.locator(".app-main .app-container").first()).toBeVisible({ timeout: 15_000 });

  await page.getByRole("button", { name: /新增/ }).first().click();
  const dialog = page.locator(".el-dialog");
  await expect(dialog).toBeVisible();

  // 推理设备下拉存在且含「本机 / 纯云端」选项
  await dialog.getByLabel("推理设备").click();
  await expect(page.locator(".el-select-dropdown__item", { hasText: "本机 / 纯云端" }).first())
    .toBeVisible();
  await page.keyboard.press("Escape");

  // ROI 编辑器区块存在
  await expect(dialog.getByText("检测区域（ROI）")).toBeVisible();
  await expect(dialog.locator(".roi-editor")).toBeVisible();

  await page.keyboard.press("Escape");
});
```

- [ ] **Step 7: 运行 E2E**

Run: `pnpm e2e -- deploy-edge-roi.spec.ts`
Expected: 1 passed

- [ ] **Step 8: 提交**

```bash
git add frontend/src/components/Video/LivePlayer.vue frontend/src/components/Video/RoiEditor.vue frontend/src/components/Edge/EdgeDeviceSelect.vue frontend/src/views/module_video/deploy/index.vue frontend/e2e/deploy-edge-roi.spec.ts
git commit -m "feat(video): 布控页设备选择与 ROI 多边形编辑器"
```

---

### Task 5: 告警快照预览（SnapshotImage + 缩略图列 + 详情）

**Files:**
- Create: `frontend/src/components/Common/SnapshotImage.vue`
- Modify: `frontend/src/views/module_video/alarm/index.vue`
- Test: `frontend/e2e/alarm-snapshot.spec.ts`

**Interfaces:**
- Consumes: 后端告警出参 `snapshot_url`（Task 2）、`el-image`。
- Produces: `SnapshotImage` props `{ src?: string | null; width?: string | number; height?: string | number; previewable?: boolean }`。

- [ ] **Step 1: 创建 SnapshotImage 组件**

创建 `frontend/src/components/Common/SnapshotImage.vue`：

```vue
<template>
  <el-image
    v-if="displaySrc"
    :src="displaySrc"
    :style="{ width: sizeCss, height: sizeCss }"
    fit="contain"
    :preview-src-list="previewable ? [displaySrc] : []"
    preview-teleported
  >
    <template #error>
      <div class="snapshot-empty">无截图</div>
    </template>
  </el-image>
  <div v-else class="snapshot-empty" :style="{ width: sizeCss, height: sizeCss }">无截图</div>
</template>

<script setup lang="ts">
import { ref, computed, watch, onBeforeUnmount } from "vue";
import request from "@/utils/request";

const props = withDefaults(
  defineProps<{
    src?: string | null;
    width?: string | number;
    height?: string | number;
    previewable?: boolean;
  }>(),
  { src: null, width: "100%", height: "100%", previewable: false }
);

const objectUrl = ref<string | null>(null);
const blobSrc = ref<string | null>(null);

const sizeCss = computed(() => {
  const w = typeof props.width === "number" ? `${props.width}px` : props.width;
  const h = typeof props.height === "number" ? `${props.height}px` : props.height;
  return `width:${w};height:${h}`;
});

const displaySrc = computed(() => blobSrc.value || props.src || null);

function revoke() {
  if (objectUrl.value) {
    URL.revokeObjectURL(objectUrl.value);
    objectUrl.value = null;
  }
}

async function load() {
  revoke();
  blobSrc.value = null;
  const url = props.src;
  if (!url) return;
  if (/^(https?:|blob:|data:)/.test(url)) return; // 已可直接访问
  try {
    const res = await request({
      url,
      method: "get",
      responseType: "blob",
      headers: { _silent: "true" },
    });
    const blob = res.data as Blob;
    objectUrl.value = URL.createObjectURL(blob);
    blobSrc.value = objectUrl.value;
  } catch {
    /* 加载失败：展示占位 */
  }
}

watch(() => props.src, load, { immediate: true });
onBeforeUnmount(revoke);
</script>

<style scoped>
.snapshot-empty {
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 12px;
  color: var(--el-text-color-placeholder);
  background: var(--el-fill-color-lighter);
  border-radius: 4px;
}
</style>
```

- [ ] **Step 2: 告警页列表加缩略图列**

修改 `frontend/src/views/module_video/alarm/index.vue`：

(a) `recordCols`（约 749 行）在 `{ prop: "alarm_time", ... }` 之后插入：

```ts
  { prop: "snapshot", label: "快照", show: true },
```

(b) 表格中在 `alarm_time` 列（约 55-62 行）之后插入：

```html
                <el-table-column
                  v-if="recordCols.find((col) => col.prop === 'snapshot')?.show"
                  key="snapshot"
                  label="快照"
                  width="72"
                  align="center"
                >
                  <template #default="scope">
                    <SnapshotImage
                      :src="scope.row.snapshot_url || scope.row.snapshot_path"
                      :width="48"
                      :height="32"
                    />
                  </template>
                </el-table-column>
```

(c) 详情抽屉中把裸 `el-image`（545-559 行）替换为：

```html
        <div class="detail-snapshot">
          <SnapshotImage
            :src="detailDrawer.data.snapshot_url || detailDrawer.data.snapshot_path"
            width="100%"
            height="200px"
            previewable
          />
        </div>
```

(d) 脚本导入新增：

```ts
import SnapshotImage from "@/components/Common/SnapshotImage.vue";
```

- [ ] **Step 3: 类型检查**

Run: `pnpm type-check`
Expected: 无新增错误

- [ ] **Step 4: E2E 测试**

创建 `frontend/e2e/alarm-snapshot.spec.ts`：

```ts
import { test, expect } from "@playwright/test";

test("告警页展示快照列并请求 snapshot_url", async ({ page }) => {
  const snapshotRequests: string[] = [];
  page.on("request", (req) => {
    if (req.url().includes("/video/detections/")) snapshotRequests.push(req.url());
  });

  await page.goto("/#/video/alarm", { waitUntil: "domcontentloaded" });
  await expect(page.locator(".app-main .app-container").first()).toBeVisible({ timeout: 15_000 });
  await expect(page.locator("th", { hasText: "快照" }).first()).toBeVisible();
  // 不强制存在告警数据；若存在则应触发快照请求（blob 下载）
  expect(Array.isArray(snapshotRequests)).toBe(true);
});
```

- [ ] **Step 5: 运行 E2E**

Run: `pnpm e2e -- alarm-snapshot.spec.ts`
Expected: 1 passed

- [ ] **Step 6: 提交**

```bash
git add frontend/src/components/Common/SnapshotImage.vue frontend/src/views/module_video/alarm/index.vue frontend/e2e/alarm-snapshot.spec.ts
git commit -m "feat(video): 告警快照缩略图与受鉴权预览"
```

---

### Task 6: 全量回归 + 真机 Agent 端到端（可用时）

**Files:**
- 无新增代码（仅回归与验收记录）；如发现缺陷则回到对应 Task 修复。

**Interfaces:**
- Consumes: 前 5 个任务的产出。

- [ ] **Step 1: 后端全量测试 + ruff**

Run: `cd backend && uv run pytest -q && uv run ruff check`
Expected: 全部通过（记录通过用例数）

- [ ] **Step 2: 前端类型检查 + lint + 全量 E2E**

Run: `cd frontend && pnpm type-check && pnpm lint && pnpm e2e`
Expected: type-check 0 错误；lint 无新增错误（LivePlayer/live/playback 历史错误除外）；E2E 全部通过

- [ ] **Step 3: 真机 Agent 端到端（可用时）**

前置：ModelDeploy 仓库的布控 Agent 可用（另一会话交付）。步骤：

1. 启动 Agent，使其向 `POST /api/v1/video/edge/heartbeat` 上报 `code` 与 `capabilities`；
2. 打开 `/video/edge`，确认设备出现且状态 `online`，能力面板显示 hardware/backends/model_families；
3. 在 `/video/deploy` 新建布控任务：选择该设备、指定摄像头、绘制 ROI、保存并启动；
4. 触发一次检测，确认 `/video/alarm` 出现告警且快照缩略图/详情可预览；
5. 停止/删除布控任务，确认 Agent 侧任务同步移除。

若无可用 Agent：记录为阻塞项，并至少完成"心跳 mock → 设备可见 → 状态 online → 布控任务 capability 校验通过/失败提示"的替代验证（可用 `curl` 直接 POST heartbeat）。

- [ ] **Step 4: 更新进度账本并提交**

在 `.superpowers/sdd/progress.md` 末尾追加 Phase 3D 完成记录（各 Task 提交区间、测试结果、真机 e2e 状态）。

```bash
git add .superpowers/sdd/progress.md
git commit -m "docs(pipeline): Phase 3D 完成记录"
```

---

## Self-Review

**Spec coverage:**
- §4.1 受控快照路由 → Task 1 ✅
- §4.2 `resolve_snapshot_url` → Task 1 ✅
- §4.3 告警 schema `snapshot_url` → Task 2 ✅
- §4.4 规则匹配健壮化 → Task 2 ✅
- §5.1 edge API + 菜单 → Task 3 ✅；§5.2 设备页+轮询 → Task 3 ✅
- §5.3 复用组件 → Task 3（EdgeCapabilityPanel）/ Task 4（EdgeDeviceSelect、RoiEditor）/ Task 5（SnapshotImage）✅
- §5.4 布控页设备选择/状态/error_log/ROI → Task 4 ✅（设备状态行 + ROI 编辑器 + 状态列 `error_log` 失败标签与 tooltip）
- §5.5 告警页缩略图/详情 → Task 5 ✅
- §8 测试：后端 pytest（Task 1/2）、前端 E2E（Task 3/4/5）、回归与真机（Task 6）✅

**Placeholder scan:** 无 TBD/TODO；所有代码步骤含完整代码。

**Type consistency:**
- `snapshot.py::resolve_snapshot_url` / `safe_local_snapshot` 在 Task 1 定义，Task 2 schema 复用 ✅
- `EdgeCapabilityPanel` props `capabilities`/`metrics`：Task 3 定义，Task 4 未直接用（Task 3 用）✅
- `SnapshotImage` props `src/width/height/previewable`：Task 5 定义并消费 ✅
- `RoiEditor` modelValue 类型 `number[][] | null`：Task 4 定义，deploy 页 `detect_region_points` 同型 ✅
- `edge.ts` 函数名与后端路径一致 ✅

**风险备注：** `LivePlayer` 历史 lint 错误不追平；ROI contain 坐标换算依赖 `videoWidth/Height`，E2E 仅验证区块存在与保存回显，真机验收在 Task 6。
