# SP5-a 规则编辑器实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让用户能按「场景 → 参数表单（含 ROI/绊线画布）→ 条件树」创建可被云端求值器命中的告警规则，并持久化场景参数原值。

**Architecture:** 后端新增**叶子能力注册表**（单一事实源）与 `compile_rule` 编译/校验层，规则接口接受 `params` 并落库（新增 JSONB 列）；前端新增 `RuleEditor` 组合组件，条件树用 `@svar-ui/vue-filter`，ROI/绊线用 `vue-konva`。

**Tech Stack:** FastAPI + SQLAlchemy 2.0 + Pydantic v2 + Alembic；Vue 3 + Vite + Element Plus + TypeScript + Playwright；`@svar-ui/vue-filter`、`vue-konva` + `konva`。

**Spec:** `docs/superpowers/specs/2026-09-15-sp5a-rule-editor-design.md`

## Global Constraints

- 代码注释与提交信息一律**中文**；提交格式 `feat(video): …` / `feat(ui): …` / `test(ui): …`。
- 只 `git add` 本任务列出的文件；**禁止 `git add -A`**。
- 后端：`cd backend && uv run pytest -q` + `uv run ruff check` 全绿；**禁止新增后端依赖**。
- 前端：`cd frontend && pnpm run type-check && pnpm run lint`；**编辑器类 UI 必须用第三方组件，禁止手写**（用户强制）。
- 前端新增依赖仅允许 spec §3 选定的 `@svar-ui/vue-filter`、`vue-konva`、`konva`。
- 条件树 UI 只产 AND/OR；后端仍兼容一元 `not`。
- 时间/坐标一律归一化（0~1），禁止像素坐标入库。

---

### Task 1: 第三方组件集成 POC（前置闸门）

**Files:**
- Modify: `frontend/package.json`（新增依赖）
- Create: `frontend/src/views/module_video/alarm/components/__poc__/PocRoi.vue`
- Create: `frontend/src/views/module_video/alarm/components/__poc__/PocFilter.vue`
- Create: `frontend/src/views/module_video/alarm/components/__poc__/PocPage.vue`（临时路由页，Task 9 删除）
- Create: `docs/superpowers/runbooks/sp5a-poc.md`

**Interfaces:**
- Produces：两个组件的可用性结论 + `v-model` 契约草案（`RoiCanvas`：`[[x,y],...]` 归一化；`ConditionTree`：条件树 JSON）。

- [ ] **Step 1: 安装依赖**

```bash
cd frontend && pnpm add @svar-ui/vue-filter vue-konva konva
```
记录实际解析到的版本（`pnpm ls @svar-ui/vue-filter vue-konva konva`）。

- [ ] **Step 2: 阅读库文档与示例**

查阅 `node_modules/@svar-ui/vue-filter/README.md`、`node_modules/@svar-ui/vue-filter/docs/**`（若有）、以及 `node_modules/@svar-ui/vue-filter/dist/**/*.d.ts` 的类型定义；确认：
- `FilterBuilder` 的 `fields`/`options` 形状与输出事件名；
- 是否支持自定义 value 编辑组件（用于 polygon/select）；
- 是否支持禁用某个 field。

把结论写进 `docs/superpowers/runbooks/sp5a-poc.md`。

- [ ] **Step 3: 写 ROI 画布 POC**

`PocRoi.vue`：`v-stage` + `v-layer`，点击加点生成多边形 `polygon`，`v-line` 绘制闭合多边形，输出 `v-model` 为归一化点列；提供「清空」按钮与当前点列 JSON 展示。

- [ ] **Step 4: 写条件树 POC**

`PocFilter.vue`：用 `FilterBuilder` 渲染 2 个 field（如 `object_present`、`count`），实时展示输出的条件 JSON（贴到 `<pre>`）。

- [ ] **Step 5: 临时页面 + 无头截图**

`PocPage.vue` 同时渲染两个 POC；用 Playwright 临时脚本（不入库）或 `pnpm run dev` + 无头浏览器打开，截图保存到 `docs/superpowers/runbooks/sp5a-poc/`。

```
# 参考命令（按本机 playright 版本调整）
cd frontend && npx playwright screenshot --viewport-size=1440,900 "http://localhost:5180/#/poc/sp5a" ../docs/superpowers/runbooks/sp5a-poc/poc.png
```

- [ ] **Step 6: 视觉核对**

用 `vision-recognition` 技能识别截图，确认：ROI 多边形可绘制、条件树可增删行列、主题不至于与 Element Plus 割裂。

