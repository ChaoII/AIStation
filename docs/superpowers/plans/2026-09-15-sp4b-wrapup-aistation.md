# SP4-b 收尾（AIStation 云端）实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 打通 `line_cross` 云端时序几何求值器、统一 GATHER 滑窗口径、让 `absence` 由 Agent 空事件心跳端到端触发。

**Architecture:** 在既有 `TemporalStore`（Redis + 内存降级）上增量扩展「轨迹位置」与「absence 触发标记」两类状态，`inference/service.py` 的 `_eval_temporal` 增加 `line_cross` 分支，`process_detection_callback` 去掉空检测早退，使静默期心跳事件能驱动 absence 评估。

**Tech Stack:** FastAPI + SQLAlchemy 2.0 + Pydantic v2；测试 pytest（内存/假 DB）；Python 3.13（`uv`）。

**Spec:** `docs/superpowers/specs/2026-09-15-sp4b-wrapup-design.md`

## Global Constraints

- 代码注释与提交信息一律**中文**；提交格式 `feat(video): …` / `fix(video): …` / `test(video): …`。
- 只 `git add` 本任务列出的文件；**禁止 `git add -A`**。
- 测试：`cd backend && uv run pytest <file> -q`，然后 `uv run pytest -q`；`uv run ruff check`（须全绿）。
- **禁止新增依赖**；仅用标准库 + 既有依赖。
- 时序逻辑时间一律由事件 `frame_timestamp`（`to_epoch`）注入，**禁止依赖 wall clock**。
- 所有非法/脏输入一律「不命中且不抛异常」（延续既有约定）。
- `query()` 既有字段语义（`\x1ffirst` / `\x1flast`）不得改变。

---

### Task 1: TemporalStore 轨迹位置观测

**Files:**
- Modify: `backend/app/api/v1/module_video/inference/temporal.py`
- Test: `backend/tests/test_temporal_positions.py`（新建）

**Interfaces:**
- Produces:
  - `TemporalStore.observe(camera_id, alarm_type, detections, ts, scope="all")` —— 行为扩展：带 `bbox` 的检测额外写入位置字段。
  - `TemporalStore.query_positions(camera_id, alarm_type, label=None, scope="all") -> dict[str, tuple[tuple[float, float] | None, tuple[float, float] | None]]` —— `{field: (prev_xy, cur_xy)}`。

- [ ] **Step 1: 写失败测试**

创建 `backend/tests/test_temporal_positions.py`：

```python
"""TemporalStore 轨迹位置观测测试（SP4-b line_cross 基础）。"""
from app.api.v1.module_video.inference.temporal import TemporalStore

CAM = 1
ALGO = "AI_DETECTION"


def _det(track_id, cx, cy, label="person", w=0.1, h=0.1):
    """构造一条带中心 (cx, cy) 的归一化检测框。"""
    return {
        "label": label,
        "confidence": 0.9,
        "track_id": track_id,
        "bbox": {"x": cx - w / 2, "y": cy - h / 2, "width": w, "height": h},
    }


def test_query_positions_first_observation_has_no_prev():
    s = TemporalStore(prefer_redis=False)
    s.observe(CAM, ALGO, [_det(1, 0.2, 0.5)], 1000)
    assert s.query_positions(CAM, ALGO, "person", "all") == {"t:1": (None, (0.2, 0.5))}


def test_query_positions_second_observation_moves_cur_to_prev():
    s = TemporalStore(prefer_redis=False)
    s.observe(CAM, ALGO, [_det(1, 0.2, 0.5)], 1000)
    s.observe(CAM, ALGO, [_det(1, 0.8, 0.5)], 1001)
    assert s.query_positions(CAM, ALGO, "person", "all") == {"t:1": ((0.2, 0.5), (0.8, 0.5))}


def test_query_positions_ignores_detections_without_bbox():
    s = TemporalStore(prefer_redis=False)
    s.observe(CAM, ALGO, [{"label": "person", "track_id": 1}], 1000)
    assert s.query_positions(CAM, ALGO, "person", "all") == {}


def test_query_positions_aggregate_all_labels():
    s = TemporalStore(prefer_redis=False)
    s.observe(
        CAM,
        ALGO,
        [_det(1, 0.2, 0.5, label="person"), _det(2, 0.3, 0.5, label="car")],
        1000,
    )
    assert set(s.query_positions(CAM, ALGO, None, "all")) == {"t:1", "t:2"}


def test_query_positions_scoped_by_region_bucket():
    s = TemporalStore(prefer_redis=False)
    s.observe(CAM, ALGO, [_det(1, 0.2, 0.5)], 1000, scope="bucketA")
    assert s.query_positions(CAM, ALGO, "person", "bucketA") == {"t:1": (None, (0.2, 0.5))}
    assert s.query_positions(CAM, ALGO, "person", "bucketB") == {}
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd backend && uv run pytest tests/test_temporal_positions.py -q`
Expected: FAIL（`AttributeError: 'TemporalStore' object has no attribute 'query_positions'`）

- [ ] **Step 3: 实现位置字段**

在 `temporal.py` 常量区追加（`_FIRST`/`_LAST` 之后）：

```python
_POS_P = "pos_p"   # 上一次观测中心 "x,y"
_POS_C = "pos_c"   # 当前观测中心 "x,y"
```

在 `_to_float` 之后追加位置序列化/解析与中心点助手：

