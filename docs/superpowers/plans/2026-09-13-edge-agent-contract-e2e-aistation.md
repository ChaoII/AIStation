# 云边布控契约统一与真机联调（AIStation 侧）Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 AIStation 下发的 Agent TaskConfig / 事件通道 / 心跳契约与 ModelDeploy `aistation_agent` 统一，并新增边缘任务快照预览的受控代理。

**Architecture:** 仅改 `module_video/edge` 与配置；`build_agent_task_config`/`build_events` 为纯函数（便于单测）；新增 `EdgeAgentClient.fetch_snapshot`（二进制，绕开 JSON `_request`）与 `EdgeService`/`EdgeController` 代理路由。E2E 由脚本编排 Broker/Agent/后端并断言。

**Tech Stack:** FastAPI + SQLAlchemy 2.0 + Pydantic v2 + httpx + pytest（`asyncio.run` 驱动异步用例，无 pytest-asyncio）。

**Spec:** `docs/superpowers/specs/2026-09-13-edge-agent-contract-e2e-design.md`
**ModelDeploy 侧计划:** 同 spec，Plan B（另仓库）。Task 5（真机 E2E）需 Plan B 完成后执行。

## Global Constraints

- 后端工作目录 `D:\AIStation\backend`；测试 `uv run pytest`；静态检查 `uv run ruff check`（只判断新增问题）。
- 前端不在本计划范围。
- 代码注释用中文；提交信息 `feat(video): 中文描述` / `fix(video): 中文描述`。
- **禁止 `git add -A` / `git add .`**；只 add 本任务涉及文件。工作区存在与本计划无关的改动（`.superpowers/sdd/*`、AI 模块删除等），一律不得纳入提交。
- 不新增 Python 依赖。
- 异步测试统一 `asyncio.run(...)`（参考 `tests/test_edge_orchestrator.py:108`）。
- 配置新增项一律带默认值，保证既有测试与默认 `cloud_only` 行为不变。

---

### Task 1: 统一 TaskConfig 契约（纯函数）

**背景:** `build_agent_task_config` 缺顶层 `algorithm_type`/`tenant`/`preview`；`build_events` 的 MQTT broker 原样传 `MQTT_BROKER_URL`（paho 不认 `mqtt://`）、未下发账号密码、client_id 误用云端消费者 ID、未下发快照配置。

**Files:**
- Modify: `backend/app/api/v1/module_video/edge/orchestrator.py`
- Modify: `backend/app/config/setting.py`（新增默认配置项）
- Modify: `backend/env/.env.dev`（新增示例键，取默认值，可保留注释）
- Test: `backend/tests/test_edge_task_config.py`

**Interfaces:**
- Produces: `normalize_broker_scheme(url: str) -> str` —— `mqtts://→ssl://`、`mqtt://→tcp://`、纯 `host:port→tcp://host:port`、空→空、其他原样。
- Produces: `build_agent_task_config(task, camera, algorithm, events=None) -> dict` 新增顶层键 `algorithm_type:str`、`tenant:str`、`preview:{enabled:bool, format:"snapshot"}`。
- Produces: `build_events(camera_id: int, edge_code: str) -> dict` —— MQTT 分支新增 `mqtt.broker`（归一化）、`mqtt.username/password`、`mqtt.client_id=f"aistation-agent-{edge_code}"`；两分支均新增顶层 `snapshot:{enabled,inline,quality,max_width}`。

- [ ] **Step 1: 写失败测试**

创建 `backend/tests/test_edge_task_config.py`：

