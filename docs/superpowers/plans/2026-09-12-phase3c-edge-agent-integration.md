# Phase 3C（重写）：AIStation 接入布控 Agent Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task.
> **前置 spec**：`docs/superpowers/specs/2026-09-12-cloud-edge-visual-analysis-design.md`
> **ModelDeploy 侧**：`docs/superpowers/specs/2026-09-12-modeldeploy-agent-handoff.md`（另会话实现）
> **说明**：原 Phase 3C（Python worker）方案作废；本计划为 AIStation 侧接入。Agent 未就绪期间，用契约/mock 单测，真机端到端待 Agent 落地。

**Goal:** AIStation 新增边缘设备管理与能力模型；把布控任务按能力编排并编译为 Agent `TaskConfig` 下发/启停；接入 Agent 检测事件（MQTT 首选 + HTTP 兼容），复用现有告警/联动/通知链路。

**Architecture:** 新增 `module_video/edge/`（设备 CRUD + 心跳）；`AlgorithmTaskModel` 增 `edge_device_id`；纯函数编译 TaskConfig 与能力校验；`EdgeAgentClient`（httpx）下发；`EdgeEventConsumer`（`aiomqtt`，懒加载，缺库降级）订阅 → 归一化 → `InferenceService.process_detection_callback`。

**Tech Stack:** FastAPI + SQLAlchemy + httpx（已有）+ aiomqtt（新增，可选）+ pytest。

## Global Constraints

- 后端 `D:\AIStation\backend`（`uv run pytest`/`uv run ruff check`，只判断新增）；中文注释；提交 `fix(video): 中文描述`；禁 `git add -A`；ruff `fix=true` 时还原无关改动。
- **不做数据库迁移**：`edge_device_id` 等新列通过 `init_app._ensure_missing_columns` 兜底 + ORM 定义（新库 create_all 直接有）。
- MQTT 客户端 `aiomqtt` 加入依赖但**懒加载**；broker 不可用/未安装时仅记录 warning，HTTP webhook 仍可用，进程不崩。
- Agent 契约以 spec §6/§7 为准；单测用 mock（httpx MockTransport / 假 MQTT 消息）。

---

### Task 1: 边缘设备管理 + 心跳 + 配置项

**背景:** 需要云端登记边缘设备及其能力，Agent 启动/周期上报心跳与能力/负载，供编排使用。当前无此实体。

**Files:**
- Create: `backend/app/api/v1/module_video/edge/__init__.py`
- Create: `backend/app/api/v1/module_video/edge/model.py`
- Create: `backend/app/api/v1/module_video/edge/schema.py`
- Create: `backend/app/api/v1/module_video/edge/service.py`
- Create: `backend/app/api/v1/module_video/edge/controller.py`
- Modify: `backend/app/api/v1/module_video/__init__.py`（注册 `EdgeRouter`）
- Modify: `backend/app/config/setting.py`（新增配置）
- Modify: `backend/app/scripts/init_app.py`（`_ensure_missing_columns` 建表/补列 + 启动事件消费者占位由 Task 3 加）
- Test: `backend/tests/test_edge_device.py`

**Interfaces:**
- `EdgeDeviceModel`（`video_edge_devices`，`ModelMixin,UserMixin`）：`name`、`code`（unique）、`control_url`、`secret`、`capabilities: JSONB`、`metrics: JSONB`、`status`（online/offline/error，默认 offline）、`last_heartbeat: datetime`、`description`。
- `capability_satisfies(capabilities: dict, requirement: dict) -> tuple[bool, str]` —— 校验模型族/后端/剩余路数/硬件；返回 `(ok, reason)`。
- REST：`GET /video/edge/list`、`POST /video/edge/create`、`PUT /video/edge/update/{id}`、`DELETE /video/edge/delete`、`GET /video/edge/detail/{id}`、`POST /video/edge/heartbeat`。
- 配置：`VIDEO_ANALYSIS_MODE`（`cloud_edge`/`cloud_only`，默认 `cloud_only`）、`EDGE_HEARTBEAT_TIMEOUT_SEC=90`、`EDGE_CONTROL_TOKEN`（可选共享密钥）。

- [ ] **Step 1: Write the failing test**

