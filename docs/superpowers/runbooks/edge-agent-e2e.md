# 云边 Agent 真机端到端联调 Runbook（MQTT / HTTP）

> 对应任务：AIStation 云边协同契约统一 · Task 5（`scripts/e2e/edge_agent_e2e.ps1`）
> 目标：一条命令驱动「AIStation 播种 → ModelDeploy `aistation_agent` 执行 → 告警落库」的完整链路，并对关键契约做断言。

## 1. 适用范围与边界

- 本脚本**只做编排与断言**，不负责拉起/重启 AIStation 后端（后端需由人工按第 3 节预先配置并启动）。
- 脚本会临时启动/清理：Docker `eclipse-mosquitto` Broker（可选）、`aistation_agent.exe`（结束时停止）。
- 两条事件通道：
  - `-Transport mqtt`：云边模式（后端 `VIDEO_ANALYSIS_MODE=cloud_edge`），Agent 发 MQTT，云端消费者订阅落库。
  - `-Transport http`：纯云模式（后端 `VIDEO_ANALYSIS_MODE=cloud_only`），Agent 直连 `detection/callback`。

## 2. 前置条件

| 项 | 要求 | 说明 |
|----|------|------|
| OS / Shell | Windows + PowerShell 7+（`pwsh`） | 脚本使用 `#Requires -Version 7.0`、`ConvertTo-Json -AsArray`、`Invoke-WebRequest -SkipHttpErrorCheck` |
| AIStation 后端 | 已启动，监听 `http://127.0.0.1:8001` | 脚本**不启动**后端；`ROOT_PATH=/api/v1` |
| 前端/DB | PostgreSQL 或 SQLite 均可 | DB 查询证据按后端实际配置 |
| Docker | 可用（`docker version`） | `-Transport mqtt` 且未 `-SkipBroker` 时需要 |
| Broker 镜像 | `docker pull eclipse-mosquitto:2` | 脚本检测不到镜像会直接报错退出 |
| Agent | `E:\CLionProjects\ModelDeploy\build\bin\aistation_agent.exe` | Plan B 已重编，含控制面 + 心跳 + MQTT/HTTP 发布 |
| 视频素材 | `E:\CLionProjects\ModelDeploy\test_data\test_video60.mp4` | 作为 `camera.rtsp_url_sub`，FFmpeg 可直接读本地文件 |
| 模型文件（默认） | `...\test_data\test_models\onnx\yolo11n\yolo11n_nms.onnx` | ONNX 检测模型（ORT/CPU），`-Scene INTRUSION` 默认 |
| 模型文件（PED_ATTR det） | `...\test_data\test_models\onnx\zhgd_det.onnx` | `-Scene PED_ATTR` 且未显式传 `-ModelPath` 时的默认检测模型 |
| 模型文件（PED_ATTR cls） | `...\test_data\test_models\onnx\zhgd_ml.onnx` | `-Scene PED_ATTR` 属性分类模型（`preset_params.cls_path`） |
| 模型文件（OCR det/cls/rec） | `...\test_data\test_models\onnx\ocr\ppocrv6_tiny\{det,cls,rec}_infer.onnx` | `-Scene OCR_TEXT` 默认三模型（det=`-ModelPath`、cls=`-ClsModelPath`、rec=`-RecModelPath`） |
| 字典（OCR） | `...\test_data\ppocrv6_tiny_dict.txt` | `-Scene OCR_TEXT` 字符字典（`preset_params.dict_path`） |
| 视频素材（OCR） | `...\test_data\test_images\ocr2.jpg` | 静态图需先用 FFmpeg 循环成 mp4 再传给 `-VideoPath`（见第 12 节） |
| 模型文件（LPR det/rec） | `...\onnx\yolov5plate.onnx` + `...\onnx\plate_recognition_color.onnx` | `-Scene LPR` 默认检测/识别模型（rec 走 `-PlateRecModelPath`，见第 13 节） |
| 视频素材（LPR） | `...\test_images\test_lpr_detection.jpg` | 车牌图同样先用 FFmpeg 循环成 mp4 再传给 `-VideoPath`（见第 13 节） |
| 模型文件（FACE_DET） | `...\test_models\onnx\seetaface\scrfd_2.5g_bnkps_shape640x640.onnx` | `-Scene FACE_DET` 默认人脸检测模型（face_detection，走 `-FaceModelPath`，见第 15 节） |
| 视频素材（FACE_DET） | `...\test_images\test_face_detection.jpg` | 人脸图同样先用 FFmpeg 循环成 mp4 再传给 `-VideoPath`（见第 15 节） |
| 模型文件（ABSENT） | `...\test_models\onnx\yolo11n\yolo11n_nms.onnx` | `-Scene ABSENT` 默认检测模型（单 det，走 `-DetModelPath`，见第 16 节） |
| 视频素材（ABSENT） | 自制「人先出现→随后空白」混合 mp4 | **不可用纯静态图/纯空白图**：需先有目标建立 `last_seen`，再静默触发 absence（见第 16 节） |
| Agent 心跳 | `heartbeat_sec` 默认 5s（`<=0` 关闭） | absence 依赖静默期空检测心跳事件（见第 16 节） |
| 登录 | `admin / 123456` | 见 `backend/app/api/v1/module_system/auth/service.py:89` |

> 视频必须先能检出目标（人/车），否则不会产生告警，`断言3` 会超时。

## 3. 后端环境变量（需人工设置并重启后端）

脚本默认假设后端为 `cloud_edge` + MQTT。请在 `backend/env/.env.dev` 设置（或导出同名环境变量）后**重启后端**：

```env
# 云边分析模式
VIDEO_ANALYSIS_MODE=cloud_edge

# MQTT 事件接入
MQTT_ENABLED=true
MQTT_BROKER_URL=tcp://127.0.0.1:1883
MQTT_TOPIC_PREFIX=aistation/default/edge
MQTT_SUBSCRIBE_TOPIC=aistation/+/edge/+/camera/+/detect

# 共享密钥（心跳校验 + 控制面）
EDGE_CONTROL_TOKEN=<Secret，与脚本 -Secret 一致>
# HTTP 回调令牌（仅 http 通道需要）
INFERENCE_CALLBACK_TOKEN=<T，与脚本 -InferenceCallbackToken 一致>
```

对应的配置定义（默认值）见 `backend/app/config/setting.py:243-278`。

### HTTP 通道（`-Transport http`）

```env
VIDEO_ANALYSIS_MODE=cloud_only
MQTT_ENABLED=false
INFERENCE_CALLBACK_TOKEN=<T>
```

### 登录验证码

登录接口带验证码（`backend/app/api/v1/module_system/auth/service.py:77`）。两种放行方式：

1. **推荐（无需改后端）**：脚本默认携带 `-CaptchaReferer http://127.0.0.1:8001/docs`。
   后端对 `referer` 以 `docs`/`redoc` 结尾的登录请求**跳过验证码**（`auth/service.py:72-77`）。
2. 设置 `CAPTCHA_ENABLE=false` 后重启后端（`setting.py:128`）。

## 4. 运行命令

```powershell
# 云边 MQTT（默认）：自动起 Broker + Agent，跑完整断言，结束清理
pwsh -NoProfile -File scripts/e2e/edge_agent_e2e.ps1 -Transport mqtt -Secret e2e-shared-secret

# 纯云 HTTP：复用已存在后端，无需 Broker
pwsh -NoProfile -File scripts/e2e/edge_agent_e2e.ps1 -Transport http -SkipBroker `
  -InferenceCallbackToken infer_callback_shared_secret

