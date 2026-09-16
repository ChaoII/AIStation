# SP5-c 告警快照叠加查看器实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 提供一个可复用的快照叠加查看器（底图 + 归一化 bbox/label/置信度/属性/track_id + 缩放平移），在告警详情与事件流详情共用；后端为告警补存 v2 `objects`。

**Architecture:** 后端只在 `ai_result` 增量补 `objects`；前端新增 `SnapshotOverlayViewer`（`vue-konva`，复用 SP5-a 已引入依赖），受保护快照经 `request` 鉴权取 blob 后绘制。

**Tech Stack:** FastAPI + Pydantic v2；Vue 3 + Element Plus + TypeScript + `vue-konva`/`konva` + Playwright。

**Spec:** `docs/superpowers/specs/2026-09-15-sp5c-snapshot-overlay-design.md`

## Global Constraints

- 代码注释与提交信息一律**中文**；格式 `feat(video): …` / `feat(ui): …` / `test(ui): …`。
- 只 `git add` 本任务列出文件；**禁止 `git add -A`**。
- 后端：`cd backend && uv run pytest -q` + `uv run ruff check` 全绿；**禁止新增后端依赖**。
- 前端：`pnpm run type-check` 0 新增错误；**禁止新增依赖**（必须复用 `vue-konva`/`konva`）。
- 不使用 `el-image` 直接消费受保护快照 URL（`<img>` 无法带自定义头）。
- 组件必须**单根元素**（AGENTS.md：多根 + `<Transition>` 白屏）。
- `ai_result` 只增字段，不改既有字段语义。

---

### Task 1: 后端告警补存 v2 `objects`

**Files:**
- Modify: `backend/app/api/v1/module_video/inference/service.py`
- Test: `backend/tests/test_alarm_ai_result_objects.py`

**Interfaces:**
- Produces: `ai_result.objects: list[dict]`（`{label,label_id,confidence,bbox,track_id?,attributes?,text?,text_score?}`）；无 `objects` 时由 `detections` 派生。

- [ ] **Step 1: 写失败测试**

创建 `backend/tests/test_alarm_ai_result_objects.py`，复用 `tests/test_temporal_leaves_e2e.py` 的假 DB/monkeypatch 手法（`_patch_runtime`、`_FakeRule`、`_Factory`）：

```python
"""告警 ai_result 补存 v2 objects 测试。"""
import asyncio

from app.api.v1.module_video.inference import service
from app.api.v1.module_video.inference.temporal import TemporalStore

CAM, ALGO = 9, "DET_ZONE"


def _ev(objects=None, detections=None, ts=1000):
    return {
        "task_id": 1, "camera_id": CAM, "algorithm_type": ALGO,
        "objects": objects if objects is not None else [],
        "detections": detections if detections is not None else [],
        "frame_timestamp": ts,
    }


def test_objects_persisted_verbatim(monkeypatch):
    """事件带 objects 时原样落库（含 attributes/track_id）。"""
    captured = {}

    class _Rule:
        id = 1
        name = "r"
        severity = "WARNING"
        notify_channels = []
        alarm_type = ALGO
        interval_seconds = 0
        conditions = None

    # 直接劫持 AlarmRecordModel 构造，捕获 ai_result
    import app.api.v1.module_video.alarm.model as alarm_model

    real_init = alarm_model.AlarmRecordModel.__init__

    def _init(self, **kw):
        captured.update(kw)
        real_init(self, **kw)

    monkeypatch.setattr(alarm_model.AlarmRecordModel, "__init__", _init)
    # _patch_runtime 复用既有 helper（假 DB + 内存 store + 短路联动/通知）
    from tests.test_temporal_leaves_e2e import _patch_runtime

    _patch_runtime(monkeypatch, _Rule(), TemporalStore(prefer_redis=False))
    obj = {"label": "person", "confidence": 0.9, "bbox": {"x": 0.1, "y": 0.1, "width": 0.2, "height": 0.2},
           "track_id": 3, "attributes": {"work_uniform": 0.2}}
    asyncio.run(service.InferenceService.process_detection_callback(_ev(objects=[obj], detections=[dict(obj)])))
    assert captured["ai_result"]["objects"] == [obj]
    assert captured["ai_result"]["detections"], "detections 兼容字段必须保留"


def test_objects_derived_from_detections_when_missing(monkeypatch):
    """HTTP 兼容路径无 objects 时由 detections 派生。"""
    captured = {}
    import app.api.v1.module_video.alarm.model as alarm_model
    real_init = alarm_model.AlarmRecordModel.__init__

    def _init(self, **kw):
        captured.update(kw); real_init(self, **kw)

    monkeypatch.setattr(alarm_model.AlarmRecordModel, "__init__", _init)
    from tests.test_temporal_leaves_e2e import _FakeRule, _patch_runtime

    _patch_runtime(monkeypatch, _FakeRule(None), TemporalStore(prefer_redis=False))
    det = {"label": "car", "confidence": 0.8, "bbox": {"x": 0.4, "y": 0.4, "width": 0.1, "height": 0.1}}
    asyncio.run(service.InferenceService.process_detection_callback(_ev(objects=[], detections=[det])))
    objs = captured["ai_result"]["objects"]
    assert len(objs) == 1 and objs[0]["label"] == "car"
```