- [ ] **Step 7: 决策闸门**

- **通过** → 记录结论（含 `fields` 配置形状）到 runbook，继续 Task 2。
- **不通过** → **停止**，把阻塞点与替代候选（`@syncfusion/ej2-vue-querybuilder` 等）回报，等用户重新选型；**不得降级为手写实现**。

- [ ] **Step 8: 提交**

```bash
git add frontend/package.json frontend/pnpm-lock.yaml frontend/src/views/module_video/alarm/components/__poc__ docs/superpowers/runbooks/sp5a-poc.md docs/superpowers/runbooks/sp5a-poc
git commit -m "feat(ui): 规则编辑器第三方组件集成 POC（vue-filter + vue-konva）"
```

---

### Task 2: 叶子能力注册表 + 能力接口

**Files:**
- Create: `backend/app/api/v1/module_video/scene/leaves.py`
- Modify: `backend/app/api/v1/module_video/scene/controller.py`（新增只读接口）
- Test: `backend/tests/test_rule_capabilities.py`

**Interfaces:**
- Produces:
  - `LEAF_CAPABILITIES: dict[str, dict]`（`subject -> {label, implemented, params:[{key,type}], ops:[...]}`）
  - `IMPLEMENTED_LEAVES: set[str]`
  - `GET /api/v1/video/scene/rule-capabilities` → `{logic, leaves}`

- [ ] **Step 1: 写失败测试**

创建 `backend/tests/test_rule_capabilities.py`：

```python
"""叶子能力注册表测试：与求值器支持集必须一致（单一事实源对拍）。"""
from app.api.v1.module_video.inference.service import TEMPORAL_SUBJECTS
from app.api.v1.module_video.scene.leaves import IMPLEMENTED_LEAVES, LEAF_CAPABILITIES

# 求值器当前实际支持的非时序叶子（见 inference/service.py:_match_conditions）
_EVALUABLE_NON_TEMPORAL = {
    "attribute", "text_match", "ocr_label", "object_present", "zone_enter", "count",
}


def test_implemented_leaves_match_evaluator():
    expected = _EVALUABLE_NON_TEMPORAL | set(TEMPORAL_SUBJECTS)
    assert IMPLEMENTED_LEAVES == expected


def test_every_entry_declares_contract():
    for subject, cap in LEAF_CAPABILITIES.items():
        assert isinstance(cap.get("label"), str) and cap["label"], subject
        assert isinstance(cap.get("implemented"), bool), subject
        assert isinstance(cap.get("params"), list), subject
        assert isinstance(cap.get("ops"), list), subject
        for p in cap["params"]:
            assert isinstance(p.get("key"), str) and isinstance(p.get("type"), str), subject


def test_implemented_flags_consistent():
    for subject, cap in LEAF_CAPABILITIES.items():
        assert cap["implemented"] is (subject in IMPLEMENTED_LEAVES), subject


def test_unimplemented_leaves_listed_for_ui():
    """未实现叶子必须列出（供前端置灰），至少覆盖人脸/姿态类。"""
    assert {"face_match", "liveness", "keypoint_geometry"} <= set(LEAF_CAPABILITIES)
    for s in ("face_match", "liveness", "keypoint_geometry"):
        assert LEAF_CAPABILITIES[s]["implemented"] is False


def test_rule_capabilities_api(test_client, auth_headers):
    resp = test_client.get("/api/v1/video/scene/rule-capabilities", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert set(data["logic"]) >= {"and", "or"}
    subjects = {x["subject"] for x in data["leaves"]}
    assert "object_present" in subjects and "line_cross" in subjects
```

- [ ] **Step 2: 运行确认失败**

Run: `cd backend && uv run pytest tests/test_rule_capabilities.py -q`
Expected: FAIL（模块不存在）

- [ ] **Step 3: 实现注册表**

创建 `backend/app/api/v1/module_video/scene/leaves.py`，内容按 spec §4.2 的 `LEAF_CAPABILITIES` 全量落地（已实现 10 个 + 未实现清单），并：

```python
IMPLEMENTED_LEAVES: set[str] = {s for s, c in LEAF_CAPABILITIES.items() if c["implemented"]}
LOGIC_OPS: list[str] = ["and", "or", "not"]


def get_capabilities() -> dict:
    """能力接口载荷：逻辑算子 + 全部叶子描述。"""
    return {"logic": LOGIC_OPS, "leaves": [{"subject": s, **c} for s, c in LEAF_CAPABILITIES.items()]}
```

