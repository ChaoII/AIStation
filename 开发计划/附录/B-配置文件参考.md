# 附录 B：配置文件参考

## 1. AI 盒子 Agent config.yaml

```yaml
# /opt/ai-box-agent/config.yaml

agent:
  # 盒子标识
  box_id: "AI-BOX-001A"                  # 硬件唯一标识（MAC/SN，固定不变）
  box_name: "门口AI盒"                    # 运维可读名称
  secret_key: "sk_abc123def456"           # 注册密钥（预共享，与 Web 端一致）

  # Web 主站地址（支持多个，逗号分隔）
  register_url: "https://web.example.com/api/v1/algorithm/agent/register"
  heartbeat_url: "https://web.example.com/api/v1/algorithm/agent/heartbeat"

  # Worker 回调地址（Worker 直连 Web）
  callback_url: "https://web.example.com/api/v1/algorithm/detection/callback"
  callback_token: "wk_shared_secret_xyz"

  # 心跳间隔（秒）
  heartbeat_interval: 30

  # Worker 可执行文件路径
  worker_python: "/usr/bin/python3"       # Python 解释器路径
  worker_script: "/opt/ai-box-agent/worker.py"

  # 本地持久化路径
  tasks_dir: "/opt/ai-box-agent/tasks/"   # 任务配置持久化目录
  snapshot_dir: "/opt/ai-box-agent/snapshots/"  # 检测快照目录
  cache_dir: "/opt/ai-box-agent/cache/"   # 离线结果缓存目录
  log_dir: "/opt/ai-box-agent/logs/"      # Agent 日志目录

  # 资源限制
  max_tasks: 4                            # 最大并发任务数
  max_restart_attempts: 3                 # Worker 崩溃最大重启次数
  result_cache_max: 1000                  # 离线结果缓存上限（条）

  # 网络
  http_timeout: 15                        # HTTP 请求超时（秒）
  retry_delays: [1, 2, 4, 8, 15, 30]     # 重试间隔（秒）

hardware:
  gpu:
    model: "NVIDIA Jetson Orin NX 16GB"
    memory_mb: 8192
    driver_version: "12.2"
    cuda_version: "12.2"
  cpu:
    cores: 8
    arch: "aarch64"
  memory_total_mb: 16384

logging:
  level: "INFO"
  format: "json"                          # json 或 text
  file: "/opt/ai-box-agent/logs/agent.log"
  max_size_mb: 100
  backup_count: 5
```

## 2. Backend settings.py 新增配置

```python
# inference callback
INFERENCE_CALLBACK_TOKEN: str = "wk_shared_secret_xyz"  # Worker 回调共享密钥
DETECTIONS_DIR: str = str(PROJECT_ROOT / "data" / "detections")  # 快照目录

# Worker 配置
INFERENCE_WORKER_PATH: str = str(PROJECT_ROOT / "app/api/v1/module_video/inference/worker.py")
INFERENCE_WORKER_PYTHON: str = sys.executable  # 当前 Python 解释器
INFERENCE_CONFIG_DIR: str = "/tmp/inference_configs/"  # 临时配置文件目录

# 调度器
INFERENCE_SCHEDULER_INTERVAL: int = 60  # 调度器检查间隔（秒）
INFERENCE_WARMUP_DELAY: int = 15  # 启动后延迟（秒）

# 盒子心跳检测
BOX_HEARTBEAT_TIMEOUT: int = 180  # 心跳超时判定（秒）
BOX_HEARTBEAT_CHECK_INTERVAL: int = 60  # 超时检测间隔（秒）
```

## 3. .env.dev 新增

```bash
# 推理配置
INFERENCE_CALLBACK_TOKEN=wk_shared_secret_xyz
INFERENCE_SCHEDULER_INTERVAL=60
INFERENCE_WARMUP_DELAY=15

# 盒子通信
BOX_HEARTBEAT_TIMEOUT=180
BOX_HEARTBEAT_CHECK_INTERVAL=60
```