# PED_ATTR 行人属性场景（det+cls 双模型 + 属性告警规则；见第 11 节）
pwsh -NoProfile -File scripts/e2e/edge_agent_e2e.ps1 -Transport mqtt -Secret e2e-shared-secret `
  -Scene PED_ATTR `
  -ModelPath E:\CLionProjects\ModelDeploy\test_data\test_models\onnx\zhgd_det.onnx `
  -ClsModelPath E:\CLionProjects\ModelDeploy\test_data\test_models\onnx\zhgd_ml.onnx

# OCR_TEXT 通用文本场景（det+cls+rec+dict + 文本规则；见第 12 节）
pwsh -NoProfile -File scripts/e2e/edge_agent_e2e.ps1 -Transport mqtt -Secret e2e-shared-secret `
  -Scene OCR_TEXT `
  -VideoPath E:\CLionProjects\ModelDeploy\test_data\test_images\ocr2_loop.mp4

# LPR 车牌识别场景（det+rec + 文本规则；见第 13 节）
pwsh -NoProfile -File scripts/e2e/edge_agent_e2e.ps1 -Transport mqtt -Secret e2e-shared-secret `
  -Scene LPR `
  -VideoPath E:\CLionProjects\ModelDeploy\test_data\test_images\test_lpr_detection_loop.mp4

# FACE_DET 人脸检测场景（单 face_detection 模型 + object_present 规则；见第 15 节）
pwsh -NoProfile -File scripts/e2e/edge_agent_e2e.ps1 -Transport mqtt -Secret e2e-shared-secret `
  -Scene FACE_DET `
  -VideoPath E:\CLionProjects\ModelDeploy\test_data\test_images\test_face_detection_loop.mp4

# ABSENT 离岗场景（单 det + absence 时序规则，需「人先出现再离开」的混合视频；见第 16 节）
pwsh -NoProfile -File scripts/e2e/edge_agent_e2e.ps1 -Transport mqtt -Secret e2e-shared-secret `
  -Scene ABSENT `
  -VideoPath E:\CLionProjects\ModelDeploy\test_data\test_images\absent_person_then_blank.mp4

# DET_ZONE 检测 + 跟踪（-Tracking）：断言告警 detections[].track_id 出现；见第 14 节
pwsh -NoProfile -File scripts/e2e/edge_agent_e2e.ps1 -Transport mqtt -Secret e2e-shared-secret `
  -Scene DET_ZONE -Tracking `
  -VideoPath E:\CLionProjects\ModelDeploy\test_data\test_video60.mp4

# 复用已有 Broker（例如 docker-compose 起的），保留数据便于人工排查
pwsh -NoProfile -File scripts/e2e/edge_agent_e2e.ps1 -Transport mqtt -SkipBroker `
  -KeepResources -KeepData

# 查看参数说明
pwsh -NoProfile -Command "Get-Help scripts/e2e/edge_agent_e2e.ps1 -Detailed"
```

常用参数（完整见脚本头部注释）：

| 参数 | 默认 | 说明 |
|------|------|------|
| `-Transport` | `mqtt` | `mqtt` / `http` |
| `-Scene` | `INTRUSION` | `INTRUSION`（单 det 模型）/ `DET_ZONE`（单 det 区域入侵，`scene_type=DET_ZONE`，见第 14 节）/ `PED_ATTR`（det+cls 属性 pipeline，见第 11 节）/ `OCR_TEXT`（det+cls+rec+dict 文本 pipeline，见第 12 节）/ `LPR`（det+rec 车牌 pipeline，见第 13 节）/ `FACE_DET`（单 face_detection 人脸 pipeline，见第 15 节）/ `ABSENT`（单 det + absence 时序规则，见第 16 节） |
| `-Secret` | `e2e-shared-secret` | Agent `--api-key`/`--secret`、EdgeDevice.secret、后端 `EDGE_CONTROL_TOKEN` |
| `-EdgeCode` | 空（运行时唯一） | 边缘设备编码 / Agent `--edge-code`；留空时按 `RunId` 生成 `edge-e2e-<RunId>`，避免软删后同码无法复用 |
| `-AgentExe` / `-VideoPath` / `-ModelPath` | 见第 2 节 | 真机素材路径；`-Scene PED_ATTR` 未显式传 `-ModelPath` 时自动改用 `zhgd_det.onnx`，`-Scene OCR_TEXT` 改用 `ppocrv6_tiny\det_infer.onnx`，`-Scene LPR` 改用 `yolov5plate.onnx`，`-Scene FACE_DET` 改用 `-FaceModelPath`，`-Scene ABSENT` 改用 `-DetModelPath` |
| `-ClsModelPath` | `...\onnx\zhgd_ml.onnx` | PED_ATTR 属性分类模型，写入 `preset_params.cls_path`；`-Scene OCR_TEXT` 未显式传入时自动改用 `ppocrv6_tiny\cls_infer.onnx` |
| `-RecModelPath` | `...\ocr\ppocrv6_tiny\rec_infer.onnx` | OCR 文本识别模型，写入 `preset_params.rec_path`；仅 `-Scene OCR_TEXT` 使用 |
| `-DictPath` | `...\test_data\ppocrv6_tiny_dict.txt` | OCR 字符字典，写入 `preset_params.dict_path`；仅 `-Scene OCR_TEXT` 使用 |
| `-PlateRecModelPath` | `...\onnx\plate_recognition_color.onnx` | LPR 车牌识别模型，写入 `preset_params.rec_path`；仅 `-Scene LPR` 使用 |
| `-FaceModelPath` | `...\onnx\seetaface\scrfd_2.5g_bnkps_shape640x640.onnx` | FACE_DET 人脸检测模型，写入 `Algorithm.model_path`；仅 `-Scene FACE_DET` 使用 |
| `-DetModelPath` | `...\onnx\yolo11n\yolo11n_nms.onnx` | ABSENT 离岗检测模型，写入 `Algorithm.model_path`；仅 `-Scene ABSENT` 使用 |
| `-DecoderHwAccel` | `none` | 算法 `runtime_config.decoder.hw_accel`；默认 CPU 解码以匹配 ORT/CPU 模型，GPU 后端改为 `cuda` |
| `-Tracking` | 关 | 算法 `runtime_config.tracking={enabled=true,algorithm=bytetrack}`，让 Agent 做 ByteTrack 跟踪并回填 `track_id`；启用后追加断言 3d（见第 5 节与第 14 节），仅检测类场景有意义 |
| `-ApiBase` | `http://127.0.0.1:8001` | 后端基址 |
| `-AgentPort` | `19090` | Agent 控制面端口 |
| `-BrokerPort` | `1883` | Broker 端口 |
| `-SkipBroker` | 关 | 跳过起 Broker |
| `-KeepResources` | 关 | 保留 Agent 进程 / Broker 容器 |
| `-KeepData` | 关 | 保留播种的 Algorithm/Camera/EdgeDevice |

## 5. 脚本流程与断言

流程：起 Broker（可选）→ 登录 → 播种 EdgeDevice → 起 Agent → 播种 Algorithm/Camera/Task#1
→ start → 轮询断言 → 去重测试 → 时段测试（Task#2 窗口外）→ stop/delete 生命周期 → 证据与清理。

> `EdgeCode` 默认按 `RunId` 生成运行时唯一值 `edge-e2e-<RunId>`（也可用 `-EdgeCode` 显式指定）；
> 设备创建、Agent `--edge-code`、MQTT 主题与日志引用统一使用该有效编码。

| # | 断言 | 数据来源 |
|---|------|----------|
| 1 | 设备 `status=online` | `GET /api/v1/video/edge/list?code=<EdgeCode>` |
| 2 | Agent 任务 `running=true` | `GET {AgentControlUrl}/api/v1/tasks` |
| 2b | 云端任务 `status=RUNNING` | `GET /api/v1/video/algorithm/task/list` |
| 3 | 出现 `algorithm_type=INTRUSION` 告警 | `GET /api/v1/video/alarm/record/list?camera_id=<id>` |
| 4 | 告警 `snapshot_url` 非空 | 告警出参计算字段 `AlarmRecordOutSchema.snapshot_url` |
| 5 | 重复 `event_id` 不重复建告警 | MQTT：经 Broker 容器 `mosquitto_pub` 连发两条同 `event_id`；HTTP：直连 `detection/callback`（后端模块级 `_CALLBACK_DEDUP` 已按 `event_id` 去重） |
| 6 | 窗口外任务在 Agent 侧停止且不产生告警 | 新建 Task#2（schedule 为明天全天）→ Agent `running=false`、`ai_result.task_id=Task2` 告警数为 0 |
| 7 | stop 同步：Agent `running=false`、云端 `STOPPED` | Task#1 |
| 8 | delete 同步：Agent `GET /api/v1/tasks/{id}` 返回 404、云端列表移除 | Task#1/#2 |
| 3b | （仅 `-Scene PED_ATTR`）`ai_result.detections[].attributes` 非空 | 告警样本 `ai_result.detections`，证明事件 `objects[].attributes` 已透传 |
| 3b | （仅 `-Scene FACE_DET`）`ai_result.detections[]` 非空（人脸框） | 告警样本 `ai_result.detections`，证明事件 `objects[]` 人脸框已归一化落库 |
| 3c | （仅 `-Scene OCR_TEXT` / `LPR`）`ai_result.detections[].text` 非空 | 告警样本 `ai_result.detections`，证明事件 `objects[].text` 已透传到检测框文本 |
| 3d | （仅 `-Tracking`）`ai_result.detections[].track_id` 至少一条出现且 `>= 0` | 告警样本 `ai_result.detections`，证明事件 `objects[].track_id` 已透传（Agent 仅在 `track_id >= 0` 时写该字段） |