- [ ] **Step 4: 新增只读接口**

在 `scene/controller.py` 增加（沿用该文件既有的 `AuthPermission` 与 `SuccessResponse` 写法）：

```python
@router.get("/rule-capabilities", summary="规则叶子能力")
async def rule_capabilities(_=Depends(AuthPermission(["video:scene:catalog"]))):
    return SuccessResponse(data=get_capabilities(), msg="获取成功")
```

> 路由须在 `/scene/catalog/{code}` 之前或以不冲突的路径注册；静态路由已在 `register_routers()` 显式接线，确认该 controller 的路由前缀为 `/video/scene`。

- [ ] **Step 5: 运行测试**

Run: `cd backend && uv run pytest tests/test_rule_capabilities.py -q` → 全通过

- [ ] **Step 6: 提交**

```bash
git add backend/app/api/v1/module_video/scene/leaves.py backend/app/api/v1/module_video/scene/controller.py backend/tests/test_rule_capabilities.py
git commit -m "feat(video): 规则叶子能力注册表与能力接口"
```

---

### Task 3: params 字段 + 编译层

**Files:**
- Modify: `backend/app/api/v1/module_video/alarm/model.py`
- Modify: `backend/app/api/v1/module_video/alarm/schema.py`
- Create: `backend/app/api/v1/module_video/scene/compile.py`
- Create: `backend/…` Alembic 迁移（由 CLI 生成）
- Test: `backend/tests/test_rule_compile.py`

**Interfaces:**
- Consumes: `LEAF_CAPABILITIES`、`IMPLEMENTED_LEAVES`（Task 2）。
- Produces:
  - `PARAM_TO_LEAF: dict[str, tuple[str, str | set[str] | None]]`
  - `compile_rule(scene_type: str | None, params: dict | None, conditions: dict | None) -> dict`
  - `RuleCompileError(Exception)`
  - `AlarmRuleModel.params` / `AlarmRuleCreate.params` / `AlarmRuleUpdate.params` / 出参 `params`

- [ ] **Step 1: 写失败测试**

创建 `backend/tests/test_rule_compile.py`：

```python
"""规则编译层测试：参数注入 + 条件校验。"""
import pytest

from app.api.v1.module_video.scene.compile import RuleCompileError, compile_rule

ROI = [[0.1, 0.1], [0.9, 0.1], [0.9, 0.9], [0.1, 0.9]]
LINE = [[0.5, 0.0], [0.5, 1.0]]


def _and(*leaves):
    return {"op": "and", "children": list(leaves)}


def test_injects_roi_into_region_leaves():
    cond = _and({"subject": "object_present", "label": "person"})
    out = compile_rule("DET_ZONE", {"roi": ROI}, cond)
    leaf = out["children"][0]
    assert leaf["region"] == ROI
    assert leaf["label"] == "person"


def test_direction_overrides_leaf_dir():
    """direction 参数必须覆盖 LINE_CROSS 默认规则的 dir 预填值。"""
    cond = _and({"subject": "line_cross", "dir": "A2B"})
    out = compile_rule("LINE_CROSS", {"line": LINE, "direction": "B2A"}, cond)
    leaf = out["children"][0]
    assert leaf["line"] == LINE
    assert leaf["dir"] == "B2A"


def test_missing_param_keeps_leaf_default():
    cond = _and({"subject": "line_cross", "dir": "A2B"})
    out = compile_rule("LINE_CROSS", {}, cond)
    assert out["children"][0]["dir"] == "A2B"
    assert "line" not in out["children"][0]


def test_threshold_and_window_injection():
    cond = _and(
        {"subject": "object_present"},
        {"subject": "count_window", "op": ">=", "value": 5},
    )
    out = compile_rule("GATHER", {"confidence_threshold": 0.6, "window_sec": 8, "count": 3}, cond)
    present, cw = out["children"]
    assert present["min_confidence"] == 0.6
    assert cw["window_sec"] == 8 and cw["value"] == 3


def test_empty_conditions_returns_empty_dict():
    assert compile_rule("DET_ZONE", {"roi": ROI}, None) == {}
    assert compile_rule("DET_ZONE", {"roi": ROI}, {}) == {}


def test_rejects_unknown_subject():
    with pytest.raises(RuleCompileError):
        compile_rule("DET_ZONE", {}, _and({"subject": "nope"}))


def test_rejects_unimplemented_subject():
    with pytest.raises(RuleCompileError):
        compile_rule("FACE_REC", {}, _and({"subject": "face_match", "op": "gte", "value": 0.6}))


def test_rejects_missing_required_key():
    with pytest.raises(RuleCompileError):
        compile_rule("DET_ZONE", {}, _and({"subject": "attribute", "op": "lt"}))  # 缺 field/value


def test_rejects_bad_op_and_bad_value():
    with pytest.raises(RuleCompileError):
        compile_rule("OVERCROWD", {}, _and({"subject": "count", "op": "~", "value": 3}))
    with pytest.raises(RuleCompileError):
        compile_rule("OVERCROWD", {}, _and({"subject": "count", "op": ">=", "value": "x"}))


def test_rejects_malformed_region():
    with pytest.raises(RuleCompileError):
        compile_rule("DET_ZONE", {"roi": [[0.1, 0.1]]}, _and({"subject": "object_present"}))


def test_not_node_is_preserved():
    cond = {"op": "not", "children": [{"subject": "object_present", "label": "person"}]}
    out = compile_rule("DET_ZONE", {}, cond)
    assert out["op"] == "not"
```

