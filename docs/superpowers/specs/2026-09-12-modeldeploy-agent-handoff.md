# AIStation 布控 Agent（ModelDeploy）— 实现交接

> 目标仓库：`E:\CLionProjects\ModelDeploy`
> 配套系统设计：AIStation 仓库 `D:\AIStation\docs\superpowers\specs\2026-09-12-cloud-edge-visual-analysis-design.md`
> 状态：本仓库据此产出正式 spec + plan 并实现
> **硬性原则：不改动 `application/surveillance`（含其源文件、测试、行为）；Agent 基于 ModelDeploy SDK 新建。**

---

## 0. 背景与目标

AIStation 是云端视频分析平台（FastAPI）。其"布控"需要**实时多路 RTSP** 推理。经评估：ModelDeploy SDK 是正确依赖；`surveillance` 是通用参考应用，**不塞入** AIStation 专属逻辑。因此新建专用**布控 Agent**：只负责「按云端配置做 RTSP 解码→推理→（可选）编码/快照→事件上报 + 能力心跳」，业务（摄像头/算法/告警/通知）由 AIStation 负责。

**非目标**：不实现 AIStation 的告警/业务；不改 `surveillance`；一期不做模型热更新/自动改派（列二期）。

---

## 1. 现状可复用资产（务必复用，勿重复造）

| 资产 | 路径 | 提供能力 |
|---|---|---|
| `TaskConfig`/`ModelConfig`/`DecoderConfig`/`EncoderConfig`/`DrawConfig` | `application/config.hpp` | 任务/模型/编解码/绘制配置 + JSON 序列化 |
| `PipelineManager` | `application/pipeline_manager.hpp` | 任务 CRUD/启停/统计/JPEG、模型库、`update_task`、`stop_all`、`load/save_to_directory`、`create_engine`、多路共享检测器池 |
| `Pipeline` | `application/pipeline.{hpp,cpp}` | 每路解码→有界队列→`detect_loop` 推理→绘制→`encode_async` |
| `InferGroup`/`InferenceEngine`/`BatchedDetector` | `application/infer_group.hpp`、`inference_engine.hpp`、`batched_detector.hpp` | 模型加载/克隆/共享批推理；`DetectionBox`/`InferResult` |
| `DrawEngine`/`VideoSource`/`VideoSink`/`video_codec` | `application/*.hpp` | 绘制、SDK 解码/编码封装 |
| `HttpServer` | `application/http_server.{hpp,cpp}` | 现成 REST 路由风格（`/api/v1/tasks...`）、统一错误体、可选鉴权/限流 |
| `runtime_factory` | `application/runtime_factory.cpp` | 后端/设备 → RuntimeOption 装配 |
| Catch2 测试 | `application/tests/*` | 测试约定（`surveillance_test`） |

> `surveillance` 的 `application/CMakeLists.txt` 把上表除 `main.cpp` 外编成 `surveillance`/`surveillance_test`。Agent 需要复用同一批组件。

**关键缺口（本任务要补）**：现有 pipeline 只把检测结果用于绘制，**没有对外事件回调**；`HttpServer` 也不认识 AIStation 的 TaskConfig（模型 URL/事件配置/心跳）。这两点是 Agent 的核心新增。

---

## 2. 新增设计

### 2.1 组件划分（薄封装）

```
application/aistation_agent/
  main.cpp                # 解析参数(--port/--data-dir/--api-key/--cloud-url/--edge-code/--secret)，装配并运行
  agent_server.{h,cpp}    # 控制面 REST（复用 HttpServer 风格；见 §3.1）
  config_adapter.{h,cpp}  # AIStation TaskConfig(JSON) → SDK TaskConfig + ModelConfig（含模型 URL 拉取）
  model_fetcher.{h,cpp}   # 按 url(s3://|http(s)://|local) 下载/校验到缓存目录
  event_bus.{h,cpp}       # 每任务检测结果回调注册与分发（节流+组装事件）
  event_publisher.{h,cpp} # EventPublisher 接口 + MqttPublisher + HttpPublisher（含本地缓存补发）
  heartbeat.{h,cpp}       # 能力探测 + 周期心跳上报
  capability.{h,cpp}      # 能力探测：可用后端/模型族/最大路数/编解码/硬件
  CMakeLists.txt
```