> 去重测试使用哨兵 `task_id=999999`，避免与真实 Agent 告警混淆。
> `-Scene PED_ATTR` 时：断言 3 匹配 `algorithm_type=PED_ATTR`，并在断言 4 后追加断言 3b（属性透传）。
> `-Scene OCR_TEXT` 时：断言 3 匹配 `algorithm_type=OCR_TEXT`，并在断言 4 后追加断言 3c（文本透传）。
> `-Scene LPR` 时：断言 3 匹配 `algorithm_type=LPR`，并在断言 4 后追加断言 3c（车牌文本透传），断言 1 后追加断言 1b（设备能力含 `lpr`）。
> `-Scene FACE_DET` 时：断言 3 匹配 `algorithm_type=FACE_DET`，并在断言 4 后追加断言 3b（人脸框透传），断言 1 后追加断言 1b（设备能力含 `face`）。
> `-Scene ABSENT` 时：断言 3 匹配 `algorithm_type=ABSENT`，断言 1 后追加断言 1b（设备能力含 `det`），断言 4 后追加断言 3b（`ai_result.detections` 为空=心跳触发）与断言 3c（`interval_seconds=30` 内不重复，容差 1 条）。
> `-Tracking` 时：断言 3 匹配当前场景的 `algorithm_type`，并在断言 3c 之后追加断言 3d（`track_id` 透传）。

## 6. 接口契约（已对照源码核验）

| 用途 | 方法 & 路径 | 关键请求字段 | 源码位置 |
|------|-------------|--------------|----------|
| 登录 | `POST /api/v1/system/auth/login` | form: `username`/`password`；`Referer` 以 docs 结尾跳过验证码 | `module_system/auth/controller.py:41`、`auth/service.py:72`、`core/security.py:53` |
| 边缘设备创建 | `POST /api/v1/video/edge/create` | `name`、`code`、`control_url`、`secret`、`capabilities` | `module_video/edge/controller.py:40`、`edge/schema.py:9` |
| 边缘设备列表 | `GET /api/v1/video/edge/list` | `code`（like）、`page_no`、`page_size` | `edge/controller.py:20`、`edge/param.py:7` |
| 心跳 | `POST /api/v1/video/edge/heartbeat` | `edge_code`/`code`、`token`、`capabilities`、`metrics` | `edge/controller.py:68`、`edge/service.py:110`（取码 `service.py:37`） |
| 算法创建 | `POST /api/v1/video/algorithm/create` | `name`、`code`、`algorithm_type`、`model_path`、`runtime_config`、`preset_params` | `algorithm/controller.py:51`、`algorithm/schema.py:7` |
| 相机创建 | `POST /api/v1/video/camera/create` | `name`、`rtsp_url_sub` | `camera/controller.py:44`、`camera/schema.py:7` |
| 任务创建 | `POST /api/v1/video/algorithm/task/create` | `camera_id`、`algorithm_id`、`edge_device_id`、`stream_type`、`detect_region`、`schedule_json` | `algorithm/controller.py:109`、`algorithm/schema.py:46` |
| 任务列表 | `GET /api/v1/video/algorithm/task/list` | `page_no`、`page_size` | `algorithm/controller.py:98` |
| 启动/停止 | `POST /api/v1/video/algorithm/task/{id}/start|stop` | 无 body | `algorithm/controller.py:158,181` |
| 任务删除 | `DELETE /api/v1/video/algorithm/task/delete` | body: `[id,...]` | `algorithm/controller.py:128` |
| 告警规则创建 | `POST /api/v1/video/alarm/rule/create` | `name`、`camera_id`、`alarm_type`、`severity`、`conditions`、`status` | `alarm/controller.py:30`、`alarm/schema.py:8` |
| 告警规则删除 | `DELETE /api/v1/video/alarm/rule/delete` | body: `[id,...]` | `alarm/controller.py:49` |
| 告警列表 | `GET /api/v1/video/alarm/record/list` | `camera_id`、`page_no`、`page_size` | `alarm/controller.py:58`、`alarm/schema.py:47` |
| 检测回调（内部） | `POST /api/v1/video/algorithm/detection/callback` | `Authorization: Bearer <INFERENCE_CALLBACK_TOKEN>` | `algorithm/controller.py:215`、`setting.py:243` |
| Agent 控制面 | `POST/GET/DELETE {control_url}/api/v1/tasks[...]` | `Authorization: Bearer <secret>` | `edge/agent_client.py:51-65`；Agent 侧 `application/aistation_agent/agent_server.cpp:129-259` |

关键编译/下发链路：`edge/orchestrator.py:89`（TaskConfig）、`:140`（events）、`:255`（start）、`:301`（stop）、`:326`（delete）。

## 7. 证据与 DB 查询

脚本会在 `%TEMP%\aistation-edge-e2e-<RunId>\` 输出 Agent 标准输出/错误日志路径。手工核验：

```bash
# 告警列表（带快照 URL）
curl -H "Authorization: Bearer <token>" \
  "http://127.0.0.1:8001/api/v1/video/alarm/record/list?camera_id=<id>&page_no=1&page_size=20"

# DB 证据（PostgreSQL 示例；快照落盘目录见 DETECTIONS_DIR）
psql -h 127.0.0.1 -U postgres -d aistation -c "
  select id, camera_id, alarm_type, status, snapshot_path,
         ai_result->>'task_id' as task_id, ai_result->>'algorithm_type' as alg,
         alarm_time
  from alarm_record
  where camera_id=<id>
  order by id desc limit 20;"