- [ ] **Step 2: 运行确认失败** → `cd backend && uv run pytest tests/test_alarm_ai_result_objects.py -q`（KeyError/AssertionError）

- [ ] **Step 3: 实现**

在 `process_detection_callback` 中，构造 `alarm_data` 之前：

```python
        # v2 objects：优先取事件携带的；HTTP 兼容路径缺失时由 detections 派生
        raw_objects = event.get("objects")
        objects = [o for o in raw_objects if isinstance(o, dict)] if isinstance(raw_objects, list) else []
        if not objects and detections:
            objects = [
                {
                    "label": d.get("label", ""),
                    "label_id": d.get("label_id", 0),
                    "confidence": d.get("confidence", 0.0),
                    "bbox": d.get("bbox") or {},
                    **({"track_id": d["track_id"]} if d.get("track_id") is not None else {}),
                    **({"attributes": d["attributes"]} if isinstance(d.get("attributes"), dict) else {}),
                    **({"text": d["text"]} if d.get("text") is not None else {}),
                }
                for d in detections
                if isinstance(d, dict)
            ]
```

并把 `"objects": objects` 写入 `alarm_data["ai_result"]`。

- [ ] **Step 4: 运行测试** → 通过
- [ ] **Step 5: 全量回归 + ruff** → `uv run pytest -q`（全绿）、`uv run ruff check`
- [ ] **Step 6: 提交**

```bash
git add backend/app/api/v1/module_video/inference/service.py backend/tests/test_alarm_ai_result_objects.py
git commit -m "feat(video): 告警 ai_result 补存 v2 objects"
```

---

### Task 2: `SnapshotOverlayViewer` 组件

**Files:**
- Create: `frontend/src/components/SnapshotOverlayViewer/index.vue`

**Interfaces:**
- props：`src: string | null`、`objects: Array<Object>`、`labelColors?: Record<string,string>`、`height?: string`
- 暴露：`data-testid="snapshot-overlay"`、`data-box-count="<n>"`、`data-image-loaded="true|false"`（供 e2e 断言）

- [ ] **Step 1: 实现组件**

要求（细节见 spec §3.2）：
- `vue-konva`：`v-stage`/`v-layer`/`v-image`/`v-rect`/`v-text`；复用 `frontend/src/views/module_video/alarm/components/RoiCanvas.vue` 的 letterbox 换算与 `ResizeObserver` 外层容器观测写法（**不要**观测被 Konva 撑大的元素）。
- 底图加载：`import request from "@/utils/request"` → `request({url, method:"get", responseType:"blob"})` → `URL.createObjectURL` → `new Image()`；`onBeforeUnmount` 时 `revokeObjectURL`；失败 → 占位 + 错误文案（`data-image-loaded="false"`）。
- 叠加：归一化 bbox → 画布坐标（`x*W`,`y*H`），边框色按 `labelColors[label] ?? hashColor(label)`；标签文字 `"{label} {conf:.2f}"`；`attributes` 逐项 `k=v` 小字；`track_id` 徽标 `#id`；`fontSize` 用画布单位。
- 交互：滚轮缩放（以指针为锚）、拖拽平移、`重置`、悬停高亮（描边加粗 + 半透明填充）、`下载`（原图 / 含叠加 PNG 用 `stage.toDataURL()`）。
- 性能：`objects.length > 200` 时只画框与标签，不画属性小字。
- **单根元素**；样式用 scoped + `--el-*` 变量。

- [ ] **Step 2: 校验** → `cd frontend && pnpm run type-check`（0 新增）；仅该文件 lint 干净
- [ ] **Step 3: 提交**

```bash
git add frontend/src/components/SnapshotOverlayViewer/index.vue
git commit -m "feat(ui): 快照叠加查看器组件（vue-konva 叠加层 + 缩放/下载）"
```

---

### Task 3: 集成告警详情抽屉

**Files:**
- Modify: `frontend/src/views/module_video/alarm/index.vue`

- [ ] **Step 1: 替换详情快照区**

把详情抽屉内的 `el-image`（`detailDrawer.data.snapshot_url || snapshot_path`）替换为：

```vue
<SnapshotOverlayViewer
  :src="detailDrawer.data.snapshot_url || detailDrawer.data.snapshot_path"
  :objects="detailDrawer.data.ai_result?.objects ?? detailDrawer.data.ai_result?.detections ?? []"
  height="420px"
/>
```

