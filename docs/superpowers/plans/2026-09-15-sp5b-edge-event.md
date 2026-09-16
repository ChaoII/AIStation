# SP5-b 边缘事件落库与实时可视化实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 落库边缘事件（只落有检测的事件）并记录命中叶子，提供分页/详情查询与 WebSocket 实时推送，前端提供实时流 + 详情抽屉 + 命中高亮。

**Architecture:** 在 `process_detection_callback` 内落库（MQTT/HTTP 两路共用）；命中叶子由新增的 `explain_conditions` 产出（与 `_match_conditions` 同语义、对拍保证）；实时推送走 Redis pub/sub → WS 端点转发。

**Tech Stack:** FastAPI + SQLAlchemy 2.0 + Alembic + Redis；Vue 3 + Element Plus + TypeScript + Playwright。

**Spec:** `docs/superpowers/specs/2026-09-15-sp5b-edge-event-design.md`

## Global Constraints

- 代码注释与提交信息一律**中文**；格式 `feat(video): …` / `feat(ui): …` / `test(video): …`。
- 只 `git add` 本任务列出文件；**禁止 `git add -A`**。
- 后端：`cd backend && uv run pytest -q` + `uv run ruff check` 全绿；**禁止新增后端依赖**（Redis 客户端已在用）。
- 前端：`pnpm run type-check` 0 新增错误；编辑器类 UI 用第三方组件（本切片无新编辑器）。
- `_match_conditions` 对外签名与语义**不得改变**（对拍测试锁定）。
- 落库失败不得阻断告警链路（仅告警日志）。

---

### Task 1: `explain_conditions` 命中叶子（纯函数，无外部依赖）

**Files:**
- Modify: `backend/app/api/v1/module_video/inference/service.py`
- Test: `backend/tests/test_explain_conditions.py`

**Interfaces:**
- Produces: `explain_conditions(conditions, detections, *, temporal=None, camera_id=None, alarm_type=None, now=None, alarm_interval=0) -> tuple[bool, list[dict]]`
  - `hits[i] = {"path": "and/0", "subject": "object_present", "detail": "person>=0.4", "negated": False}`
- `_match_conditions(...)` 内部改为 `explain_conditions(...)[0]`，签名/返回不变。

- [ ] **Step 1: 写失败测试**

创建 `backend/tests/test_explain_conditions.py`：

