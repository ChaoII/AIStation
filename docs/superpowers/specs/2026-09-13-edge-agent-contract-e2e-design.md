# 边缘布控 Agent 契约统一与真机联调 设计

> 创建日期：2026-09-13
> 状态：方向已确认（方案 2：双侧统一契约；B5/B6/B7 全部纳入，不延期）
> 关联：
> - 系统设计 `docs/superpowers/specs/2026-09-12-cloud-edge-visual-analysis-design.md`
> - Agent 交接 `docs/superpowers/specs/2026-09-12-modeldeploy-agent-handoff.md`
> - AIStation 侧已实现：Phase 3C（`module_video/edge`）、Phase 3D（云边前端）
> - ModelDeploy 侧已实现：`application/aistation_agent/`（10/10 任务，终审通过）

## 1. 背景与现状

AIStation（云）与 ModelDeploy `aistation_agent`（边）**各自按 spec 独立实现并已完工，但从未真机联调**。原 Phase 3C 明确「Agent 未就绪期间用 mock，真机端到端待 Agent 落地」，该遗留项即为本次工作。

逐字段比对两侧实际实现后，确认了一批契约不一致与能力缺口（见 §4/§6）。本次目标：**把两侧契约统一到同一份定义，并在真机上把 MQTT、HTTP 两条事件通道各跑通一次**；沿途发现的缺陷一并修复。

### 1.1 已确认一致（不改）
- 控制面 REST：`GET /health`、`GET /readyz`、`GET /api/v1/metrics`、`POST/GET /api/v1/tasks`、`POST /api/v1/tasks/:id/start|stop`、`PUT/DELETE /api/v1/tasks/:id`、`GET /api/v1/tasks/:id/stats|snapshot.jpg`。
- 心跳：`POST {cloud_url}/api/v1/video/edge/heartbeat`，载荷 `{edge_code,token,capabilities,metrics,version}`。
- 事件字段：`event_id/edge_code/camera_id/task_id/algorithm_type/ts/detections[{label,label_id,confidence,bbox{x,y,width,height}}]/latency_ms/snapshot/schema_version`，`bbox` 归一化。
- HTTP 事件回调鉴权：`Authorization: Bearer {INFERENCE_CALLBACK_TOKEN}`。
- 能力族取值 `["det","cls","face"]` 与编排要求 `"det"` 匹配。
- 模型本地路径（无 scheme / `file://`）与远端 URL 拉取逻辑。

## 2. 目标

1. 统一 TaskConfig / 事件 / 心跳契约，消除 §4、§6 列出的不一致。
2. 边缘侧落地 **schedule（布控时段）**、**ROI 多边形精确过滤**、**事件内联快照**、**快照预览**。
3. 真机端到端：MQTT 与 HTTP 两条通道均完成「下发 → 推理 → 事件 → 告警落库」。
4. 双侧既有测试全绿、无回归。

## 3. 非目标

- 不改 `application/surveillance`（硬性约束，沿用 Agent 交接 §0）。
- 不做模型热更新 / 自动改派（明确二期）。
- 不引入对象存储上传（快照走内联 base64，见 §4.4）。
- FLV 实时视频推流：见 §6.4 的判定说明。

## 4. 统一契约

约定：**以 AIStation 现有数据模型为准**，Agent 适配；编号 C1–C8 为本次必须达成项。

### 4.1 TaskConfig（统一后）

```jsonc
{
  "task_id": 123,
  "tenant": "default",                       // 主题/多租户；缺省 default
  "algorithm_type": "INTRUSION",             // C1：Agent 原样回带进事件
  "camera": { "id": 7, "name": "北门", "url": "rtsp://... | /abs/video.mp4", "transport": "tcp" },
  "models": [
    { "name": "aistation-det", "type": "det", "backend": "ort", "device": "cpu",
      "url": "/abs/model.onnx",              // 本地路径或 http(s)/s3 URL
      "labels": ["person","car"], "input_size": [640,640], "confidence_threshold": 0.45 }
  ],
  "roi": [[0.1,0.1],[0.9,0.1],[0.9,0.9],[0.1,0.9]],   // C5：归一化多边形（空=全画面）
  "sensitivity": 60,
  "schedule": { "slots": [ { "day": 0, "start": 8, "end": 18 } ] },  // C5：见 4.2
  "alarm_interval_sec": 30,
  "events": {
    "transport": "mqtt",                     // mqtt | http
    "mqtt": {
      "broker": "tcp://host:1883",           // C2：统一 tcp:// | ssl://
      "topic": "aistation/default/edge/edge-01/camera/7/detect",
      "qos": 1,
      "client_id": "aistation-agent-edge-01", // C4：每边缘唯一
      "username": "", "password": ""          // C3：可为空
    },
    "http": { "url": "http://cloud/.../detection/callback", "token": "..." },
    "buffer": { "dir": "./events_buffer", "max_mb": 512 },
    "snapshot": { "enabled": true, "inline": true, "quality": 75, "max_width": 640 } // C7
  },
  "preview": { "enabled": true, "format": "snapshot" },   // C8：snapshot 快照流
  "decoder": { "hw_accel": "cuda", "device_only": true, "rtsp_transport": "tcp" },
  "encoder": { "codec": "h264_nvenc", "format": "flv", "bitrate_kbps": 2500 }
}
```