```python
"""Agent TaskConfig / 事件通道契约编译测试。"""
from app.api.v1.module_video.edge import orchestrator as orch
from app.api.v1.module_video.edge.orchestrator import (
    build_agent_task_config,
    build_events,
    normalize_broker_scheme,
)


class _Cam:
    id = 7
    name = "北门"
    rtsp_url_sub = "rtsp://cam/7"
    stream_id = "cam7"


class _Alg:
    name = "入侵检测"
    algorithm_type = "INTRUSION"
    model_path = "/abs/det.onnx"
    runtime_config = {"backend": "ort", "device": "cpu"}
    preset_params = {"confidence_threshold": 0.4, "labels": ["person"]}


class _Task:
    id = 123
    camera_id = 7
    algorithm_id = 1
    stream_type = "SUB"
    detect_region = {"points": [[0.1, 0.1], [0.9, 0.1], [0.9, 0.9], [0.1, 0.9]]}
    sensitivity = 60
    schedule_json = {"slots": [{"day": 0, "start": 8, "end": 18}]}
    runtime_overrides = None
    params_overrides = None


def test_normalize_broker_scheme():
    assert normalize_broker_scheme("mqtt://h:1883") == "tcp://h:1883"
    assert normalize_broker_scheme("mqtts://h:8883") == "ssl://h:8883"
    assert normalize_broker_scheme("h:1883") == "tcp://h:1883"
    assert normalize_broker_scheme("tcp://h:1883") == "tcp://h:1883"
    assert normalize_broker_scheme("") == ""


def test_task_config_contract_fields():
    cfg = build_agent_task_config(_Task(), _Cam(), _Alg(), events={})
    assert cfg["algorithm_type"] == "INTRUSION"
    assert cfg["tenant"] == "default"
    assert cfg["preview"] == {"enabled": True, "format": "snapshot"}
    assert cfg["schedule"] == {"slots": [{"day": 0, "start": 8, "end": 18}]}


def test_build_events_mqtt(monkeypatch):
    monkeypatch.setattr(orch.settings, "VIDEO_ANALYSIS_MODE", "cloud_edge")
    monkeypatch.setattr(orch.settings, "MQTT_BROKER_URL", "mqtt://broker:1883")
    monkeypatch.setattr(orch.settings, "MQTT_USERNAME", "u")
    monkeypatch.setattr(orch.settings, "MQTT_PASSWORD", "p")
    ev = build_events(camera_id=7, edge_code="edge-01")
    assert ev["transport"] == "mqtt"
    assert ev["mqtt"]["broker"] == "tcp://broker:1883"
    assert ev["mqtt"]["client_id"] == "aistation-agent-edge-01"
    assert ev["mqtt"]["username"] == "u"
    assert ev["mqtt"]["password"] == "p"
    assert ev["mqtt"]["topic"].endswith("/camera/7/detect")
    assert ev["snapshot"]["inline"] is True


def test_build_events_http(monkeypatch):
    monkeypatch.setattr(orch.settings, "VIDEO_ANALYSIS_MODE", "cloud_only")
    ev = build_events(camera_id=7, edge_code="local")
    assert ev["transport"] == "http"
    assert ev["http"]["url"].endswith("/video/algorithm/detection/callback")
    assert ev["snapshot"]["enabled"] is True
```

- [ ] **Step 2: 运行确认失败**

Run: `cd backend && uv run pytest tests/test_edge_task_config.py -q`
Expected: FAIL（`normalize_broker_scheme` 不存在 / 键缺失）

- [ ] **Step 3: 新增配置项**

在 `backend/app/config/setting.py` 的 MQTT 配置块（`MQTT_QOS` 之后）追加：

```python
    # 事件内联快照（Agent 采集 JPEG → base64 随事件上报）
    MQTT_SNAPSHOT_ENABLED: bool = True
    MQTT_SNAPSHOT_INLINE: bool = True
    MQTT_SNAPSHOT_QUALITY: int = 75
    MQTT_SNAPSHOT_MAX_WIDTH: int = 640
    # 边缘预览（当前以受控快照流实现）
    EDGE_PREVIEW_ENABLED: bool = True
```

- [ ] **Step 4: 实现 orchestrator 改动**

在 `backend/app/api/v1/module_video/edge/orchestrator.py` 的 `_resolve_stream_url` 之后新增：

```python
def normalize_broker_scheme(url: str) -> str:
    """把 MQTT Broker 地址统一为 paho 可识别的 tcp:// 或 ssl://。

    Agent 用 paho，只认 tcp:// 与 ssl://；aiomqtt 侧由 parse_mqtt_broker 解析。
    空串原样返回；未知 scheme 原样返回，交由实现/运维纠正。
    """
    raw = (url or "").strip()
    if not raw:
        return ""
    if raw.startswith("mqtts://"):
        return "ssl://" + raw[len("mqtts://"):]
    if raw.startswith("mqtt://"):
        return "tcp://" + raw[len("mqtt://"):]
    if "://" not in raw:
        return "tcp://" + raw
    return raw
```