# 设备在线状态
psql ... -c "select id, code, status, control_url, last_heartbeat from edge_device order by id desc limit 5;"
```

- `snapshot_url` 由 `AlarmRecordOutSchema.snapshot_url` 计算得到（`alarm/schema.py:62`），本地文件位于 `DETECTIONS_DIR`（`setting.py:248`）时返回 `/api/v1/video/detections/<rel>`（`inference/snapshot.py:47`）。
- Agent 事件落盘队列目录：`./events_buffer/<task_id>/`（相对 Agent 进程工作目录；`edge/orchestrator.py:152`）。

## 8. 已知差异 / 与 brief 的偏差

1. **brief 中的 `GET /api/v1/video/edge/tasks` 不存在**。Agent 任务运行态改由 Agent 控制面 `GET {control_url}/api/v1/tasks` 查询（`agent_server.cpp:152`）；云端任务态由 `GET /api/v1/video/algorithm/task/list` 查询。
2. **HTTP 通道已支持 `event_id` 去重（与原 brief 的差异已修复）**：`detection_callback_controller`（`algorithm/controller.py:215`）复用 `edge/consumer.py` 的 `dedup()`，以模块级 `_CALLBACK_DEDUP` 按 `event_id` 幂等去重（命中返回 `{"alarm_created": false, "reason": "duplicate"}`），与 MQTT 消费者（`edge/consumer.py:229-246`）行为一致。`-Transport http` 下重复投递只新建 1 条告警，脚本对该断言按 OK 处理。注：`InferenceService.process_detection_callback`（`inference/service.py:24`）本身仍不处理 `event_id`。
3. **schedule 更新不向 Agent 回传**：`PUT /api/v1/video/algorithm/task/update/{id}` 只改 DB（`algorithm/service.py:57`），且 Agent `POST /api/v1/tasks` 对已存在 id 返回 400（`pipeline_manager.cpp:129`），故无法“原地改 schedule 再重启”。脚本改为**新建窗口外 Task#2**验证时段透传与 Agent 侧调度。
4. Broker 默认镜像匿名访问：`eclipse-mosquitto:2` 默认不允许匿名且仅监听容器内。脚本会挂载临时 `mosquitto.conf`（`listener 1883 0.0.0.0` + `allow_anonymous true`），见 `Start-Broker`。
5. **HTTP 通道已复用 MQTT 事件归一化（内联快照修复）**：`detection_callback_controller` 在 token 校验与 `event_id` 去重后调用 `edge/consumer.py:normalize_edge_event`，把 Agent 嵌套结构 `snapshot.ref`/`snapshot.data`/`ts` 映射为 `snapshot_path`/`snapshot_data`/`frame_timestamp` 再交给 `InferenceService.process_detection_callback`。此前 HTTP 通道直传原始 body，`snapshot.data` 未映射导致告警 `snapshot_path` 为空；扁平/旧版 payload 原样透传，行为不变。

## 9. 排障表

| 现象 | 可能原因 | 处理 |
|------|----------|------|
| 设备一直 `offline` | Agent 未启动 / 心跳目标错误 / 心跳被拒绝 | 看 Agent stdout `[Heartbeat] post failed`；确认 `--cloud-url` 指向后端、`EDGE_CONTROL_TOKEN` 与 `--secret` 一致 |
| **心跳无 `code` → 设备不落库/报“设备编码不能为空”** | Agent 未传 `edge_code`（C9 回归） | 心跳取码逻辑 `edge/service.py:37` 优先 `code`，兼容 `edge_code`；确认 Agent 版本已含 C9 修复且启动带 `--edge-code` |
| 设备存在但无 `control_url` | 心跳先于 `/edge/create` 自动 upsert | 脚本已先播种设备再起 Agent，并对已存在 code 走 update 兜底；手工可 `PUT /api/v1/video/edge/update/{id}` 补 `control_url`/`secret` |
| 启动任务报「边缘设备能力不足」 | 设备 capabilities 缺 `model_families=["det"]` 或 `backends=["ort"]` | 播种时写入 capabilities；Agent 心跳会覆盖为其上报值（`capability.cpp` 含 det/ort） |
| 任务启动报 `边缘 Agent 返回错误 400: task already exists` | 重复对同一 task 调 start（Agent 不允许重复 create） | 先 stop+delete 再重建；见第 8 节第 3 条 |
| 无告警、Agent 任务 running | MQTT 连不上 / 主题不匹配 / 模型未检出 | ① 核对 `MQTT_BROKER_URL` scheme（见下行）；② 核对 `MQTT_SUBSCRIBE_TOPIC` 与 Agent 主题 `aistation/default/edge/<edge_code>/camera/<id>/detect`；③ 换可检出目标的视频 |
| **MQTT 连不上 / scheme 报错** | `MQTT_BROKER_URL` 用了 `mqtt://` 且被要求 paho 格式，或 `mqtts://` 端口错 | 后端 `normalize_broker_scheme` 会把 `mqtt://→tcp://`、`mqtts://→ssl://`（`edge/orchestrator.py:71`）；TLS 默认端口 8883（`edge/consumer.py:45`）。明文用 `tcp://127.0.0.1:1883` |
| Broker 起不来 / 后端订阅失败 | 未挂载允许匿名的配置，或端口占用 | 用脚本默认配置；或 `docker run ... -v <conf>:/mosquitto/config/mosquitto.conf`；确认 1883 未被占用 |
| **模型加载失败（本地 vs 远端）** | `model_path` 与 Agent 所在机器不匹配 | Agent 对无 scheme 的路径按**本地文件**处理，需目标机存在（`model_fetcher.cpp:104`）；远端用 `http(s)://`/`s3://` 由 `ModelFetcher` 下载，`s3://` 需 `--s3-endpoint`（`model_fetcher.cpp:138`） |
| 告警 `snapshot_url` 为空 | 快照未内联/未落盘 | 确认 `MQTT_SNAPSHOT_ENABLED/INLINE=true`（`setting.py:273`）、`DETECTIONS_DIR` 可写；HTTP 通道确认事件带 `snapshot.data` |
| 登录失败/验证码错误 | 验证码开启 | 用 `-CaptchaReferer http://127.0.0.1:8001/docs` 或设 `CAPTCHA_ENABLE=false` 重启后端 |
| Agent `/health` 未就绪 | 端口占用 / 绑定失败 | 看 Agent stderr `failed to bind`；改 `-AgentPort` |

## 10. 脚本自身校验

```powershell
# 语法校验（不执行编排）
pwsh -NoProfile -Command "[scriptblock]::Create((Get-Content -Raw scripts/e2e/edge_agent_e2e.ps1)) | Out-Null; 'OK'"

# 如安装 PSScriptAnalyzer
pwsh -NoProfile -Command "Invoke-ScriptAnalyzer -Path scripts/e2e/edge_agent_e2e.ps1"
```

## 11. PED_ATTR 行人属性场景（`-Scene PED_ATTR`）

前置：ModelDeploy（Plan B）已支持 `pedestrian_attribute`（det+cls）pipeline，且本机存在
`zhgd_det.onnx`（检测）与 `zhgd_ml.onnx`（属性分类）两个 ONNX 模型。

```powershell
pwsh -NoProfile -File scripts/e2e/edge_agent_e2e.ps1 -Transport mqtt -Secret e2e-shared-secret `
  -Scene PED_ATTR `
  -ModelPath E:\CLionProjects\ModelDeploy\test_data\test_models\onnx\zhgd_det.onnx `
  -ClsModelPath E:\CLionProjects\ModelDeploy\test_data\test_models\onnx\zhgd_ml.onnx
```

### 11.1 播种内容

**Algorithm**（`POST /api/v1/video/algorithm/create`）：

```jsonc
{
  "algorithm_type": "PED_ATTR",
  "scene_type": "PED_ATTR",
  "model_path": "<zhgd_det.onnx 绝对路径>",
  "runtime_config": { "backend": "ort", "device": "cpu",
                      "decoder": { "hw_accel": "none", "device_only": false, "rtsp_transport": "tcp" } },
  "preset_params": {
    "cls_path": "<zhgd_ml.onnx 绝对路径>",
    "attributes": ["safety_helmet", "reflective_vest", "safety_rope", "work_uniform"],
    "confidence_threshold": 0.4,
    "cls_threshold": 0.5
  }
}
```

`scene_type=PED_ATTR` 使 `build_agent_task_config` 编译出单条 `type=pedestrian_attribute`
的模型条目（`det_url` + `cls_url` + `attributes` + `cls_threshold`，见 `edge/orchestrator.py:115`）。

**AlarmRule**（`POST /api/v1/video/alarm/rule/create`）：

```jsonc
{
  "camera_id": <本次相机 id>,
  "alarm_type": "PED_ATTR",
  "severity": "WARNING",
  "conditions": { "op": "and",
    "children": [ { "subject": "attribute", "field": "work_uniform", "op": "lt", "value": 0.99 } ] },
  "status": true
}
```

> 规则匹配键是 `camera_id` + `alarm_type`，且 `alarm_type` 必须等于事件的 `algorithm_type`
> （本例均为 `PED_ATTR`），否则规则不生效（`inference/service.py:111`）。
>
> **阈值 0.99 是故意放宽**：属性叶子语义为「分数 < 阈值 即违规」，用 0.99 可保证示例视频
> 必出告警，用于验证「事件→归一化→属性规则→告警落库」整条链路。生产应改为合理阈值
> （如 `work_uniform < 0.5`）；本脚本为链路验证不校验「合规不告警」分支。

### 11.2 事件与属性语义

Agent 上报事件 v2（`objects[]`），每个对象带 `attributes = {属性名: 分数}`，分数含义为
「具有该属性的概率」。云端 `normalize_edge_event` 把 `objects[]` 归一化为
`detections[]` 并保留 `attributes`（`edge/consumer.py:44`），最终落到
`video_alarm_records.ai_result.detections[].attributes`。

期望属性标签：`safety_helmet`（安全帽）、`reflective_vest`（反光衣）、
`safety_rope`（安全带）、`work_uniform`（工作服）。

### 11.3 新增断言

| # | 断言 | 判据 |
|---|------|------|
| 3 | 出现 `algorithm_type=PED_ATTR` 告警 | 断言 3 按 `$effectiveAlgorithmType` 过滤 |
| 3b | `ai_result.detections[].attributes` 非空 | 告警样本中至少一个 detection 带 `attributes`，证明事件 `objects[].attributes` 已透传 |
| 4 | 告警 `snapshot_url` 非空 | 同默认场景 |

脚本结束清理：`AlarmRule` → `Algorithm` → `Camera` → `EdgeDevice`（`-KeepData` 时保留）。

### 11.4 排障

| 现象 | 可能原因 | 处理 |
|------|----------|------|
| 断言 3 超时、无 PED_ATTR 告警 | 规则 `alarm_type` 与事件 `algorithm_type` 不一致 / 无规则 | 核对 `alarm_type=PED_ATTR`；确认事件 `algorithm_type` 由 TaskConfig 透传 |
| 断言 3 超时但 Agent 有事件 | 规则条件不命中 | 本例 `value=0.99` 几乎必命中；若仍不中，检查事件 `attributes` 是否含 `work_uniform` |
| 断言 3b 失败 | 事件未带 `attributes`（Plan B 未编译属性头） | 用 `-KeepData` 重跑并查 `video_alarm_records.ai_result->'detections'`，确认 Agent 事件 `objects[].attributes` |
| cls 模型加载失败 | `preset_params.cls_path` 路径在 Agent 机不存在 | 核对 `-ClsModelPath` 指向 Agent 可读的绝对路径 |

## 12. OCR_TEXT 通用文本场景（`-Scene OCR_TEXT`）

前置：ModelDeploy（Plan B）已支持 `ocr`（det+cls+rec+dict）pipeline，且本机存在
`ppocrv6_tiny\{det,cls,rec}_infer.onnx` 与 `ppocrv6_tiny_dict.txt`。

### 12.1 视频素材（静态图循环为 mp4）

脚本只接受视频地址（FFmpeg 可直接读 mp4），先把静态图循环成短 mp4：

```powershell
# 用 ocr2.jpg 生成 30s、25fps 的循环视频（需本机有 ffmpeg）
ffmpeg -y -loop 1 -i E:\CLionProjects\ModelDeploy\test_data\test_images\ocr2.jpg `
  -t 30 -r 25 -pix_fmt yuv420p `
  E:\CLionProjects\ModelDeploy\test_data\test_images\ocr2_loop.mp4