### 4.2 schedule 语义（C5）

AIStation 实际模型为 **7×24 网格**，统一采用：

```jsonc
{ "slots": [ { "day": 0, "start": 8, "end": 18 } ] }
```

- `day`：`0..6` 对应 **周一..周日**（ISO，周一=0；与前端 `weekDays=["周一",...,"周日"]` 一致）。
- `start` / `end`：**整点小时** `0..24`，`[start, end)` 半开区间；`end=24` 表示到当日末。
- `slots` 为空或缺省 → **不限制时段**（全天有效）。
- 判定：以**边缘本地时区**当前 星期+小时 落于任一 slot 则 active。
- 跨天（如 22:00–次日 06:00）本期不支持；若需，另开 slot（前端网格本身以日为界）。

### 4.3 事件载荷

沿用现有字段，新增/明确：

```jsonc
{
  "event_id": "uuid", "edge_code": "edge-01", "camera_id": 7, "task_id": 123,
  "algorithm_type": "INTRUSION",
  "ts": "2026-09-13T08:00:00.123Z",
  "detections": [ { "label": "person", "label_id": 0, "confidence": 0.91,
                    "bbox": { "x":0.1,"y":0.2,"width":0.15,"height":0.3 } } ],
  "latency_ms": 12.3,
  "snapshot": { "data": "<base64 jpeg>", "width": 640, "height": 360 },  // C7：inline
  "schema_version": 1
}
```

- C7：`snapshot.data` 内联 base64（受 `events.snapshot` 控制）；AIStation 现有 `normalize_edge_event`/`process_detection_callback` 已支持 `snapshot.data` → 落 `DETECTIONS_DIR`。
- 不实现 `s3://` 上传；`snapshot.ref` 保留字段但本期 Agent 不产出。

### 4.4 心跳 / 控制面
不变（§1.1）。

## 5. AIStation 侧改动

| 文件 | 改动 |
|---|---|
| `backend/app/api/v1/module_video/edge/orchestrator.py` | C1 下发 `algorithm_type`、`tenant`；C2 broker scheme 归一化（`mqtt://→tcp://`、`mqtts://→ssl://`）；C3 下发 `username/password`；C4 per-edge `client_id`；C7 `events.snapshot`；C8 `preview`；C5 原样透传 `schedule_json` |
| `backend/app/config/setting.py` | 新增 `MQTT_SNAPSHOT_ENABLED/INLINE/QUALITY/MAX_WIDTH`（带默认，默认开启 inline）；`EDGE_PREVIEW_ENABLED` |
| `backend/app/api/v1/module_video/edge/controller.py` + `service.py` | C8 新增受控预览代理：`GET /video/edge/{device_id}/tasks/{task_id}/snapshot`（鉴权 `module_video:algorithm:query`，经 `device.control_url` + Bearer secret 取 Agent `/api/v1/tasks/{task_id}/snapshot.jpg`，落受控返回 JPEG） |
| 测试 | `tests/test_edge_task_config.py`：C1–C4/C7/C8 纯函数断言 |
| 前端 | 布控详情/列表按需展示「边缘预览」快照（复用受控路由+定时刷新）；仅新增/触碰文件 |

不改：事件消费链路（已兼容 `snapshot.data`）、心跳、控制面客户端。

## 6. ModelDeploy 侧改动（`application/aistation_agent/`）

### 6.1 契约适配 `config_adapter.{hpp,cpp}`
- C1：解析顶层 `algorithm_type`（已有）→ 确认随 `AdaptedTask` 传出。
- C2：`normalize_broker_scheme()`：`mqtt://→tcp://`、`mqtts://→ssl://`、纯 `host:port→tcp://host:port`；用于 `MqttConfig.broker`。
- C3：透传 `mqtt.username/password`（已解析，确认落到 `MqttConfig`）。
- C5：解析 `schedule.slots[{day,start,end}]` → `AdaptedTask.schedule`。
- C7：解析 `events.snapshot{enabled,inline,quality,max_width}` → `AdaptedTask.snapshot`。
- C8：解析 `preview.enabled/format`（format `snapshot` 时无需 FLV 编码）。