```python
def _center(d) -> tuple[float, float] | None:
    """取检测框中心 (x + w/2, y + h/2)；bbox 缺失/非法返回 None。"""
    if not isinstance(d, dict):
        return None
    bbox = d.get("bbox")
    if not isinstance(bbox, dict):
        return None
    x = _to_float(bbox.get("x"))
    y = _to_float(bbox.get("y"))
    w = _to_float(bbox.get("width"))
    h = _to_float(bbox.get("height"))
    if None in (x, y, w, h):
        return None
    return (x + w / 2.0, y + h / 2.0)


def _ser_pos(pos: tuple[float, float]) -> str:
    """位置序列化为 "x,y"（保留 6 位小数，避免浮点噪声）。"""
    return f"{round(pos[0], 6)},{round(pos[1], 6)}"


def _parse_pos(raw) -> tuple[float, float] | None:
    """解析位置："x,y" 字符串或 [x, y] 序列；非法返回 None。"""
    if isinstance(raw, (list, tuple)) and len(raw) >= 2:
        x = _to_float(raw[0])
        y = _to_float(raw[1])
        return None if x is None or y is None else (x, y)
    if not isinstance(raw, str):
        return None
    parts = raw.split(",")
    if len(parts) != 2:
        return None
    x = _to_float(parts[0])
    y = _to_float(parts[1])
    return None if x is None or y is None else (x, y)
```

把 `observe()` 改为同时收集位置（替换原 `grouped` 循环与写入循环）：

```python
        scope = scope or _SCOPE_ALL
        grouped: dict[str, dict[str, float]] = {}
        positions: dict[str, dict[str, tuple[float, float]]] = {}
        for d in detections:
            if not isinstance(d, dict):
                continue
            label = d.get("label")
            if not isinstance(label, str):
                label = ""
            field = self._field(d.get("track_id"), now)
            grouped.setdefault(label, {})[field] = now
            center = _center(d)
            if center is not None:
                positions.setdefault(label, {}).setdefault(field, center)
        for label, fields in grouped.items():
            key = self._key(camera_id, alarm_type, label, scope)
            self._observe_locked(key, fields, positions.get(label, {}))
```

把 `_observe_locked` 签名与实现改为（新增 `positions` 参数与位置推进）：

```python
    def _observe_locked(self, key: str, fields: dict[str, float],
                        positions: dict[str, tuple[float, float]] | None = None) -> None:
        """在同一把锁内完成读-改-写；位置推进 prev <- 旧 cur，cur <- 新中心。"""
        positions = positions or {}
        with self._lock:
            current = self._read_hash_nolock(key)
            mapping: dict[str, float] = {}
            for field, value in fields.items():
                prev_first = _to_float(current.get(field + _SEP + _FIRST))
                prev_last = _to_float(current.get(field + _SEP + _LAST))
                mapping[field + _SEP + _FIRST] = value if prev_first is None else min(prev_first, value)
                mapping[field + _SEP + _LAST] = value if prev_last is None else max(prev_last, value)

            pos = positions.get(field)
            if pos is not None:
                old_cur = _parse_pos(current.get(field + _SEP + _POS_C))
                if old_cur is not None:
                    mapping[field + _SEP + _POS_P] = _ser_pos(old_cur)
                mapping[field + _SEP + _POS_C] = _ser_pos(pos)
            self._write_hash_nolock(key, mapping)
```

> 注意缩进：位置推进代码必须位于 `for field, value in fields.items():` 循环体内。

在 `query()` 之后新增：

```python
    def query_positions(self, camera_id, alarm_type, label=None, scope: str = _SCOPE_ALL):
        """返回 ``{track_key: (prev_xy | None, cur_xy)}``；label=None 聚合全部标签。"""
        scope = scope or _SCOPE_ALL
        out: dict[str, tuple[tuple[float, float] | None, tuple[float, float] | None]] = {}
        for key in self._keys(camera_id, alarm_type, label, scope):
            h = self._read_hash(key)
            prevs: dict[str, tuple[float, float]] = {}
            curs: dict[str, tuple[float, float]] = {}
            for k, v in h.items():
                if not isinstance(k, str):
                    continue
                if k.endswith(_SEP + _POS_C):
                    p = _parse_pos(v)
                    if p is not None:
                        curs[k[: -len(_SEP + _POS_C)]] = p
                elif k.endswith(_SEP + _POS_P):
                    p = _parse_pos(v)
                    if p is not None:
                        prevs[k[: -len(_SEP + _POS_P)]] = p
            for field, cur in curs.items():
                out[field] = (prevs.get(field), cur)
        return out
```

- [ ] **Step 4: 运行测试确认通过**

Run: `cd backend && uv run pytest tests/test_temporal_positions.py -q`
Expected: `5 passed`

- [ ] **Step 5: 回归既有测试**

Run: `cd backend && uv run pytest tests/test_temporal_leaves.py -q`
Expected: 全通过（位置字段为增量，不影响 `query()`）

- [ ] **Step 6: 提交**

```bash
git add backend/app/api/v1/module_video/inference/temporal.py backend/tests/test_temporal_positions.py
git commit -m "feat(video): 时序存储记录轨迹位置供越线几何判定"
```

---

### Task 2: line_cross 时序几何求值器 + 目录接线