```python
"""命中叶子解释测试：与 _match_conditions 判定必须逐例一致（对拍）。"""
from app.api.v1.module_video.inference.service import _match_conditions, explain_conditions
from app.api.v1.module_video.inference.temporal import TemporalStore

CAM, ALGO = 1, "DET_ZONE"


def _det(label="person", conf=0.9, cx=0.5, cy=0.5, w=0.2, h=0.2, track_id=None, attrs=None, text=None):
    d = {"label": label, "confidence": conf,
         "bbox": {"x": cx - w / 2, "y": cy - h / 2, "width": w, "height": h}}
    if track_id is not None:
        d["track_id"] = track_id
    if attrs:
        d["attributes"] = attrs
    if text is not None:
        d["text"] = text
    return d


ROI = [[0.2, 0.2], [0.8, 0.2], [0.8, 0.8], [0.2, 0.8]]


def _explain(cond, dets, **kw):
    return explain_conditions(cond, dets, temporal=kw.pop("temporal", TemporalStore(prefer_redis=False)),
                              camera_id=CAM, alarm_type=ALGO, now=kw.pop("now", 1000), **kw)


def test_and_hits_paths():
    cond = {"op": "and", "children": [
        {"subject": "object_present", "label": "person"},
        {"subject": "count", "op": ">=", "value": 1},
    ]}
    ok, hits = _explain(cond, [_det()])
    assert ok is True
    assert [h["path"] for h in hits] == ["and/0", "and/1"]
    assert hits[0]["subject"] == "object_present"


def test_or_reports_only_matched_branch():
    cond = {"op": "or", "children": [
        {"subject": "object_present", "label": "car"},
        {"subject": "object_present", "label": "person"},
    ]}
    ok, hits = _explain(cond, [_det(label="person")])
    assert ok is True
    assert [h["path"] for h in hits] == ["or/1"]


def test_not_marks_negated():
    cond = {"op": "not", "children": [{"subject": "object_present", "label": "car"}]}
    ok, hits = _explain(cond, [_det(label="person")])
    assert ok is True
    assert hits and hits[0]["negated"] is True


def test_no_hits_when_unmatched():
    cond = {"op": "and", "children": [{"subject": "object_present", "label": "car"}]}
    ok, hits = _explain(cond, [_det(label="person")])
    assert ok is False and hits == []


def test_temporal_leaf_detail():
    store = TemporalStore(prefer_redis=False)
    store.observe(CAM, ALGO, [_det(track_id=1)], 1000)
    store.observe(CAM, ALGO, [_det(track_id=1)], 1006)
    cond = {"op": "and", "children": [{"subject": "dwell", "label": "person", "min_sec": 5}]}
    ok, hits = _explain(cond, [], temporal=store, now=1006)
    assert ok is True
    assert "dwell" in hits[0]["detail"]


def test_matches_match_conditions_everywhere():
    """对拍：任何条件下两者判定必须一致。"""
    store = TemporalStore(prefer_redis=False)
    store.observe(CAM, ALGO, [_det(track_id=1)], 1000)
    cases = [
        ({"op": "and", "children": [{"subject": "object_present", "label": "person"}]}, [_det()]),
        ({"op": "or", "children": [{"subject": "count", "op": ">=", "value": 5}]}, [_det()]),
        ({"op": "not", "children": [{"subject": "object_present", "label": "car"}]}, [_det()]),
        ({"subject": "attribute", "field": "work_uniform", "op": "lt", "value": 0.5}, [_det(attrs={"work_uniform": 0.2})]),
        ({"subject": "text_match", "regex": "京"}, [_det(text="京A12345")]),
        ({"subject": "dwell", "label": "person", "min_sec": 5}, []),
        ({"subject": "object_present", "label": "person", "region": ROI}, [_det()]),
        ({}, [_det()]),
    ]
    for cond, dets in cases:
        a = _match_conditions(cond, dets, temporal=store, camera_id=CAM, alarm_type=ALGO, now=1006, alarm_interval=0)
        b = explain_conditions(cond, dets, temporal=store, camera_id=CAM, alarm_type=ALGO, now=1006, alarm_interval=0)[0]
        assert a == b, cond
```

- [ ] **Step 2: 运行确认失败**

Run: `cd backend && uv run pytest tests/test_explain_conditions.py -q` → FAIL（`explain_conditions` 不存在）

- [ ] **Step 3: 重构求值器**

在 `service.py` 中把 `_match_conditions` 的内部实现改为「返回 `(bool, hits)`」，并新增薄封装：

```python
def _eval_tree(conditions, dets, *, temporal, camera_id, alarm_type, now, alarm_interval):
    """返回 (是否命中, 命中叶子列表)；hit = {"path","subject","detail","negated"}。"""
    # 将原 eval_leaf/eval_node 提升为模块级内部函数 _eval_leaf(...) / 保留嵌套闭包，
    # 关键改动：eval_node 返回 (bool, hits)，逻辑节点聚合子节点 hits；
    # not 节点：命中时把 children 的 hits 标记 negated=True 返回。
    ...
```

`detail` 生成规则（简洁、可读、中文）：
- `object_present/zone_enter`：`f"{label or '*'} conf={conf:.2f}"`
- `count`：`f"{count}{op}{value}"`
- `attribute`：`f"{field}={score:.2f}{op}{value}"`
- `text_match`/`ocr_label`：`f"text~{pattern}"` / `f"text⊃{needle}"`
- `dwell`：`f"dwell {elapsed:.0f}s>={min_sec}s"`；`count_window`：`f"window {n}{op}{value}"`
- `absence`：`f"absence {silent:.0f}s>={gap}s"`；`line_cross`：`f"cross {prev}->{cur} dir={dir}"`

然后：

```python
def _match_conditions(conditions, detections, *, temporal=None, camera_id=None,
                      alarm_type=None, now=None, alarm_interval=0) -> bool:
    """评估规则条件树（行为与返回类型不变；命中细节见 explain_conditions）。"""
    return explain_conditions(
        conditions, detections, temporal=temporal, camera_id=camera_id,
        alarm_type=alarm_type, now=now, alarm_interval=alarm_interval,
    )[0]


def explain_conditions(conditions, detections, *, temporal=None, camera_id=None,
                       alarm_type=None, now=None, alarm_interval=0):
    """评估并返回 (bool, hits)；空/None 条件视为命中且 hits=[]。"""
```

