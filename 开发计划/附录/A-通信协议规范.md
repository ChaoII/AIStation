# 附录 A：AI 盒子通信协议规范

## 概述

本文档定义 AI 盒子 Agent 与 Web 主站之间的通信协议。所有请求由 Agent 主动发起，Web 端在响应中返回待执行命令。

## 基础信息

| 项目 | 值 |
|------|-----|
| 传输协议 | HTTPS（生产）/ HTTP（开发） |
| 认证方式 | 注册使用 secret_key，后续使用 JWT Bearer Token |
| 数据格式 | JSON |
| 编码 | UTF-8 |
| 超时 | Agent → Web: 15s, Web → Agent (回调): 10s |

## Agent → Web 接口

### 1. 注册

```
POST /api/v1/algorithm/agent/register
```

**认证：** 无（使用 secret_key 验证）

**请求体：**
```json
{
  "box_id": "AI-BOX-001A",
  "name": "门口AI盒",
  "secret_key": "预共享密钥",
  "ip_address": "10.0.1.50",
  "agent_port": 9510,
  "api_version": "1.0.0",
  "gpu_info": {
    "model": "NVIDIA Jetson Orin NX 16GB",
    "memory_mb": 8192,
    "driver_version": "12.2",
    "cuda_version": "12.2"
  },
  "cpu_info": {
    "cores": 8,
    "arch": "aarch64"
  },
  "memory_total": 16384,
  "max_tasks": 4
}
```

**成功响应 (200)：**
```json
{
  "code": 200,
  "data": {
    "box_db_id": 1,
    "token": "eyJhbGciOiJIUzI1NiIs..."
  },
  "msg": "注册成功"
}
```

**错误响应：**
```json
{
  "code": 401,
  "msg": "secret_key 验证失败"
}
```

### 2. 心跳

```
POST /api/v1/algorithm/agent/heartbeat
```

**认证：** `Authorization: Bearer <token>`

**请求体：**
```json
{
  "box_id": 1,
  "timestamp": "2026-05-31T10:00:00Z",
  "tasks": [
    {
      "task_id": 1,
      "local_status": "RUNNING",
      "fps": 12.5,
      "inference_latency_ms": 8.3,
      "uptime_sec": 3600,
      "pid": 12345
    },
    {
      "task_id": 2,
      "local_status": "STOPPED",
      "uptime_sec": 0
    }
  ],
  "resource_usage": {
    "gpu_util_percent": 65,
    "gpu_mem_used_mb": 4096,
    "cpu_percent": 45,
    "memory_used_mb": 8192
  }
}
```

**响应（带回命令）：**
```json
{
  "code": 200,
  "data": {
    "server_time": "2026-05-31T10:00:30Z",
    "commands": [
      {
        "command_id": "cmd_abc123",
        "action": "start_task",
        "task_id": 3,
        "priority": 1,
        "config": {
          "task_id": 3,
          "camera_id": 24,
          "camera_name": "仓库_内部东",
          "algorithm_type": "INTRUSION",
          "stream_url": "http://zlm:80/live/camera_24.live.flv",
          "model_path": "/data/models/intrusion/engine.onnx",
          "runtime_config": {
            "engine": "tensorrt",
            "gpu": {"enabled": true, "device_id": 0},
            "threads": 4,
            "batch_size": 1,
            "input_width": 640,
            "input_height": 640
          },
          "preset_params": {
            "conf_threshold": 0.5,
            "nms_threshold": 0.45
          },
          "detect_region": [[0.1,0.1],[0.9,0.1],[0.9,0.9],[0.1,0.9]],
          "sensitivity": 50,
          "callback_url": "https://web.example.com/api/v1/algorithm/detection/callback",
          "callback_token": "worker_shared_secret",
          "fps_target": 5,
          "alarm_interval": 30,
          "snapshot_dir": "/opt/ai-box-agent/snapshots/"
        }
      },
      {
        "command_id": "cmd_def456",
        "action": "stop_task",
        "task_id": 2
      },
      {
        "command_id": "cmd_ghi789",
        "action": "reload_model",
        "task_id": 1,
        "config": {
          "model_path": "/data/models/intrusion/v2.0.0/engine.onnx",
          "preset_params": {"conf_threshold": 0.3}
        }
      }
    ]
  }
}
```

### 3. 状态上报（可选的独立接口）

如果心跳包太大，可以使用独立的状态上报接口：

```
POST /api/v1/algorithm/agent/report-status
```

请求体同心跳的 tasks 数组部分，响应不返回命令。

### 4. 结果回调（复用阶段1 接口）

```
POST /api/v1/algorithm/detection/callback
```

**认证：** `Authorization: Bearer <worker_callback_token>`（Worker 的共享密钥，不是 Agent 的 JWT）

**请求体：**
```json
{
  "task_id": 1,
  "box_id": 1,
  "camera_id": 24,
  "algorithm_type": "INTRUSION",
  "detections": [
    {
      "label": "person",
      "label_id": 0,
      "confidence": 0.92,
      "bbox": {"x": 0.1, "y": 0.2, "width": 0.3, "height": 0.5}
    }
  ],
  "snapshot_data": "/9j/4AAQ...base64 JPEG...",
  "snapshot_path": "2026-05-31/1_1717123456.jpg",
  "frame_timestamp": "2026-05-31T10:00:05.789Z",
  "inference_latency_ms": 12.3
}
```

## 命令类型枚举

| action | 说明 | 必需字段 |
|--------|------|----------|
| `start_task` | 启动新任务 | task_id, config (完整) |
| `stop_task` | 停止任务 | task_id |
| `restart_task` | 重启任务 | task_id |
| `reload_model` | 热重载模型 | task_id, config (增量) |
| `update_config` | 更新运行配置 | task_id, config (增量) |

## 状态枚举

### local_status

| 值 | 说明 |
|----|------|
| `PENDING` | 等待 Agent 拾取 |
| `RUNNING` | Worker 进程正常运行 |
| `STOPPED` | 已正常停止 |
| `ERROR` | Worker 异常退出 |
| `UNKNOWN` | 盒子离线，状态未知 |

### Box status

| 值 | 说明 |
|----|------|
| `ONLINE` | 心跳正常 |
| `OFFLINE` | 心跳超时（>3周期） |
| `ERROR` | Agent 上报错误状态 |
| `DRAINING` | 维护模式（逐步迁移任务） |

## Agent HTTP 返回

Agent 连接到 Web 时，返回值可以是：

```
200 OK            成功
401 Unauthorized  token 过期或无效（Agent 应重新注册）
429 Too Many      限流中（Agent 应等待后重试）
503 Service       Web 暂时不可用（Agent 应保持长间隔重试）
```

## Worker → Agent（本地接口）

Worker 进程通过 stderr JSON 向 Agent 报告状态：

Worker stdout 保留给 print 调试，stderr 格式：

```json
{"type":"heartbeat","task_id":1,"fps":12.5,"latency_ms":8.3}
{"type":"detection","task_id":1,"count":2,"labels":["person","car"]}
{"type":"error","task_id":1,"msg":"stream_disconnected"}
{"type":"shutdown","task_id":1,"uptime":3600,"total_detections":150}
```

Agent 从 PIPE 读取 stderr 解析这些事件。