```

### 12.2 运行命令

```powershell
pwsh -NoProfile -File scripts/e2e/edge_agent_e2e.ps1 -Transport mqtt -Secret e2e-shared-secret `
  -Scene OCR_TEXT `
  -VideoPath E:\CLionProjects\ModelDeploy\test_data\test_images\ocr2_loop.mp4
```

> 未显式传 `-ModelPath` / `-ClsModelPath` 时，OCR 场景自动改用
> `ppocrv6_tiny\det_infer.onnx` 与 `cls_infer.onnx`；`-RecModelPath` / `-DictPath`
> 已有对应默认值。`-EdgeCode` / `-Secret` 等与默认场景一致。

### 12.3 播种内容

**Algorithm**（`POST /api/v1/video/algorithm/create`）：

```jsonc
{
  "algorithm_type": "OCR_TEXT",
  "scene_type": "OCR_TEXT",
  "model_path": "<ppocrv6_tiny/det_infer.onnx 绝对路径>",
  "runtime_config": { "backend": "ort", "device": "cpu",
                      "decoder": { "hw_accel": "none", "device_only": false } },
  "preset_params": {
    "cls_path": "<ppocrv6_tiny/cls_infer.onnx 绝对路径>",
    "rec_path": "<ppocrv6_tiny/rec_infer.onnx 绝对路径>",
    "dict_path": "<ppocrv6_tiny_dict.txt 绝对路径>",
    "input_size": [960, 960],
    "confidence_threshold": 0.3
  }
}
```

`scene_type=OCR_TEXT` 使 `build_agent_task_config` 编译出单条 `type=ocr`
的模型条目（`det_url` + `cls_url` + `rec_url` + `dict_url`，见
`edge/orchestrator.py:125`）；设备能力校验要求 `model_families=["ocr"]`
（`scene/catalog.py:306`，Agent 心跳上报的能力清单含 `ocr`）。

**AlarmRule**（`POST /api/v1/video/alarm/rule/create`）：

```jsonc
{
  "camera_id": <本次相机 id>,
  "alarm_type": "OCR_TEXT",
  "severity": "WARNING",
  "conditions": { "op": "and",
    "children": [ { "subject": "text_match", "regex": ".+" } ] },
  "status": true
}
```

> 规则匹配键是 `camera_id` + `alarm_type`，且 `alarm_type` 必须等于事件的
> `algorithm_type`（本例均为 `OCR_TEXT`），否则规则不生效（`inference/service.py:111`）。
>
> **正则 `.+` 是故意放宽**：只要任一识别框文本非空即命中，用于验证
> 「事件→归一化→文本规则→告警落库」整条链路。生产应改为业务需要的正则
> （如 `\d{4,}`）；本脚本为链路验证不校验「无文本不告警」分支。

### 12.4 事件与文本语义

Agent 上报事件 v2（`objects[]`），每个对象可带 `text`（识别文本）与
`text_score`（置信度）。云端 `normalize_edge_event` 把 `objects[].text/text_score`
归一化并入 `detections[]`（`edge/consumer.py`），最终落到
`video_alarm_records.ai_result.detections[].text`。规则叶子 `text_match`
（正则）与 `ocr_label`（子串）均基于该字段判定（`inference/service.py:75-89`）。

### 12.5 新增断言与证据

| # | 断言 | 判据 |
|---|------|------|
| 3 | 出现 `algorithm_type=OCR_TEXT` 告警 | 断言 3 按 `$effectiveAlgorithmType` 过滤 |
| 3c | `ai_result.detections[].text` 非空 | 告警样本中至少一个 detection 的 `text` 为非空字符串 |
| 4 | 告警 `snapshot_url` 非空 | 同默认场景 |

```bash
# 文本证据（DB，PostgreSQL 示例）
psql ... -c "select id, alarm_type,
  ai_result->'detections'->0->>'text' as ocr_text
  from video_alarm_records where camera_id=<id> order by id desc limit 5;"
```

脚本结束清理：`AlarmRule` → `Algorithm` → `Camera` → `EdgeDevice`（`-KeepData` 时保留）。

### 12.6 排障

| 现象 | 可能原因 | 处理 |
|------|----------|------|
| 断言 3 超时、无 OCR 告警 | 规则 `alarm_type` 与事件 `algorithm_type` 不一致 / 无规则 | 核对 `alarm_type=OCR_TEXT`；确认事件 `algorithm_type` 由 TaskConfig 透传 |
| 断言 3 超时但 Agent 有事件 | 规则正则未命中（识别文本为空） | 本例 `.+` 只要非空即命中；若仍不中，确认视频可识别出文字（换清晰素材） |
| 断言 3c 失败 | 事件未带 `text`（Plan B 未编译 OCR 头 / 未透传） | 用 `-KeepData` 重跑并查 `video_alarm_records.ai_result->'detections'`，确认 Agent 事件 `objects[].text` |
| 启动任务报「边缘设备能力不足」 | 设备 capabilities 缺 `model_families=["ocr"]` | 脚本已按场景播种该能力；手工核对 `GET /api/v1/video/edge/list` 的 capabilities（Agent 心跳上报含 `ocr`） |
| det/cls/rec 或字典加载失败 | `preset_params` 路径在 Agent 机不存在 | 核对 `-ModelPath`/`-ClsModelPath`/`-RecModelPath`/`-DictPath` 指向 Agent 可读绝对路径 |

## 13. LPR 车牌识别场景（`-Scene LPR`）

前置：ModelDeploy（Plan B）已支持 `lpr`（det+rec）pipeline，且本机存在
`yolov5plate.onnx`（车牌检测）与 `plate_recognition_color.onnx`（车牌字符识别）两个 ONNX 模型。

### 13.1 视频素材（静态图循环为 mp4）

脚本只接受视频地址（FFmpeg 可直接读 mp4），先把车牌静态图循环成短 mp4：

```powershell
# 用 test_lpr_detection.jpg 生成 30s、25fps 的循环视频（需本机有 ffmpeg）
ffmpeg -y -loop 1 -i E:\CLionProjects\ModelDeploy\test_data\test_images\test_lpr_detection.jpg `
  -t 30 -r 25 -pix_fmt yuv420p `
  E:\CLionProjects\ModelDeploy\test_data\test_images\test_lpr_detection_loop.mp4
