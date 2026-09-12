# 云边协同视觉分析系统 设计（AIStation × ModelDeploy）

> 创建日期：2026-09-12
> 状态：方向已确认（用户赞同"基于 ModelDeploy SDK 新建专用布控 Agent，不改 surveillance"）
> 关联：`2026-09-11-pipeline-optimization-program-design.md`（Phase 3 的布控部分按本文重写）

## 1. 背景与目标

AIStation 现有视频布控依赖未安装的 `modeldeploy`(FastDeploy) Python 模块，且把"解码 + 推理 + 调度 + 告警"全塞在 Python worker 里，实时性与多路能力都不足。本地存在 **ModelDeploy**（自研 C++ 推理 SDK：`ModelDeploySDK` + `csrc/video`、`csrc/vision`、`ServingServer`、`surveillance` 应用），是布控算法的正确依赖。

目标：构建**云边协同的视觉分析系统**——
- **边缘模式（云边协同）**：边缘设备运行基于 ModelDeploy SDK 的**布控 Agent**，负责 RTSP 解码→推理→（可选）编码/快照→事件上报；云端 AIStation 统一管理与编排。
- **纯云端模式**：无边缘设备时，同一 Agent 作为本机/服务器进程运行，AIStation 与 Agent 同网直连。
- 两模式**共用同一事件模型、配置 schema 与控制面**，仅传输/拓扑不同。

## 2. 总体架构

```
                         ┌─────────────────────── 云端 AIStation ───────────────────────┐
                         │ 视频模块：摄像头/算法/布控任务/告警/事件联动/通知/大屏         │
                         │ 边缘设备管理：注册/能力清单/心跳/状态                          │
                         │ 任务编排：按能力把布控任务下发到指定 Agent                      │
                         │ 事件接入：MQTT 订阅 / HTTP webhook  → 复用 InferenceService      │
                         │ 前端：布控、预览、告警、设备                              │
                         └───────┬───────────────────────────────┬─────────────────────┘
                                 │ 配置下发(HTTP)                 │ 事件上报(MQTT / HTTP)
                                 ▼                               ▲
                    ┌────────────────────┐          ┌───────────────────────────┐
                    │ 控制面 REST        │          │ MQTT Broker(Mosquitto/EMQX)│
                    └─────────┬──────────┘          └─────────────▲─────────────┘
                              ▼                                    │
        ┌──────────────────────────── 布控 Agent（基于 ModelDeploy SDK） ─────────┐
        │ 每路=1 Pipeline：VideoDecoder(NVDEC) → InferGroup(ORT/TRT/MNN) →        │
        │   检测结果 →（可选）DrawEngine+VideoEncoder(FLV) / snapshot             │
        │ 事件发布：MQTT(QoS1 + 本地缓存补发) / HTTP webhook；event_id 去重        │
        │ 控制面：/health /tasks 增删启停 /tasks/:id/stats                          │
        └──────────────────────────────────────────────────────────────────────────┘
```

**仓库划分**
- **ModelDeploy 仓库（另开会话）**：新增 `application/aistation_agent/`（布控 Agent），复用并抽取 `application/` 中可复用的 pipeline 组件为共享库；新增 MQTT/HTTP 事件发布与边缘缓存；`surveillance` 保持不动。
- **AIStation 仓库（本会话）**：边缘设备管理 + 任务编排 + 事件接入 + 前端；Phase 3C 由"Python worker"改为"接布控 Agent"。

## 3. 两种运行模式

| 维度 | 云边协同（边缘） | 纯云端 |
|---|---|---|
| Agent 位置 | 边缘设备（Jetson/工控机/GPU 盒子） | 服务器本机/同网主机 |
| 事件传输 | MQTT（边缘首选，断网缓存补发） | MQTT 或 HTTP webhook（二选一） |
| 断网 | Agent 本地缓存 + 恢复补发；云端显示"离线" | 不涉及 |
| 模型 | 云端训练/转换后分发到边缘 | 本地直接加载 |
| 适用 | 多分散点位、弱网、就地算力 | 集中算力、低点位、简单部署 |

AIStation 侧通过配置项 `video.analysis_mode = cloud_edge | cloud_only` 切换默认行为；单设备/单任务也可覆盖。

## 4. 边缘设备与能力模型（云端管理）