修改 `build_agent_task_config` 的返回字典，在 `"camera": {...},` 之前加入顶层字段，并在 `"encoder": {...},` 之后加入 `preview`：

```python
    return {
        "task_id": task.id,
        "tenant": merged_runtime.get("tenant") or "default",
        "algorithm_type": getattr(algorithm, "algorithm_type", "") or "",
        "camera": {
```

```python
        "encoder": merged_runtime.get("encoder") or {"codec": "h264_nvenc", "format": "flv", "bitrate_kbps": 2500},
        "preview": {
            "enabled": bool(getattr(settings, "EDGE_PREVIEW_ENABLED", True)),
            "format": "snapshot",
        },
    }
```

替换 `build_events` 全文为：

```python
def build_events(camera_id: int, edge_code: str) -> dict:
    """按视频分析模式构造事件通道参数（云端 HTTP 回调 / 边缘 MQTT）。

    MQTT：broker scheme 归一化为 paho 可识别形式；client_id 每边缘唯一；
    账号密码按 settings 下发。两分支均携带内联快照配置。
    """
    snapshot = {
        "enabled": bool(getattr(settings, "MQTT_SNAPSHOT_ENABLED", True)),
        "inline": bool(getattr(settings, "MQTT_SNAPSHOT_INLINE", True)),
        "quality": int(getattr(settings, "MQTT_SNAPSHOT_QUALITY", 75)),
        "max_width": int(getattr(settings, "MQTT_SNAPSHOT_MAX_WIDTH", 640)),
    }
    buffer = {"dir": "./events_buffer", "max_mb": 512}
    if settings.VIDEO_ANALYSIS_MODE == "cloud_edge":
        prefix = getattr(settings, "MQTT_TOPIC_PREFIX", "aistation/default/edge").rstrip("/")
        base = f"{prefix}/{edge_code}".rstrip("/")
        return {
            "transport": "mqtt",
            "mqtt": {
                "broker": normalize_broker_scheme(getattr(settings, "MQTT_BROKER_URL", "")),
                "topic_prefix": base,
                "topic": f"{base}/camera/{camera_id}/detect",
                "qos": int(getattr(settings, "MQTT_QOS", 1)),
                "client_id": f"aistation-agent-{edge_code}",
                "username": getattr(settings, "MQTT_USERNAME", "") or "",
                "password": getattr(settings, "MQTT_PASSWORD", "") or "",
            },
            "buffer": buffer,
            "snapshot": snapshot,
        }
    return {
        "transport": "http",
        "http": {
            "url": f"http://127.0.0.1:{settings.SERVER_PORT}{settings.ROOT_PATH}/video/algorithm/detection/callback",
            "token": settings.INFERENCE_CALLBACK_TOKEN,
        },
        "buffer": buffer,
        "snapshot": snapshot,
    }
```

- [ ] **Step 5: 运行确认通过**

Run: `cd backend && uv run pytest tests/test_edge_task_config.py -q`
Expected: PASS（4 passed）

- [ ] **Step 6: 补 env 示例键**

在 `backend/env/.env.dev` 末尾追加（值可留空以走默认；此处给出 E2E 常用示例）：

```
# —— 云边布控（真机联调示例，按需启用）——
# VIDEO_ANALYSIS_MODE=cloud_edge
# MQTT_ENABLED=true
# MQTT_BROKER_URL=tcp://127.0.0.1:1883
# MQTT_TOPIC_PREFIX=aistation/default/edge
# MQTT_SUBSCRIBE_TOPIC=aistation/+/edge/+/camera/+/detect
# MQTT_CLIENT_ID=aistation-events
# EDGE_CONTROL_TOKEN=change-me
# INFERENCE_CALLBACK_TOKEN=infer_callback_shared_secret
```

- [ ] **Step 7: 全量 + ruff + 提交**