```

### 13.2 运行命令

```powershell
pwsh -NoProfile -File scripts/e2e/edge_agent_e2e.ps1 -Transport mqtt -Secret e2e-shared-secret `
  -Scene LPR `
  -VideoPath E:\CLionProjects\ModelDeploy\test_data\test_images\test_lpr_detection_loop.mp4
```

> 未显式传 `-ModelPath` 时，LPR 场景自动改用 `yolov5plate.onnx`；识别模型默认由
> `-PlateRecModelPath`（默认 `plate_recognition_color.onnx`）写入 `preset_params.rec_path`。
> `-EdgeCode` / `-Secret` 等与默认场景一致。

### 13.3 播种内容

**Algorithm**（`POST /api/v1/video/algorithm/create`）：

```jsonc
{
  "algorithm_type": "LPR",
  "scene_type": "LPR",
  "model_path": "<yolov5plate.onnx 绝对路径>",
  "runtime_config": { "backend": "ort", "device": "cpu",
                      "decoder": { "hw_accel": "none", "device_only": false } },
  "preset_params": {
    "rec_path": "<plate_recognition_color.onnx 绝对路径>",
    "input_size": [640, 640],
    "confidence_threshold": 0.25
  }
}
```

`scene_type=LPR` 使 `build_agent_task_config` 编译出单条 `type=lpr` 的模型条目
（`det_url` + `rec_url`，见 `edge/orchestrator.py:136`）；设备能力校验要求
`model_families=["lpr"]`（`scene/catalog.py:290`，Agent 心跳上报的能力清单含 `lpr`）。

**AlarmRule**（`POST /api/v1/video/alarm/rule/create`）：

```jsonc
{
  "camera_id": <本次相机 id>,
  "alarm_type": "LPR",
  "severity": "WARNING",
  "conditions": { "op": "and",
    "children": [ { "subject": "text_match", "regex": ".+" } ] },
  "status": true
}
```

> 规则匹配键是 `camera_id` + `alarm_type`，且 `alarm_type` 必须等于事件的
> `algorithm_type`（本例均为 `LPR`），否则规则不生效（`inference/service.py:111`）。
>
> 场景目录 `LPR` 的默认规则即 `text_match` 正则 `.+`（`scene/catalog.py:294`，评估器
> 尚未实现 `plate_match` 叶子）；只要任一车牌框识别文本非空即命中，用于验证
> 「事件→归一化→车牌文本规则→告警落库」整条链路。生产应改为业务需要的车牌正则
> （如 `^京[A-Z0-9]{5,6}$`）；本脚本为链路验证不校验「无车牌不告警」分支。

### 13.4 事件与车牌文本语义

Agent 上报事件 v2（`objects[]`），车牌对象带 `text`（识别文本）与 `text_score`
（置信度）。云端 `normalize_edge_event` 把 `objects[].text/text_score` 归一化并入
`detections[]`（`edge/consumer.py`），最终落到
`video_alarm_records.ai_result.detections[].text`。规则叶子 `text_match`（正则）与
`ocr_label`（子串）均基于该字段判定（`inference/service.py:75-89`）。

### 13.5 新增断言与证据

| # | 断言 | 判据 |
|---|------|------|
| 1b | 设备 `capabilities.model_families` 含 `lpr` | `GET /api/v1/video/edge/list?code=<EdgeCode>` |
| 3 | 出现 `algorithm_type=LPR` 告警 | 断言 3 按 `$effectiveAlgorithmType` 过滤 |
| 3c | `ai_result.detections[].text` 非空 | 告警样本中至少一个 detection 的 `text` 为非空字符串（车牌文本） |
| 4 | 告警 `snapshot_url` 非空 | 同默认场景 |

```bash
# 车牌证据（DB，PostgreSQL 示例）
psql ... -c "select id, alarm_type,
  ai_result->'detections'->0->>'text' as plate_text
  from video_alarm_records where camera_id=<id> order by id desc limit 5;"
```

脚本结束清理：`AlarmRule` → `Algorithm` → `Camera` → `EdgeDevice`（`-KeepData` 时保留）。

### 13.6 排障

| 现象 | 可能原因 | 处理 |
|------|----------|------|
| 断言 3 超时、无 LPR 告警 | 规则 `alarm_type` 与事件 `algorithm_type` 不一致 / 无规则 | 核对 `alarm_type=LPR`；确认事件 `algorithm_type` 由 TaskConfig 透传 |
| 断言 3 超时但 Agent 有事件 | 规则正则未命中（车牌文本为空） | 本例 `.+` 只要非空即命中；若仍不中，确认视频可清晰检出车牌（换素材/调 `confidence_threshold`） |
| 断言 3c 失败 | 事件未带 `text`（Plan B 未编译 lpr 头 / 未透传） | 用 `-KeepData` 重跑并查 `video_alarm_records.ai_result->'detections'`，确认 Agent 事件 `objects[].text` |
| 启动任务报「边缘设备能力不足」 | 设备 capabilities 缺 `model_families=["lpr"]` | 脚本已按场景播种该能力；手工核对 `GET /api/v1/video/edge/list` 的 capabilities（Agent 心跳上报含 `lpr`） |
| det/rec 模型加载失败 | `preset_params` 路径在 Agent 机不存在 | 核对 `-ModelPath`/`-PlateRecModelPath` 指向 Agent 可读绝对路径 |

## 14. 跟踪 track_id 场景（`-Scene DET_ZONE -Tracking`）

前置：ModelDeploy（Plan B）已支持逐帧目标跟踪（ByteTrack），能在事件 v2 `objects[].track_id`
回填稳定轨迹号；`-Scene DET_ZONE -Tracking` 使用单 det 模型（默认 `yolo11n_nms.onnx`）与
`test_video60.mp4`（含目标，能持续检出才可能稳定赋 ID）。对应 SP4 跟踪纵切片
（`docs/superpowers/specs/2026-09-15-tracking-slice-design.md`）。

### 14.1 运行命令

```powershell
pwsh -NoProfile -File scripts/e2e/edge_agent_e2e.ps1 -Transport mqtt -Secret e2e-shared-secret `
  -Scene DET_ZONE -Tracking `
  -VideoPath E:\CLionProjects\ModelDeploy\test_data\test_video60.mp4
```

> `-Scene DET_ZONE` 为单 det 检测场景（`algorithm_type=DET_ZONE`、`scene_type=DET_ZONE`，
> 设备能力要求 `model_families=["det"]`）。`-Tracking` 与场景正交：任何检测类场景
> （`DET_ZONE`/`INTRUSION`）均可叠加，脚本把 `runtime_config.tracking` 写入 Algorithm。

### 14.2 播种内容

**Algorithm**（`POST /api/v1/video/algorithm/create`）：

```jsonc
{
  "algorithm_type": "DET_ZONE",
  "scene_type": "DET_ZONE",
  "model_path": "<yolo11n_nms.onnx 绝对路径>",
  "runtime_config": {
    "backend": "ort", "device": "cpu",
    "decoder": { "hw_accel": "none", "device_only": false, "rtsp_transport": "tcp" },
    "tracking": { "enabled": true, "algorithm": "bytetrack" }
  },
  "preset_params": { "confidence_threshold": 0.4, "input_size": [640, 640] }
}
```

`build_agent_task_config` 把 `runtime_config.tracking` 编译为 Agent TaskConfig 顶层
`tracking={enabled,algorithm}`（缺省 `{"enabled": false, "algorithm": "bytetrack"}`，
见 `edge/orchestrator.py:105-111`）。

### 14.3 事件与 track_id 语义

Agent 在 `tracking.enabled=true` 时对每帧检测结果跑跟踪器，把 `track_id` 回填到 detection，
并在事件 v2 `objects[].track_id` 上报（仅 `>= 0` 才写）。云端 `normalize_edge_event`
把 `objects[].track_id` 并入 `detections[]`（`edge/consumer.py:60`），最终落到
`video_alarm_records.ai_result.detections[].track_id`。关闭跟踪时 `track_id=-1`（不下发该字段）。

### 14.4 新增断言与证据

| # | 断言 | 判据 |
|---|------|------|
| 3 | 出现 `algorithm_type=DET_ZONE` 告警 | 断言 3 按 `$effectiveAlgorithmType` 过滤 |
| 3d | `ai_result.detections[].track_id` 至少一条出现且 `>= 0` | 告警样本中至少一个 detection 带 `track_id` 且数值 `>= 0` |
| 4 | 告警 `snapshot_url` 非空 | 同默认场景 |

```bash
# 跟踪证据（DB，PostgreSQL 示例）
psql ... -c "select id, alarm_type,
  jsonb_path_query_array(ai_result, '$.detections[*].track_id') as track_ids
  from video_alarm_records where camera_id=<id> order by id desc limit 5;"