- [ ] **Step 4: 运行测试**

Run: `cd backend && uv run pytest tests/test_explain_conditions.py tests/test_temporal_leaves.py tests/test_line_cross.py tests/test_alarm_rule_match.py -q` → 全通过

- [ ] **Step 5: 全量回归**

Run: `cd backend && uv run pytest -q` → 全通过（既有判定不变）

- [ ] **Step 6: 提交**

```bash
git add backend/app/api/v1/module_video/inference/service.py backend/tests/test_explain_conditions.py
git commit -m "feat(video): 规则求值支持命中叶子解释并保持判定语义"
```

---

### Task 2: 事件表 + 落库服务

**Files:**
- Create: `backend/app/api/v1/module_video/edge/model.py`（或并入该模块既有 model 文件）
- Modify: `backend/app/api/v1/module_video/inference/service.py`（落库调用）
- Create: Alembic 迁移（CLI 生成）
- Test: `backend/tests/test_edge_event_store.py`

**Interfaces:**
- Consumes: `explain_conditions`（Task 1）。
- Produces:
  - `EdgeEventModel`（表 `video_edge_events`）
  - `async def record_edge_event(event: dict, *, matched: bool, rule_id: int | None, matched_leaves: list) -> int | None`
  - `process_detection_callback` 返回体新增 `event_id`

- [ ] **Step 1: 写失败测试**

创建 `backend/tests/test_edge_event_store.py`（复用 `test_temporal_leaves_e2e.py` 的假 DB/monkeypatch 手法，但落库断言用真实测试库）：

```python
"""边缘事件落库测试：筛选/幂等/命中叶子。"""
import asyncio

import pytest

from app.api.v1.module_video.inference import service

EV = {
    "event_id": "ev-1", "edge_code": "edge-01", "camera_id": 1, "task_id": 2,
    "algorithm_type": "DET_ZONE", "ts": "2026-09-15T00:00:00.000Z",
    "objects": [{"label": "person", "confidence": 0.9,
                 "bbox": {"x": 0.4, "y": 0.4, "width": 0.2, "height": 0.2}}],
    "detections": [{"label": "person", "confidence": 0.9,
                    "bbox": {"x": 0.4, "y": 0.4, "width": 0.2, "height": 0.2}}],
    "latency_ms": 12.3,
}


def test_empty_event_is_not_persisted(db_session):
    from app.api.v1.module_video.edge.store import count_events
    before = count_events(db_session)
    assert asyncio.run(service._persist_edge_event({**EV, "event_id": "ev-empty", "objects": [], "detections": []},
                                                   matched=False, rule_id=None, matched_leaves=[])) is None
    assert count_events(db_session) == before


def test_same_event_id_is_idempotent(db_session):
    async def _run():
        first = await service._persist_edge_event(EV, matched=True, rule_id=1,
                                                 matched_leaves=[{"path": "and/0", "subject": "object_present"}])
        second = await service._persist_edge_event(EV, matched=True, rule_id=1, matched_leaves=[])
        return first, second
    first, second = asyncio.run(_run())
    assert first is not None and second is None


def test_snapshot_data_not_persisted(db_session):
    import json
    asyncio.run(service._persist_edge_event({**EV, "event_id": "ev-snap", "snapshot_data": "AAAA"},
                                            matched=False, rule_id=None, matched_leaves=[]))
    from app.api.v1.module_video.edge.store import get_event_by_event_id
    row = get_event_by_event_id(db_session, "ev-snap")
    assert "snapshot_data" not in json.dumps(row.objects, ensure_ascii=False) + json.dumps(row.detections, ensure_ascii=False)
```

> `db_session`/`count_events`/`get_event_by_event_id` 为测试辅助：若 tests 无 `db_session` fixture，按 `tests/test_alarm_rule_params.py` 的做法用真实 DB 会话（`async_db_session`）在测试内打开；辅助函数随本任务实现。

- [ ] **Step 2: 运行确认失败**

Run: `cd backend && uv run pytest tests/test_edge_event_store.py -q` → FAIL

- [ ] **Step 3: 建表模型**

`edge/model.py`（沿用项目 `MappedBase` + `ModelMixin` 风格；`objects`/`detections` 用 `JSONB`）：