- [ ] **Step 2: 运行确认失败**

Run: `cd backend && uv run pytest tests/test_rule_compile.py -q` → FAIL（模块不存在）

- [ ] **Step 3: 实现编译层**

创建 `backend/app/api/v1/module_video/scene/compile.py`：

```python
"""规则编译层：把场景参数展开进条件树，并校验条件的可求值性。

求值器（inference/service.py）只认具体数值/点列，本模块是唯一把 params
落成可评估 conditions 的地方，保证前后端无口径漂移（spec §4.3/§4.4）。
"""
from app.api.v1.module_video.scene.leaves import LEAF_CAPABILITIES, IMPLEMENTED_LEAVES

LOGIC_OPS = ("and", "or", "not")
# 参数键 -> (叶子键, 适用 subject 集合 | 单个 subject | None=所有声明该键的叶子)
PARAM_TO_LEAF: dict[str, tuple[str, object]] = {
    "roi": ("region", None),
    "line": ("line", "line_cross"),
    "direction": ("dir", "line_cross"),
    "labels": ("labels", {"object_present", "count", "count_window", "dwell", "absence", "line_cross"}),
    "confidence_threshold": ("min_confidence", "object_present"),
    "count": ("value", {"count", "count_window"}),
    "window_sec": ("window_sec", "count_window"),
    "dwell_sec": ("min_sec", "dwell"),
    "min_sec": ("min_sec", "dwell"),
    "gap_sec": ("gap_sec", "absence"),
    "pattern": ("regex", "text_match"),
}
_NUMERIC_TYPES = {"int", "float"}
_POINT_LIST_TYPES = {"polygon", "polyline", "point"}
_NUMERIC_OPS = {">=", ">", "<=", "<", "=="}


class RuleCompileError(Exception):
    """条件树非法（不可求值）。"""


def _is_num(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _valid_points(v) -> bool:
    if not isinstance(v, (list, tuple)) or len(v) < 2:
        return False
    for p in v:
        if not isinstance(p, (list, tuple)) or len(p) < 2:
            return False
        if not (_is_num(p[0]) and _is_num(p[1])):
            return False
    return True


def _applicable(target, subject: str) -> bool:
    if target is None:
        return True
    if isinstance(target, str):
        return target == subject
    return subject in target


def _injects(cap: dict, key: str) -> bool:
    """该叶子是否声明了此键（决定 roi=region 这类 None 绑定的适用范围）。"""
    return any(p.get("key") == key for p in cap.get("params", []))


def _validate_leaf(subject: str, leaf: dict) -> None:
    cap = LEAF_CAPABILITIES.get(subject)
    if cap is None:
        raise RuleCompileError(f"未知叶子 subject={subject!r}")
    if not cap["implemented"]:
        raise RuleCompileError(f"叶子 subject={subject!r} 尚未实现，暂不支持配置")
    ops = cap.get("ops") or []
    if ops:
        op = leaf.get("op")
        if op not in ops:
            raise RuleCompileError(f"叶子 {subject} 的 op={op!r} 不受支持，可用 {ops}")
    for p in cap["params"]:
        key, typ = p["key"], p["type"]
        if key not in leaf:
            # 非必填键：region/labels/track_id/label/labels/min_confidence 可缺省
            continue
        val = leaf[key]
        if typ in _NUMERIC_TYPES and not _is_num(val):
            raise RuleCompileError(f"叶子 {subject} 的 {key} 必须为数值，实际 {val!r}")
        if typ in _POINT_LIST_TYPES and not _valid_points(val):
            raise RuleCompileError(f"叶子 {subject} 的 {key} 必须为点列 [[x,y],...]")
    # attribute/text_match/count 的语义必填键（求值器硬依赖）
    required = {"attribute": ("field", "value"), "text_match": ("regex",), "ocr_label": ("contains",),
                "count": ("value",), "count_window": ("window_sec", "value"),
                "dwell": ("min_sec",), "absence": ("gap_sec",)}
    for key in required.get(subject, ()):
        if key not in leaf:
            raise RuleCompileError(f"叶子 {subject} 缺少必填键 {key}")


def _compile_node(node, params: dict):
    if not isinstance(node, dict):
        raise RuleCompileError("条件节点必须为对象")
    op = node.get("op")
    if op in LOGIC_OPS:
        kids = node.get("children") or []
        if not isinstance(kids, (list, tuple)):
            raise RuleCompileError("逻辑节点 children 必须为数组")
        return {"op": op, "children": [_compile_node(k, params) for k in kids]}
    subject = node.get("subject")
    if not isinstance(subject, str):
        raise RuleCompileError("叶子缺少 subject")
    out = dict(node)
    for pkey, (leafkey, target) in PARAM_TO_LEAF.items():
        if pkey not in params:
            continue
        if not _applicable(target, subject):
            continue
        cap = LEAF_CAPABILITIES.get(subject) or {}
        if leafkey != "region" and not _injects(cap, leafkey):
            continue
        out[leafkey] = params[pkey]
    _validate_leaf(subject, out)
    return out


def compile_rule(scene_type, params, conditions):
    """校验并展开条件树；空条件返回 {}（求值器视为匹配一切）。"""
    if not conditions:
        return {}
    if not isinstance(conditions, dict):
        raise RuleCompileError("conditions 必须为对象")
    return _compile_node(conditions, params or {})
```

