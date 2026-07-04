# 模型训练模块设计

## 概述

在 AIStation 标注模块基础上，构建工业级模型训练流水线。训练框架支持 PaddleX 和 Ultralytics（YOLO），以 Docker 镜像形式运行在本地 GPU 服务器上。训练完成后的模型进入模型仓库（带版本管理），可通过评估模块验证指标，并可部署到现有的推理流水线中。

## 模块结构

独立插件 `module_train`，自动发现路由，不耦合现有代码。

```
backend/app/plugin/module_train/
  plugin.toml          # 插件元数据
  __init__.py
  controller.py        # REST 接口
  service.py           # 业务逻辑
  model.py             # 数据模型
  schema.py            # Pydantic 请求/响应
  scheduler.py         # 训练任务调度器
  docker_utils.py      # Docker 镜像管理
  ws.py                # WebSocket 日志推送

frontend/src/views/module_train/
  repo/index.vue       # 模型仓库
  task/index.vue       # 训练任务列表 + 创建
  task/detail.vue      # 训练详情（实时日志）
  eval/index.vue       # 模型评估
```

## 数据模型

### train_models（模型仓库）

| 字段 | 类型 | 说明 |
|------|------|------|
| id | int PK | |
| name | str(128) | 模型名称 |
| framework | str(32) | PaddleX / Ultralytics |
| version | str(32) | 语义版本号 |
| description | text | 描述 |
| storage_path | str(512) | RustFS 存储路径 |
| format | str(32) | 导出格式（ONNX / Paddle / TorchScript） |
| metrics | JSONB | 最新评估指标 |
| annotation_dataset_id | int FK | 来源标注数据集 |
| status | str(16) | draft / released / archived |
| created_id | int FK | |
| created_time | datetime | |

同 `name` 下 `version` 递增，支持版本对比。

### train_tasks（训练任务）

| 字段 | 类型 | 说明 |
|------|------|------|
| id | int PK | |
| name | str(128) | 任务名称 |
| framework | str(32) | PaddleX / Ultralytics |
| dataset_id | int FK | 标注数据集 ID |
| model_repo_id | int FK nullable | 产出模型 ID |
| base_model_id | int FK nullable | 基础模型 ID（迁移学习） |
| docker_image | str(256) | 使用的镜像 |
| hyperparams | JSONB | 超参数配置 |
| status | str(16) | pending / running / success / failed / cancelled |
| progress | int | 0-100 |
| error_log | text | 失败日志 |
| started_at | datetime | |
| finished_at | datetime | |
| created_id | int FK | |

### train_evals（模型评估）

| 字段 | 类型 | 说明 |
|------|------|------|
| id | int PK | |
| model_repo_id | int FK | 评估的模型版本 |
| eval_dataset_id | int FK | 评估数据集 |
| metrics | JSONB | 详细指标 |
| status | str(16) | pending / running / success / failed |
| log | text | 评估日志 |
| created_id | int FK | |

## 核心流转

### 训练生命周期

```
PENDING → RUNNING → SUCCESS
                  → FAILED
                  → CANCELLED
```

1. 用户创建训练任务（选择数据集、框架、超参数）
2. `POST /train/task/create` → 写入 `train_tasks`（status=pending）
3. 调度器 `scheduler.py` 轮询 `PENDING` 任务（每秒）
4. 调度器执行 `docker run --gpus all ... PaddleX/Ultralytics 镜像`
5. 调度器异步读取容器 stdout，每行通过 WebSocket 推前端
6. 训练完成 → 导出模型 → 上传 RustFS → 写入 `train_models`
7. 更新 `train_tasks.status = success`

### 调度器设计

复用推理模块 `scheduler.py` 的模式：

- 单例 asyncio 任务，后台常驻
- 维护 `_running_tasks: dict[int, asyncio.subprocess.Process]`
- 扫描 `PENDING` 任务并启动
- 并行限制：默认同时运行 1 个训练（可通过配置调整）
- 健康检查：`docker inspect` 检查容器状态
- 停止训练：`process.terminate()` → `docker rm -f`
- 自动清理：进程退出后更新状态，清理资源

