# SP6-a 规则作用域扩组与跨相机聚合实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让告警规则可作用于「相机组」（一条规则覆盖组内多台相机），并新增跨相机聚合叶子 `group_count` / `group_coverage`。

**Architecture:** `AlarmRule` 增加可选 `group_id`（与 `camera_id` 恰有其一）；评估改为「查全部作用域匹配规则 → 逐条评估 → 各自建告警」；聚合叶子在评估期跨相机读取时序状态（不新增跨相机写路径）。

**Tech Stack:** FastAPI + SQLAlchemy 2.0 + Alembic；Vue 3 + Element Plus + TypeScript + Playwright。

**Spec:** `docs/superpowers/specs/2026-09-15-sp6a-rule-scope-group-design.md`

## Global Constraints

- 代码注释与提交信息一律**中文**；格式 `feat(video): …` / `feat(ui): …` / `test(ui): …`。
- 只 `git add` 本任务列出文件；**禁止 `git add -A`**。
- 后端：`cd backend && uv run pytest -q` + `uv run ruff check` 全绿；**禁止新增后端依赖**。
- 前端：`pnpm run type-check` 0 新增；禁止新增依赖。
- **单条规则命中时，既有行为与返回体必须保持不变**（`rule_matched` 保留）。
- 新增形参一律带默认值（`scope=None`、`group_camera_ids=None`），既有调用点不得受影响。
- `TemporalStore` 只增只读聚合方法，**不新增跨相机写路径**。

---

### Task 1: 数据模型 + 迁移 + 作用域校验

**Files:**
- Modify: `backend/app/api/v1/module_video/alarm/model.py`
- Modify: `backend/app/api/v1/module_video/alarm/schema.py`
- Modify: `backend/app/api/v1/module_video/alarm/service.py`（作用域校验）
- Create: Alembic 迁移（CLI 生成）
- Test: `backend/tests/test_rule_scope_model.py`

**Interfaces:**
- Produces: `AlarmRuleModel.group_id`（可空 FK）、`camera_id` 可空；`AlarmRuleCreate/Update/Out.group_id`；作用域校验（恰有其一）。

- [ ] **Step 1: 写失败测试**

```python
"""规则作用域数据模型与校验测试。"""
import pytest

from app.api.v1.module_video.alarm.model import AlarmRuleModel


def test_model_exposes_group_id_and_nullable_camera_id():
    cols = AlarmRuleModel.__table__.columns
    assert "group_id" in cols
    assert cols["group_id"].nullable is True
    assert cols["camera_id"].nullable is True


def test_create_rule_requires_exactly_one_scope(test_client, auth_headers):
    # 都为空
    r1 = test_client.post("/api/v1/video/alarm/rule/create", headers=auth_headers, json={
        "name": "x", "alarm_type": "DET_ZONE", "severity": "WARNING", "status": True,
    })
    assert r1.status_code == 400
    # 都填（camera_id 与 group_id 同时给）
    r2 = test_client.post("/api/v1/video/alarm/rule/create", headers=auth_headers, json={
        "name": "x", "alarm_type": "DET_ZONE", "severity": "WARNING", "status": True,
        "camera_id": 1, "group_id": 1,
    })
    assert r2.status_code == 400
```

- [ ] **Step 2: 运行确认失败** → `cd backend && uv run pytest tests/test_rule_scope_model.py -q`

- [ ] **Step 3: 改模型**

`alarm/model.py`：

```python
    camera_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("video_cameras.id", ondelete="CASCADE"), nullable=True, index=True
    )
    # 作用域：camera_id 与 group_id 恰有其一非空（组规则覆盖组内多台相机）
    group_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("video_camera_groups.id", ondelete="SET NULL"), nullable=True, index=True
    )
```

- [ ] **Step 4: 改 schema**

`AlarmRuleCreate/Update/Out`：`camera_id: int | None`、新增 `group_id: int | None`。

- [ ] **Step 5: 加作用域校验**

`alarm/service.py` create/update 路径（写库前）：