```python
"""边缘设备能力校验测试。"""
from app.api.v1.module_video.edge.service import capability_satisfies


def test_capability_ok():
    cap = {"model_families": ["det"], "backends": ["trt"], "max_channels": 4}
    ok, reason = capability_satisfies(cap, {"model_family": "det", "backend": "trt", "running_channels": 2})
    assert ok is True and reason == ""


def test_capability_missing_family():
    cap = {"model_families": ["det"], "backends": ["trt"], "max_channels": 4}
    ok, reason = capability_satisfies(cap, {"model_family": "ocr", "backend": "trt", "running_channels": 0})
    assert ok is False and "模型" in reason


def test_capability_full():
    cap = {"model_families": ["det"], "backends": ["trt"], "max_channels": 1}
    ok, reason = capability_satisfies(cap, {"model_family": "det", "backend": "trt", "running_channels": 1})
    assert ok is False and "路数" in reason
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/test_edge_device.py -q`
Expected: FAIL（模块不存在）。

- [ ] **Step 3: Implement**

`edge/model.py` 定义 `EdgeDeviceModel`（列同 Interfaces）。
`edge/service.py`：
```python
class EdgeService:
    @staticmethod
    def capability_satisfies(capabilities: dict, requirement: dict) -> tuple[bool, str]:
        cap = capabilities or {}
        fam = requirement.get("model_family")
        if fam and fam not in (cap.get("model_families") or []):
            return False, f"设备不支持模型族 {fam}"
        be = requirement.get("backend")
        if be and be not in (cap.get("backends") or []):
            return False, f"设备不支持后端 {be}"
        maxc = int(cap.get("max_channels") or 0)
        running = int(requirement.get("running_channels") or 0)
        if maxc and running >= maxc:
            return False, f"设备并发布控路数已满 ({running}/{maxc})"
        return True, ""
```
`edge/controller.py`：标准 CRUD（`AuthPermission(["module_video:edge:query|create|update|delete"])`）+ 心跳：
```python
@EdgeRouter.post("/heartbeat", summary="边缘设备心跳/能力上报")
async def edge_heartbeat(body: dict = Body(...)) -> JSONResponse:
    # 可选共享密钥鉴权
    if settings.EDGE_CONTROL_TOKEN and body.get("token") != settings.EDGE_CONTROL_TOKEN:
        raise CustomException(msg="无效的设备凭证", code=403)
    await EdgeService.heartbeat(body)
    return SuccessResponse(msg="ok")
```
`EdgeService.heartbeat`：按 `code` upsert：更新 `capabilities`/`metrics`/`status=online`/`last_heartbeat`；不存在则创建（`name=code`）。
`__init__.py` 注册 `EdgeRouter`。
`setting.py` 加配置项（带默认）。
`init_app._ensure_missing_columns` 增加建表兜底（对旧库 `CREATE TABLE IF NOT EXISTS video_edge_devices`，与 train_predicts 同法），并为 `video_algorithm_tasks` 补 `edge_device_id INTEGER`。

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && uv run pytest tests/test_edge_device.py -q`
Expected: PASS

- [ ] **Step 5: 权限/菜单**：在 `init_app` 的视频按钮权限补 `module_video:edge:*`（若沿用现有视频菜单权限体系，按现网做法补种）。

- [ ] **Step 6: full suite + ruff + commit**

```bash
git add backend/app/api/v1/module_video/edge backend/app/api/v1/module_video/__init__.py backend/app/config/setting.py backend/app/scripts/init_app.py backend/tests/test_edge_device.py
git commit -m "feat(video): 边缘设备管理/心跳/能力校验与配置项"
```

---

### Task 2: 布控任务编排（TaskConfig 编译 + 能力校验 + 下发）

**背景:** 布控任务需指定边缘设备，编译为 Agent `TaskConfig` 并经控制面下发/启停。

**Files:**
- Modify: `backend/app/api/v1/module_video/algorithm/model.py`（`edge_device_id`）
- Create: `backend/app/api/v1/module_video/edge/agent_client.py`
- Create: `backend/app/api/v1/module_video/edge/orchestrator.py`
- Modify: `backend/app/api/v1/module_video/algorithm/controller.py`（start/stop 走编排）
- Modify: `backend/app/api/v1/module_video/algorithm/schema.py`（`edge_device_id`）
- Test: `backend/tests/test_edge_orchestrator.py`

**Interfaces:**
- Produces: `build_agent_task_config(task, camera, algorithm) -> dict` —— 产出 spec §6 的 `TaskConfig`（camera/models/roi/sensitivity/schedule/events/decoder/encoder）。
- Produces: `EdgeAgentClient(control_url, secret)`：`async dispatch(config)`、`async start(task_id)`、`async stop(task_id)`、`async delete(task_id)`（httpx；超时/错误抛 `CustomException`）。
- Produces: `EdgeOrchestrator.start_task(task_id)` —— 取任务→设备能力校验→编译→下发→启停→更新状态；能力不满足返回失败原因。

- [ ] **Step 1: Write the failing test**

```python
"""TaskConfig 编译测试。"""
from app.api.v1.module_video.edge.orchestrator import build_agent_task_config