**Files:**
- Modify: `backend/app/api/v1/module_video/inference/service.py`
- Modify: `backend/app/api/v1/module_video/scene/catalog.py`
- Modify: `backend/tests/test_scene_catalog.py`
- Test: `backend/tests/test_line_cross.py`（新建）

**Interfaces:**
- Consumes: `TemporalStore.query_positions(...)`（Task 1）。
- Produces: `TEMPORAL_SUBJECTS` 含 `"line_cross"`；叶子契约
  `{"subject":"line_cross","line":[[x,y],[x,y],…],"dir":"A2B"|"B2A"|"both","region"?:[[x,y]…],"label"?:str,"labels"?:[str]}`。

- [ ] **Step 1: 写失败测试**

创建 `backend/tests/test_line_cross.py`：

```python
"""line_cross 云端时序几何求值器测试（SP4-b 收尾）。"""
from app.api.v1.module_video.inference.service import _match_conditions
from app.api.v1.module_video.inference.temporal import TemporalStore

CAM = 1
ALGO = "AI_DETECTION"
# 竖向绊线 x=0.5：起点 (0.5,0) → 终点 (0.5,1)，左侧(x<0.5)为 A 侧
VLINE = [[0.5, 0.0], [0.5, 1.0]]
ROI = [[0.2, 0.2], [0.8, 0.2], [0.8, 0.8], [0.2, 0.8]]


def _det(track_id, cx, cy, label="person", w=0.1, h=0.1):
    return {
        "label": label,
        "confidence": 0.9,
        "track_id": track_id,
        "bbox": {"x": cx - w / 2, "y": cy - h / 2, "width": w, "height": h},
    }


def _cross(store, leaf, now):
    return _match_conditions(
        {"op": "and", "children": [leaf]},
        [],
        temporal=store,
        camera_id=CAM,
        alarm_type=ALGO,
        now=now,
        alarm_interval=0,
    )


def _leaf(**extra):
    leaf = {"subject": "line_cross", "line": VLINE, "dir": "A2B"}
    leaf.update(extra)
    return leaf


def test_cross_a2b_matches_left_to_right():
    s = TemporalStore(prefer_redis=False)
    s.observe(CAM, ALGO, [_det(1, 0.2, 0.5)], 1000)
    s.observe(CAM, ALGO, [_det(1, 0.8, 0.5)], 1001)
    assert _cross(s, _leaf(), 1001) is True


def test_cross_b2a_matches_only_reverse_direction():
    s = TemporalStore(prefer_redis=False)
    s.observe(CAM, ALGO, [_det(1, 0.8, 0.5)], 1000)
    s.observe(CAM, ALGO, [_det(1, 0.2, 0.5)], 1001)
    assert _cross(s, _leaf(), 1001) is False
    assert _cross(s, _leaf(dir="B2A"), 1001) is True
    assert _cross(s, _leaf(dir="both"), 1001) is True


def test_cross_same_side_does_not_match():
    s = TemporalStore(prefer_redis=False)
    s.observe(CAM, ALGO, [_det(1, 0.1, 0.5)], 1000)
    s.observe(CAM, ALGO, [_det(1, 0.3, 0.5)], 1001)
    assert _cross(s, _leaf(), 1001) is False


def test_cross_without_prev_does_not_match():
    s = TemporalStore(prefer_redis=False)
    s.observe(CAM, ALGO, [_det(1, 0.8, 0.5)], 1001)
    assert _cross(s, _leaf(), 1001) is False


def test_cross_outside_segment_extent_does_not_match():
    """绊线只在两点之间有效；延长线上的位移不算越界。"""
    s = TemporalStore(prefer_redis=False)
    s.observe(CAM, ALGO, [_det(1, 0.2, 1.5)], 1000)
    s.observe(CAM, ALGO, [_det(1, 0.8, 1.5)], 1001)
    assert _cross(s, _leaf(), 1001) is False


def test_cross_region_filters_track():
    """越界发生在 region 外 → 被区域过滤掉。"""
    s = TemporalStore(prefer_redis=False)
    s.observe(CAM, ALGO, [_det(1, 0.2, 0.05)], 1000)
    s.observe(CAM, ALGO, [_det(1, 0.8, 0.05)], 1001)
    assert _cross(s, _leaf(region=ROI), 1001) is False
    assert _cross(s, _leaf(), 1001) is True


def test_cross_fires_once_per_crossing():
    """穿越后位置前移，不再重复命中。"""
    s = TemporalStore(prefer_redis=False)
    s.observe(CAM, ALGO, [_det(1, 0.2, 0.5)], 1000)
    s.observe(CAM, ALGO, [_det(1, 0.8, 0.5)], 1001)
    assert _cross(s, _leaf(), 1001) is True
    s.observe(CAM, ALGO, [_det(1, 0.9, 0.5)], 1002)
    assert _cross(s, _leaf(), 1002) is False


def test_cross_invalid_inputs_do_not_raise():
    s = TemporalStore(prefer_redis=False)
    s.observe(CAM, ALGO, [_det(1, 0.2, 0.5)], 1000)
    s.observe(CAM, ALGO, [_det(1, 0.8, 0.5)], 1001)
    for bad in (
        {"subject": "line_cross", "line": None},
        {"subject": "line_cross", "line": [[0.5, 0.0]]},
        {"subject": "line_cross", "line": "line"},
        {"subject": "line_cross", "line": VLINE, "dir": "???"},
        {"subject": "line_cross", "line": [[0.5, "x"], [0.5, 1.0]]},
        {"subject": "line_cross", "line": [[0.5, 0.5], [0.5, 0.5]]},
    ):
        assert _cross(s, bad, 1001) is False


def test_temporal_subjects_contains_line_cross():
    from app.api.v1.module_video.inference.service import TEMPORAL_SUBJECTS

    assert "line_cross" in TEMPORAL_SUBJECTS
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd backend && uv run pytest tests/test_line_cross.py -q`
Expected: FAIL（`test_temporal_subjects_contains_line_cross` 失败；其余因未知叶子不命中而失败）