### 2.2 检测事件钩子（核心）

在**不复用 `surveillance` 行为**的前提下，为 Agent 增加一条事件通道：
- 在 `Pipeline` 的检测关键路径完成后（拿到 `InferResult`/`DetectionBox` 列表）触发一个**回调**（新增可选成员，默认空=不影响 `surveillance`）。
- 暴露 `EventBus`：`register(task_id, sink)` / `unregister(task_id)`；`sink(DetectionEvent)`。
- `PipelineManager` 增加 `set_event_sink(task_id, sink)`（或 `EventBus` 由 Agent 注入 Pipeline 构造）——**实现方式二选一，但必须保证 surveillance 未注册时零行为差异**。
- 事件组装：应用 ROI 过滤（已在 pipeline 内）、`alarm_interval_sec` 节流（label 维度）、`event_id=uuid`、`ts`、`latency_ms`。

> 推荐：给 `Pipeline` 增加 `std::function<void(const std::vector<DetectionBox>&, double latency_ms)> on_detections_`（默认空），`PipelineManager::create_task` 之余提供 setter；Agent 注入。surveillance 不调用 setter，行为不变。

### 2.3 事件发布

`EventPublisher` 接口：`bool publish(const DetectionEvent& e)`。
- `MqttPublisher`：`paho.mqtt.c` 或 `mosquitto` 客户端；QoS1；稳定 `client_id`；断线重连；发布主题见 §3.3。
- `HttpPublisher`：POST `events.http.url`，`Authorization: Bearer {token}`，超时/重试。
- **本地缓存补发**（边缘）：发布失败/离线时写本地队列（目录文件或 SQLite，`buffer.dir`/`max_mb`）；恢复后按序补发；`event_id` 供云端去重；超限丢最旧并计数（暴露于 `/api/v1/metrics`）。

### 2.4 能力探测与心跳

- `capability.detect()`：依据构建开关与运行环境产出 `{hardware:{platform,gpu_model,vram_mb}, backends:[...], model_families:[...], max_channels, codecs:{decode,encode,hw}}`。
  - `backends` 由编译时的 `ENABLE_ORT/MNN/TRT/NCNN/SOPHGO` 决定（编译期宏）。
  - `platform` 依据 `WITH_GPU`/Jetson/Sophgo/CPU 探测。
- 启动 + 周期（默认 30s）`POST {cloud_url}/api/v1/video/edge/heartbeat`：
  `{edge_code, token, capabilities, metrics:{running_channels,event_queue_len,event_dropped_total,cpu,gpu,vram}, version}`；失败退避重试，不阻塞布控。

---

## 3. 接口契约（**必须与 AIStation 严格一致**）

### 3.1 控制面 REST（Agent 监听，默认端口 19090；`Authorization: Bearer <secret>` 非空启用）

| 方法 | 路径 | 请求 | 响应 |
|---|---|---|---|
| GET | `/health` | — | `{status:"ok"}`（进程在线） |
| GET | `/readyz` | — | 200/503（无任务卡在 Loading/Failed） |
| GET | `/api/v1/metrics` | — | 文本或 JSON：在跑路数、事件队列、丢弃计数 |
| POST | `/api/v1/tasks` | AIStation TaskConfig（§3.2） | `{task_id}`；模型拉取失败→400 |
| GET | `/api/v1/tasks` | — | `{items:[{task_id,name,running,input_url,preview_url,models,error}]}` |
| GET | `/api/v1/tasks/:id` | — | 单任务状态 |
| POST | `/api/v1/tasks/:id/start` | — | `{running:true}` |
| POST | `/api/v1/tasks/:id/stop` | — | `{running:false}` |
| PUT | `/api/v1/tasks/:id` | TaskConfig（先停后改） | 200 |
| DELETE | `/api/v1/tasks/:id` | — | 200 |
| GET | `/api/v1/tasks/:id/stats` | — | 透传 PipelineManager stats（fps/丢弃/延迟） |
| GET | `/api/v1/tasks/:id/snapshot.jpg` | — | 最新帧 JPEG |

统一错误体：`{ "error": { "code": "...", "message": "..." } }`（与 ServingServer 一致）。
状态码：200/400(BAD_REQUEST)/401(UNAUTHORIZED)/404(NOT_FOUND)/503(MODEL_NOT_READY)。