```python
def _validate_scope(data: dict) -> None:
    """作用域校验：camera_id 与 group_id 恰有其一非空。"""
    has_cam = data.get("camera_id") is not None
    has_grp = data.get("group_id") is not None
    if has_cam == has_grp:
        raise CustomException(msg="规则作用域非法：camera_id 与 group_id 必须且只能指定一个")
```

（`CustomException` 按该模块既有导入；默认 HTTP 400。）

- [ ] **Step 6: 生成并执行迁移**

```bash
cd backend && uv run main.py revision --env=dev && uv run main.py upgrade --env=dev
```
检查生成文件只含 `video_alarm_rules` 的 `camera_id` 改可空 + 新增 `group_id`（+ 索引）。若 autogenerate 带出无关漂移，手工裁剪为最小迁移，并写**降级路径**（`downgrade` 恢复 `camera_id` NOT NULL 需先保证无 NULL 行——写明注释）。

- [ ] **Step 7: 运行测试 + 全量回归**

Run: `cd backend && uv run pytest tests/test_rule_scope_model.py -q` → 通过
Run: `cd backend && uv run pytest -q` → 全绿

- [ ] **Step 8: 提交**

```bash
git add backend/app/api/v1/module_video/alarm/model.py backend/app/api/v1/module_video/alarm/schema.py backend/app/api/v1/module_video/alarm/service.py backend/tests/test_rule_scope_model.py backend/alembic/versions/<新迁移>.py
git commit -m "feat(video): 告警规则作用域支持相机组（camera_id 可空 + group_id）"
```

---

### Task 2: 作用域查询 + 多规则多条告警

**Files:**
- Modify: `backend/app/api/v1/module_video/inference/service.py`
- Test: `backend/tests/test_rule_scope.py`

**Interfaces:**
- Consumes: `AlarmRuleModel.group_id`（Task 1）。
- Produces：`process_detection_callback` 返回 `alarm_ids: list[int]` + `rule_matched_list: list[str]`；`rule_matched`（首个）与 `alarm_id` 保留。

- [ ] **Step 1: 写失败测试**

```python
"""规则作用域匹配与多规则告警测试（假 DB）。"""
import asyncio

from app.api.v1.module_video.inference import service
from app.api.v1.module_video.inference.temporal import TemporalStore

# 复用 tests/test_temporal_leaves_e2e.py 的 _patch_runtime / _FakeRule / _Factory 手法，
# 但 _Factory 需支持"返回多条规则"与"相机 group_id 查询"：
#   - 规则查询返回 [直绑规则, 组绑规则]
#   - 相机 group_id 查询返回 7
# 断言：两条规则都命中 → alarm_ids 长度 2、rule_matched_list 含两者。
```

（本步需扩展该测试的假会话：查询 `AlarmRuleModel` 返回多条；查询 `CameraModel.group_id` 返回固定值。若既有 `_Factory` 不支持，写一个本文件专用的最小假会话实现——**不要** mock 掉评估逻辑。）

- [ ] **Step 2: 运行确认失败**

- [ ] **Step 3: 实现**

`process_detection_callback` 规则查询与评估改为：

```python
        async with async_db_session() as session:
            cam_group_id = (
                await session.execute(
                    select(CameraModel.group_id).where(CameraModel.id == camera_id)
                )
            ).scalar_one_or_none()

            scope_conds = [AlarmRuleModel.camera_id == camera_id]
            if cam_group_id is not None:
                scope_conds.append(AlarmRuleModel.group_id == cam_group_id)

            stmt = select(AlarmRuleModel).where(
                or_(*scope_conds),
                AlarmRuleModel.alarm_type == alarm_type,
                AlarmRuleModel.status.is_(True),
                AlarmRuleModel.is_deleted.is_(False),
            )
            rules = list((await session.execute(stmt)).scalars().all())

            group_camera_ids: list[int] = []
            if cam_group_id is not None:
                group_camera_ids = [
                    int(row) for row in (
                        await session.execute(
                            select(CameraModel.id).where(CameraModel.group_id == cam_group_id)
                        )
                    ).scalars().all()
                ]
```

- 逐条评估（把既有「观测 → 评估 → 建告警」抽成 `_evaluate_rule(...)`）：