```python
class EdgeEventModel(ModelMixin, MappedBase):
    """边缘事件（v2 归一化后落库；只落有检测的事件）。"""

    __tablename__ = "video_edge_events"
    __table_args__ = (
        Index("ix_edge_event_camera_id_id", "camera_id", "id"),
        Index("ix_edge_event_algo_id", "algorithm_type", "id"),
        Index("ix_edge_event_matched_id", "matched", "id"),
    )

    event_id: Mapped[str] = mapped_column(String(64), unique=True, index=True, comment="Agent 事件 UUID")
    edge_code: Mapped[str | None] = mapped_column(String(64), comment="边缘设备码")
    camera_id: Mapped[int | None] = mapped_column(Integer, comment="相机")
    task_id: Mapped[int | None] = mapped_column(Integer, comment="布控任务")
    algorithm_type: Mapped[str | None] = mapped_column(String(64), comment="场景码")
    ts: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), comment="事件时间")
    objects: Mapped[list | None] = mapped_column(JSONB, comment="v2 对象数组")
    detections: Mapped[list | None] = mapped_column(JSONB, comment="兼容检测数组")
    latency_ms: Mapped[float | None] = mapped_column(Float, comment="推理耗时(ms)")
    snapshot_ref: Mapped[str | None] = mapped_column(String(512), comment="快照引用")
    matched: Mapped[bool] = mapped_column(Boolean, default=False, comment="是否命中规则")
    matched_rule_id: Mapped[int | None] = mapped_column(Integer, comment="命中规则")
    matched_leaves: Mapped[list | None] = mapped_column(JSONB, comment="命中叶子解释")
```

- [ ] **Step 4: 落库服务**

`edge/store.py`：

```python
"""边缘事件持久化：只落有检测的事件，event_id 幂等。"""

async def record_edge_event(event: dict, *, matched: bool, rule_id, matched_leaves) -> int | None:
    if not (event.get("objects") or event.get("detections")):
        return None
    ...
```

- 用 `insert(...).on_conflict_do_nothing(index_elements=["event_id"])`（PG）或先查后插（跨库兼容），返回新行 id / None（重复/空事件）。
- `ts` 由 `to_epoch(frame_timestamp)` 转 UTC datetime；`snapshot_data` 丢弃，仅存 `snapshot_ref`。
- 失败仅 `log.warning` 并返回 None（不抛）。

在 `process_detection_callback` 中：命中判定后调用 `record_edge_event(...)`，并把命中叶子写入返回体：

```python
        event_id = event.get("event_id")
        hit_leaves: list = []
        if rule is not None and rule.conditions:
            matched, hit_leaves = explain_conditions(rule.conditions, detections, temporal=..., ...)
            if not matched:
                await record_edge_event(event, matched=False, rule_id=rule.id, matched_leaves=[])
                return {"alarm_created": False, "reason": "rule_not_matched", "event_id": event_id}
        # 命中（或规则为空）→ 建告警后落库
        await record_edge_event(event, matched=True, rule_id=rule.id if rule else None, matched_leaves=hit_leaves)
```

（保持既有早退顺序：空检测且非时序 → `no_detections` 早退且不落库。）

- [ ] **Step 5: 生成并执行迁移**

```bash
cd backend && uv run main.py revision --env=dev && uv run main.py upgrade --env=dev
```
确认迁移只新增 `video_edge_events` 表与索引。

- [ ] **Step 6: 运行测试 + 全量回归**

Run: `cd backend && uv run pytest tests/test_edge_event_store.py -q` → 全通过
Run: `cd backend && uv run pytest -q` → 全通过

- [ ] **Step 7: 提交**

```bash
git add backend/app/api/v1/module_video/edge/model.py backend/app/api/v1/module_video/edge/store.py backend/app/api/v1/module_video/inference/service.py backend/tests/test_edge_event_store.py backend/alembic/versions/<新迁移>.py
git commit -m "feat(video): 边缘事件落库（只落有检测事件 + 命中叶子）"
```

---

### Task 3: 查询接口（list/detail）

**Files:**
- Modify: `backend/app/api/v1/module_video/edge/controller.py`
- Test: `backend/tests/test_edge_event_api.py`

**Interfaces:**
- Produces: `GET /video/edge/event/list`、`GET /video/edge/event/detail/{id}`

- [ ] **Step 1: 写失败测试**

