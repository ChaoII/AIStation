# 场景注册表 + PED_ATTR 纵切片（AIStation 侧）Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans. Steps use checkbox (`- [ ]`).

**Goal:** 把「任务类型目录」落成 AIStation 的**场景注册表**核心资产，并打通 `PED_ATTR`（工作服/安全帽）纵切片的云端侧：场景编译为 Agent pipeline TaskConfig、事件 v2 归一化、属性规则判定。

**Architecture:** 新增静态 `module_video/scene/`（`catalog.py` 单一事实源 + API）；`AlgorithmModel` 增 `scene_type`；`build_agent_task_config` 按场景产出多模型 pipeline；`normalize_edge_event` 把事件 v2 的 `objects[]` 归一化为既有 `detections`；`AlarmRuleModel` 增 `conditions`，在 `process_detection_callback` 内做属性规则判定。

**Tech Stack:** FastAPI + SQLAlchemy 2.0 + Pydantic v2 + pytest（`asyncio.run`，无 pytest-asyncio）。

**Spec:** `docs/superpowers/specs/2026-09-14-visual-deployment-program-design.md`（§3 目录 / §4 注册表 / §5 契约 / §6 规则 / §7 切片）
**配套处理计划:** `2026-09-14-scene-registry-ped-attr-modeldeploy.md`（Plan B，另仓库）

## Global Constraints

- 后端 `D:\AIStation\backend`；`uv run pytest` / `uv run ruff check`（只判新增）。
- 中文注释；提交 `feat(video): …` / `fix(video): …`；**禁 `git add -A`**；工作区存在无关改动（`.gitignore`、`module_ai`、`backend/data/` 等），只 add 本任务文件。
- 不做 Alembic 迁移：新列用 `init_app._ensure_missing_columns` 兜底（`video_algorithms.scene_type`、`video_alarm_rules.conditions`）。
- 向后兼容：事件 v1（`detections`）继续可用；TaskConfig 新增字段可选。
- 不新增依赖。

---

### Task 1: 场景注册表模块（任务类型目录核心资产）

**Files:**
- Create: `backend/app/api/v1/module_video/scene/__init__.py`
- Create: `backend/app/api/v1/module_video/scene/catalog.py`
- Create: `backend/app/api/v1/module_video/scene/schema.py`
- Create: `backend/app/api/v1/module_video/scene/controller.py`
- Modify: `backend/app/api/v1/module_video/__init__.py`（注册 SceneRouter）
- Test: `backend/tests/test_scene_catalog.py`

**Interfaces:**
- Produces: `catalog.py`：
  - `@dataclass(frozen=True) SceneDef(code, name, category, scene_type, model_families, pipeline, param_schema, default_rule, needs_tracking, description)`
  - `SCENES: dict[str, SceneDef]`（覆盖 spec §3 全部场景码）
  - `get_scene(code) -> SceneDef | None`、`list_scenes() -> list[SceneDef]`
- Produces API：`GET /video/scene/catalog`（列表，支持 `category` 过滤）、`GET /video/scene/catalog/{code}`（详情；404）。
- Consumes：`AuthPermission`、`SuccessResponse`、`OperationLogRoute`。

- [ ] **Step 1: 写失败测试**

创建 `backend/tests/test_scene_catalog.py`：

```python
"""场景注册表（任务类型目录）测试。"""
from app.api.v1.module_video.scene.catalog import SCENES, get_scene, list_scenes


def test_catalog_contains_core_scenes():
    for code in ("DET_ZONE", "LINE_CROSS", "GATHER", "PED_ATTR", "OCR_TEXT", "LPR", "FACE_REC"):
        assert code in SCENES, code
        assert SCENES[code].name and SCENES[code].scene_type


def test_ped_attr_pipeline_and_params():
    s = get_scene("PED_ATTR")
    assert s is not None
    assert s.model_families == ["pedestrian_attribute"]
    roles = {p["role"] for p in s.pipeline}
    assert roles == {"det", "cls"}
    keys = {p["key"] for p in s.param_schema}
    assert {"attributes", "roi", "confidence_threshold", "cls_threshold"} <= keys
    assert s.needs_tracking is False


def test_list_scenes_filter_by_category():
    tracks = list_scenes(category="tracking")
    assert all(x.category == "tracking" for x in tracks)
    assert list_scenes()  # 非空


def test_get_scene_missing():
    assert get_scene("NOPE") is None
```