Run: `cd backend && uv run pytest -q && uv run ruff check app/api/v1/module_video/edge/orchestrator.py app/config/setting.py tests/test_edge_task_config.py`
Expected: 全绿；ruff `All checks passed!`

```bash
git add backend/app/api/v1/module_video/edge/orchestrator.py backend/app/config/setting.py backend/env/.env.dev backend/tests/test_edge_task_config.py
git commit -m "feat(video): 统一 Agent TaskConfig 契约（algorithm_type/tenant/MQTT/快照/预览）"
```

---

### Task 2: 心跳字段兼容 `edge_code`（C9）

**背景:** Agent 心跳载荷用 `edge_code`，AIStation `EdgeService.heartbeat` 读 `code` → 真机首次心跳报「设备编码不能为空」。

**Files:**
- Modify: `backend/app/api/v1/module_video/edge/service.py`
- Test: `backend/tests/test_edge_heartbeat.py`

**Interfaces:**
- Produces: `extract_device_code(body: dict) -> str` —— 返回 `body["code"] or body["edge_code"]`（strip）；空返回 `""`。
- `EdgeService.heartbeat` 使用该函数取 code。

- [ ] **Step 1: 写失败测试**

创建 `backend/tests/test_edge_heartbeat.py`：

```python
"""边缘心跳字段兼容测试（Agent 发 edge_code，云端兼容 code）。"""
from app.api.v1.module_video.edge.service import extract_device_code


def test_extract_prefers_code():
    assert extract_device_code({"code": "edge-01", "edge_code": "x"}) == "edge-01"


def test_extract_falls_back_to_edge_code():
    assert extract_device_code({"edge_code": "edge-01"}) == "edge-01"


def test_extract_empty():
    assert extract_device_code({}) == ""
    assert extract_device_code({"edge_code": "  "}) == ""
```

- [ ] **Step 2: 运行确认失败**

Run: `cd backend && uv run pytest tests/test_edge_heartbeat.py -q`
Expected: FAIL（`extract_device_code` 不存在）

- [ ] **Step 3: 实现**

在 `backend/app/api/v1/module_video/edge/service.py` 的 `capability_satisfies` 之后新增：

```python
def extract_device_code(body: dict) -> str:
    """从心跳载荷取设备编码：优先 `code`，兼容 Agent 的 `edge_code`。"""
    return str(body.get("code") or body.get("edge_code") or "").strip()
```

把 `EdgeService.heartbeat` 内：

```python
        code = str(body.get("code") or "").strip()
```

替换为：

```python
        code = extract_device_code(body)
```

- [ ] **Step 4: 运行确认通过**

Run: `cd backend && uv run pytest tests/test_edge_heartbeat.py -q`
Expected: PASS（3 passed）

- [ ] **Step 5: 全量 + ruff + 提交**

Run: `cd backend && uv run pytest -q && uv run ruff check app/api/v1/module_video/edge/service.py tests/test_edge_heartbeat.py`
Expected: 全绿

```bash
git add backend/app/api/v1/module_video/edge/service.py backend/tests/test_edge_heartbeat.py
git commit -m "fix(video): 心跳兼容 Agent 的 edge_code 字段"
```

---

### Task 3: 边缘任务快照受控代理

**背景:** Agent 有 `GET /api/v1/tasks/{id}/snapshot.jpg`；需由 AIStation 受鉴权代理给前端。`EdgeAgentClient._request` 只处理 JSON，必须新增二进制方法。

**Files:**
- Modify: `backend/app/api/v1/module_video/edge/agent_client.py`
- Modify: `backend/app/api/v1/module_video/edge/service.py`
- Modify: `backend/app/api/v1/module_video/edge/controller.py`
- Test: `backend/tests/test_edge_snapshot_proxy.py`

**Interfaces:**
- Produces: `EdgeAgentClient.fetch_snapshot(task_id: int, timeout: float = 5.0) -> bytes` —— 调 `GET {control_url}/api/v1/tasks/{task_id}/snapshot.jpg`，非 2xx 或空体抛 `CustomException(code=502,status_code=502)`。
- Produces: `EdgeService.get_task_snapshot_service(device_id: int, task_id: int, auth) -> bytes` —— 取设备（control_url/secret），调用客户端；失败抛 `CustomException`。
- Produces: `GET /video/edge/{device_id}/tasks/{task_id}/snapshot` → `Response(media_type="image/jpeg")`，鉴权 `module_video:algorithm:query`。