覆盖：分页、按 `camera_id`/`algorithm_type`/`matched`/时间区间/关键字筛选、detail 命中、detail 404。沿用 `tests/test_alarm_rule_params.py` 的建机/建规则手法造一条事件（或直接调用 `record_edge_event` 造数据）。

- [ ] **Step 2-4: 实现并验证**

按该项目 controller/service/crud 惯例实现（权限用 edge 模块既有串，如 `module_video:edge:query`）；`page_no/page_size` 与项目分页响应一致（`{page_no,page_size,total,has_next,items}`）。detail 返回全量 `objects`/`detections`/`matched_leaves`。

Run: `cd backend && uv run pytest tests/test_edge_event_api.py -q` → 全通过

- [ ] **Step 5: 提交**

```bash
git add backend/app/api/v1/module_video/edge/controller.py backend/app/api/v1/module_video/edge/service.py backend/tests/test_edge_event_api.py
git commit -m "feat(video): 边缘事件查询接口（分页/筛选/详情）"
```

---

### Task 4: Redis pub/sub + WebSocket 实时推送

**Files:**
- Create: `backend/app/api/v1/module_video/edge/event_bus.py`
- Modify: `backend/app/api/v1/module_video/edge/controller.py`（WS 端点）
- Test: `backend/tests/test_edge_event_ws.py`

**Interfaces:**
- Produces:
  - `async def publish_edge_event(payload: dict) -> None`（Redis 频道 `ai:edge:event`；Redis 不可用 → 进程内 asyncio 广播降级）
  - `WS /api/v1/video/edge/event/ws?token=<jwt>`

- [ ] **Step 1: 写失败测试**

用 `fakeredis`（既有依赖）+ `TestClient.websocket_connect` 覆盖：鉴权失败即关闭（`4401`）；`publish_edge_event` 后 WS 收到 `{"type":"event","data":{...}}`。

- [ ] **Step 2-4: 实现**

- `event_bus.py`：进程内 `set[asyncio.Queue]` 订阅者集合 + Redis pub/sub（`redis.asyncio`）；`publish_edge_event` 双写（本地队列 + Redis publish），Redis 不可用仅本地并告警。
- WS 端点：解析 query `token` → 复用既有 JWT 校验（参考项目 WS 鉴权写法）→ 注册订阅者 → `while True: await queue.get() → send_json`；断开时注销。
- `process_detection_callback` 落库成功后调用 `publish_edge_event(detail)`（try/except 包裹，失败仅告警）。

Run: `cd backend && uv run pytest tests/test_edge_event_ws.py -q` → 全通过

- [ ] **Step 5: 提交**

```bash
git add backend/app/api/v1/module_video/edge/event_bus.py backend/app/api/v1/module_video/edge/controller.py backend/app/api/v1/module_video/inference/service.py backend/tests/test_edge_event_ws.py
git commit -m "feat(video): 边缘事件 Redis 广播与 WebSocket 实时推送"
```

---

### Task 5: TTL 清理

**Files:**
- Create: `backend/app/api/v1/module_video/edge/retention.py`
- Modify: 应用启动流程（挂 asyncio 任务）
- Test: `backend/tests/test_edge_event_retention.py`

- [ ] **Step 1: 写失败测试**：造 2 条事件（一条 `created_time` 早于阈值）→ `purge_old_events(30)` 返回 1 且只删旧条。
- [ ] **Step 2-4: 实现**：`async def purge_old_events(retention_days: int = 30) -> int`（按 `created_time < now - days` 删除）；启动时跑一次 + 每 3600s 循环；`settings.EDGE_EVENT_RETENTION_DAYS` 默认 30（加入 setting 与本任务文件）。
- [ ] **Step 5: 提交** `feat(video): 边缘事件 TTL 清理`

---

### Task 6: 前端事件流页面

**Files:**
- Create: `frontend/src/api/module_video/edge_event.ts`
- Create: `frontend/src/views/module_video/event_stream/index.vue`
- Modify: 菜单（`sys_menu` 插入 + admin 授权，按 AGENTS.md 流程）

**Interfaces:**
- Consumes: `GET /video/edge/event/list|detail/{id}`、`WS /api/v1/video/edge/event/ws`。
- Produces: 页面路由 `/video/event-stream`。