- [ ] **Step 3: 实现几何求值器**

在 `service.py` 的 `TEMPORAL_SUBJECTS` 增加 `"line_cross"`：

```python
TEMPORAL_SUBJECTS = ("dwell", "count_window", "absence", "line_cross")
```

在 `_point_in_polygon` 之后新增几何助手：

```python
def _orient(a, b, c) -> float:
    """叉积 (B-A)×(C-A)：>0 表示 C 在有向线段 A→B 左侧。"""
    return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])


def _segments_cross(p1, p2, p3, p4, eps: float = 1e-12) -> bool:
    """两线段是否真正相交（严格跨立；共线/仅端点触碰视为不相交）。"""
    d1 = _orient(p3, p4, p1)
    d2 = _orient(p3, p4, p2)
    d3 = _orient(p1, p2, p3)
    d4 = _orient(p1, p2, p4)
    return (
        ((d1 > eps and d2 < -eps) or (d1 < -eps and d2 > eps))
        and ((d3 > eps and d4 < -eps) or (d3 < -eps and d4 > eps))
    )


def _parse_line(leaf: dict) -> tuple[tuple[float, float], tuple[float, float]] | None:
    """解析绊线折线：取首尾两点构成有向线段；非法/退化返回 None。"""
    line = leaf.get("line")
    if not isinstance(line, (list, tuple)) or len(line) < 2:
        return None

    def _pt(p):
        if not isinstance(p, (list, tuple)) or len(p) < 2:
            return None
        x = _as_float(p[0])
        y = _as_float(p[1])
        if x is None or y is None:
            return None
        return (x, y)

    a = _pt(line[0])
    b = _pt(line[-1])
    if a is None or b is None or a == b:
        return None
    return a, b


def _point_pass_region(pt, leaf: dict) -> bool:
    """点是否落在叶子 region 内；未限定 region 返回 True，非法区域返回 False。"""
    if not isinstance(leaf, dict) or leaf.get("region") is None:
        return True
    pts = _region_of(leaf)
    if not pts:
        return False
    return _point_in_polygon(pt[0], pt[1], pts)
```

在 `_query_temporal` 之后新增位置查询助手：

```python
def _query_positions(temporal, camera_id, alarm_type: str, leaf: dict, scope: str):
    """读取轨迹位置状态；无标签限制时聚合全部标签（与 _query_temporal 同构）。"""
    labels = _leaf_labels(leaf)
    if not labels:
        return temporal.query_positions(camera_id, alarm_type, None, scope)
    merged: dict = {}
    for lab in labels:
        merged.update(temporal.query_positions(camera_id, alarm_type, lab, scope))
    return merged
```

在 `_eval_temporal` 的 `count_window` 分支之后、`absence` 分支之前插入：

```python
    if subject == "line_cross":
        line = _parse_line(leaf)
        if line is None:
            return False
        direction = leaf.get("dir", "A2B")
        if direction not in ("A2B", "B2A", "both"):
            return False
        l0, l1 = line
        positions = _query_positions(temporal, camera_id, alarm_type, leaf, scope)
        for _field, (prev, cur) in positions.items():
            if prev is None or cur is None:
                continue
            if not _point_pass_region(cur, leaf):
                continue
            if not _segments_cross(prev, cur, l0, l1):
                continue
            s_prev = _orient(l0, l1, prev)
            s_cur = _orient(l0, l1, cur)
            if direction == "both":
                return True
            if direction == "A2B" and s_prev > 0 > s_cur:
                return True
            if direction == "B2A" and s_prev < 0 < s_cur:
                return True
        return False
```

同步更新 `_match_conditions` docstring，追加一行：

```
    - line_cross：{"subject":"line_cross","line":[[x,y],…],"dir":"A2B|B2A|both","region"?}
      轨迹上一帧中心与当前帧中心连线是否真正穿越绊线（首尾两点），并按方向命中。
```

- [ ] **Step 4: 运行测试确认通过**

Run: `cd backend && uv run pytest tests/test_line_cross.py -q`
Expected: `9 passed`

- [ ] **Step 5: 目录接线（LINE_CROSS）**

在 `catalog.py` 把 `LINE_CROSS` 定义为（去掉 TODO 与符号化 `line`）：

```python
_add(SceneDef(
    "LINE_CROSS", "越界/绊线", "tracking", "LINE_CROSS", ["det"], [_DET, _TRACK],
    [_LINE, _DIRECTION, _CONF],
    # line_cross 时序几何叶子（SP4-b 收尾已实现）：绊线由任务参数在运行时注入，
    # 默认规则不写符号化 line（与 region 同理，符号引用无法被求值器解析）。
    {"op": "and", "children": [{"subject": "line_cross", "dir": "A2B"}]},
    True, "目标轨迹穿越绊线",
))
```