- 表格缩略图**保持** `el-image`（列表性能）。
- 保证页面仍为**单根元素**（AGENTS.md）。

- [ ] **Step 2: 校验** → `pnpm run type-check`
- [ ] **Step 3: 提交**

```bash
git add frontend/src/views/module_video/alarm/index.vue
git commit -m "feat(ui): 告警详情抽屉接入快照叠加查看器"
```

---

### Task 4: 集成事件流详情抽屉

**Files:**
- Modify: `frontend/src/views/module_video/event_stream/index.vue`

- [ ] **Step 1: 抽屉内增加查看器**

```vue
<SnapshotOverlayViewer
  :src="activeEvent?.snapshot_ref || null"
  :objects="activeEvent?.objects ?? activeEvent?.detections ?? []"
  height="360px"
/>
```

- `snapshot_ref` 为 http(s) 时直接使用；否则传受保护相对路径（组件内部经 `request` 鉴权取图）。
- 保留既有检测列表与命中叶子标签。

- [ ] **Step 2: 校验** → `pnpm run type-check`
- [ ] **Step 3: 提交**

```bash
git add frontend/src/views/module_video/event_stream/index.vue
git commit -m "feat(ui): 事件流详情抽屉接入快照叠加查看器"
```

---

### Task 5: e2e + 视觉核对

**Files:**
- Create: `frontend/e2e/sp5c-snapshot-overlay.spec.ts`
- Create: `docs/superpowers/runbooks/sp5c-visual.md` + 截图目录

- [ ] **Step 1-3**：读既有 e2e helper（参考 `sp5a-rule-editor.spec.ts` / `sp5b-event-stream.spec.ts`）→ 写 spec：登录 → 事件页 → 打开详情 → 断言 `[data-testid="snapshot-overlay"]` 存在且 `data-image-loaded="true"`、`data-box-count` 等于 `objects` 数量 → `pnpm run e2e -- sp5c-snapshot-overlay` 通过。
  - 若真实快照缺失导致 `data-image-loaded="false"`，则同时断言该属性并说明（不伪造图片）；优先用具快照的真实事件。
- [ ] **Step 4**：截图（抽屉打开、叠加可见）+ `vision-recognition` 核对。
- [ ] **Step 5: 提交**

```bash
git add frontend/e2e/sp5c-snapshot-overlay.spec.ts docs/superpowers/runbooks/sp5c-visual.md docs/superpowers/runbooks/sp5c-visual
git commit -m "test(ui): 快照叠加查看器 e2e 与视觉核对"
```

---

### Task 6: 真机核对

- [ ] **Step 1**：用已有真实告警（含快照）在告警页打开详情，确认底图 + 框 + 属性渲染、缩放/平移下叠加与底图同步、下载可用。
- [ ] **Step 2**：结论写入 `.superpowers/sdd/sp5c-task-6-report.md`（含截图）。

---

### Task 7: 总回归

- [ ] **Step 1**：`cd backend && uv run pytest -q`（全绿）+ `uv run ruff check`（确认无本切片新增）。
- [ ] **Step 2**：`cd frontend && pnpm run type-check && pnpm run lint && pnpm run e2e`（SP5-c 用例通过；若全量有环境性抖动，隔离复跑确认）。
- [ ] **Step 3**：报告写入 `.superpowers/sdd/sp5c-task-7-report.md`。

---

## Self-Review

**Spec 覆盖：**

| Spec 条目 | 落点 |
|-----------|------|
| §3.1 告警补存 `objects`（含派生回退） | Task 1 |
| §3.2 组件接口/渲染/交互/取图鉴权 | Task 2 |
| §3.3 两处集成（告警 + 事件流） | Task 3 / Task 4 |
| §3.4 视觉约束与截图核对 | Task 5 + Task 6 |
| §4 验收（单测/type-check/e2e/截图/真机） | Task 1 / 2-5 / 6；Task 7 总回归 |
| §5 风险（canvas 断言、鉴权取图、老记录回退、性能、letterbox） | Task 2（`data-*` 供断言 + letterbox 复用 + >200 降级）、Task 3（`?? detections` 回退）、Task 5（截图核对） |
| §6 兼容性（只增字段、不新增依赖/表） | Task 1 / Task 2 |

**类型一致性：** `ai_result.objects`（Task 1）与查看器 `objects` prop（Task 2）字段一致（`label/confidence/bbox/track_id/attributes/text`）；两处集成（Task 3/4）均用 `objects ?? detections` 回退，命名一致；`data-testid`/`data-box-count`/`data-image-loaded`（Task 2 定义）与 Task 5 断言一致。

**占位符扫描：** Task 1 含完整代码与预期输出；Task 2 给出明确行为契约与复用来源（RoiCanvas 的 letterbox/观测写法）；Task 3-7 为集成与验证，含具体代码片段与命令。