```

脚本结束清理：`Algorithm` → `Camera` → `EdgeDevice`（`-KeepData` 时保留）。

### 14.5 排障

| 现象 | 可能原因 | 处理 |
|------|----------|------|
| 断言 3d 失败（无 `track_id`） | Agent 未启用跟踪 / 未回填 / 事件未带 `objects[].track_id` | 用 `-KeepData` 重跑并查 `video_alarm_records.ai_result->'detections'`；确认 Algorithm 的 `runtime_config.tracking.enabled=true` 且 Agent 版本支持跟踪 |
| 断言 3d 失败但断言 3 通过 | 检测到目标但未形成轨迹（目标过少/抽帧稀疏） | 换含持续运动目标的视频；跟踪状态在抽帧/丢帧下可能断轨（可接受，见 spec §7） |
| 断言 3 超时、无 `DET_ZONE` 告警 | 规则 `alarm_type` 与事件 `algorithm_type` 不一致 / 无规则 | 该场景不播种显式规则，后端按无规则直接落告警；仍超时则核对视频是否可检出目标 |
| 启动任务报「边缘设备能力不足」 | 设备 capabilities 缺 `model_families=["det"]` | 脚本已按场景播种该能力（`Seed-EdgeDevice` 默认 `["det"]`）；手工核对 `GET /api/v1/video/edge/list` |
| 模型加载失败 | `model_path` 在 Agent 机不存在 | 核对 `-ModelPath` 指向 Agent 可读绝对路径 |

## 15. FACE_DET 人脸检测场景（`-Scene FACE_DET`）

前置：ModelDeploy（Plan B）已支持 `face_detection`（SCRFD）pipeline，能把人脸框并入事件 v2
`objects[]`；本机存在 `scrfd_2.5g_bnkps_shape640x640.onnx`（输入固定 640x640，ORT/CPU）。

### 15.1 视频素材（静态图循环为 mp4）

脚本只接受视频地址（FFmpeg 可直接读 mp4），先把人脸静态图循环成短 mp4：

```powershell
# 用 test_face_detection.jpg 生成 30s、25fps 的循环视频（需本机有 ffmpeg）
ffmpeg -y -loop 1 -i E:\CLionProjects\ModelDeploy\test_data\test_images\test_face_detection.jpg `
  -t 30 -r 25 -pix_fmt yuv420p `
  E:\CLionProjects\ModelDeploy\test_data\test_images\test_face_detection_loop.mp4
```

> `test_images\` 下人脸素材：`test_face_detection.jpg`（另见 `test_face_detection0-5.*`、
> `test_face.jpg`、`test_face1-3.jpg`）。本 runbook 选用文件名含 `face_detection` 的
> `test_face_detection.jpg`，与 SCRFD 检测场景对应；换图时用文件名确认素材含人脸。

### 15.2 运行命令

```powershell
pwsh -NoProfile -File scripts/e2e/edge_agent_e2e.ps1 -Transport mqtt -Secret e2e-shared-secret `
  -Scene FACE_DET `
  -VideoPath E:\CLionProjects\ModelDeploy\test_data\test_images\test_face_detection_loop.mp4
```

> 未显式传 `-ModelPath` 时，FACE_DET 场景自动改用 `-FaceModelPath`
> （默认 `seetaface\scrfd_2.5g_bnkps_shape640x640.onnx`）。`-EdgeCode` / `-Secret` 等与默认场景一致。

### 15.3 播种内容

**Algorithm**（`POST /api/v1/video/algorithm/create`）：

```jsonc
{
  "algorithm_type": "FACE_DET",
  "scene_type": "FACE_DET",
  "model_path": "<scrfd_2.5g_bnkps_shape640x640.onnx 绝对路径>",
  "runtime_config": { "backend": "ort", "device": "cpu",
                      "decoder": { "hw_accel": "none", "device_only": false } },
  "preset_params": { "input_size": [640, 640], "confidence_threshold": 0.3 }
}
```

`scene_type=FACE_DET` 使 `build_agent_task_config` 编译出单条 `type=face_detection`
的模型条目（`url` 取 `model_path`，见 `edge/orchestrator.py:153`）；场景目录要求设备具备
`model_families` 含 `face_detection`（`scene/catalog.py:260`）。

**AlarmRule**（`POST /api/v1/video/alarm/rule/create`）：

```jsonc
{
  "camera_id": <本次相机 id>,
  "alarm_type": "FACE_DET",
  "severity": "WARNING",
  "conditions": { "op": "and", "children": [ { "subject": "object_present" } ] },
  "status": true
}
```

> 规则匹配键是 `camera_id` + `alarm_type`，且 `alarm_type` 必须等于事件的
> `algorithm_type`（本例均为 `FACE_DET`），否则规则不生效（`inference/service.py:111`）。
>
> **不限定 `label` 是故意放宽**：人脸模型 `labels` 为空/随模型而异，限定 `"face"` 可能漏命中；
> 只要出现任一人脸框即命中，用于验证「事件→归一化→object_present 规则→告警落库」整条链路。
> 生产可改为 `object_present` + `label` 或 `count >= N`。

### 15.4 事件与人脸框语义

Agent 上报事件 v2（`objects[]`），人脸框由 `label/label_id/confidence/bbox` 承载；
云端 `normalize_edge_event` 把 `objects[]` 归一化为 `detections[]`（`edge/consumer.py`），
最终落到 `video_alarm_records.ai_result.detections[]`。人脸 `keypoints` 暂不上报（后续 FACE_LANDMARK）。

### 15.5 新增断言与证据

| # | 断言 | 判据 |
|---|------|------|
| 1b | 设备 `capabilities.model_families` 含 `face` | `GET /api/v1/video/edge/list?code=<EdgeCode>`（Agent 心跳上报的人脸族名） |
| 3 | 出现 `algorithm_type=FACE_DET` 告警 | 断言 3 按 `$effectiveAlgorithmType` 过滤 |
| 3b | `ai_result.detections[]` 非空（人脸框） | 告警样本中至少一个人脸检测框 |
| 4 | 告警 `snapshot_url` 非空 | 同默认场景 |

```bash
# 人脸证据（DB，PostgreSQL 示例）
psql ... -c "select id, alarm_type,
  jsonb_array_length(ai_result->'detections') as n_dets
  from video_alarm_records where camera_id=<id> order by id desc limit 5;"
