# 附录 C：故障排查指南

## 1. Worker 无法启动

### 现象

```
inference.scheduler - WARNING - Worker 启动失败: task_id=1, error=...
```

### 排查步骤

```bash
# 1. 检查配置文件是否生成
ls -la /tmp/infer_*.json

# 2. 手动运行 Worker 测试
python worker.py --config /tmp/infer_1_xxx.json

# 3. 检查模型文件是否存在
ls -la /data/models/intrusion/engine.onnx

# 4. 检查 stream_url 是否可达
ffprobe http://localhost:80/live/camera_24.live.flv

# 5. 检查 GPU 是否可用
python -c "import torch; print(torch.cuda.is_available())"
nvidia-smi

# 6. 检查 ModelDeploy
python -c "
from modeldeploy import get_version
from modeldeploy.vision import UltralyticsDet
print(f'ModelDeploy {get_version()}')
print('SDK OK')
"
```

### 常见原因

| 原因 | 解决方案 |
|------|----------|
| 模型路径错误 | 检查 `model_path` 是否为绝对路径 |
| GPU 显存不足 | `nvidia-smi` 检查显存，减少并发任务数 |
| ModelDeploy 未安装 | `pip install modeldeploy` |
| OpenCV 无法解码流 | 用 VLC/ffplay 测试 stream_url 是否可播放 |
| 配置文件格式错误 | `python -c "import json; json.load(open('/tmp/infer_1.json'))"` |

## 2. Worker 进程意外退出

### 日志标识

```
inference.scheduler - WARNING - Worker 进程退出: task_id=1, returncode=-9
```

### 排查

```bash
# 1. 查看 Worker stderr 日志
# 日志在 scheduler 的 stderr PIPE 中
# 或 journalctl（如果作为 systemd 服务运行）

# 2. 检查进程退出码
# returncode=-9  → SIGKILL (OOM Killer)
# returncode=-11 → SIGSEGV (段错误，CUDA 问题)
# returncode=-15 → SIGTERM (正常停止)

# 3. 检查系统日志
dmesg | grep -i "oom\|killed"
journalctl -k | grep -i "oom"

# 4. 检查 GPU 是否 hang
nvidia-smi -a | grep "Gpu"
```

### 常见原因

| 退出码 | 原因 | 解决方案 |
|--------|------|----------|
| -9 | OOM Killer | 减少并发任务，或为 Worker 设置 cgroup 内存限制 |
| -11 | CUDA 段错误 | 检查 CUDA 版本兼容性，更新 GPU 驱动 |
| -6 | SIGABRT | ModelDeploy 内部断言失败，上报 issue |

## 3. 检测无事件

### 排查步骤

```bash
# 1. Worker 日志确认推理正常
# 查看 Worker stderr 是否有 DETECT 行
journalctl -u ai-box-agent --since "5 min ago" | grep "DETECT"

# 2. 降低阈值测试
# 临时修改 preset_params.conf_threshold = 0.1

# 3. 测试模型是否能检测物体
python -c "
from modeldeploy.vision import UltralyticsDet
model = UltralyticsDet('model.onnx')
import cv2
img = cv2.imread('test.jpg')
results = model.predict(img)
print(f'Detected: {len(results)}')
for r in results:
    print(f'  {r.label_id} {r.score:.3f} {r.box}')
"

# 4. 确认回调是否到达 Web
tail -f logs/app.log | grep "callback"
```

### 常见原因

| 原因 | 说明 |
|------|------|
| conf_threshold 过高 | 默认 0.5 可能过滤掉低置信度检测，先调至 0.25 |
| 模型不匹配 | 如用 COCO 模型检测"遗留物"，模型无此概念 |
| ROI 区域错误 | `detect_region` 多边形坐标可能有效区域外 |
| 码流分辨率过低 | 子码流可能只有 640×360，小目标不可见 |

## 4. 告警未推送

### 排查步骤