- [ ] **Step 1: 写失败测试**

创建 `backend/tests/test_edge_snapshot_proxy.py`：

```python
"""边缘任务快照代理路由测试。"""
from app.api.v1.module_video.edge.agent_client import EdgeAgentClient

_FAKE_JPEG = b"\xff\xd8\xff\xe0fake-jpeg"


def _fake_fetch(self, task_id, timeout=5.0):
    """异步打桩：不触网，直接返回假 JPEG。"""
    async def _coro() -> bytes:
        return _FAKE_JPEG
    return _coro()


def test_snapshot_proxy_returns_jpeg(test_client, auth_headers, monkeypatch):
    # 1) 建一个边缘设备（含控制地址与密钥）
    created = test_client.post(
        "/api/v1/video/edge/create",
        headers=auth_headers,
        json={"name": "e2e", "code": "edge-snap", "control_url": "http://127.0.0.1:19090", "secret": "s"},
    )
    assert created.status_code == 200, created.text
    device_id = created.json()["data"]["id"]

    # 2) 打桩 Agent 快照获取（绕过网络）
    monkeypatch.setattr(EdgeAgentClient, "fetch_snapshot", _fake_fetch)

    # 3) 命中代理路由
    resp = test_client.get(
        f"/api/v1/video/edge/{device_id}/tasks/777/snapshot",
        headers=auth_headers,
    )
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("image/jpeg")
    assert resp.content == _FAKE_JPEG


def test_snapshot_proxy_requires_auth(test_client):
    resp = test_client.get("/api/v1/video/edge/1/tasks/1/snapshot")
    assert resp.status_code in (401, 403)
```

> 说明：`monkeypatch.setattr(EdgeAgentClient, "fetch_snapshot", _fake_fetch)` 打桩后测试不触网；`_fake_fetch` 必须是普通函数返回协程（服务层 `await` 它）。

- [ ] **Step 2: 运行确认失败**

Run: `cd backend && uv run pytest tests/test_edge_snapshot_proxy.py -q`
Expected: FAIL（路由/方法不存在）

- [ ] **Step 3: 实现 `fetch_snapshot`**

在 `backend/app/api/v1/module_video/edge/agent_client.py` 末尾（`delete` 之后）新增：

```python
    async def fetch_snapshot(self, task_id: int, timeout: float = 5.0) -> bytes:
        """取 Agent 侧最新帧 JPEG（二进制，绕开仅处理 JSON 的 _request）。"""
        url = f"{self.control_url}/api/v1/tasks/{task_id}/snapshot.jpg"
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.get(url, headers=self._headers())
        except httpx.HTTPError as e:
            raise CustomException(msg=f"边缘快照请求失败: {url} ({e})", code=502, status_code=502) from e
        if response.status_code >= 400:
            raise CustomException(
                msg=f"边缘快照返回错误 {response.status_code}",
                code=502,
                status_code=502,
            )
        if not response.content:
            raise CustomException(msg="边缘快照为空", code=502, status_code=502)
        return response.content
```

- [ ] **Step 4: 实现 service**

在 `backend/app/api/v1/module_video/edge/service.py` 的 `EdgeService` 内新增：

```python
    @classmethod
    async def get_task_snapshot_service(cls, device_id: int, task_id: int, auth: AuthSchema) -> bytes:
        """经边缘设备控制面代理取某任务最新帧 JPEG。"""
        from .agent_client import EdgeAgentClient

        device = await EdgeCRUD(auth).get_by_id_crud(id=device_id)
        if not device:
            raise CustomException(msg="边缘设备不存在", code=404, status_code=404)
        if not (device.control_url or "").strip():
            raise CustomException(msg="边缘设备未配置控制面地址", code=400, status_code=400)
        client = EdgeAgentClient(device.control_url, device.secret)
        return await client.fetch_snapshot(task_id)
```