```python
        matched_rules, alarm_ids = [], []
        for rule in rules:
            res = await _evaluate_rule(rule, event, detections, camera_id, alarm_type,
                                       event_now, group_camera_ids, ...)
            if res.get("alarm_created"):
                matched_rules.append(rule.name)
                alarm_ids.append(res["alarm_id"])
```

- 早退语义聚合：`not detections and not any(has_temporal)` → `no_detections`；无规则 → `rule_not_matched`；有规则但全未命中 → `rule_not_matched`。
- 返回：`{"alarm_created": bool(alarm_ids), "alarm_id": alarm_ids[0] if alarm_ids else None, "alarm_ids": alarm_ids, "rule_matched": matched_rules[0] if matched_rules else None, "rule_matched_list": matched_rules}`。
- 时序叶子的 `_observe_temporal_event` 对**每条时序规则**执行（幂等；同 `(camera,label)` 重复观测无副作用）。
- `group_camera_ids` 传给 `explain_conditions(..., group_camera_ids=group_camera_ids)`（形参在 Task 3 落地；本任务先传 `None` 或直接加上形参——若与 Task 3 并行会冲突，**本任务不加该形参**，仅预留注释）。

- [ ] **Step 4: 测试 + 全量回归**

Run: `cd backend && uv run pytest tests/test_rule_scope.py tests/test_temporal_leaves_e2e.py tests/test_alarm_rule_params.py -q` → 通过
Run: `cd backend && uv run pytest -q` → 全绿（**单条命中场景行为不变**）

- [ ] **Step 5: 提交**

```bash
git add backend/app/api/v1/module_video/inference/service.py backend/tests/test_rule_scope.py
git commit -m "feat(video): 规则评估支持相机组作用域与多规则多条告警"
```

---

### Task 3: 跨相机聚合叶子

**Files:**
- Modify: `backend/app/api/v1/module_video/inference/temporal.py`
- Modify: `backend/app/api/v1/module_video/inference/service.py`
- Test: `backend/tests/test_group_leaves.py`

**Interfaces:**
- Consumes: `TemporalStore`。
- Produces:
  - `TemporalStore.query_multi(camera_ids, alarm_type, label=None, scope="all") -> dict[str, tuple[float, float]]`（键含 `camera_id` 前缀）
  - `TEMPORAL_SUBJECTS` += `"group_count"`, `"group_coverage"`
  - `_match_conditions` / `explain_conditions` 新增 `group_camera_ids: list[int] | None = None`

- [ ] **Step 1: 写失败测试**

```python
"""跨相机聚合叶子测试。"""
from app.api.v1.module_video.inference.service import _match_conditions
from app.api.v1.module_video.inference.temporal import TemporalStore

CAM_A, CAM_B, ALGO = 1, 2, "AI_DETECTION"


def _det(track_id, label="person", cx=0.5, cy=0.5, w=0.1, h=0.1):
    return {"label": label, "confidence": 0.9, "track_id": track_id,
            "bbox": {"x": cx - w / 2, "y": cy - h / 2, "width": w, "height": h}}


def _ev(store, leaf, cam, now, ids):
    return _match_conditions(leaf, [], temporal=store, camera_id=cam, alarm_type=ALGO,
                             now=now, alarm_interval=0, group_camera_ids=ids)


STORE = TemporalStore(prefer_redis=False)


def test_group_count_sums_dedup_across_cameras():
    s = TemporalStore(prefer_redis=False)
    s.observe(CAM_A, ALGO, [_det(1), _det(2)], 1000)
    s.observe(CAM_B, ALGO, [_det(1), _det(3)], 1001)   # track 1 与 A 相机同号但独立
    leaf = {"subject": "group_count", "window_sec": 60, "op": ">=", "value": 4}
    assert _ev(s, leaf, CAM_A, 1002, [CAM_A, CAM_B]) is True     # 2 + 2 = 4（不去重跨相机）
    assert _ev(s, leaf, CAM_A, 1002, [CAM_A]) is False           # 单相机只有 2


def test_group_count_window_excludes_stale():
    s = TemporalStore(prefer_redis=False)
    s.observe(CAM_A, ALGO, [_det(1)], 1000)
    s.observe(CAM_B, ALGO, [_det(2)], 1001)
    leaf = {"subject": "group_count", "window_sec": 10, "op": ">=", "value": 2}
    assert _ev(s, leaf, CAM_A, 1005, [CAM_A, CAM_B]) is True
    assert _ev(s, leaf, CAM_A, 1020, [CAM_A, CAM_B]) is False    # 两条都已超出窗口


def test_group_count_without_group_context_never_matches():
    s = TemporalStore(prefer_redis=False)
    s.observe(CAM_A, ALGO, [_det(1)], 1000)
    leaf = {"subject": "group_count", "window_sec": 60, "op": ">=", "value": 1}
    assert _ev(s, leaf, CAM_A, 1001, None) is False


def test_group_coverage_ratio_over_group_size():
    s = TemporalStore(prefer_redis=False)
    s.observe(CAM_A, ALGO, [_det(1)], 1000)
    leaf = {"subject": "group_coverage", "window_sec": 60, "op": ">=", "value": 0.5}
    # 组内 4 台相机，仅 1 台有目标 → 0.25 < 0.5
    assert _ev(s, leaf, CAM_A, 1001, [CAM_A, CAM_B, 3, 4]) is False
    assert _ev(s, leaf, CAM_A, 1001, [CAM_A, CAM_B]) is True     # 1/2 = 0.5
```