- [ ] **Step 2: 运行确认失败**

Run: `cd backend && uv run pytest tests/test_scene_catalog.py -q`
Expected: FAIL（`ModuleNotFoundError: ...scene.catalog`）

- [ ] **Step 3: 实现 `catalog.py`（全量目录）**

结构（节选示例，实施时按 spec §3 补全全部场景码）：

```python
"""任务类型目录（场景注册表）——单一事实源。

每个场景定义：所需模型 pipeline、参数 schema、默认规则、所需边缘能力。
对齐 spec: docs/superpowers/specs/2026-09-14-visual-deployment-program-design.md §3/§4。
"""
from dataclasses import dataclass, field


@dataclass(frozen=True)
class SceneDef:
    code: str
    name: str
    category: str            # detection/tracking/classification/pose/seg/obb/face/lpr/ocr/doc/other
    scene_type: str          # 与 code 一致（写入 TaskConfig.scene_type）
    model_families: list[str]
    pipeline: list[dict]     # [{"role":"det","type":"detection"},{"role":"cls","type":"classification"}]
    param_schema: list[dict] # [{"key":"roi","type":"polygon"},...]
    default_rule: dict = field(default_factory=dict)
    needs_tracking: bool = False
    description: str = ""


_POLY = {"key": "roi", "type": "polygon", "label": "检测区域"}
_CONF = {"key": "confidence_threshold", "type": "float", "default": 0.4, "label": "置信度"}
_DET = {"role": "det", "type": "detection"}
_CLS = {"role": "cls", "type": "classification"}

SCENES: dict[str, SceneDef] = {}


def _add(s: SceneDef) -> None:
    SCENES[s.code] = s


_add(SceneDef("PED_ATTR", "工作服/安全帽/反光衣/安全带", "attribute", "PED_ATTR",
              ["pedestrian_attribute"], [_DET, _CLS],
              [_POLY, _CONF,
               {"key": "cls_threshold", "type": "float", "default": 0.5, "label": "属性阈值"},
               {"key": "attributes", "type": "list", "label": "属性标签",
                "default": ["safety_helmet", "reflective_vest", "safety_rope", "work_uniform"]}],
              {"op": "and", "children": [{"subject": "attribute", "field": "work_uniform", "op": "lt", "value": 0.5}]},
              False, "人体检测 + 多标签属性分类"))

_add(SceneDef("DET_ZONE", "区域入侵", "detection", "DET_ZONE", ["det"], [_DET],
              [_POLY, _CONF, {"key": "labels", "type": "list", "default": ["person"]}],
              {"op": "and", "children": [{"subject": "object_present", "label": "person", "region": "roi"}]},
              False, "区域内出现目标"))
# …按 spec §3 继续补全：LINE_CROSS/LOITER/GATHER/OVERCROWD/ABSENT/ILLEGAL_PARK/ABANDON/FIRE_SMOKE/
#   TRAFFIC_DET/SCENE_CLS/DEFECT_CLS/ACTION_CLS/ACTION_SKELETON/FALL/SMOKE_PHONE/CLIMB/NO_MASK/
#   HAND_GESTURE/I_SEG/SEM_AREA/SAM_SEG/OBB_DET/FACE_DET/FACE_REC/STRANGER/FACE_ATTR/FACE_ANTISPOOF/
#   FACE_LANDMARK/FACE_CROWD/LPR/LPR_LIST/OCR_TEXT/METER_OCR/DOC_TABLE/BARCODE/DEPTH_SAFE/REID_TRACK/DEPLOY_TRACK


def get_scene(code: str) -> SceneDef | None:
    return SCENES.get(code)


def list_scenes(category: str | None = None) -> list[SceneDef]:
    items = list(SCENES.values())
    if category:
        items = [s for s in items if s.category == category]
    return items
```