### 6.2 schedule 执行（C5，任务级启停 + 事件级兜底）
- 新增 `ScheduleController`（`agent_runtime` 内，独立线程，默认 30s 轮询）：
  - 对每个已注册任务按 §4.2 判定 active；active→`mgr_.start_task`，inactive→`mgr_.stop_task`（幂等，使用 `list_tasks().running` 去抖）。
  - 任务创建/更新时登记 schedule；删除时注销。
- **兜底**：`EventBus` 的 `EventMeta` 携带 schedule，`on_detections` 入口再次判定；窗口外直接丢弃（防止启停切换竞态漏发）。
- 线程安全：schedule slot 变换与启停均经锁；停止时先停线程再析构。

### 6.3 ROI 多边形精确过滤（C6）
- `config_adapter` 保留完整多边形（不再只取外接矩形）→ `AdaptedTask.roi_polygon`。
- SDK 侧：仍以**外接矩形**（`roi_norm=[x,y,w,h]`）设置 `ModelConfig`，用于裁剪/降算力。
- **精确门控**：`EventBus.on_detections` 输入各框中心点做**射线法点在多边形内**判定，仅保留多边形内的检测；`roi` 为空则不过滤。
- 新增纯函数 `point_in_polygon(x,y,pts)` 单测（凹多边形、边界、退化输入）。

### 6.4 事件快照与预览（C7/C8）
- **快照**：`events.snapshot.enabled && inline` 时，事件发布前取 `PipelineManager::get_task_jpeg(task_id, quality)`，按 `max_width` 等比缩放，JPEG→base64 写入 `snapshot.data` + `width/height`。
  - 采集发生在**发布线程/队列 worker**，不得阻塞 `detect_loop`；失败仅告警、事件照发（无 snapshot）。
  - 未启用或取帧失败 → 事件不带 snapshot（AIStation 已容忍）。
- **预览**：`preview.format=="snapshot"` 时，直接复用既有 Agent `/api/v1/tasks/:id/snapshot.jpg`（已实现），由 AIStation §5 受控代理转发；前端定时刷新。
  - FLV 实时流：当前 Agent 的 `enable_preview/output_url` 仅为**占位赋值，无编码推流实现**；真正的 FLV 实时流需要「编码器 + 流媒体服务」新子系统，与本次「事件链路对接」正交。**本次交付快照流预览**；FLV 若需，另立 spec（见 §9 开放问题）。

### 6.5 测试（Catch2）
- `test_config_adapter`：C1/C2/C5/C7/C8 解析；broker scheme 归一化表驱动。
- `test_schedule`（新增）：窗口内/外、空 slots=全天、day 边界、start/end 端点、跨 slot。
- `test_event_bus`：schedule 兜底丢弃、ROI 多边形过滤（内含/边界/多边形外）、快照字段。
- `test_e2e_agent` 增补：带 schedule+snapshot 的本地视频跑通，断言事件含 `snapshot.data`。

### 6.6 构建/回归
- 既有 `build`（`BUILD_AISTATION_AGENT=ON`、`ENABLE_MQTT=ON`）重编 `aistation_agent` + `aistation_agent_test`。
- `ctest` 运行 `[aistation_agent]`；确保 `surveillance` 行为不变（未触碰其源）。

## 7. 真机端到端联调

### 7.1 环境
- Broker：Docker `eclipse-mosquitto`（匿名，映射 `1883`；如带鉴权则配 C3）。
- 视频/模型夹具（ModelDeploy 既有资产）：
  - 视频 `E:\CLionProjects\ModelDeploy\test_data\test_video60.mp4`
  - 模型 `E:\CLionProjects\ModelDeploy\test_data\test_models\onnx\yolo11n\yolo11n_nms.onnx`
- Agent：`E:\CLionProjects\ModelDeploy\build\bin\aistation_agent.exe`
  `--host 127.0.0.1 --port 19090 --data-dir <tmp> --model-cache-dir <tmp> --api-key <S> --secret <S> --cloud-url http://127.0.0.1:8001 --edge-code edge-01 --heartbeat-interval 10`
  （`--api-key` 用于 AgentServer 控制面 Bearer 鉴权、`--secret` 用于心跳 token；实现时确认二者与 AIStation `EDGE_CONTROL_TOKEN`、`EdgeDevice.secret` 的对应关系并保持一致。）
- AIStation：`.env.dev` 设
  `VIDEO_ANALYSIS_MODE=cloud_edge`、`MQTT_ENABLED=true`、`MQTT_BROKER_URL=tcp://127.0.0.1:1883`、
  `MQTT_TOPIC_PREFIX=aistation/default/edge`、`MQTT_SUBSCRIBE_TOPIC=aistation/+/edge/+/camera/+/detect`、
  `MQTT_CLIENT_ID=aistation-events`、`INFERENCE_CALLBACK_TOKEN=<T>`、`EDGE_CONTROL_TOKEN=<S>`（与 Agent secret 一致）。