- [ ] **Step 6: 更新目录测试**

在 `tests/test_scene_catalog.py` 的 `_IMPLEMENTED_LEAF_KEYS` 增加一行：

```python
    "line_cross": None,
```

在其后追加新测试：

```python
def test_line_cross_default_rule_uses_line_cross_leaf():
    """LINE_CROSS 默认规则必须落到已实现的 line_cross 叶子，且不写符号化 line。"""
    scene = get_scene("LINE_CROSS")
    assert scene is not None
    leaves = list(_iter_rule_leaves(scene.default_rule))
    assert [leaf.get("subject") for leaf in leaves] == ["line_cross"]
    for leaf in leaves:
        assert not isinstance(leaf.get("line"), str), "line 不得为符号化字符串"
        assert leaf.get("dir", "A2B") in ("A2B", "B2A", "both")
```

并把 `test_default_rules_implemented_leaves_are_evaluable` 末尾的非空守卫改为：

```python
    assert {"dwell", "count_window", "absence", "line_cross"} <= checked
```

- [ ] **Step 7: 运行目录与几何测试**

Run: `cd backend && uv run pytest tests/test_scene_catalog.py tests/test_line_cross.py -q`
Expected: 全通过

- [ ] **Step 8: 提交**

```bash
git add backend/app/api/v1/module_video/inference/service.py backend/app/api/v1/module_video/scene/catalog.py backend/tests/test_scene_catalog.py backend/tests/test_line_cross.py
git commit -m "feat(video): line_cross 云端时序几何求值器并接线目录"
```

---

### Task 3: GATHER 滑窗参数口径统一为 window_sec

**Files:**
- Modify: `backend/app/api/v1/module_video/scene/catalog.py`
- Modify: `backend/tests/test_scene_catalog.py`

**Interfaces:**
- Produces: `GATHER.param_schema` 含 `{"key":"window_sec",…}`；`GATHER.default_rule` 的 `count_window.window_sec == 5`。

- [ ] **Step 1: 写失败测试**

在 `tests/test_scene_catalog.py` 追加：

```python
def test_gather_param_schema_uses_window_sec():
    """GATHER 滑窗参数必须与规则口径一致（window_sec / 秒），不得再用帧数 window。"""
    scene = get_scene("GATHER")
    assert scene is not None
    keys = {p["key"] for p in scene.param_schema}
    assert "window_sec" in keys
    assert "window" not in keys
    param = next(p for p in scene.param_schema if p["key"] == "window_sec")
    assert param["default"] == 5
    leaf = next(iter(_iter_rule_leaves(scene.default_rule)))
    assert leaf.get("subject") == "count_window"
    assert leaf.get("window_sec") == param["default"]
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd backend && uv run pytest tests/test_scene_catalog.py::test_gather_param_schema_uses_window_sec -q`
Expected: FAIL（`"window_sec" in keys` 为假）

- [ ] **Step 3: 改目录参数**

在 `catalog.py` 的 `GATHER` 定义中替换参数项：

```python
    [_POLY, _COUNT, {"key": "window_sec", "type": "int", "default": 5, "label": "滑窗时长(秒)"}, _CONF],
```

并将该场景注释首行改为：

```python
    # count_window 时序叶子（SP4-b 已实现）：滑窗 5 秒内去重目标数 >= value(=5)。
```

- [ ] **Step 4: 运行测试确认通过**

Run: `cd backend && uv run pytest tests/test_scene_catalog.py -q`
Expected: 全通过

- [ ] **Step 5: 提交**

```bash
git add backend/app/api/v1/module_video/scene/catalog.py backend/tests/test_scene_catalog.py
git commit -m "fix(video): GATHER 滑窗参数口径统一为 window_sec(秒)"
```

---

### Task 4: absence 空事件评估 + 触发防抖

**Files:**
- Modify: `backend/app/api/v1/module_video/inference/temporal.py`
- Modify: `backend/app/api/v1/module_video/inference/service.py`
- Modify: `backend/tests/test_temporal_leaves_e2e.py`

**Interfaces:**
- Consumes: `TemporalStore`、`_iter_temporal_leaves`、`_leaf_scope`、`temporal_store`。
- Produces:
  - `temporal.ABSENT_ALL`（常量 `"__all__"`）
  - `TemporalStore.get_absent_fired(camera_id, alarm_type, label, scope="all") -> float | None`
  - `TemporalStore.set_absent_fired(camera_id, alarm_type, label, scope, ts) -> None`
  - `service._mark_absence_fired(camera_id, alarm_type, conditions, now, temporal=None) -> None`
  - 行为：`process_detection_callback` 对「空检测且规则含时序叶子」的事件仍执行规则评估。

- [ ] **Step 1: 写失败测试**

在 `tests/test_temporal_leaves_e2e.py` 末尾追加：