- [ ] **Step 4: 实现 `schema.py` + `controller.py` 并注册**

`schema.py`：`SceneOutSchema`（code/name/category/scene_type/model_families/pipeline/param_schema/default_rule/needs_tracking/description）用 `BaseModel`。

`controller.py`：

```python
from dataclasses import asdict
from fastapi import APIRouter, Depends, Path
from fastapi.responses import JSONResponse
from app.api.v1.module_system.auth.schema import AuthSchema
from app.common.response import SuccessResponse
from app.core.dependencies import AuthPermission
from app.core.router_class import OperationLogRoute
from .catalog import get_scene, list_scenes

SceneRouter = APIRouter(route_class=OperationLogRoute, prefix="/scene", tags=["场景目录"])


@SceneRouter.get("/catalog", summary="查询任务类型目录")
async def list_scene_catalog_controller(
    category: str | None = None,
    auth: AuthSchema = Depends(AuthPermission(["module_video:algorithm:query"])),
) -> JSONResponse:
    items = [asdict(s) for s in list_scenes(category=category)]
    return SuccessResponse(data={"items": items, "total": len(items)}, msg="查询成功")


@SceneRouter.get("/catalog/{code}", summary="查询场景详情")
async def get_scene_controller(
    code: str = Path(..., description="场景码"),
    auth: AuthSchema = Depends(AuthPermission(["module_video:algorithm:query"])),
) -> JSONResponse:
    s = get_scene(code)
    if s is None:
        from app.core.exceptions import CustomException
        raise CustomException(msg="场景不存在", code=404, status_code=404)
    return SuccessResponse(data=asdict(s), msg="查询成功")
```

`module_video/__init__.py` 加 `from .scene.controller import SceneRouter` + `video_router.include_router(SceneRouter)`。

- [ ] **Step 5: 运行确认通过**

Run: `cd backend && uv run pytest tests/test_scene_catalog.py -q`
Expected: PASS（4 passed）

- [ ] **Step 6: 全量 + ruff + 提交**

Run: `cd backend && uv run pytest -q && uv run ruff check app/api/v1/module_video/scene tests/test_scene_catalog.py`
Expected: 全绿

```bash
git add backend/app/api/v1/module_video/scene backend/app/api/v1/module_video/__init__.py backend/tests/test_scene_catalog.py
git commit -m "feat(video): 新增任务类型目录（场景注册表）与查询接口"
```

---

### Task 2: `AlgorithmModel.scene_type` + 补列

**Files:**
- Modify: `backend/app/api/v1/module_video/algorithm/model.py`
- Modify: `backend/app/api/v1/module_video/algorithm/schema.py`
- Modify: `backend/app/scripts/init_app.py`（`_ensure_missing_columns` 的 `video_algorithms` 列表）
- Test: `backend/tests/test_algorithm_scene_type.py`

**Interfaces:**
- Produces: `AlgorithmModel.scene_type: Mapped[str | None]`；`AlgorithmCreateSchema.scene_type` + `AlgorithmOutSchema.scene_type`。

- [ ] **Step 1: 写失败测试**

```python
"""算法 scene_type 字段测试。"""
from app.api.v1.module_video.algorithm.schema import AlgorithmCreateSchema, AlgorithmOutSchema


def test_scene_type_in_schemas():
    assert "scene_type" in AlgorithmCreateSchema.model_fields
    assert "scene_type" in AlgorithmOutSchema.model_fields
```

- [ ] **Step 2: 运行确认失败** → `uv run pytest tests/test_algorithm_scene_type.py -q` FAIL