### 3.2 TaskConfig（AIStation 下发 → Agent 消费）

```jsonc
{
  "task_id": 123,
  "camera": { "id": 7, "name": "北门", "url": "rtsp://...", "transport": "tcp" },
  "models": [
    { "name": "aistation-det", "type": "det", "backend": "trt", "device": "gpu",
      "url": "s3://.../model.engine", "labels": ["person","car"], "input_size": [640,640],
      "confidence_threshold": 0.45 }
  ],
  "roi": [[0.1,0.1],[0.9,0.1],[0.9,0.9],[0.1,0.9]],
  "sensitivity": 60,
  "schedule": { "days": [0,1,2,3,4], "start": "08:00", "end": "18:00" },
  "alarm_interval_sec": 30,
  "preview": { "enabled": true, "format": "flv" },
  "events": {
    "transport": "mqtt",
    "mqtt": { "broker": "tcp://edge-broker:1883", "topic": "aistation/default/edge/edge-01/camera/7/detect",
              "qos": 1, "client_id": "aistation-agent-edge-01", "username": "", "password": "" },
    "http": { "url": "http://cloud/api/v1/video/algorithm/detection/callback", "token": "..." },
    "buffer": { "dir": "./events_buffer", "max_mb": 512 }
  },
  "decoder": { "hw_accel": "cuda", "device_only": true, "rtsp_transport": "tcp" },
  "encoder": { "codec": "h264_nvenc", "format": "flv", "bitrate_kbps": 2500 }
}
```
映射：`roi`→`ModelConfig.roi`（或 pipeline ROI mask）；`sensitivity`→`confidence_threshold` 参考（AIStation 已按灵敏度给出 `confidence_threshold`，Agent 直接用后者为准）；`preview`→`enable_preview`+`output_url/preview_url`（用 SDK 编码）；`events`→事件发布；`decoder/encoder`→`DecoderConfig/EncoderConfig`。

### 3.3 事件契约（Agent → 云端）

主题：`aistation/{tenant}/edge/{edge_code}/camera/{camera_id}/detect`
（AIStation 订阅通配 `aistation/+/edge/+/camera/+/detect`；`tenant` 默认 `default`）

```jsonc
{
  "event_id": "uuid",
  "edge_code": "edge-01",
  "camera_id": 7, "task_id": 123,
  "algorithm_type": "INTRUSION",
  "ts": "2026-09-12T08:00:00.123Z",
  "detections": [
    { "label": "person", "label_id": 0, "confidence": 0.91,
      "bbox": { "x": 0.1, "y": 0.2, "width": 0.15, "height": 0.3 } }   // 归一化
  ],
  "latency_ms": 12.3,
  "snapshot": { "ref": "edge-01/cam7/2026-09-12/xxxx.jpg" },
  "schema_version": 1
}
```
- `bbox` 归一化（除以帧宽高），与 AIStation 现 callback 一致。
- `snapshot.ref`：相对引用；边缘把快照上传对象存储（或低频内联 base64，字段 `snapshot.data`）。
- `algorithm_type` 由 TaskConfig 传入（AIStation 侧提供），Agent 原样带回。
- HTTP 通道：同一 JSON POST 到 `events.http.url`，头 `Authorization: Bearer {token}`。

### 3.4 心跳

`POST {cloud_url}/api/v1/video/edge/heartbeat`
```jsonc
{ "edge_code":"edge-01", "token":"...",
  "capabilities": { "hardware": {...}, "backends": ["trt","mnn"], "model_families": ["det","cls",...],
                    "max_channels": 8, "codecs": {"decode":["h264","h265"],"encode":["h264"],"hw":["nvenc"]} },
  "metrics": { "running_channels": 2, "event_queue_len": 0, "event_dropped_total": 0 },
  "version": "1.0.0" }
```

---

## 4. 构建与依赖