```python
class _FakeRuleThrottled(_FakeRule):
    """带节流间隔的规则（absence 防抖依赖 interval_seconds）。"""

    interval_seconds = 30


def _heartbeat(ts):
    """构造一次空检测心跳事件（Agent 静默期上报）。"""
    return {
        "task_id": 1,
        "camera_id": CAM,
        "algorithm_type": ALGO,
        "detections": [],
        "heartbeat": True,
        "frame_timestamp": ts,
    }


def test_absence_alarm_on_heartbeat_after_gap(monkeypatch):
    """先出现目标，静默超过 gap_sec 后由心跳事件触发 absence 告警。"""
    store = TemporalStore(prefer_redis=False)
    rule = _FakeRule({
        "op": "and",
        "children": [{"subject": "absence", "label": "person", "gap_sec": 30}],
    })
    _patch_runtime(monkeypatch, rule, store)

    first = asyncio.run(service.InferenceService.process_detection_callback(_event(1000)))
    assert first == {"alarm_created": False, "reason": "rule_not_matched"}

    early = asyncio.run(service.InferenceService.process_detection_callback(_heartbeat(1010)))
    assert early == {"alarm_created": False, "reason": "rule_not_matched"}

    after = asyncio.run(service.InferenceService.process_detection_callback(_heartbeat(1040)))
    assert after["alarm_created"] is True
    assert after["rule_matched"] == rule.name


def test_absence_heartbeat_throttled_within_interval(monkeypatch):
    """同一节流窗口内，心跳触发的 absence 告警不重复。"""
    store = TemporalStore(prefer_redis=False)
    rule = _FakeRuleThrottled({
        "op": "and",
        "children": [{"subject": "absence", "label": "person", "gap_sec": 30}],
    })
    _patch_runtime(monkeypatch, rule, store)

    asyncio.run(service.InferenceService.process_detection_callback(_event(1000)))
    first = asyncio.run(service.InferenceService.process_detection_callback(_heartbeat(1040)))
    assert first["alarm_created"] is True

    second = asyncio.run(service.InferenceService.process_detection_callback(_heartbeat(1045)))
    assert second == {"alarm_created": False, "reason": "rule_not_matched"}


def test_absence_rearms_after_detection_resumes(monkeypatch):
    """检测恢复后重新计时，再次静默超时可再次告警。"""
    store = TemporalStore(prefer_redis=False)
    rule = _FakeRuleThrottled({
        "op": "and",
        "children": [{"subject": "absence", "label": "person", "gap_sec": 30}],
    })
    _patch_runtime(monkeypatch, rule, store)

    asyncio.run(service.InferenceService.process_detection_callback(_event(1000)))
    assert asyncio.run(
        service.InferenceService.process_detection_callback(_heartbeat(1040))
    )["alarm_created"] is True

    # 目标重新出现（推进 last_seen，解除 gap 条件）
    asyncio.run(service.InferenceService.process_detection_callback(_event(1050)))
    assert asyncio.run(
        service.InferenceService.process_detection_callback(_heartbeat(1090))
    )["alarm_created"] is True


def test_heartbeat_without_temporal_rule_is_noop(monkeypatch):
    """规则非时序时，空检测心跳维持既有 no_detections 语义。"""
    store = TemporalStore(prefer_redis=False)
    rule = _FakeRule({
        "op": "and",
        "children": [{"subject": "object_present", "label": "person"}],
    })
    _patch_runtime(monkeypatch, rule, store)

    res = asyncio.run(service.InferenceService.process_detection_callback(_heartbeat(1000)))
    assert res == {"alarm_created": False, "reason": "no_detections"}
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd backend && uv run pytest tests/test_temporal_leaves_e2e.py -q`
Expected: FAIL（心跳事件返回 `no_detections`，absence 用例不通过）

- [ ] **Step 3: 实现 absence 触发标记**

在 `temporal.py` 常量区追加：

```python
_ABSENT_MARK = "__absent__"
# 无 label（或仅给 labels 列表）时 absence 标记使用的聚合标签
ABSENT_ALL = "__all__"
```

`TemporalStore.__init__` 增加内存标记字典（`self._memory` 之后）：

```python
        self._memory_meta: dict[str, float] = {}
```

在 `query_positions` 之后新增：

```python
    # ------------------------------------------------------------- absence 标记
    @staticmethod
    def _absent_key(camera_id, alarm_type, label, scope: str) -> str:
        return f"{KEY_PREFIX}:{camera_id}:{alarm_type}:{_ABSENT_MARK}:{scope}:{label}"

    def get_absent_fired(self, camera_id, alarm_type, label, scope: str = _SCOPE_ALL) -> float | None:
        """读取 absence 上次触发时间；无记录返回 None。"""
        scope = scope or _SCOPE_ALL
        key = self._absent_key(camera_id, alarm_type, label, scope)
        rd = self._get_redis()
        if rd is not None:
            try:
                return _to_float(rd.get(key))
            except Exception as e:
                log.warning(f"absence 标记读取失败，降级内存: {e}")
                self._redis = None
                self._redis_failed = True
        with self._lock:
            return self._memory_meta.get(key)

    def set_absent_fired(self, camera_id, alarm_type, label, scope: str, ts: float) -> None:
        """记录 absence 本次触发时间，用于同一节流窗口内不重复告警。"""
        scope = scope or _SCOPE_ALL
        key = self._absent_key(camera_id, alarm_type, label, scope)
        rd = self._get_redis()
        if rd is not None:
            try:
                rd.setex(key, _TTL_SEC, str(float(ts)))
                return
            except Exception as e:
                log.warning(f"absence 标记写入失败，降级内存: {e}")
                self._redis = None
                self._redis_failed = True
        with self._lock:
            self._memory_meta[key] = float(ts)
```

并把 `reset()` 改为同时清理内存标记（Redis 侧 `scan_iter(f"{KEY_PREFIX}:*")` 已覆盖标记键）：