- [ ] **Step 4: 运行测试**

Run: `cd backend && uv run pytest tests/test_rule_compile.py -q` → 全通过

- [ ] **Step 5: 加 params 列与 schema**

- `alarm/model.py`：`AlarmRuleModel` 增加

```python
    params: Mapped[dict] = mapped_column(JSONB, default=dict, server_default="{}", comment="场景参数原值")
```

（沿用该文件既有的 `JSONB` 导入与类型标注风格。）
- `alarm/schema.py`：`AlarmRuleCreate`/`AlarmRuleUpdate`/出参 schema 增加 `params: dict = Field(default_factory=dict, description="场景参数原值")`。

- [ ] **Step 6: 生成并执行迁移**

```bash
cd backend && uv run main.py revision --env=dev && uv run main.py upgrade --env=dev
```
检查生成的迁移脚本只含 `alarm_rule.params` 的加列（`server_default="{}"`）。

- [ ] **Step 7: 提交**

```bash
git add backend/app/api/v1/module_video/scene/compile.py backend/app/api/v1/module_video/alarm/model.py backend/app/api/v1/module_video/alarm/schema.py backend/tests/test_rule_compile.py backend/alembic/versions/<新迁移>.py
git commit -m "feat(video): 规则参数编译层与 params 字段"
```

---

### Task 4: 规则接口接入编译校验

**Files:**
- Modify: `backend/app/api/v1/module_video/alarm/service.py`
- Test: `backend/tests/test_alarm_rule_params.py`

**Interfaces:**
- Consumes: `compile_rule`、`RuleCompileError`（Task 3）。
- Produces: create/update 在写库前调用编译；`params` 参与持久化。

- [ ] **Step 1: 写失败测试**

创建 `backend/tests/test_alarm_rule_params.py`（用 `test_client`/`auth_headers` fixture）：