- [ ] **Step 2: 运行确认失败**

- [ ] **Step 3: 实现 `query_multi`**

`temporal.py` 在 `query()` 之后新增：

```python
    def query_multi(self, camera_ids, alarm_type, label=None, scope: str = _SCOPE_ALL):
        """跨相机聚合读取：返回 ``{(camera_id, track_key): (first, last)}``。

        跨相机 track_id 独立，故键含 camera_id 前缀；调用方自行决定是否复用 track_id。
        """
        scope = scope or _SCOPE_ALL
        out: dict[tuple[int, str], tuple[float, float]] = {}
        for cam in camera_ids or []:
            for field, rng in self.query(cam, alarm_type, label, scope).items():
                out[(int(cam), field)] = rng
        return out
```

- [ ] **Step 4: 实现叶子求值**

`service.py`：

- `TEMPORAL_SUBJECTS = ("dwell", "count_window", "absence", "line_cross", "group_count", "group_coverage")`
- `_match_conditions` / `explain_conditions` 新增形参 `group_camera_ids: list[int] | None = None`，并透传到 `_eval_temporal(..., group_camera_ids=...)`。
- `_eval_temporal` 新增两分支：

```python
    if subject in ("group_count", "group_coverage"):
        if not group_camera_ids or camera_id is None or now is None:
            return False                      # 无组上下文 → fail-closed
        window = _as_float(leaf.get("window_sec"))
        if window is None or window < 0:
            return False
        op = leaf.get("op")
        if op not in (">=", ">", "<=", "<", "=="):
            return False
        target = _as_float(leaf.get("value"))
        if target is None:
            return False
        labels = _leaf_labels(leaf)
        # 聚合只读：逐相机读取各自时序状态（含 region 分桶）
        merged: dict = {}
        for lab in (labels or [None]):
            merged.update(temporal.query_multi(group_camera_ids, alarm_type, lab, scope))
        start = now - window
        active = {cam for (cam, _field), (_f, last) in merged.items() if last >= start}
        if subject == "group_count":
            count = sum(1 for (_cam, _field), (_f, last) in merged.items() if last >= start)
            return _compare_count(count, op, target)
        ratio = (len(active) / len(group_camera_ids)) if group_camera_ids else 0.0
        return _compare_count(ratio, op, target)
```

- `detail` 文案：`group_count → f"group {count}{op}{value}"`；`group_coverage → f"group cov {active}/{total}{op}{value}"`。
- 组叶子**不支持 `region`**（v1）：若给了 `region`，`_leaf_scope` 会分桶，聚合仍逐相机按同 scope 读取（行为一致，无需特判）。

- [ ] **Step 5: 测试 + 全量回归**

Run: `cd backend && uv run pytest tests/test_group_leaves.py -q` → 通过
Run: `cd backend && uv run pytest -q` → 全绿

- [ ] **Step 6: 提交**

