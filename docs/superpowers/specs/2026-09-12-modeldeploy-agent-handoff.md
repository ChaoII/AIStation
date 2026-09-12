# 交接：为 AIStation 构建布控 Agent（ModelDeploy 仓库）

> 目标仓库：`E:\CLionProjects\ModelDeploy`
> 关联设计：`D:\AIStation\docs\superpowers\specs\2026-09-12-cloud-edge-visual-analysis-design.md`
> 状态：待 ModelDeploy 会话据此产出本仓库的 spec + plan 并实现
> 原则：**不改动 `application/surveillance`**；基于 **ModelDeploy SDK** 新建专用应用。

## 背景

AIStation 是云端视频分析平台（FastAPI）。其"布控"需要实时多路 RTSP 推理。经评估：
- ModelDeploy SDK（`csrc/video`、`csrc/vision`、`ModelDeploySDK.dll`）是布控算法的正确依赖；
- `surveillance` 是通用参考应用，**不应**塞入 AIStation 专属的任务同步/告警/MQTT 逻辑；
- 因此新建**专用布控 Agent**（应用），`surveillance` 保持不动。

本 Agent 只负责：按云端下发的配置做「RTSP 解码 → 推理 →（可选）编码/快照 → 事件上报」，并上报自身能力/心跳。业务（摄像头/算法/告警/通知）由 AIStation 负责。

## 交付物

### 1. 共享 pipeline 组件抽取（重构，行为不变）
把 `application/` 中与 AIStation 无关、可复用的部分抽为共享库（供 `surveillance` 与 Agent 共用），**保持 `surveillance` 行为与测试不变**：
- `video_source`/`video_sink`/`video_codec`、`infer_group`、`draw_engine`、`perf_stats` 等。
- 目标：Agent 不复制这些实现；`surveillance` 改链接共享库。
- 若抽取风险高，可先复制到 Agent 并在后续抽取——但需在 plan 中明确取舍。

### 2. 新应用 `application/aistation_agent/`
- 顶层 CMake 开关 `BUILD_AISTATION_AGENT`（默认 OFF），依赖 `BUILD_VISION`（自动）+ 视频模块。
- **控制面（REST，`cpp-httplib`，端口可配，默认 19090）**：
  - `GET /health`、`GET /readyz`、`GET /api/v1/metrics`（在跑路数/队列/事件计数）。
  - `POST /api/v1/tasks`（下发 TaskConfig，见 §3）、`GET /api/v1/tasks`、`GET /api/v1/tasks/:id`。
  - `POST /api/v1/tasks/:id/start`、`POST /api/v1/tasks/:id/stop`、`PUT /api/v1/tasks/:id`、`DELETE /api/v1/tasks/:id`。
  - `GET /api/v1/tasks/:id/stats`、`GET /api/v1/tasks/:id/snapshot.jpg`。
  - 鉴权：`Authorization: Bearer <secret>`（非空启用）；统一错误体 `{error:{code,message}}`。
- **能力/心跳上报**：启动与周期（默认 30s）向云端 `POST {cloud}/api/v1/video/edge/heartbeat` 上报：
  `{edge_code, capabilities:{hardware,backends,model_families,max_channels,codecs}, metrics:{cpu,gpu,vram,running_channels}, version}`。
  失败重试；云端不可达不阻塞本地布控。