- [ ] **Step 1: API 封装**：`getEdgeEventList(params)`、`getEdgeEventDetail(id)`、`buildEdgeEventWsUrl(token)`。
- [ ] **Step 2: 页面**：
  - 筛选区：相机/场景（`getSceneCatalog`）/是否命中/时间范围/关键字；
  - 视图切换：「实时」（WS 追加，上限 200 行，暂停/继续/清屏）｜「历史」（`list` 分页）；
  - 表格列：时间、相机、场景、目标摘要、延迟、命中 tag；
  - 行点击 → `el-drawer` 详情：检测列表（label/置信度/track_id/属性/文本）、命中规则、**命中叶子高亮标签**、快照引用；
  - **单根元素**（AGENTS.md：多根 + `<Transition>` 会白屏）。
- [ ] **Step 3: 校验**：`pnpm run type-check`（0 新增）；仅本任务文件 lint 干净。
- [ ] **Step 4: 提交** `feat(ui): 边缘事件实时流页面（WS + 详情 + 命中高亮）`

---

### Task 7: Playwright e2e + 视觉核对

**Files:**
- Create: `frontend/e2e/sp5b-event-stream.spec.ts`
- Create: `docs/superpowers/runbooks/sp5b-visual.md` + 截图目录

- [ ] **Step 1-3**：读既有 e2e helper → 写 spec（登录 → 事件页 → 历史模式（造一条事件）→ 打开详情 → 断言命中叶子标签）→ `pnpm run e2e -- sp5b-event-stream` 通过。
- [ ] **Step 4**：截图 + `vision-recognition` 核对与既有模块风格一致。
- [ ] **Step 5: 提交** `test(ui): 边缘事件流 e2e 与视觉核对`

---

### Task 8: 真机联调

- [ ] **Step 1**：按 `docs/superpowers/runbooks/edge-agent-e2e.md` 起 broker + 后端（`cloud_edge`+MQTT）+ Agent；用 `-Scene DET_ZONE` 播含 person 视频。
- [ ] **Step 2**：断言 `video_edge_events` 有新行（含 objects）；前端「实时」页 <2s 内出现该事件；详情含命中叶子。
- [ ] **Step 3**：还原 `.env.dev`、停 broker/agent、重启后端。
- [ ] **Step 4**：把结果写入 `.superpowers/sdd/sp5b-task-8-report.md`。

---

### Task 9: 总回归

- [ ] **Step 1**：`cd backend && uv run pytest -q`（全绿）+ `uv run ruff check`（确认无本切片文件新增告警）。
- [ ] **Step 2**：`cd frontend && pnpm run type-check && pnpm run lint`（仅本切片文件无新增）+ `pnpm run e2e`（全绿）。
- [ ] **Step 3**：报告写入 `.superpowers/sdd/sp5b-task-9-report.md`。

---

## Self-Review

**Spec 覆盖：**

| Spec 条目 | 落点 |
|-----------|------|
| §3.1 表结构/索引/只落有检测/幂等 | Task 2 |
| §3.2 写入点（callback 内）+ 失败不阻断 | Task 1 Step 3 + Task 2 Step 4 |
| §3.3 `explain_conditions` + 对拍 | Task 1 |
| §3.4 list/detail 接口 + 权限 | Task 3 |
| §3.4 WS + Redis pub/sub + token 鉴权 | Task 4 |
| §3.5 TTL 清理 + 配置项 | Task 5 |
| §3.6 前端页面/抽屉/命中高亮/菜单 | Task 6 |
| §4 验收（单测/e2e/截图/真机） | Task 1-5 单测、Task 7 e2e+截图、Task 8 真机、Task 9 回归 |
| §6 兼容性（`_match_conditions` 不变、返回体仅新增 event_id） | Task 1 Step 5、Task 2 Step 4 |

**类型一致性：** `explain_conditions` 返回 `tuple[bool, list[dict]]`（Task 1）与 Task 2 落库消费一致；`record_edge_event(event, *, matched, rule_id, matched_leaves)` 在 Task 2 定义、Task 4 广播前复用；`publish_edge_event(payload)` 在 Task 4 定义与调用一致；前端 `getEdgeEventList/Detail` 与后端路径一致。

**占位符扫描：** Task 1/2 含完整关键代码与预期输出；Task 3-5 给出接口契约、行为与验收命令（沿用项目既有 controller/service 惯例，避免臆造与本项目不符的样板）；Task 6-9 含明确交付物与校验命令。