```python
    def reset(self) -> None:
        """清空内存与 Redis 中本 store 写入的状态（测试用）。"""
        with self._lock:
            self._memory.clear()
            self._memory_meta.clear()
        rd = self._get_redis()
        if rd is not None:
            try:
                for k in rd.scan_iter(match=f"{KEY_PREFIX}:*"):
                    rd.delete(k)
            except Exception as e:
                log.warning(f"时序状态清理失败: {e}")
```

- [ ] **Step 4: 实现 absence 防抖判定（纯读取）**

在 `service.py` 顶部导入处把 `ABSENT_ALL` 加入既有 import：

```python
from app.api.v1.module_video.inference.temporal import (
    ABSENT_ALL,
    region_fingerprint,
    temporal_store,
    to_epoch,
)
```

把 `_eval_temporal` 的 `absence` 分支替换为：

```python
    if subject == "absence":
        gap = _as_float(leaf.get("gap_sec"))
        if gap is None or gap < 0:
            return False
        if not entries:
            return False
        last_seen = max(last for _first, last in entries.values())
        if (now - last_seen) < gap:
            return False
        # 同一节流窗口内不重复告警（alarm_interval<=0 表示不节流）
        label = leaf.get("label")
        mark_label = label if isinstance(label, str) and label else ABSENT_ALL
        fired = temporal.get_absent_fired(camera_id, alarm_type, mark_label, scope)
        interval = _as_float(alarm_interval) or 0.0
        if fired is not None and interval > 0 and (now - fired) < interval:
            return False
        return True
```

在 `_observe_temporal_event` 之后新增：

```python
def _mark_absence_fired(camera_id, alarm_type: str, conditions, now: float, temporal=None) -> None:
    """规则命中后写入 absence 触发标记，避免心跳在同一节流窗口内重复告警。"""
    temporal = temporal or temporal_store
    try:
        for leaf in _iter_temporal_leaves(conditions):
            if leaf.get("subject") != "absence":
                continue
            scope, ok = _leaf_scope(leaf)
            if not ok:
                continue
            label = leaf.get("label")
            if not isinstance(label, str) or not label:
                label = ABSENT_ALL
            temporal.set_absent_fired(camera_id, alarm_type, label, scope, now)
    except Exception as e:
        log.warning(f"absence 触发标记写入失败: {e}")
```

- [ ] **Step 5: 调整 process_detection_callback 早退顺序**

在 `process_detection_callback` 中：
1. 删除原有的

```python
        if not detections:
            return {"alarm_created": False, "reason": "no_detections"}
```

2. 在 `detections = event.get("detections", [])` 之后补一行健壮化：

```python
        if not isinstance(detections, list):
            detections = []
```

3. 在规则查询块（`rule = pick_alarm_rule(...)`）之后插入：

```python
        alarm_type = algorithm_type or "AI_DETECTION"
        event_now = to_epoch(frame_timestamp)
        has_temporal = bool(
            rule is not None and rule.conditions and _has_temporal_leaf(rule.conditions)
        )
        # 无检测：仅当规则含时序叶子（absence 等）时才继续评估，否则维持既有语义
        if not detections and not has_temporal:
            return {"alarm_created": False, "reason": "no_detections"}
```

4. 把原有的时序观测/评估块改为复用 `alarm_type` / `event_now`：

```python
        if rule is not None and rule.conditions:
            # 时序叶子需先写入本次观测（按事件 ts），再评估；非时序规则行为不变
            if has_temporal:
                _observe_temporal_event(
                    camera_id,
                    alarm_type,
                    detections,
                    event_now,
                    rule.conditions,
                )
            if not _match_conditions(
                rule.conditions,
                detections,
                camera_id=camera_id,
                alarm_type=alarm_type,
                now=event_now,
                alarm_interval=getattr(rule, "interval_seconds", 0) or 0,
            ):
                return {"alarm_created": False, "reason": "rule_not_matched"}
            if has_temporal:
                # 命中后写入 absence 触发标记（纯读取的 _eval_temporal 不改状态）
                _mark_absence_fired(camera_id, alarm_type, rule.conditions, event_now)
```

5. 告警 `description` 兼容空检测：把原 `description` 一行替换为：

```python
            "description": (
                f"AI 检测到 {len(detections)} 个目标: "
                f"{', '.join(d.get('label', '') for d in detections[:5])}"
                if detections
                else (f"{rule.name}：区域内持续无目标" if rule else "区域内持续无目标")
            ),
```

6. 其余（快照保存、规则查询、告警写入、联动/通知）保持不变；确认 `alarm_data["alarm_type"]` 使用局部 `alarm_type`。

- [ ] **Step 6: 运行测试确认通过**

Run: `cd backend && uv run pytest tests/test_temporal_leaves_e2e.py tests/test_temporal_leaves.py -q`
Expected: 全通过

- [ ] **Step 7: 全量回归 + lint**

Run: `cd backend && uv run pytest -q` → 全通过
Run: `cd backend && uv run ruff check` → `All checks passed!`

- [ ] **Step 8: 提交**

```bash
git add backend/app/api/v1/module_video/inference/temporal.py backend/app/api/v1/module_video/inference/service.py backend/tests/test_temporal_leaves_e2e.py
git commit -m "feat(video): absence 支持静默期心跳事件评估并加触发防抖"
```

---

### Task 5: E2E 脚本 ABSENT 分支 + runbook + 真机联调