- [ ] **Step 3: 实现**

`algorithm/model.py` 在 `algorithm_type` 之后加：

```python
    scene_type: Mapped[str | None] = mapped_column(String(64), nullable=True, comment="场景码（任务类型目录，如 PED_ATTR）")
```

`algorithm/schema.py`：`AlgorithmCreateSchema`/`AlgorithmOutSchema` 各加 `scene_type: str | None = Field(default=None, max_length=64, description="场景码")`（Create 用 Field，Out 直接类型注解即可）。

`init_app.py` `new_columns["video_algorithms"]` 列表加 `("scene_type", "VARCHAR(64)")`。

- [ ] **Step 4: 通过 + 全量 + ruff + 提交**

```bash
git add backend/app/api/v1/module_video/algorithm/model.py backend/app/api/v1/module_video/algorithm/schema.py backend/app/scripts/init_app.py backend/tests/test_algorithm_scene_type.py
git commit -m "feat(video): 算法配置增加 scene_type 场景码"
```

---

### Task 3: 编排按场景编译 pipeline（PED_ATTR）

**Files:**
- Modify: `backend/app/api/v1/module_video/edge/orchestrator.py`
- Test: `backend/tests/test_edge_task_config.py`（追加用例）

**Interfaces:**
- Produces: `build_agent_task_config` 增顶层 `scene_type`；当 `algorithm.scene_type == "PED_ATTR"` 时，`models` 产出**单条 pipeline 条目**：`{name,type:"pedestrian_attribute",backend,device,det_url,cls_url,attributes,labels,input_size,confidence_threshold,cls_threshold,password}`；其它场景保持单模型条目（`type=_resolve_model_type(...)`）。
- Consumes: `catalog.get_scene`（取 pipeline/参数默认）、`settings`。

- [ ] **Step 1: 追加失败测试**

在 `backend/tests/test_edge_task_config.py` 追加：

```python
class _AlgAttr:
    name = "工作服"
    algorithm_type = "PED_ATTR"
    scene_type = "PED_ATTR"
    model_path = "/models/zhgd_det.onnx"
    runtime_config = {"backend": "ort", "device": "cpu"}
    preset_params = {"cls_path": "/models/zhgd_ml.onnx",
                     "attributes": ["safety_helmet", "work_uniform"],
                     "confidence_threshold": 0.4, "cls_threshold": 0.5}


class _TaskAttr(_Task):
    algorithm_id = 2


def test_ped_attr_pipeline_config():
    cfg = build_agent_task_config(_TaskAttr(), _Cam(), _AlgAttr(), events={})
    assert cfg["scene_type"] == "PED_ATTR"
    m = cfg["models"][0]
    assert m["type"] == "pedestrian_attribute"
    assert m["det_url"] == "/models/zhgd_det.onnx"
    assert m["cls_url"] == "/models/zhgd_ml.onnx"
    assert m["attributes"] == ["safety_helmet", "work_uniform"]
    assert m["cls_threshold"] == 0.5
```

- [ ] **Step 2: 运行确认失败**

Run: `cd backend && uv run pytest tests/test_edge_task_config.py::test_ped_attr_pipeline_config -q` → FAIL

- [ ] **Step 3: 实现**

`orchestrator.py` 顶部 import `from app.api.v1.module_video.scene.catalog import get_scene`。在 `build_agent_task_config` 内，构建 `models` 前：

```python
    scene = get_scene(getattr(algorithm, "scene_type", "") or "")
    base_model = {
        "name": algorithm.name,
        "backend": merged_runtime.get("backend") or "trt",
        "device": merged_runtime.get("device") or "gpu",
        "labels": labels,
        "input_size": input_size,
        "confidence_threshold": confidence,
    }
    if scene is not None and scene.code == "PED_ATTR":
        models = [{
            **base_model,
            "type": "pedestrian_attribute",
            "det_url": algorithm.model_path or "",
            "cls_url": merged_params.get("cls_path") or merged_runtime.get("cls_path") or "",
            "attributes": merged_params.get("attributes") or [],
            "cls_threshold": merged_params.get("cls_threshold", 0.5),
            "password": merged_runtime.get("model_password") or "",
        }]
    else:
        models = [{**base_model, "type": _resolve_model_type(algorithm), "url": algorithm.model_path or ""}]
```