新增实体 **EdgeDevice（边缘设备）**（`module_video/edge`）：
- 标识：`id/name/code`、`mqtt_client_id`、`control_url`（Agent 控制面基址）、`secret`（控制面鉴权）。
- 能力 `capabilities`（JSON）：
  - `hardware`: `{ platform: nvidia|sophgo|cpu|jetson, gpu_model, vram_mb, tpu }`
  - `backends`: `["ort","trt","mnn","ncnn","sophgo"]`（与 ModelDeploy 构建开关对应）
  - `model_families`: `["det","cls","seg","pose","obb","ocr","lpr",...]`
  - `max_channels`: 最大并发布控路数
  - `codecs`: `{decode:["h264","h265"], encode:["h264","h265"], hw:["nvenc","bmh264enc",...]}`
  - `metrics`: 实时上报（CPU/GPU/显存/在跑路数）
- 心跳/状态：`online/offline/busy/error`，最后心跳时间。
- 管理面：注册/编辑/删除、能力上报（Agent 启动注册或心跳携带）、查看实时指标。

**能力上报**：Agent 启动与心跳时 `POST /api/v1/edge/heartbeat`（云端）携带能力与负载；云端落库，供编排使用。

## 5. 任务编排（按能力下发）

布控任务（AIStation 现有 `video_algorithm_tasks`）增加 `edge_device_id`（为空=纯云端本机 Agent）。

**编排**：创建/启动布控任务时：
1. 校验目标边缘设备是否满足：模型族 ∈ `model_families`、后端 ∈ `backends`、在跑路数 < `max_channels`、硬件工况正常。
2. 把 `camera + algorithm + task(ROI/灵敏度/时段/告警间隔)` 编译为 **Agent TaskConfig**（见 §6），经控制面 `POST /tasks`（或 `PUT`）下发。
3. 启停：`POST /tasks/:id/start|stop`；删除：`DELETE /tasks/:id`。
4. 失败回退：设备离线/不满足 → 任务标记 `pending/error` 并给出原因；可选自动改派到其它满足设备。

**模型分发**：AIStation 训练的模型 → 导出为 ModelDeploy 可加载格式（检测/分割等 → ONNX；NVIDIA 可转 TensorRT engine；边缘按 `backends` 选择）。分发方式：
- 边缘可访问对象存储（RustFS/S3）→ 下发给 Agent 模型 URL，Agent 自行拉取校验；
- 或云端控制面带外推送。
模型文件与 `labels`/`input_size`/`type` 一并在 TaskConfig 中声明。

## 6. Agent TaskConfig（云端下发 / Agent 消费）

对齐 ModelDeploy `ModelConfig`/`DecoderConfig`/`EncoderConfig`（见 `application/config.hpp`），并加 AIStation 需要的字段：

```jsonc
{
  "task_id": 123,
  "camera": { "id": 7, "name": "北门", "url": "rtsp://...", "transport": "tcp" },
  "models": [
    { "name": "aistation-det", "type": "det", "backend": "trt", "device": "gpu",
      "url": "s3://.../model.engine", "labels": ["person","car"], "input_size": [640,640],
      "confidence_threshold": 0.45 }
  ],
  "roi": [[0.1,0.1],[0.9,0.1],[0.9,0.9],[0.1,0.9]],   // 归一化，Agent 内做 mask
  "sensitivity": 60,
  "schedule": { "days": [0,1,2,3,4], "start": "08:00", "end": "18:00" },
  "alarm_interval_sec": 30,
  "preview": { "enabled": true, "format": "flv" },      // 可选标注推流
  "events": {
    "transport": "mqtt",                                 // mqtt | http
    "mqtt": { "broker": "tcp://edge-broker:1883", "topic_prefix": "aistation/cam07",
              "qos": 1, "client_id": "aistation-agent-aistation-det" },
    "http": { "url": "http://cloud/api/v1/video/algorithm/detection/callback",
              "token": "..." },
    "buffer": { "dir": "./events_buffer", "max_mb": 512 } // 边缘断网缓存
  },
  "decoder": { "hw_accel": "cuda", "device_only": true },
  "encoder": { "codec": "h264_nvenc", "format": "flv", "bitrate_kbps": 2500 }
}
```

## 7. 事件模型（两端统一）

**主题**：`aistation/{tenant}/edge/{edge_code}/camera/{camera_id}/detect`
（纯云端可省略 edge 段：`aistation/{tenant}/camera/{camera_id}/detect`）