```python
"""规则接口：params 持久化 + 条件编译校验。"""
ROI = [[0.1, 0.1], [0.9, 0.1], [0.9, 0.9], [0.1, 0.9]]


def _body(camera_id):
    return {
        "name": "编译规则", "camera_id": camera_id, "alarm_type": "DET_ZONE",
        "severity": "WARNING", "interval_seconds": 30, "status": True,
        "params": {"roi": ROI, "confidence_threshold": 0.6},
        "conditions": {"op": "and", "children": [{"subject": "object_present", "label": "person"}]},
    }


def test_create_rule_compiles_and_persists_params(test_client, auth_headers, a_camera_id):
    resp = test_client.post("/api/v1/video/alarm/rule/create", headers=auth_headers, json=_body(a_camera_id))
    assert resp.status_code == 200, resp.text
    rid = resp.json()["data"]["id"]
    detail = test_client.get(f"/api/v1/video/alarm/rule/detail/{rid}", headers=auth_headers).json()["data"]
    assert detail["params"]["roi"] == ROI
    leaf = detail["conditions"]["children"][0]
    assert leaf["region"] == ROI and leaf["min_confidence"] == 0.6


def test_create_rule_rejects_invalid_conditions(test_client, auth_headers, a_camera_id):
    body = _body(a_camera_id)
    body["conditions"] = {"op": "and", "children": [{"subject": "nope"}]}
    resp = test_client.post("/api/v1/video/alarm/rule/create", headers=auth_headers, json=body)
    assert resp.status_code == 400
```

> `a_camera_id` fixture：若 tests 目录无现成 fixture，则在测试内先调用摄像机创建接口或复用已有测试的建机流程（参考 `tests/test_alarm_rule_match.py` 的写法）。**不要**mock 掉编译层。

- [ ] **Step 2: 运行确认失败**

Run: `cd backend && uv run pytest tests/test_alarm_rule_params.py -q` → FAIL（params 未落库/非法条件未拒绝）

- [ ] **Step 3: 接入编译**

在 `alarm/service.py` 的 create/update 路径（写库前）：

```python
from app.api.v1.module_video.scene.compile import RuleCompileError, compile_rule

        data = obj_in.model_dump() if hasattr(obj_in, "model_dump") else dict(obj_in)
        try:
            data["conditions"] = compile_rule(data.get("alarm_type"), data.get("params"), data.get("conditions"))
        except RuleCompileError as e:
            raise CustomException(msg=f"规则条件非法：{e}")
```

（`CustomException` 按该模块既有导入；确认其默认 HTTP 400。）

- [ ] **Step 4: 运行测试**

Run: `cd backend && uv run pytest tests/test_alarm_rule_params.py tests/test_rule_compile.py tests/test_alarm_rule_match.py -q` → 全通过

- [ ] **Step 5: 全量回归 + lint**

Run: `cd backend && uv run pytest -q` → 全通过
Run: `cd backend && uv run ruff check` → `All checks passed!`

- [ ] **Step 6: 提交**

```bash
git add backend/app/api/v1/module_video/alarm/service.py backend/tests/test_alarm_rule_params.py
git commit -m "feat(video): 规则创建/更新接入条件编译校验"
```

---

### Task 5: 前端 API + RoiCanvas 组件

**Files:**
- Create: `frontend/src/api/module_video/scene.ts`
- Create: `frontend/src/views/module_video/alarm/components/RoiCanvas.vue`
- Modify: `frontend/src/api/module_video/alarm.ts`（类型标注 `params`）

**Interfaces:**
- Produces:
  - `getSceneCatalog(params?)`、`getSceneDetail(code)`、`getRuleCapabilities()`
  - `RoiCanvas` props：`mode: "polygon" | "polyline"`、`background?: string`；`v-model`：`number[][]`（归一化）

- [ ] **Step 1: 写 API 封装**

创建 `frontend/src/api/module_video/scene.ts`（沿用 `@/utils/request` 与既有模块写法）：

```ts
import request from "@/utils/request";

export function getSceneCatalog(params?: any) {
  return request({ url: "/video/scene/catalog", method: "get", params });
}

export function getSceneDetail(code: string) {
  return request({ url: `/video/scene/catalog/${code}`, method: "get" });
}

export function getRuleCapabilities() {
  return request({ url: "/video/scene/rule-capabilities", method: "get" });
}
```

- [ ] **Step 2: 写 RoiCanvas**

`RoiCanvas.vue`：`vue-konva` 的 `v-stage`/`v-layer`/`v-line`/`v-circle`/`v-image`。
要求：
- 点击空白处按序加点；多边形闭合（`closed: true`），折线不闭合；
- 顶点可拖拽（`v-circle` `draggable` + `dragend` 回写）；
- 「撤销」删最后一点、「清空」清空；
- 归一化：内部 `x/width`、`y/height`，`v-model` 进出均为 `[[x,y],...]`（0~1，保留 6 位小数）；
- 容器尺寸自适应（`ResizeObserver`），底图等比铺满（`object-fit: contain` 语义按 stage 宽高比处理）。