class _Cam: id = 7; name = "北门"; rtsp_url_sub = "rtsp://cam/7"; stream_id = "cam7"
class _Alg:
    name = "入侵检测"; algorithm_type = "INTRUSION"; model_path = "s3://m/det.onnx"
    runtime_config = {"backend": "trt", "device": "gpu"}; preset_params = {"conf_threshold": 0.45}
class _Task:
    id = 123; camera_id = 7; algorithm_id = 1; stream_type = "SUB"
    detect_region = {"points": [[0.1, 0.1], [0.9, 0.1], [0.9, 0.9], [0.1, 0.9]]}
    sensitivity = 60; schedule_json = {"days": [0, 1], "start": "08:00", "end": "18:00"}


def test_build_task_config_basic():
    cfg = build_agent_task_config(_Task(), _Cam(), _Alg(), events={"transport": "http", "http": {"url": "http://cloud/cb", "token": "t"}})
    assert cfg["task_id"] == 123
    assert cfg["camera"]["url"].startswith("rtsp://")
    assert cfg["models"][0]["type"] in ("det", "detection")
    assert cfg["roi"][0][0] == 0.1
    assert cfg["events"]["transport"] == "http"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/test_edge_orchestrator.py -q`
Expected: FAIL。

- [ ] **Step 3: Implement**

`orchestrator.build_agent_task_config`：把 task/camera/algorithm 映射为 spec §6（`models[0].type` 由 `algorithm.runtime_config.task_type` 或算法类型推断，缺省 `det`；`url=model_path`；`labels` 来自 `preset_params.labels`；`confidence_threshold` 来自 preset；`roi` 用 detect_region.points 或 x1y1x2y2 归一化；`events` 由调用方按分析模式传入）。
`thresholds/pyproject.toml` 加 `aiomqtt`（Task 3 用；可先加）。
`agent_client.EdgeAgentClient`：httpx POST `{control_url}/api/v1/tasks`，`Authorization: Bearer {secret}`；`start/stop/delete` 对应 `/tasks/{task_id}/start|stop`、`DELETE /tasks/{task_id}`；错误抛出含状态码/消息。
`EdgeOrchestrator.start_task`：取任务/设备（`edge_device_id`，空则用 `cloud_only` 本机默认控制地址 `settings.EDGE_LOCAL_CONTROL_URL`）；`capability_satisfies`；编译（`events` 由 `settings.VIDEO_ANALYSIS_MODE` 决定 MQTT/HTTP 参数）；`dispatch`+`start`；成功置 `status=RUNNING`，失败置 `ERROR` + `error_log`（无该列则用 `description`/新列，报告说明）。
`algorithm/controller.py` 的 `start_inference_controller`/`stop_inference_controller` 改为调用编排（保留旧 worker 路径作为 `cloud_only`+无 Agent 时的回退，或直接替换——按实现情况报告）。

- [ ] **Step 4: Run test + full + ruff + commit**

```bash
git add backend/app/api/v1/module_video/edge/agent_client.py backend/app/api/v1/module_video/edge/orchestrator.py backend/app/api/v1/module_video/algorithm backend/tests/test_edge_orchestrator.py
git commit -m "feat(video): 布控任务编排(能力校验+TaskConfig编译+Agent下发)"
```

---

### Task 3: 事件接入（MQTT 消费者 + 归一化）

**背景:** Agent 经 MQTT（或 HTTP）上报检测事件；云端订阅并复用现有告警链路。

**Files:**
- Create: `backend/app/api/v1/module_video/edge/consumer.py`
- Modify: `backend/app/api/v1/module_video/inference/service.py`（事件归一化）
- Modify: `backend/app/scripts/init_app.py`（lifespan 启动/停止消费者）
- Modify: `backend/app/config/setting.py`（MQTT 配置）
- Test: `backend/tests/test_edge_event_intake.py`

**Interfaces:**
- Produces: `normalize_edge_event(payload: dict) -> dict` —— 兼容：`snapshot.ref` → `snapshot_path`（相对）；保留 `edge_code`；`detections` 原样（已与 callback 兼容）。
- Produces: `EdgeEventConsumer`：`async start()`/`async stop()`；订阅 `settings.MQTT_TOPIC_PREFIX/+/camera/+/detect`（或配置的通配）；收到即 `payload=json.loads` → `normalize_edge_event` → `InferenceService.process_detection_callback`（含 `event_id` 去重：短时缓存已处理 id）。
- 配置：`MQTT_ENABLED`、`MQTT_BROKER_URL`、`MQTT_USERNAME`、`MQTT_PASSWORD`、`MQTT_TOPIC_PREFIX="aistation/+/edge"`、`MQTT_CLIENT_ID`、`MQTT_QOS=1`。

- [ ] **Step 1: Write the failing test**

```python
"""事件归一化与去重测试。"""
from app.api.v1.module_video.edge.consumer import normalize_edge_event, dedup