**Files:**
- Modify: `scripts/e2e/edge_agent_e2e.ps1`
- Modify: `docs/superpowers/runbooks/edge-agent-e2e.md`

**Interfaces:**
- Consumes: Agent 心跳（ModelDeploy 计划 Task 2 产出，事件含 `heartbeat:true`、`detections:[]`）。
- Produces: `-Scene ABSENT` 可执行分支。

> 执行要点：脚本已按 `FACE_DET` 模式在 ~10 处（`ValidateSet`、能力播种、模型路径、
> 算法描述、`scene_type`、AlarmRule 播种、断言、清理）做分支。新增 `ABSENT` 时**逐处
> 镜像 FACE_DET 的写法**，不要改动任何 FACE_DET 既有行为。

- [ ] **Step 1: 通读 FACE_DET 分支锚点**

Run: `rg -n "FACE_DET" scripts/e2e/edge_agent_e2e.ps1`
记录各处，作为 `ABSENT` 的镜像锚点。

- [ ] **Step 2: 新增 ABSENT 场景分支**

按 FACE_DET 模式逐处添加 `ABSENT`：

1. `ValidateSet(...)` 增加 `"ABSENT"`。
2. 新增参数 `-DetModelPath`（默认 `zhgd_det` onnx 路径），用于 `ABSENT` 的 `detection` 管线。
3. 能力播种：`ABSENT` 要求设备能力含 `det`。
4. 算法：`algorithm_type="ABSENT"`、`scene_type="ABSENT"`、`model_path=$DetModelPath`、`preset_params={"confidence_threshold":0.3}`、`runtime_config={"backend":"ort","device":"cpu","decoder":{"hw_accel":"none","device_only":false}}`。
5. AlarmRule：`alarm_type="ABSENT"`、`conditions={"op":"and","children":[{"subject":"absence","label":"person","gap_sec":10}]}`、`interval_seconds=30`。
6. 断言：
   - 播放含 person 的视频若干秒 → 使 `last_seen` 有历史；
   - 停止/切换为空画面后等待 `> gap_sec`，断言出现 `algorithm_type="ABSENT"` 告警（由心跳驱动）；
   - 断言 `ai_result.detections == []`；
   - 断言同一 `interval_seconds` 内不重复创建第二告警（容差 1 条）。
7. 清理：删除该 AlarmRule 与 AlgorithmTask（沿用既有清理段）。

- [ ] **Step 3: 语法校验（不运行编排）**

Run: `pwsh -NoProfile -Command "[scriptblock]::Create((Get-Content -Raw scripts/e2e/edge_agent_e2e.ps1)) | Out-Null; 'OK'"`
Expected: `OK`

- [ ] **Step 4: 真机联调**

前置：`backend/env/.env.dev` 开启 `VIDEO_ANALYSIS_MODE=cloud_edge` + MQTT + `EDGE_CONTROL_TOKEN`；`docker` 启动 mosquitto；重启后端；启动 `aistation_agent`（含心跳）。
Run: `pwsh -NoProfile -File scripts/e2e/edge_agent_e2e.ps1 -Transport mqtt -Scene ABSENT -SkipBroker -VideoPath <person视频> -Secret e2e-shared-secret -EdgeCode e2e-absent-1`
Expected: 全部断言通过（含 absence 心跳告警）。
收尾：还原 `.env.dev`、停 broker/agent、重启后端。

- [ ] **Step 5: 更新 runbook**

在 `docs/superpowers/runbooks/edge-agent-e2e.md` 增加 `ABSENT` 小节：说明 absence 依赖 Agent 空事件心跳（`heartbeat_sec` 默认 5s）、`gap_sec` 与 `interval_seconds` 的语义与推荐取值、以及"先有目标再有静默"的联调前置条件。

- [ ] **Step 6: 提交**

```bash
git add scripts/e2e/edge_agent_e2e.ps1 docs/superpowers/runbooks/edge-agent-e2e.md
git commit -m "test(video): ABSENT 场景真机联调脚本与 runbook"
```

---

## Self-Review

**Spec 覆盖：**

| Spec 条目 | 落点 |
|-----------|------|
| §3.1 位置状态 + `query_positions` | Task 1 |
| §3.1 line_cross 求值 + 方向/区域/一次穿越 | Task 2 |
| §3.1 目录 LINE_CROSS 去符号化 line | Task 2 Step 5-6 |
| §3.2 GATHER window_sec | Task 3 |
| §3.3 云端去早退 + 空检测告警兼容 | Task 4 Step 5 |
| §3.3 absence 防抖标记 | Task 4 Step 3-4 |
| §3.3 Agent 心跳 | **ModelDeploy 计划 Task 1-2** |
| §4 测试策略（AIStation 部分） | Task 1-4 测试 + Task 5 真机 |
| §6 验收标准 1/2/3/4 | Task 2 / Task 3 / Task 4 + Task 5 / 各任务 lint+全量 |

**类型一致性：** `query_positions` 返回 `{field: (prev, cur)}`（Task 1）与 Task 4 位置消费一致；`ABSENT_ALL` 由 Task 4 Step 3 定义、Step 4 导入，命名一致；`_mark_absence_fired` 签名在 Step 4 定义与 Step 5 调用一致。

**占位符扫描：** 无 TBD/TODO 实现留白；Task 5 为脚本改动 + 真机验证，含明确逐处要求与校验命令。