- [ ] **Step 3: 类型检查**

Run: `cd frontend && pnpm run type-check` → 通过

- [ ] **Step 4: 提交**

```bash
git add frontend/src/api/module_video/scene.ts frontend/src/views/module_video/alarm/components/RoiCanvas.vue frontend/src/api/module_video/alarm.ts
git commit -m "feat(ui): 场景接口封装与 ROI/绊线画布组件"
```

---

### Task 6: 条件树组件（vue-filter 封装）

**Files:**
- Create: `frontend/src/views/module_video/alarm/components/ConditionTree.vue`

**Interfaces:**
- Consumes: `getRuleCapabilities()`（Task 5）、POC 结论（Task 1 runbook）。
- Produces: `ConditionTree` props：`modelValue: object`（条件树 JSON）、`sceneType?: string`；`v-model` 双向。

- [ ] **Step 1: 实现封装**

按 Task 1 记录的 `@svar-ui/vue-filter` 用法，把 `LEAF_CAPABILITIES` 编译为 `fields`：
- 每个 `implemented` 叶子一个 field（`label` 用中文名）；
- `operators` 来自叶子 `ops`（空则给默认 `is`）；
- 叶子参数按 §4.6 的 `type` 分派编辑器（复用 Task 5 的 `RoiCanvas` 处理 polygon/polyline）；
- `implemented === false` 的叶子在此场景下隐藏（不渲染进 `fields`），但保留在 `unavailableLeaves` 提示区展示（置灰列表 + "未实现"标签）；
- 输出：把库的 JSON 转成后端条件树（`{op, children:[{subject, ...}]}`）；输入：反向解析。
- **只产 AND/OR**；若解析到一元 `not`（历史数据），以只读提示展示，不允许在 UI 新建。

- [ ] **Step 2: 类型检查 + lint**

Run: `cd frontend && pnpm run type-check && pnpm run lint`

- [ ] **Step 3: 提交**

```bash
git add frontend/src/views/module_video/alarm/components/ConditionTree.vue
git commit -m "feat(ui): 条件树组件（vue-filter 封装，按能力注册表驱动）"
```

---

### Task 7: RuleEditor 与页面集成

**Files:**
- Create: `frontend/src/views/module_video/alarm/components/SceneParamsForm.vue`
- Create: `frontend/src/views/module_video/alarm/components/RuleEditor.vue`
- Modify: `frontend/src/views/module_video/alarm/index.vue`

**Interfaces:**
- Consumes: `RoiCanvas`、`ConditionTree`、`getSceneCatalog`、`getRuleCapabilities`。
- Produces: `RuleEditor` props：`sceneType: string`、`modelValue: {params, conditions}`；`v-model` 双向；校验方法 `validate()`。

- [ ] **Step 1: SceneParamsForm**

按 `catalog.param_schema` 渲染：`polygon`/`polyline`/`point` → `RoiCanvas`；`int`/`float` → `el-input-number`；`str` → `el-input`；`list` → `el-select multiple allow-create`（`default` 作初始项）；`bool` → `el-switch`。输出 `params` 对象。

- [ ] **Step 2: RuleEditor**

编排：场景 `el-select`（来自 `getSceneCatalog`）→ 载入 `param_schema` + `default_rule` → `SceneParamsForm` → `ConditionTree`（初始值 = `default_rule`）→ 底部实时预览「即将保存的条件 JSON」（只读 `<pre>`）。

- [ ] **Step 3: 集成 alarm/index.vue**

- 规则对话框内嵌 `RuleEditor`，`ruleForm` 增加 `scene_type`/`params`/`conditions`；
- 保存时提交 `{...ruleForm, algorithm_type: scene_type, params, conditions}`；
- 编辑时用 detail 的 `params` + `conditions` 回填；
- 保留既有字段（name/camera/severity/sensitivity/interval/status/description）不动。

- [ ] **Step 4: 类型检查 + lint**

Run: `cd frontend && pnpm run type-check && pnpm run lint`

- [ ] **Step 5: 提交**

```bash
git add frontend/src/views/module_video/alarm/components/SceneParamsForm.vue frontend/src/views/module_video/alarm/components/RuleEditor.vue frontend/src/views/module_video/alarm/index.vue
git commit -m "feat(ui): 规则编辑器组件与告警规则页集成"
```

---

### Task 8: Playwright e2e + 视觉核对