**载荷**（与现有 `detection callback` 事件兼容并扩展）：
```jsonc
{
  "event_id": "uuid",                 // 去重
  "edge_code": "edge-01",
  "camera_id": 7, "task_id": 123,
  "algorithm_type": "INTRUSION",
  "ts": "2026-09-12T08:00:00.123Z",
  "detections": [
    { "label": "person", "label_id": 0, "confidence": 0.91,
      "bbox": { "x": 0.1, "y": 0.2, "width": 0.15, "height": 0.3 } }
  ],
  "latency_ms": 12.3,
  "snapshot": { "ref": "edge-01/cam7/2026-09-12/xxxx.jpg" },  // 相对引用；或内联 base64(小图/低频)
  "schema_version": 1
}
```
- **可靠性**：MQTT QoS1 + `event_id` 幂等去重；Agent 断网写本地队列（文件/嵌入式 broker 持久会话），恢复按序补发；队列超限按最旧丢弃并计数告警。
- **云端接入**：`aistation-events` 消费者订阅 `aistation/+/edge/+/camera/+/detect`（或通配），映射到现有 `InferenceService.process_detection_callback` 生成 `alarm_record` → 事件联动 → 通知。
- **快照**：边缘将快照上传对象存储（或随事件 base64，低频）；云端 `alarm_record.snapshot_path` 存**引用**，经受控 HTTP 路由展示（Phase 3C 已设计）。

## 8. 预览与快照

- **边缘预览**：Agent 可选推 FLV/RTSP（`preview.enabled`）；AIStation 前端布控页用 Agent 的播放地址（或经 ZLM 转封装）。
- **快照**：Agent 提供 `/tasks/:id/snapshot.jpg`（低频）+ 事件内引用；云端统一由受控路由展示。
- **告警短视频**（可选，后续）：Agent 缓存事件前后 N 秒片段并上报引用。

## 9. 安全与多租户

- 控制面（云端→Agent）：Bearer/共享密钥（`EdgeDevice.secret`）；可选 TLS。
- 事件面（Agent→Broker）：MQTT 用户名/密码或 TLS 证书；主题带 `tenant`，云端消费者按租户隔离。
- 云端内 `EdgeDevice`/任务/告警沿用现有数据权限。
- 注册：边缘首次接入用一次性注册码绑定到云端（可选，二期）。

## 10. 交付拆分

**A. ModelDeploy 会话（另开，独立 spec+plan）**
1. 抽取 `application/` 可复用 pipeline 组件为共享库（`surveillance` 与 Agent 共用）。
2. 新建 `application/aistation_agent/`：控制面（`/health`、`/tasks` 增删启停、`/tasks/:id/stats`）+ 消费 §6 配置。
3. 事件发布：MQTT（首选，QoS1 + 本地队列补发）与 HTTP webhook；`event_id` 去重。
4. 能力上报/心跳到云端；模型按 URL 拉取与校验。
5. 可选 WebSocket/MQTT 控制（二期）。
6. MQTT 依赖评估（如 `paho.mqtt.c`/`mosquitto`）与边缘构建开关。

**B. AIStation 会话（本仓库）**
1. 新增 `module_video/edge`：EdgeDevice 模型/CRUD/心跳接口/能力与指标。
2. 布控任务增加 `edge_device_id` 与编排逻辑（能力校验、配置编译、下发启停）。
3. 事件接入：MQTT 消费者（`paho-mqtt`/`aiomqtt`）→ 复用 `InferenceService`；保留 HTTP webhook 兼容。
4. 模型导出对接 ModelDeploy 格式（ONNX/engine）与分发（对象存储 URL）。
5. 前端：边缘设备管理页、布控页设备选择与状态、告警快照/预览。
6. Phase 3C 原"Python worker"相关内容重写或废弃。

## 11. 验收标准

- 云边模式：注册边缘设备 → 能力可见 → 下发布控任务 → 边缘实时推理 → 事件经 MQTT 到达云端生成告警/联动/通知；断网后恢复补发不丢事件。
- 纯云端模式：同样的任务在服务器本机 Agent 上跑通并出告警。
- 任务编排：能力不满足时给出明确原因/自动改派。
- 快照/预览可在前端展示。
- 两端均有测试；关键链路真机验证（本地有 Docker、ModelDeploy 已构建）。

## 12. 风险与取舍

- **跨仓库协作**：ModelDeploy 侧 Agent 是关键依赖 → 先行落地其 spec/plan，并用最小 Agent（单路 det + HTTP 事件）尽早端到端验证，再接 MQTT/边缘缓存。
- **MQTT 引入**：边缘需 broker；服务器模式可退化 HTTP，避免强制运维成本。
- **模型格式**：边缘后端（TRT/MNN/SOPHGO）各异，模型分发需按能力选择与转换；先支持 ONNX(ORT) 一条线跑通。
- **能力编排复杂度**：先做"手动指定设备 + 能力校验"，自动改派为后续增强。