```bash
git add backend/app/api/v1/module_video/inference/temporal.py backend/app/api/v1/module_video/inference/service.py backend/tests/test_group_leaves.py
git commit -m "feat(video): 新增跨相机聚合叶子 group_count/group_coverage"
```

---

### Task 4: 能力注册表 + 编译层作用域校验

**Files:**
- Modify: `backend/app/api/v1/module_video/scene/leaves.py`
- Modify: `backend/app/api/v1/module_video/scene/compile.py`
- Modify: `backend/tests/test_rule_capabilities.py`、`backend/tests/test_rule_compile.py`

**Interfaces:**
- Produces: `LEAF_CAPABILITIES` 含两新叶子；`compile_rule(scene_type, params, conditions, *, scope=None)`。

- [ ] **Step 1: 写失败测试**

```python
# test_rule_capabilities.py 追加
def test_group_leaves_registered():
    from app.api.v1.module_video.scene.leaves import LEAF_CAPABILITIES, IMPLEMENTED_LEAVES
    for s in ("group_count", "group_coverage"):
        assert s in LEAF_CAPABILITIES and LEAF_CAPABILITIES[s]["implemented"] is True
        assert s in IMPLEMENTED_LEAVES


# test_rule_compile.py 追加
def test_group_leaf_rejected_on_camera_scope():
    cond = {"op": "and", "children": [{"subject": "group_count", "window_sec": 60, "op": ">=", "value": 2}]}
    with pytest.raises(RuleCompileError):
        compile_rule("GATHER", {}, cond, scope="camera")
    assert compile_rule("GATHER", {}, cond, scope="group")["children"][0]["subject"] == "group_count"


def test_camera_leaf_allowed_on_group_scope():
    cond = {"op": "and", "children": [{"subject": "object_present", "label": "person"}]}
    out = compile_rule("DET_ZONE", {}, cond, scope="group")
    assert out["children"][0]["subject"] == "object_present"
```

- [ ] **Step 2: 运行确认失败**

- [ ] **Step 3: 实现**

- `leaves.py`：`group_count`（params `label`/`labels`/`window_sec`/`value`，ops 比较符）、`group_coverage`（params `window_sec`/`value`，ops 比较符），`implemented=True`。
- `compile.py`：
  - `_GROUP_LEAVES = {"group_count", "group_coverage"}`
  - `compile_rule(..., scope=None)`：`scope == "camera"` 且叶子 ∈ `_GROUP_LEAVES` → `RuleCompileError("group_* 叶子仅可用于相机组作用域的规则")`；`scope in (None, "group")` 放行（默认放行以兼容既有调用）。
  - `PARAM_TO_LEAF` 增加：`window_sec → {"group_count","group_coverage"}`（注意原 `window_sec → count_window` 需并存 → 把值类型从"单 subject"扩展为集合，或为组叶子单独加条目名如 `group_window_sec`；**采用后者以避免破坏既有映射语义**）。
  - 必填键校验：`group_count` → `("window_sec","value")`；`group_coverage` → `("window_sec","value")`。

- [ ] **Step 4: 测试 + 全量回归**

Run: `cd backend && uv run pytest tests/test_rule_capabilities.py tests/test_rule_compile.py -q` → 通过
Run: `cd backend && uv run pytest -q` → 全绿（对拍测试须保持一致）

- [ ] **Step 5: 提交**

```bash
git add backend/app/api/v1/module_video/scene/leaves.py backend/app/api/v1/module_video/scene/compile.py backend/tests/test_rule_capabilities.py backend/tests/test_rule_compile.py
git commit -m "feat(video): 组叶子接入能力注册表与编译期作用域校验"
```

---

### Task 5: 前端规则作用域选择

**Files:**
- Modify: `frontend/src/api/module_video/alarm.ts`（`group_id` 类型）
- Modify: `frontend/src/views/module_video/alarm/components/RuleEditor.vue`
- Modify: `frontend/src/views/module_video/alarm/index.vue`（列表/详情展示作用域 + 提交 `scope`）

- [ ] **Step 1: RuleEditor 增加作用域**