def test_normalize_snapshot_ref():
    ev = {"event_id": "e1", "edge_code": "edge-01", "camera_id": 7, "task_id": 1,
          "detections": [{"label": "person", "confidence": 0.9, "bbox": {"x": 0.1, "y": 0.1, "width": 0.2, "height": 0.2}}],
          "snapshot": {"ref": "edge-01/cam7/2026-09-12/x.jpg"}}
    out = normalize_edge_event(ev)
    assert out["snapshot_path"] == "edge-01/cam7/2026-09-12/x.jpg"
    assert out["edge_code"] == "edge-01"
    assert out["detections"][0]["label"] == "person"


def test_dedup_event_id():
    d = dedup()
    assert d.seen("e1") is False   # 首次未见
    d.mark("e1")
    assert d.seen("e1") is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/test_edge_event_intake.py -q`
Expected: FAIL。

- [ ] **Step 3: Implement**

`normalize_edge_event`：`{**payload, "snapshot_path": (payload.get("snapshot") or {}).get("ref") or payload.get("snapshot_path")}`。
`dedup`：小型有界集合（如 `collections.OrderedDict`，上限 5000，TTL 10min）提供 `seen(id)`/`mark(id)`。
`EdgeEventConsumer`：懒 `import aiomqtt`；连接 `settings.MQTT_BROKER_URL`，订阅；循环 `async for message in client.messages:` → `json.loads` → 去重 → `await InferenceService.process_detection_callback(ev)`；异常记录并退避重连。`MQTT_ENABLED=false` 或导入失败 → `logger.warning` 并直接返回（不阻塞启动）。
`init_app` lifespan：`asyncio.create_task(EdgeEventConsumer().run())`；关闭时 cancel。

- [ ] **Step 4: Run test + full + ruff + commit**

```bash
git add backend/app/api/v1/module_video/edge/consumer.py backend/app/api/v1/module_video/inference/service.py backend/app/scripts/init_app.py backend/app/config/setting.py backend/tests/test_edge_event_intake.py
git commit -m "feat(video): 接入布控 Agent 事件(MQTT消费者+归一化+去重)"
```

---

## Self-Review

**Spec coverage（对照云边 spec §4/§5/§7/§10-B）:**
- 边缘设备/能力/心跳 → Task 1 ✅
- 任务编排/能力校验/TaskConfig 下发 → Task 2 ✅
- 事件接入（MQTT+HTTP 兼容、复用告警链路、去重）→ Task 3 ✅
- 前端（设备管理页、布控设备选择、预览/快照）→ 归 Phase 3D（本计划不含）✅（范围外说明）

**Placeholder scan:** 无 TBD；`error_log` 列问题与旧 worker 回退均给出"按实现情况报告"的明确处理。

**Type consistency:** `capability_satisfies`/`build_agent_task_config`/`EdgeAgentClient`/`normalize_edge_event` 命名一致。

**风险:** Agent 未落地 → 单测用 mock；真机端到端待 ModelDeploy 会话产出 Agent 后联调（spec 已给契约）。新增 `aiomqtt` 依赖需 `uv sync`；broker 未起时消费者降级不崩。`edge_device_id` 等无需迁移（ORM + 启动补列）。