## 4. 模型目录结构

```
data/models/
├── models.json                        # 模型注册信息（自动生成）
├── intrusion/                         # 入侵检测
│   ├── v1.0.0/
│   │   ├── engine.onnx               # 模型文件
│   │   └── metadata.json             # 元数据
│   ├── v2.0.0/
│   │   ├── engine.onnx
│   │   └── metadata.json
│   └── current -> v2.0.0/            # 当前版本符号链接
├── line_crossing/
│   └── v1.0.0/
│       ├── engine.onnx
│       └── metadata.json
├── crowd_count/
│   └── v1.0.0/...
├── fire_smoke/
│   └── v1.0.0/...
├── vehicle_detect/
│   └── v1.0.0/...
├── object_left/
│   └── v1.0.0/...
├── face_detect/
│   └── v1.0.0/
│       ├── det.onnx                  # 人脸检测模型
│       ├── rec.onnx                  # 人脸特征提取模型
│       └── metadata.json
└── behavior_analysis/
    └── v1.0.0/
        ├── engine.onnx               # 姿态估计模型
        └── metadata.json
```

### metadata.json 格式

```json
{
  "version": "v2.0.0",
  "created_at": "2026-05-01T10:00:00Z",
  "framework": "ultralytics",
  "base_model": "yolov8n",
  "dataset": "custom_intrusion_v3",
  "dataset_size": 15000,
  "classes": ["person", "car", "bicycle", "motorcycle"],
  "metrics": {
    "mAP50": 0.892,
    "mAP50-95": 0.654,
    "precision": 0.912,
    "recall": 0.875
  },
  "input_size": [640, 640],
  "format": "onnx",
  "checksum_sha256": "abcdef123456..."
}
```

## 5. 快照目录结构

```
data/detections/
├── 2026-05-31/
│   ├── 1_1717123456.jpg              # {task_id}_{unix_timestamp}.jpg
│   ├── 1_1717123489.jpg
│   ├── 2_1717123500.jpg
│   └── ...
├── 2026-06-01/
│   └── ...
└── .retention_days                    # 保留天数标记文件 (default: 7)
```

## 6. Docker Compose 扩展

```yaml
# docker-compose.yaml 新增/修改

version: '3.8'

services:
  postgres:
    image: postgres:17
    # ... 现有配置

  redis:
    image: redis:7
    # ... 现有配置

  zlmediakit:
    image: zlmediakit/zlmediakit:master
    # ... 现有配置

  web:
    build: ./backend
    ports:
      - "8001:8001"
    environment:
      - INFERENCE_CALLBACK_TOKEN=wk_shared_secret_xyz
    depends_on:
      - postgres
      - redis

  prometheus:
    image: prom/prometheus:latest
    volumes:
      - ./deploy/prometheus.yml:/etc/prometheus/prometheus.yml
    ports:
      - "9090:9090"

  grafana:
    image: grafana/grafana:latest
    ports:
      - "3000:3000"
    depends_on:
      - prometheus

  loki:
    image: grafana/loki:latest
    ports:
      - "3100:3100"

  promtail:
    image: grafana/promtail:latest
    volumes:
      - ./deploy/promtail.yml:/etc/promtail/promtail.yml
      - /var/log:/var/log
```

## 7. Nginx 配置参考

```nginx
# /etc/nginx/sites-available/video-surveillance

upstream web_backend {
    ip_hash;
    server 10.0.1.1:8001;
    server 10.0.1.2:8001;
    server 10.0.1.3:8001;
}

server {
    listen 443 ssl;
    server_name web.example.com;

    ssl_certificate /etc/ssl/certs/example.crt;
    ssl_certificate_key /etc/ssl/private/example.key;

    client_max_body_size 10M;

    location /api/ {
        proxy_pass http://web_backend;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_read_timeout 30s;
    }

    location /ws/ {
        proxy_pass http://web_backend;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_read_timeout 3600s;
    }

    location /recordings/ {
        proxy_pass http://web_backend;
    }
}
```