```bash
# 1. 检查告警规则是否存在
curl http://localhost:8001/api/v1/alarm/rule/list?camera_id=24

# 2. 检查 notify_channels 是否包含 WS_PUSH
curl http://localhost:8001/api/v1/alarm/rule/list | jq '.data.items[] | {name, notify_channels}'

# 3. 检查 WebSocket 连接数
curl http://localhost:8001/api/v1/alarm/ws/status  # 自定义端点
# 或检查 WebSocket 日志

# 4. 检查告警记录是否创建
curl http://localhost:8001/api/v1/alarm/record/list?camera_id=24&page_size=5

# 5. 手动触发测试告警
curl -X POST http://localhost:8001/api/v1/alarm/notification/test \
  -d '{"channel": "WS_PUSH", "config": {}}'
```

### 常见原因

| 原因 | 解决方案 |
|------|----------|
| 告警规则未配置 | 在告警管理页面创建对应 camera + alarm_type 的规则 |
| interval_seconds 节流 | 等待间隔过后再次触发 |
| WebSocket 未连接 | 检查前端 WS URL 和 token |

## 5. AI 盒子离线

### 排查步骤

```bash
# 1. 检查 Agent 进程
ssh ai-box-1 "systemctl status ai-box-agent"

# 2. 检查 Agent 日志
ssh ai-box-1 "journalctl -u ai-box-agent -n 50 --no-pager"

# 3. 测试网络连通性
ssh ai-box-1 "curl -s -o /dev/null -w '%{http_code}' https://web.example.com/api/v1/algorithm/agent/heartbeat -X POST"

# 4. 检查防火墙
ssh ai-box-1 "nc -zv web.example.com 443"

# 5. 检查盒子上证书是否过期
ssh ai-box-1 "openssl s_client -connect web.example.com:443 -servername web.example.com < /dev/null 2>/dev/null | openssl x509 -noout -dates"
```

### 常见原因

| 原因 | 解决方案 |
|------|----------|
| 网络中断 | 等待自动恢复，或检查物理网络 |
| Agent 崩溃 | `systemctl restart ai-box-agent` |
| JWT 过期 | Agent 应自动重新注册，检查 config.yaml 中 secret_key 是否匹配 |
| 防火墙变动 | 确保盒子能访问 Web 主站的 443 端口 |
| DNS 解析失败 | 检查 `/etc/resolv.conf` 或改用 IP 地址 |

## 6. GPU 显存不足

### 排查

```bash
# 查看显存使用
nvidia-smi

# 查看每个 Worker 的显存占用
nvidia-smi --query-compute-apps=pid,name,used_gpu_memory --format=csv

# 设置模型使用 FP16 降低显存
# runtime_config: {"enable_fp16": true}
```

### 解决方案

| 方案 | 说明 |
|------|------|
| 启用 FP16 | 显存减半，精度损失可忽略 |
| 减少并发任务 | 降低 `max_tasks` |
| 使用子码流 | 降低输入分辨率（如 640×360 → 320×256）|
| 升级 GPU | 更换更大显存的 GPU 或增加盒子 |

## 7. 日志诊断工具

### 实时监控 Worker

```bash
# 方式1：Scheduler 日志
tail -f backend/logs/app.log | grep "inference"

# 方式2：Agent 日志
tail -f /opt/ai-box-agent/logs/agent.log

# 方式3：Worker 直出（如果配置了文件）
tail -f /opt/ai-box-agent/logs/worker_1.log

# 方式4：查看最近心跳
curl -s http://localhost:8001/api/v1/algorithm/box/list?page_size=100 | jq '.data.items[] | {name, status, last_heartbeat, running_tasks}'
```

### 性能分析

```bash
# 推理延迟分布
curl -s http://localhost:8001/api/v1/algorithm/task/1/inference-status | jq '.data.inference_latency_ms'

# I/O 分析
iostat -x 1

# GPU 分析
nvidia-smi dmon -s pucvmet -d 1
```