把返回字典的 `"models": [...]` 换成 `"models": models`，并新增顶层 `"scene_type": getattr(algorithm, "scene_type", "") or ""`。

- [ ] **Step 4: 通过 + 全量 + ruff + 提交**

```bash
git add backend/app/api/v1/module_video/edge/orchestrator.py backend/tests/test_edge_task_config.py
git commit -m "feat(video): 编排按场景编译 pedestrian_attribute pipeline"
```

---

### Task 4: 事件 v2 归一化（objects → detections + 保留属性）

**Files:**
- Modify: `backend/app/api/v1/module_video/edge/consumer.py`（`normalize_edge_event`）
- Test: `backend/tests/test_edge_event_intake.py`（追加用例）

**Interfaces:**
- Produces: `normalize_edge_event(payload)` 在 `schema_version==2`（或有 `objects` 无 `detections`）时，派生 `normalized["detections"]`（label/label_id/confidence/bbox + `attributes`），并保留 `objects/schema_version/scene_type`；v1 行为不变。

- [ ] **Step 1: 追加失败测试**

```python
def test_normalize_event_v2_objects_to_detections():
    from app.api.v1.module_video.edge.consumer import normalize_edge_event
    ev = {
        "event_id": "e2", "camera_id": 7, "task_id": 1, "schema_version": 2,
        "scene_type": "PED_ATTR",
        "objects": [{"label": "person", "label_id": 0, "confidence": 0.9,
                     "bbox": {"x": 0.1, "y": 0.1, "width": 0.2, "height": 0.2},
                     "attributes": {"work_uniform": 0.2}}],
    }
    out = normalize_edge_event(ev)
    assert out["scene_type"] == "PED_ATTR"
    assert len(out["detections"]) == 1
    d = out["detections"][0]
    assert d["label"] == "person" and d["bbox"]["x"] == 0.1
    # 属性为 {属性名: 分数}（分数=具有该属性的概率；违规=分数低于阈值）
    assert d["attributes"]["work_uniform"] == 0.2


def test_normalize_event_v1_unchanged():
    from app.api.v1.module_video.edge.consumer import normalize_edge_event
    ev = {"detections": [{"label": "person"}]}
    out = normalize_edge_event(ev)
    assert out["detections"] == [{"label": "person"}]
```

- [ ] **Step 2: 运行确认失败** → FAIL

- [ ] **Step 3: 实现**

在 `normalize_edge_event` 的 `normalized = {**payload, ...}` 之后追加：

```python
    # 事件 v2：objects[] → detections[]（复用既有告警链路），并保留属性/scene_type
    if not normalized.get("detections") and isinstance(payload.get("objects"), list):
        dets = []
        for obj in payload["objects"]:
            if not isinstance(obj, dict):
                continue
            bbox = obj.get("bbox") or {}
            det = {
                "label": obj.get("label", ""),
                "label_id": obj.get("label_id", 0),
                "confidence": obj.get("confidence", 0.0),
                "bbox": bbox,
            }
            if obj.get("track_id") is not None:
                det["track_id"] = obj["track_id"]
            if isinstance(obj.get("attributes"), dict):
                det["attributes"] = obj["attributes"]
            dets.append(det)
        normalized["detections"] = dets
    return normalized
```

（注意：现有函数末尾是 `return normalized`；把新逻辑插在 return 之前。）

- [ ] **Step 4: 通过 + 全量 + ruff + 提交**