- 顶层 `CMakeLists.txt` 新增 `option(BUILD_AISTATION_AGENT "build AIStation edge agent" OFF)`；`option(ENABLE_MQTT "enable MQTT event publisher" OFF)`。
- `BUILD_AISTATION_AGENT=ON` 时强制 `BUILD_VISION=ON`、`BUILD_VIDEO=ON`（参照 `BUILD_SURVEILLANCE` 的强制逻辑）。
- `application/CMakeLists.txt`：新增 `if (BUILD_AISTATION_AGENT) ... add_executable(aistation_agent ...) ... endif()`；**复用同一批 `APP_SOURCES`（除 `main.cpp`）**，避免复制。
  - 若要与 `surveillance` 共用源文件，把可复用源编译为对象库/静态库（如 `app_common`），`surveillance` 与 `aistation_agent` 各自链接——**保证 `surveillance` 目标与测试仍全绿**。
- MQTT：`ENABLE_MQTT=ON` 引入 `paho.mqtt.c`（vcpkg/子模块）或 `mosquitto`；OFF 时仅 HTTP 事件（`MqttPublisher` 编译为空实现）。
- 交叉编译/Jetson/Sophgo 与 `surveillance` 同法。

构建示例：
```bash
cmake -S . -B build -G Ninja -DBUILD_AISTATION_AGENT=ON -DENABLE_MQTT=ON -DBUILD_VISION=ON -DWITH_GPU=ON
cmake --build build --target aistation_agent --parallel
cmake --build build --target aistation_agent_test --parallel   # 若配测试
```

---

## 5. 任务拆分（建议顺序，各自可验证）

1. **共享源库抽取**：把 `application` 可复用源（除 `main.cpp`）编译为 `app_common`；`surveillance`/`surveillance_test` 链接之，**测试全绿（行为不变）**。
2. **Agent 骨架 + 控制面**：`main.cpp` + `agent_server`（`/health`、`/api/v1/tasks` 增删改查/启停/统计/snapshot），内部复用 `PipelineManager`；`ConfigAdapter` 解析 §3.2（先本地路径模型）→ 单路本地视频文件 det 跑通。
3. **检测事件钩子**：`Pipeline`/`PipelineManager` 增加可选 `on_detections` 回调（默认空）；`EventBus` 注册分发；`alarm_interval_sec` 节流、`event_id`。
4. **HTTP 事件发布**：`HttpPublisher` 发 §3.3 到本地 mock 接收器；错误重试。
5. **MQTT 事件发布**：`MqttPublisher`（QoS1）+ `ENABLE_MQTT`；订阅端收到。
6. **边缘缓存补发**：离线写队列、恢复补发、超限丢弃计数、`event_id` 去重。
7. **能力探测与心跳**：`capability.detect()` + `POST .../heartbeat`（对 mock 云端）。
8. **模型 URL 拉取**：`model_fetcher`（s3/http/local）+ 校验 + 按 `backend/type` 构造；ONNX(ORT) 优先，TRT/MNN 次之。
9. **预览/快照**：FLV 推流 + `/snapshot.jpg`；与 AIStation 前端联调。
10. （二期）控制面 WebSocket/MQTT 双向、模型热更新、自动改派。

---

## 6. 验收

- 单路 RTSP（本地素材/文件）→ det → **事件经 HTTP 与 MQTT 各到达一次**（不重复、不丢）。
- 断网 30s 事件缓存，恢复后补齐且云端按 `event_id` 去重。
- `/api/v1/tasks` 生命周期正确；能力/心跳在云端可见；`/snapshot.jpg` 可取。
- **`surveillance` 的行为与测试保持不变**（抽取共享库后其测试仍全绿）。
- 单元测试（Catch2，沿用 `application/tests` 习惯）：ConfigAdapter 映射、EventBus 节流、缓存补发、capability、心跳载荷。

## 7. 风险 / 开放问题

- `on_detections` 注入方式：改 `Pipeline` 构造 vs `PipelineManager` setter——选可保证 surveillance 零差异者；实现前先确认插入点（`pipeline.cpp` 的 `detect_loop` 拿到结果处）。
- 异步发布线程模型：事件发布需与检测线程解耦（有界队列 + 独立发布线程），避免阻塞 `detect_loop`。
- 模型格式/后端：边缘后端各异，一期先 ONNX(ORT) 一条线；TRT/MNN 按 `backends` 选择。
- MQTT 库选型（paho.mqtt.c vs mosquitto）与 vcpkg 可用性需先验证。
- 与 AIStation 的契约以本文为准；任何变更需同步 AIStation 侧（`module_video/edge`、`build_agent_task_config`、`consumer`）。
