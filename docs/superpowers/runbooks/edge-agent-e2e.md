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
| 模型文件 | `...\test_data\test_models\onnx\yolo11n\yolo11n_nms.onnx` | ONNX 检测模型（ORT/CPU） |
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
| `-Secret` | `e2e-shared-secret` | Agent `--api-key`/`--secret`、EdgeDevice.secret、后端 `EDGE_CONTROL_TOKEN` |
| `-AgentExe` / `-VideoPath` / `-ModelPath` | 见第 2 节 | 真机素材路径 |
| `-DecoderHwAccel` | `none` | 算法 `runtime_config.decoder.hw_accel`；默认 CPU 解码以匹配 ORT/CPU 模型，GPU 后端改为 `cuda` |
| `-ApiBase` | `http://127.0.0.1:8001` | 后端基址 |
| `-AgentPort` | `19090` | Agent 控制面端口 |
| `-BrokerPort` | `1883` | Broker 端口 |
| `-SkipBroker` | 关 | 跳过起 Broker |
| `-KeepResources` | 关 | 保留 Agent 进程 / Broker 容器 |
| `-KeepData` | 关 | 保留播种的 Algorithm/Camera/EdgeDevice |

## 5. 脚本流程与断言

流程：起 Broker（可选）→ 登录 → 播种 EdgeDevice → 起 Agent → 播种 Algorithm/Camera/Task#1
→ start → 轮询断言 → 去重测试 → 时段测试（Task#2 窗口外）→ stop/delete 生命周期 → 证据与清理。

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

> 去重测试使用哨兵 `task_id=999999`，避免与真实 Agent 告警混淆。

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