### 7.2 种子数据
- EdgeDevice：`code=edge-01`，`control_url=http://127.0.0.1:19090`，`secret=<S>`，`capabilities.model_families=["det"]`、`backends=["ort"]`、`max_channels>=1`。
- Algorithm：`code=aistation-det`，`algorithm_type=INTRUSION`，`model_path=<onnx 绝对路径>`，`runtime_config={"backend":"ort","device":"cpu","decoder":{"hw_accel":"<按 SDK 支持的软件解码取值，实现时确认>"}}`，`preset_params={"confidence_threshold":0.4,"labels":[...],"input_size":[640,640]}`。
- Camera：`rtsp_url_sub=<mp4 绝对路径>`（`stream_type=SUB`）。
- AlgorithmTask：绑定上三者，`edge_device_id=<device>`，`detect_region` 给一个覆盖画面中部的多边形，`sensitivity=60`，`schedule_json={"slots":[...]}`。

### 7.3 流程（两条通道各一次）
1. 起 broker / Agent / 后端；等待心跳 → 断言 EdgeDevice `status=online`、`capabilities` 可见。
2. 调 `POST /video/algorithm/task/{id}/start`（AIStation）→ 编排下发+启动。
3. 断言 Agent `/api/v1/tasks` 中出现该 task 且 `running=true`。
4. 等待事件：MQTT 经 `EdgeEventConsumer`；HTTP 经回调路由 → `process_detection_callback`。
5. 断言：`alarm_record` 落库；`alarm_type`/`ai_result.algorithm_type == "INTRUSION"`；`snapshot_path` 非空（内联快照已落 `DETECTIONS_DIR`）；重复 `event_id` 不重复建告警。
6. 时段外：将 schedule 调到当前不在窗口，断言不再产生新告警（任务被停或事件被兜底丢弃）。
7. 收尾：停任务 → `POST .../stop` → 断言 Agent 任务停止；删除任务 → Agent 侧同步删除。
8. HTTP 通道：`VIDEO_ANALYSIS_MODE=cloud_only` 重跑 2–7（事件走 `events.http`）。

### 7.4 产物
- 可复现脚本：`scripts/e2e/edge_agent_e2e.ps1`（编排 broker/Agent/后端/种子/断言，参数 `-Transport mqtt|http`）。
- 联调 runbook：`docs/superpowers/runbooks/edge-agent-e2e.md`（环境、命令、排障、证据）。

## 8. 验收标准

- 双侧单测：AIStation `uv run pytest`（含新增 `test_edge_task_config.py`）全绿 + `ruff` 无新增；ModelDeploy `ctest` 的 `[aistation_agent]` 全绿，`surveillance` 不受影响。
- 真机 E2E：MQTT 与 HTTP **各**跑通 §7.3，关键断言全部通过并留存证据（日志/DB 查询/截图）。
- `algorithm_type` 正确贯通；schedule 生效；ROI 多边形过滤生效；事件含内联快照并可展示。
- 无 `git add -A`；提交信息 `feat(video): …` / `fix(video): …`（AIStation）与 ModelDeploy 既有规范一致。

## 9. 风险与开放问题

1. **FLV 实时流**：Agent 无推流实现，属新子系统。**本次以快照流预览交付**；若要求 FLV，需另立 spec/plan（涉及编码器与流媒体服务选型）。
2. **ROI mask vs 外接矩形+多边形门控**：采用后者（精确过滤事件、裁剪降算力），不改 SDK mask 语义。
3. **快照体积**：内联 base64 增大事件体；以 `max_width`/`quality`/`alarm_interval_sec` 约束，默认 640/75。
4. **CPU/文件夹具**：真实边缘为 RTSP+GPU；本次联调用本地视频+ORT/CPU，链路等价，性能不代表生产。
5. **schedule 跨天**：不支持，slot 以日为界（前端网格即是）。
6. **时区**：以边缘本地时区判定；如云端/边缘时区不一致需运维对齐。
7. **MQTT 鉴权/TLS**：本次匿名明文；C2/C3 已为鉴权/TLS 留好通道。

## 10. 交付拆分

- **Spec（本文）** → 复核通过后进入计划。
- **Plan A（AIStation 仓库）**：§5 改动 + §7 脚本/runbook 中的云端部分。
- **Plan B（ModelDeploy 仓库）**：§6 改动 + 对应测试。
- 两者各自独立可验证；§7 真机联调在 A+B 均完成、Agent 重编后进行（需本地 Docker 与 GPU/CPU 环境）。