- 顶部新增「作用域」`el-radio-group`（相机 / 相机组）；
- 相机模式 → 相机下拉（既有数据源）；组模式 → 相机组下拉（`/video/camera/group/list`）；
- `v-model` 输出 `{ scope, camera_id, group_id, params, conditions }`；
- 条件树 `fields` 按 `scope` 过滤：`scope === "camera"` 时剔除 `group_count`/`group_coverage`。

- [ ] **Step 2: alarm/index.vue 集成**

- 提交带上 `scope`（仅用于前端选择，后端由 `camera_id`/`group_id` 判定）；
- 列表与详情展示作用域（相机名 / 组名）。

- [ ] **Step 3: 校验** → `cd frontend && pnpm run type-check`（0 新增）；仅本任务文件 lint 干净
- [ ] **Step 4: 提交**

```bash
git add frontend/src/api/module_video/alarm.ts frontend/src/views/module_video/alarm/components/RuleEditor.vue frontend/src/views/module_video/alarm/index.vue
git commit -m "feat(ui): 规则编辑器支持相机/相机组作用域选择"
```

---

### Task 6: e2e + 视觉核对

**Files:** `frontend/e2e/sp6a-rule-scope.spec.ts`、`docs/superpowers/runbooks/sp6a-visual.md` + 截图

- [ ] 建组规则（选相机组 + `group_count` 叶子）→ 保存 → 列表作用域显示组名；`pnpm run e2e -- sp6a-rule-scope` 通过；截图 + `vision-recognition` 核对。
- [ ] 提交 `test(ui): 规则作用域与聚合叶子 e2e 与视觉核对`

---

### Task 7: 真机联调

- [ ] 用同一视频源建**两台相机**并加入同一**相机组**；各自建单相机 `DET_ZONE` 任务并启动；
- [ ] 建**组规则**（`group_count window_sec=10 op=">=" value=2`，`interval_seconds=30`）；
- [ ] 断言：两台相机事件到达后组规则命中并产生**一条**告警（`rule_matched_list` 含组规则名）；单相机规则不受影响；
- [ ] 还原环境；结论写入 `.superpowers/sdd/sp6a-task-7-report.md`。

---

### Task 8: 总回归

- [ ] `cd backend && uv run pytest -q` + `uv run ruff check`（确认无本切片新增）
- [ ] `cd frontend && pnpm run type-check && pnpm run lint && pnpm run e2e`（SP6-a 用例通过；环境性抖动需隔离复跑确认）
- [ ] 报告写入 `.superpowers/sdd/sp6a-task-8-report.md`

---

## Self-Review

**Spec 覆盖：**

| Spec 条目 | 落点 |
|-----------|------|
| §3.1 `camera_id` 可空 + `group_id` + 恰有其一 | Task 1 |
| §3.2 作用域查询 + 多规则多条告警 + 返回体 | Task 2 |
| §3.3 `group_count` / `group_coverage`（去重键、窗口、fail-closed） | Task 3 |
| §3.4 能力注册表 + 编译期作用域校验 | Task 4 |
| §3.5 前端作用域选择 + 按 scope 过滤 fields | Task 5 |
| §4 验收（单测/e2e/截图/真机/回归） | Task 1-4 / 6 / 7 / 8 |
| §5 风险（语义变更锁定、track 去重歧义、叶子误用、组删除） | Task 2（单条不变 + 全量回归）、Task 3（键含 camera_id）、Task 4（编译校验）、Task 1（`ondelete=SET NULL`） |
| §6 兼容性（形参默认值、迁移仅该表） | Task 2/3/4（默认值）、Task 1（迁移） |

**类型一致性：** `query_multi` 返回键 `(camera_id, track_key)`（Task 3 定义与使用一致）；`group_camera_ids`（Task 3 定义）由 Task 2 的规则评估路径后续传入（Task 2 明确标注"本任务不加该形参"，避免与 Task 3 冲突）；`compile_rule(..., scope=)`（Task 4）与 Task 5 前端提交的 `scope` 语义一致（`camera|group`）。

**占位符扫描：** Task 1/3 含完整关键代码；Task 2 给出查询与聚合代码骨架并指明需扩展假会话（非 TODO，而是明确要求"写本文件专用最小假会话，不得 mock 评估逻辑"）；Task 4-8 含契约、命令与验收标准。