**Files:**
- Create: `frontend/e2e/sp5a-rule-editor.spec.ts`
- Create: `docs/superpowers/runbooks/sp5a-visual.md`（截图与结论）

**Interfaces:**
- Consumes: 全部前端组件。

- [ ] **Step 1: 读现有 e2e 写法**

Run: `cd frontend && ls e2e`，并阅读 1 个既有 spec，复用其登录/导航 helper。

- [ ] **Step 2: 写 e2e**

覆盖：登录 → `/video/alarm`（按既有路由 hash）→ 切到「告警规则」→ 新建 → 选场景 `DET_ZONE` → 在画布上点 4 个点生成 ROI → 条件树加一个 `object_present` 叶子 → 保存 → 列表出现新规则 → 重新打开 → 断言 ROI 点列与条件树回填一致。

- [ ] **Step 3: 运行 e2e**

Run: `cd frontend && pnpm run e2e -- sp5a-rule-editor` → 全通过

- [ ] **Step 4: 无头截图 + 视觉核对**

对「规则编辑器对话框（含画布 ROI 与条件树）」截图，用 `vision-recognition` 技能核对：与既有模块（`module_system/param` 风格）一致、无严重样式割裂；把截图与结论写入 `docs/superpowers/runbooks/sp5a-visual.md`。

- [ ] **Step 5: 提交**

```bash
git add frontend/e2e/sp5a-rule-editor.spec.ts docs/superpowers/runbooks/sp5a-visual.md docs/superpowers/runbooks/sp5a-visual
git commit -m "test(ui): 规则编辑器 e2e 与视觉核对"
```

---

### Task 9: 清理与总回归

**Files:**
- Delete: `frontend/src/views/module_video/alarm/components/__poc__/`（及临时路由）

- [ ] **Step 1: 删除 POC 页面与临时路由**

删除 `__poc__/` 目录与 `frontend/src/router` 中临时加的 `/poc/sp5a` 路由（若有）。

- [ ] **Step 2: 后端总回归**

Run: `cd backend && uv run pytest -q` → 全通过
Run: `cd backend && uv run ruff check` → `All checks passed!`

- [ ] **Step 3: 前端总检查**

Run: `cd frontend && pnpm run type-check && pnpm run lint && pnpm run e2e` → 全通过

- [ ] **Step 4: 提交**

```bash
git add -u frontend/src/views/module_video/alarm/components/__poc__ frontend/src/router
git commit -m "chore(ui): 移除规则编辑器 POC 临时页面"
```

---

## Self-Review

**Spec 覆盖：**

| Spec 条目 | 落点 |
|-----------|------|
| §3.1 条件树选型 `@svar-ui/vue-filter` | Task 1（POC 闸门）+ Task 6 |
| §3.2 画布选型 `vue-konva`+`konva` | Task 1 + Task 5 |
| §4.1 `params` 列 + 迁移 | Task 3 Step 5-6 |
| §4.2 叶子能力注册表 + 接口 | Task 2 |
| §4.3 `PARAM_TO_LEAF` + 注入语义（参数覆盖同名键） | Task 3 Step 3 + 测试 `test_direction_overrides_leaf_dir` |
| §4.4 `compile_rule` 校验/展开 | Task 3 |
| §4.5 接口变更（capabilities + create/update 编译） | Task 2 + Task 4 |
| §4.6 前端组件（RuleEditor/SceneParamsForm/RoiCanvas/ConditionTree + api） | Task 5-7 |
| §4.7 视觉约束与截图核对 | Task 8 |
| §5 测试与验收（单测/对拍/e2e/截图） | Task 2-4 单测、Task 8 e2e+截图、Task 9 总回归 |
| §5 POC 前置闸门与回退 | Task 1 Step 7 |

**类型一致性：** `compile_rule(scene_type, params, conditions)` 签名在 Task 3 定义、Task 4 调用一致；`LEAF_CAPABILITIES`/`IMPLEMENTED_LEAVES` 在 Task 2 定义、Task 3 消费一致；`RoiCanvas` 的 `v-model: number[][]` 在 Task 5 定义、Task 6/7 使用一致；`getRuleCapabilities()` 在 Task 5 定义、Task 6 消费一致。

**占位符扫描：** 后端任务含完整代码与预期输出；Task 1（POC）与前端组件任务因依赖第三方库 API，给出明确契约、行为要求与验收命令（非 TODO 占位），并由 Task 1 的闸门先行锁定 API 形态。