```

脚本结束清理：`AlarmRule` → `Algorithm` → `Camera` → `EdgeDevice`（`-KeepData` 时保留）。

### 15.6 排障

| 现象 | 可能原因 | 处理 |
|------|----------|------|
| 启动任务报「边缘设备能力不足: 设备不支持模型族 face_detection」 | 场景目录要求 `face_detection`，而 Agent 心跳上报的族名为 `face`（`capability.cpp`） | 已知命名差异：脚本播种 `["face_detection","face"]` 兜底，但心跳会覆盖为 Agent 上报值；若仍报错，需将场景目录 `FACE_DET.model_families` 对齐为 `face`（或让 Agent 上报 `face_detection`） |
| 断言 3 超时、无 `FACE_DET` 告警 | 规则 `alarm_type` 与事件 `algorithm_type` 不一致 / 无规则 | 核对 `alarm_type=FACE_DET`；确认事件 `algorithm_type` 由 TaskConfig 透传 |
| 断言 3 超时但 Agent 有事件 | 规则 `object_present` 未命中（无人脸框） | 换含清晰人脸的素材（`test_face_detection.jpg`）；确认 `confidence_threshold=0.3` 下能检出 |
| 断言 3b 失败 | 事件未带人脸框（Agent 未把 `face_detection` 并入 sink） | 用 `-KeepData` 重跑并查 `video_alarm_records.ai_result->'detections'`，确认 Agent 事件 `objects[]` 含人脸框 |
| 模型加载失败 | `-FaceModelPath` 在 Agent 机不存在 | 核对指向 Agent 可读绝对路径（`seetaface\scrfd_2.5g_bnkps_shape640x640.onnx`） |

## 16. ABSENT 离岗/无人场景（`-Scene ABSENT`）

前置：ModelDeploy 已支持**空事件心跳**（`heartbeat_sec > 0`），Agent 在任务运行期每
`heartbeat_sec` 上报一条空检测事件 `{detections:[], objects:[], heartbeat:true, ...}`；
云端 `process_detection_callback` 对含时序叶子（absence）的规则不再因空检测早退，并按
`rule.interval_seconds` 做触发防抖。对应 SP4-b 收尾
（`docs/superpowers/specs/2026-09-15-sp4b-wrapup-design.md` §3.3）。

> 关键前置：**视频必须「人先出现、随后离开画面」**。absence 判定依据是「距最近一次
> 观测到 `person` 的时长 >= `gap_sec`」；若全程空白（`last_seen` 无历史），求值器一律
> 不命中，`断言3` 会超时。

### 16.1 混合视频素材制作

脚本只接受视频地址（FFmpeg 可直接读 mp4）。推荐把「含人片段」与「空画面片段」拼接成一条：

```powershell
# 1) 含人片段（例如 6s，需能检出 person）
ffmpeg -y -i E:\dst\person_clip.mp4 -t 6 -r 25 -pix_fmt yuv420p E:\dst\part_person.mp4
# 2) 空白片段（例如 20s，纯背景/纯黑；> gap_sec + 若干心跳周期）
ffmpeg -y -f lavfi -i color=c=black:s=1280x720:d=20 -r 25 -pix_fmt yuv420p E:\dst\part_blank.mp4
# 3) 拼接（concat demuxer）
"file 'part_person.mp4'`nfile 'part_blank.mp4'" | Set-Content E:\dst\concat.txt -Encoding ascii
ffmpeg -y -f concat -safe 0 -i E:\dst\concat.txt -c copy `
  E:\CLionProjects\ModelDeploy\test_data\test_images\absent_person_then_blank.mp4
```

> 空白片段的时长建议 >= `gap_sec`（本脚本 10s）+ 2~3 个心跳周期（`heartbeat_sec` 默认 5s），
> 即 >= 25s，确保静默期内至少有一次心跳到达云端。
> 若无法拼视频，也可用「人片段」与「纯背景片段」两次运行分别验证：先播人片段使 `last_seen`
> 有历史，再切到空白源等待心跳触发（脚本单次运行只接受一个 `-VideoPath`，故推荐拼接）。

### 16.2 运行命令

```powershell
pwsh -NoProfile -File scripts/e2e/edge_agent_e2e.ps1 -Transport mqtt -Secret e2e-shared-secret `
  -Scene ABSENT `
  -VideoPath E:\CLionProjects\ModelDeploy\test_data\test_images\absent_person_then_blank.mp4
```

> 未显式传 `-ModelPath` 时，ABSENT 场景自动改用 `-DetModelPath`
> （默认 `yolo11n_nms.onnx`）。`-EdgeCode` / `-Secret` 等与默认场景一致。

### 16.3 播种内容

**Algorithm**（`POST /api/v1/video/algorithm/create`）：

```jsonc
{
  "algorithm_type": "ABSENT",
  "scene_type": "ABSENT",
  "model_path": "<yolo11n_nms.onnx 绝对路径>",
  "runtime_config": { "backend": "ort", "device": "cpu",
                      "decoder": { "hw_accel": "none", "device_only": false } },
  "preset_params": { "confidence_threshold": 0.3 }
}
```

`scene_type=ABSENT` 使 `build_agent_task_config` 编译出单条 `type=det` 的模型条目
（设备能力校验要求 `model_families=["det"]`，`scene/catalog.py:110`）。

**AlarmRule**（`POST /api/v1/video/alarm/rule/create`）：

```jsonc
{
  "camera_id": <本次相机 id>,
  "alarm_type": "ABSENT",
  "severity": "WARNING",
  "interval_seconds": 30,
  "conditions": { "op": "and",
    "children": [ { "subject": "absence", "label": "person", "gap_sec": 10 } ] },
  "status": true
}
```

> 规则匹配键是 `camera_id` + `alarm_type`，且 `alarm_type` 必须等于事件的
> `algorithm_type`（本例均为 `ABSENT`），否则规则不生效（`inference/service.py:111`）。

### 16.4 心跳与 absence 时序语义

| 概念 | 归属 | 含义 | 本脚本取值 |
|------|------|------|-----------|
| `heartbeat_sec` | Agent 任务配置 | 任务运行期每 N 秒上报一条空检测事件；`<=0` 关闭、`>=1` 生效 | 默认 5s（Agent 侧） |
| `gap_sec` | AlarmRule 条件叶子 | 「距最近一次观测到 `label` 的时长」达到该秒数才命中 absence | 10s |
| `interval_seconds` | AlarmRule 字段 | 告警防抖窗口：同一窗口内 absence 不重复告警（云端触发后写标记，窗口内再命中也不建告警） | 30s |

- 目标出现时，Agent 上报含 `detections` 的事件，云端写入 `last_seen`（时序存储，TTL 24h）。
- 目标离开后，视频进入静默期。**普通帧不再产生事件**（Agent 空框不发布），唯一到达云端的
  就是心跳空检测事件；`(now - last_seen) >= gap_sec` 时 absence 命中并建告警。
- 首次告警后 `interval_seconds=30` 内，心跳继续到达但被防抖标记拦住，不重复建告警；
  检测恢复后 `last_seen` 推进、gap 条件为假，静默再次超时后可重新告警。

### 16.5 新增断言与证据

| # | 断言 | 判据 |
|---|------|------|
| 1b | 设备 `capabilities.model_families` 含 `det` | `GET /api/v1/video/edge/list?code=<EdgeCode>` |
| 3 | 出现 `algorithm_type=ABSENT` 告警 | 断言 3 按 `$effectiveAlgorithmType` 过滤（由心跳驱动的告警） |
| 3b | `ai_result.detections` 为空 | 告警样本 `ai_result.detections` 为 `[]`，证明告警来自空检测心跳而非真实框 |
| 3c | `interval_seconds=30` 内不重复建告警（容差 1 条） | 首次告警后等待 15s（< 30s）再统计新增 `ABSENT` 告警数 `<= 1` |

```bash
# 离岗证据（DB，PostgreSQL 示例）
psql ... -c "select id, alarm_type,
  jsonb_array_length(ai_result->'detections') as n_dets,
  ai_result->>'task_id' as task_id
  from video_alarm_records where camera_id=<id> order by id desc limit 5;"
```

脚本结束清理：`AlarmRule` → `Algorithm` → `Camera` → `EdgeDevice`（`-KeepData` 时保留）。

### 16.6 排障

| 现象 | 可能原因 | 处理 |
|------|----------|------|
| 断言 3 超时、无 `ABSENT` 告警 | 视频全程无目标（`last_seen` 无历史）；或视频没有真正的静默段；或 Agent `heartbeat_sec<=0` 未发心跳 | 换「人先出现再离场」的混合视频；确认 Agent 心跳已开启（`heartbeat_sec` 默认 5s）；确认后端为已含 SP4-b 收尾的实现（空检测不再早退） |
| 断言 3 超时但 Agent 有含检测事件 | 规则 `alarm_type` 与事件 `algorithm_type` 不一致 / 无规则 / `label` 不匹配 | 核对 `alarm_type=ABSENT`；确认视频能检出 `person`（模型 `labels` 含 person） |
| 断言 3b 失败（detections 非空） | 命中的是真实检测事件而非心跳空事件 | 检查视频静默段是否仍有残留检出（`confidence_threshold` 过低）；提高 `gap_sec` 前的静默质量 |
| 断言 3c 失败（短窗内多条） | `interval_seconds` 未生效 / 云端防抖标记写入失败 | 核对 AlarmRule `interval_seconds=30` 已落库；用 `-KeepData` 重跑查 DB，确认 Redis/内存标记正常（`ai:temporal:*:__absent__:*`） |
| 启动任务报「边缘设备能力不足」 | 设备 capabilities 缺 `model_families=["det"]` | 脚本已按场景播种该能力（`Seed-EdgeDevice` 默认 `["det"]`）；手工核对 `GET /api/v1/video/edge/list` |
| 模型加载失败 | `-DetModelPath` 在 Agent 机不存在 | 核对指向 Agent 可读绝对路径（`yolo11n\yolo11n_nms.onnx`） |