```bash
git add backend/app/api/v1/module_video/edge/consumer.py backend/tests/test_edge_event_intake.py
git commit -m "feat(video): 事件 v2 归一化 objects 为 detections 并保留属性"
```

---

### Task 5: 属性规则（`AlarmRule.conditions` + 判定）

**Files:**
- Modify: `backend/app/api/v1/module_video/alarm/model.py`（`conditions`）
- Modify: `backend/app/api/v1/module_video/alarm/schema.py`
- Modify: `backend/app/scripts/init_app.py`（`video_alarm_rules` 补列）
- Modify: `backend/app/api/v1/module_video/inference/service.py`（属性规则判定）
- Test: `backend/tests/test_attribute_rule.py`

**Interfaces:**
- Produces: `AlarmRuleModel.conditions: Mapped[dict | None]`；schema 增 `conditions`。
- Produces: `_match_conditions(conditions: dict | None, detections: list[dict]) -> bool`（纯函数；支持 `{op:and/or/not, children}` 与叶子 `attribute`），放 `service.py` 顶部。
- `process_detection_callback`：找到 rule 后，若 `rule.conditions` 非空且不匹配 → 返回 `{"alarm_created": False, "reason": "rule_not_matched"}`。

- [ ] **Step 1: 写失败测试**

```python
"""属性规则判定测试。"""
from app.api.v1.module_video.inference.service import _match_conditions


def test_attribute_leaf_match():
    # 属性为 {名: 分数}；分数=具有该属性的概率，违规=分数低于阈值
    cond = {"op": "and", "children": [{"subject": "attribute", "field": "work_uniform", "op": "lt", "value": 0.5}]}
    dets = [{"label": "person", "attributes": {"work_uniform": 0.2}}]
    assert _match_conditions(cond, dets) is True


def test_attribute_leaf_no_match():
    cond = {"op": "and", "children": [{"subject": "attribute", "field": "work_uniform", "op": "lt", "value": 0.1}]}
    dets = [{"label": "person", "attributes": {"work_uniform": 0.2}}]
    assert _match_conditions(cond, dets) is False


def test_empty_conditions_match_all():
    assert _match_conditions(None, [{"label": "person"}]) is True
    assert _match_conditions({}, [{"label": "person"}]) is True


def test_or_and_not():
    dets = [{"label": "person", "attributes": {"work_uniform": 0.2}}]
    assert _match_conditions({"op": "or", "children": [
        {"subject": "attribute", "field": "safety_helmet", "op": "lt", "value": 0.5},
        {"subject": "attribute", "field": "work_uniform", "op": "lt", "value": 0.5},
    ]}, dets) is True
    assert _match_conditions({"op": "not", "children": [
        {"subject": "attribute", "field": "work_uniform", "op": "lt", "value": 0.5},
    ]}, dets) is False
```

- [ ] **Step 2: 运行确认失败** → FAIL

- [ ] **Step 3: 实现模型/列/schema**

`alarm/model.py` `AlarmRuleModel` 加：

```python
    conditions: Mapped[dict | None] = mapped_column(JSONB, nullable=True, comment="规则条件树（spec §6）")
```

`alarm/schema.py` `AlarmRuleCreateSchema` 加 `conditions: dict | None = Field(default=None, description="规则条件树")`；`AlarmRuleOutSchema` 加 `conditions: dict | None = None`。

`init_app.py` `new_columns` 增 `"video_alarm_rules": [("conditions", "JSONB")]`。

- [ ] **Step 4: 实现判定函数 + 接入**

`inference/service.py` 顶部（`class InferenceService` 前）新增（纯函数，便于单测）：