- [ ] **Step 5: 实现 controller 路由**

在 `backend/app/api/v1/module_video/edge/controller.py` 顶部 `from fastapi.responses import JSONResponse` 改为：

```python
from fastapi.responses import JSONResponse, Response
```

并在心跳路由之后新增：

```python
@EdgeRouter.get("/{device_id}/tasks/{task_id}/snapshot", summary="边缘任务快照预览")
async def get_edge_task_snapshot_controller(
    device_id: int = Path(..., description="边缘设备ID"),
    task_id: int = Path(..., description="布控任务ID"),
    auth: AuthSchema = Depends(AuthPermission(["module_video:algorithm:query"])),
) -> Response:
    content = await EdgeService.get_task_snapshot_service(device_id=device_id, task_id=task_id, auth=auth)
    return Response(content=content, media_type="image/jpeg", headers={"Cache-Control": "no-store"})
```

- [ ] **Step 6: 运行确认通过**

Run: `cd backend && uv run pytest tests/test_edge_snapshot_proxy.py -q`
Expected: PASS（2 passed）

- [ ] **Step 7: 全量 + ruff + 提交**

Run: `cd backend && uv run pytest -q && uv run ruff check app/api/v1/module_video/edge/agent_client.py app/api/v1/module_video/edge/service.py app/api/v1/module_video/edge/controller.py tests/test_edge_snapshot_proxy.py`
Expected: 全绿

```bash
git add backend/app/api/v1/module_video/edge/agent_client.py backend/app/api/v1/module_video/edge/service.py backend/app/api/v1/module_video/edge/controller.py backend/tests/test_edge_snapshot_proxy.py
git commit -m "feat(video): 边缘任务快照受控代理路由"
```

---

### Task 4: 前端布控详情展示边缘快照预览（可选，若前端已有布控详情）

**背景:** 若 `deploy` 详情/列表需要展示边缘预览，用新增受控路由 + 定时刷新。**若前端暂无落点，本任务可跳过并在报告中说明**（后端能力已就绪）。

**Files:**
- Modify: `frontend/src/api/module_video/edge.ts`（新增 `getEdgeTaskSnapshotUrl`）
- Modify: 布控页详情组件（按实际落点，仅少量改动）

**Interfaces:**
- Produces: `edgeSnapshotUrl(deviceId, taskId) -> string`（返回 `/api/v1/video/edge/{d}/tasks/{t}/snapshot`，配合既有 request 基址）。

- [ ] **Step 1: 实现 URL 助手**

在 `frontend/src/api/module_video/edge.ts` 末尾新增：

```ts
export function edgeTaskSnapshotUrl(deviceId: number, taskId: number): string {
  return `/api/v1/video/edge/${deviceId}/tasks/${taskId}/snapshot`;
}
```

- [ ] **Step 2: 详情展示（按现有页面结构）**

在布控任务详情/抽屉中，当 `task.edge_device_id` 存在且任务 RUNNING 时，用 `<el-image>` 指向 `edgeTaskSnapshotUrl(...)`，以 `setInterval` 2s 刷新（组件卸载清理）。仅改一处，遵循现有 Element Plus 写法。

- [ ] **Step 3: 类型检查**

Run: `cd frontend && pnpm run type-check`
Expected: 无新增错误

- [ ] **Step 4: 提交（如落地）**

```bash
git add frontend/src/api/module_video/edge.ts frontend/src/views/module_video/deploy/index.vue
git commit -m "feat(video): 布控页展示边缘快照预览"
```

---

### Task 5: 真机端到端联调（MQTT + HTTP）与 runbook

**前置:** Plan B（ModelDeploy）全部完成并已重编 `aistation_agent.exe`；本机 Docker 可用。

**Files:**
- Create: `scripts/e2e/edge_agent_e2e.ps1`
- Create: `docs/superpowers/runbooks/edge-agent-e2e.md`

**Interfaces:**
- 脚本参数：`-Transport mqtt|http`、`-AgentExe`、`-VideoPath`、`-ModelPath`、`-EdgeCode`、`-Secret`、`-ApiBase`、`-BackendDir`。
- 断言：设备 online、Agent 任务 running、告警落库且 `algorithm_type=INTRUSION`、快照非空、重复 event_id 不重复建告警、停/删同步。