### 3. TaskConfig（Agent 消费，字段与 AIStation 对齐）
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
  "events": { "transport": "mqtt", "mqtt": {...}, "http": {...}, "buffer": {...} },
  "decoder": { "hw_accel": "cuda", "device_only": true },
  "encoder": { "codec": "h264_nvenc", "format": "flv", "bitrate_kbps": 2500 }
}
```
映射到 ModelDeploy 的 `ModelConfig`/`DecoderConfig`/`EncoderConfig`（`application/config.hpp`）。`type` 用 ModelDeploy 内置族（`det/cls/seg/pose/obb/sem/depth/face/ocr/lpr`）。

### 4. 事件发布（核心新增）
- **载荷**（两会话统一，`schema_version=1`）：
  ```jsonc
  { "event_id":"uuid","edge_code":"edge-01","camera_id":7,"task_id":123,
    "algorithm_type":"INTRUSION","ts":"...Z",
    "detections":[{"label":"person","label_id":0,"confidence":0.91,
                   "bbox":{"x":0.1,"y":0.2,"width":0.15,"height":0.3}}],
    "latency_ms":12.3,"snapshot":{"ref":"edge-01/cam7/2026-09-12/x.jpg"},
    "schema_version":1 }
  ```
- **MQTT 传输**（边缘首选）：`paho.mqtt.c` 或 `mosquitto` 客户端；QoS1；主题 `aistation/{tenant}/edge/{edge_code}/camera/{camera_id}/detect`；`client_id` 稳定；遗嘱/重连。
- **HTTP 传输**（服务器/直连）：`POST {events.http.url}`，`Authorization: Bearer {token}`，超时与重试。
- **报警节流**：按 `alarm_interval_sec`（或 label 维度）限频，逻辑与 AIStation 现有 worker 一致。
- **边缘缓存补发**：本地队列（目录 + 文件或 SQLite），断网写入，恢复按序补发；`event_id` 支持云端去重；超限（`max_mb`）丢最旧并计数。
- **快照**：按 `snapshot.ref` 上传对象存储（或内联 base64，低频/小图可配）。

### 5. 模型获取
- 支持 `models[].url`（`s3://`/`http(s)://`/本地路径）：下载到缓存目录 + 校验（大小/hash 可选）+ 按 `backend/type` 构造。
- 复用 SDK `runtime_factory`/内置构造；后端由 `capabilities.backends` 与模型 `backend` 共同决定。

### 6. 构建与依赖
- 新开关（示例）：`BUILD_AISTATION_AGENT`、`ENABLE_MQTT`（引入 MQTT 客户端，默认 OFF 时仅 HTTP 事件）。
- 保持现有后端开关语义（`ENABLE_ORT/MNN/TRT/NCNN/SOPHGO`）；MNN 由 `ENABLE_MNN=ON` 启用（AIStation 侧按设备选择）。
- 交叉编译/边缘（Jetson/Sophgo）与现有 `surveillance` 一致。

## 建议实施顺序（每步可验证）
1. **共享组件抽取**：`surveillance` 链接共享库且测试全绿（行为不变）。
2. **Agent 骨架**：控制面 `/health` + `/tasks` 增删启停 + `TaskConfig` 解析；单路本地视频文件 det 跑通（无事件）。
3. **事件- HTTP**：单路 det → `POST` 到本地 mock/HTTP 接收器；含节流与 `event_id`。
4. **事件- MQTT**：接 broker，QoS1 发布；订阅端收到。
5. **边缘缓存**：断网写队列、恢复补发、超限丢弃计数。
6. **能力/心跳上报**：向云端 mock 上报；云端不可达降级。
7. **模型 URL 拉取与后端选择**；ONNX(ORT) 优先，其次 TRT/MNN。
8. **预览/快照**：FLV 推流与 `/snapshot.jpg`；与 AIStation 前端联调。
9. **（二期）** 控制面 WebSocket/MQTT 双向、模型热更新、自动改派。

## 验收
- 单路 RTSP（本地素材）→ det → 事件经 HTTP 与 MQTT 各到达一次（不重复、不丢）。
- 断网 30s 事件缓存，恢复后补齐且云端去重生效。
- `/tasks` 生命周期正确；能力/心跳在云端可见。
- 不修改 `surveillance` 的行为（其测试仍全绿）。

## 交付给 AIStation 的接口契约（必须严格对齐）
- 控制面 REST 路径与语义、`TaskConfig` 字段、事件主题与载荷、心跳载荷、错误体——见本文件与 `2026-09-12-cloud-edge-visual-analysis-design.md` §6/§7。
- 任何契约变更需同步 AIStation 侧接入（本会话产出对应 spec）。