```python
def _match_conditions(conditions: dict | None, detections: list[dict]) -> bool:
    """评估规则条件树；空/None 视为命中。

    叶子支持 attribute：{"subject":"attribute","field":名,"op":"lt|gt|le|ge|eq","value":数}。
    事件里 attributes 为 {属性名: 分数}（分数=具有该属性的概率）；违规=分数低于阈值。
    其它叶子后续扩展；未知叶子不命中。
    """
    if not conditions:
        return True

    def eval_leaf(leaf: dict) -> bool:
        if leaf.get("subject") == "attribute":
            field = leaf.get("field")
            op = leaf.get("op", "eq")
            value = float(leaf.get("value", 0.0))
            for d in detections or []:
                score = (d.get("attributes") or {}).get(field)
                if score is None:
                    continue
                score = float(score)
                if op == "lt" and score < value:
                    return True
                if op == "gt" and score > value:
                    return True
                if op == "le" and score <= value:
                    return True
                if op == "ge" and score >= value:
                    return True
                if op == "eq" and score == value:
                    return True
        return False

    def eval_node(node: dict) -> bool:
        if node.get("op"):
            op = node["op"]
            kids = node.get("children") or []
            if op == "and":
                return all(eval_node(k) for k in kids) if kids else True
            if op == "or":
                return any(eval_node(k) for k in kids)
            if op == "not":
                return not any(eval_node(k) for k in kids)
            return False
        return eval_leaf(node)

    return eval_node(conditions)
```

在 `process_detection_callback` 内、`rule = pick_alarm_rule(...)` 之后、`severity = ...` 之前插入：

```python
        if rule is not None and rule.conditions and not _match_conditions(rule.conditions, detections):
            return {"alarm_created": False, "reason": "rule_not_matched"}
```

- [ ] **Step 5: 通过 + 全量 + ruff + 提交**

```bash
git add backend/app/api/v1/module_video/alarm/model.py backend/app/api/v1/module_video/alarm/schema.py backend/app/scripts/init_app.py backend/app/api/v1/module_video/inference/service.py backend/tests/test_attribute_rule.py
git commit -m "feat(video): 告警规则支持条件树与属性判定"
```

---

### Task 6: PED_ATTR 真机 E2E（前置：Plan B 完成）

**Files:**
- Modify: `scripts/e2e/edge_agent_e2e.ps1`（新增 `-Scene PED_ATTR` 分支：播种 det+cls 双模型算法与属性规则）
- Modify: `docs/superpowers/runbooks/edge-agent-e2e.md`

**Interfaces:**
- 算法 `scene_type="PED_ATTR"`，`model_path=<zhgd_det.onnx>`，`preset_params={"cls_path":"<zhgd_ml.onnx>","attributes":[...],"confidence_threshold":0.4,"cls_threshold":0.5}`。
- 规则 `conditions={"op":"and","children":[{"subject":"attribute","field":"work_uniform","op":"lt","value":0.5}]}`（分数=具有「穿工作服」的概率，低于阈值=违规）。
- 断言：事件含 `objects[].attributes`；违规出告警（含快照）；合规不告警。

- [ ] **Step 1..4**：脚本加场景分支 → 起 broker/Agent → 播种 → start → 断言（沿用既有骨架，新增属性断言）。
- [ ] **Step 5**：更新 runbook（PED_ATTR 用法、真实模型路径、期望标签）。
- [ ] **Step 6**：提交 `test(video): PED_ATTR 属性场景真机联调`。

---

## Self-Review

**Spec coverage:** §3 目录 → Task 1；§4 注册表 → Task 1；§5.1 pipeline TaskConfig → Task 3；§5.2 事件 v2 → Task 4；§6 规则（属性叶子）→ Task 5；§7 切片 → Task 3/4/5/6；`scene_type` → Task 2。
**Placeholder scan:** 无 TBD；Task 1 catalog 明确「按 spec §3 补全全部场景码」并列全清单。
**Type consistency:** `SceneDef`/`get_scene`/`scene_type`/`pedestrian_attribute`/`conditions`/`_match_conditions` 命名前后一致。
**风险:** 事件 v1 兼容（Task 4 只在不含 detections 时派生）；属性叶子仅本期最小集，其它叶子后续扩。