- [ ] **Step 1: 起 broker 与 Agent**

- `docker run -d --name aistation-mqtt -p 1883:1883 eclipse-mosquitto`（匿名；如需鉴权则挂配置并配 `MQTT_USERNAME/PASSWORD`）。
- 起 Agent：
  `& $AgentExe --host 127.0.0.1 --port 19090 --data-dir <tmp> --model-cache-dir <tmp> --api-key $Secret --secret $Secret --cloud-url $ApiBase --edge-code $EdgeCode --heartbeat-interval 10`

- [ ] **Step 2: 种子数据**

用 admin 登录取 token，依次 `POST /api/v1/video/edge/create`、`POST /api/v1/video/algorithm/create`（`algorithm_type=INTRUSION`、`model_path=$ModelPath`、`runtime_config={"backend":"ort","device":"cpu"}`、`preset_params={"confidence_threshold":0.4,"input_size":[640,640]}`）、`POST /api/v1/video/camera/create`（`rtsp_url_sub=$VideoPath`）、`POST /api/v1/video/algorithm/task/create`（含 `edge_device_id`、覆盖中部的 `detect_region`、`schedule_json={"slots":[{"day":<今天>,"start":0,"end":24}]}`）。

- [ ] **Step 3: 启动并断言**

`POST /api/v1/video/algorithm/task/{id}/start`；轮询 `GET /api/v1/video/edge/tasks`（Agent）/`GET /api/v1/video/alarm/list`（云端），断言：
1. 设备 `status=online`；
2. Agent 任务 `running=true`；
3. 出现新告警且 `ai_result.algorithm_type == "INTRUSION"`；
4. 告警 `snapshot_url` 非空（内联快照已落 `DETECTIONS_DIR`）；
5. 再次投递相同 `event_id` 不新增告警。

- [ ] **Step 4: 时段与生命周期**

把 schedule 调到当前窗口外（更新任务），确认不再新增告警；`POST .../stop` 断言 Agent 任务停止；`DELETE` 任务断言 Agent 侧同步删除。

- [ ] **Step 5: HTTP 通道复跑**

设 `VIDEO_ANALYSIS_MODE=cloud_only` 重启后端，重复 Step 2–4，断言事件走 `events.http` 到达。

- [ ] **Step 6: 记录 runbook 与证据**

`docs/superpowers/runbooks/edge-agent-e2e.md` 记录：环境版本、命令、关键日志、DB 查询（`alarm_record` 行）、失败排障表（心跳无 code → C9；MQTT 连不上 → scheme；模型路径 → 本地/远端）。

- [ ] **Step 7: 提交**

```bash
git add scripts/e2e/edge_agent_e2e.ps1 docs/superpowers/runbooks/edge-agent-e2e.md
git commit -m "test(video): 云边 Agent 真机端到端联调脚本与 runbook"
```

---

## Self-Review

**Spec coverage:**
- C1 algorithm_type / C1 tenant → Task 1 ✅
- C2 broker scheme → Task 1 ✅
- C3 username/password → Task 1 ✅
- C4 per-edge client_id → Task 1 ✅
- C5 schedule 透传 → Task 1（AIStation 侧；执行在 Plan B）✅
- C7 snapshot 下发 → Task 1 ✅
- C8 preview 下发（快照流）→ Task 1 + Task 3（代理）+ Task 4（前端）✅
- C9 心跳 edge_code → Task 2 ✅
- 真机 E2E → Task 5 ✅

**Placeholder scan:** 无 TBD；Task 4 允许「无落点则跳过并报告」已显式说明。

**Type consistency:** `normalize_broker_scheme`/`extract_device_code`/`fetch_snapshot`/`get_task_snapshot_service` 命名前后一致。

**风险:** Task 3 测试对 `EdgeAgentClient.fetch_snapshot` 打桩，不依赖真实 Agent；Task 5 依赖 Plan B 与本地 Docker/CPU 环境，属集成验证。