### Docker 管理

`docker_utils.py` 负责：

- 首次拉取镜像（`docker pull paddlecloud/paddlex:...`）
- 构建运行命令（挂载数据集、配置 GPU、环境变量）
- 停止/删除容器
- 清理临时目录

示例运行命令：

```
docker run --gpus all --rm \
  -v /datasets/xxx:/data \
  -v /output/xxx:/output \
  -e EPOCHS=100 -e BATCH=16 \
  paddlecloud/paddlex:3.0 \
  paddlex --train /data --output /output
```

### 数据集导出

训练前自动将标注数据集导出为目标框架的格式：

- **Ultralytics**: 导出为 `images/` + `labels/` 目录，YOLO 格式 `.txt`
- **PaddleX**: 导出为 PaddleX 标准格式（XML/JSON + 图像）

### 日志流 WebSocket

- 前端连接 `ws://host/api/v1/ws/train/logs?task_id={id}`
- 调度器每读取一行 stdout，推送给该 task_id 的所有 WS 连接
- 前端用 `AnsiUp` 库渲染彩色终端日志

### 模型导出

训练完成后支持的导出格式：

- Ultralytics: ONNX / TorchScript / Paddle 格式
- PaddleX: ONNX / Paddle Inference 格式
- 导出后上传到 RustFS（S3），路径存入 `train_models.storage_path`

## 前端页面

### 模型仓库 `repo/index.vue`

```
表格：模型名 | 框架 | 最新版本 | 最新指标(mAP) | 操作
点击行展开版本列表：v1 / v2 / v3 指标对比
操作：
  - 创建训练（基于此模型继续训练）
  - 评估（选择数据集跑评估）
  - 部署（注册到 video_algorithms）
  - 导出（选择格式下载）
```

### 训练任务 `task/index.vue`

新建弹窗：

```
选择数据集 [下拉]
选择框架   [PaddleX / Ultralytics]
基础模型   [可选]
超参数配置  [动态表单 / JSON 编辑器]
  epochs / batch / lr / optimizer / ...
  （不同框架参数不同，动态渲染）
GPU 设备   [下拉选择 device_id]
```

任务列表：

```
表格：任务名 | 框架 | 数据集 | 状态 | 进度 | 操作
运行中：点击进入详情页（实时日志）
已完成：操作有「评估」「导出」「查看模型」
```

训练详情页 `task/detail.vue`：

```
实时日志区域（终端风格，ANSI 彩色）
[停止训练] [导出模型] 按钮
训练结束后显示摘要指标
```

### 模型评估 `eval/index.vue`

- 选择模型版本 + 选择评估数据集
- 创建评估任务 → 调度器跑 eval
- 显示 mAP@0.5 / mAP@0.5:0.95 / Precision / Recall / F1
- 支持两个版本指标对比（雷达图或表格）

### 导航结构

```
数据标注
├── 数据集管理
├── 标注任务
├── 工作量统计
└── 模型训练（新）
    ├── 模型仓库
    ├── 训练任务
    └── 模型评估
```

## 扩展点

### 远程 GPU 方案（未来）

当需要远程 GPU 服务器时：

1. 远程机器部署轻量 Agent（docker client + 定时轮询）
2. Agent 通过 Redis pub/sub 或 HTTP 长轮询获取任务
3. 拉取镜像 → 运行训练 → 上报日志和状态
4. 主节点 scheduler 只需将任务标记为 `remote_pending`，由 Agent 认领

此方案为扩展设计，不包含在当前实现范围内。

### 新的训练框架接入

只需新增：
1. Docker 镜像配置
2. 数据集导出器
3. 超参模板配置
4. 模型导出器

即可支持新的训练框架。

## 当前未包含的功能

- **AutoML / 超参搜索** — 当前超参由用户手动配置，后续可增加自动搜索
- **分布式训练** — 单机单卡/多卡，不支持多机
- **模型量化** — 导出时不做量化，保留 FP32
- **数据集版本管理** — 训练时使用标注数据集的当前快照
- **训练资源配额** — 用户级 GPU 时间/并发限制（不在 v1 范围）
