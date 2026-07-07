# 模型评估（验证）与预测测试模块设计

## 目标

为 Ultralytics/PaddleX 模型提供完整的评估（val）和预测（predict）功能，复用现有的训练 Docker 基础设施。

## 架构概览

评估和预测作为独立子模块，位于 `module_train` 插件内。遵循现有的训练任务模式：

```
controller → service → scheduler/executor → docker_utils
                               ↕
                            ws.py（日志广播）
```

每个模块有独立的列表页、详情页、调度器/执行器。

## 数据模型

### TrainEval（增强现有模型 `model.py:54`）

```python
# 新增字段
model_id: int | None           # 具体模型版本（可选，默认为 model_repo_id 下最新模型）
hyperparams: JSONB | None      # val 参数：imgsz, conf, iou, batch, device 等
started_at: DateTime | None
finished_at: DateTime | None
eval_dataset_id: int           # 已有
model_repo_id: int             # 已有
metrics: JSONB | None          # 已有，val 输出的精度指标
status: TrainStatus enum       # 已有
log: Text | None               # 已有
```

### TrainPredict（新建模型）

```python
class TrainPredict(ModelMixin, UserMixin, MappedBase):
    __tablename__ = "train_predicts"

    model_repo_id: int           # 模型仓库 ID
    model_id: int                # 具体模型版本 ID
    framework: TrainFramework    # ultralytics / paddlex
    source_type: str             # 'dataset' | 'upload'
    source_dataset_id: int | None  # 源数据集 ID
    source_images: JSONB | None     # 上传图片的原始 URL 列表
    result_images: JSONB | None     # 预测结果图片 URL 列表
    result_zip_path: str | None     # RustFS 上的结果 ZIP 路径
    hyperparams: JSONB | None       # predict 参数：conf, iou, imgsz, device, save_txt, save_conf
    status: TrainStatus enum
    started_at: DateTime | None
    finished_at: DateTime | None
    log: Text | None
```

## 后端模块

### 1. 评估调度器 `eval_scheduler.py`

类比 `scheduler.py`，但更轻量：

- `eval_running_tasks: dict[int, dict]` — 跟踪运行中的评估
- `start_evaluation(task_id)` — 设置状态为 RUNNING，启动异步任务
- `_execute_evaluation(task_id)`:
  1. `pull_image()` (可跳过如果已拉取)
  2. `export_dataset()` — 导评估数据集到 YOLO 格式
  3. Mount dataset 到 `/data`，model 权重到 `/output`
  4. `run_container()` — 执行 `yolo val model=/output/model.pt data=/data/dataset.yaml`
  5. `follow_container_logs()` — 实时日志广播 + 解析 metrics
  6. `wait_container()` → 获取 exit code
  7. 成功：解析 stdout 中的 val metrics（precision, recall, mAP@50, mAP@50:95），存入 `TrainEval.metrics`
  8. 失败：捕获错误日志
  9. `remove_container()` — 清理
- `stop_evaluation(task_id)` — 设置取消标志，停止容器

### 2. 预测执行器 `predict_executor.py`

- `predict_running_tasks: dict[int, dict]`
- `start_prediction(task_id)`:
  1. 准备 source：
     - `source_type == 'dataset'`：调用 `exporter.export_dataset()` 仅导出图片（不生成 yaml）
     - `source_type == 'upload'`：从 RustFS 下载上传的图片到临时目录
  2. `run_container()` — `yolo predict model=/output/model.pt source=/data/images save_txt=true save_conf=true`
  3. `follow_container_logs()` — 实时日志
  4. 收集结果：从容器输出目录 `runs/detect/predict/` 读取结果图片
  5. 上传结果 ZIP 到 RustFS
  6. 更新 `TrainPredict.result_images` / `result_zip_path`
- `stop_prediction(task_id)` — 停止容器

### 3. API 端点

**评估**（在 `controller.py` 中）：

| 端点 | 方法 | 说明 |
|------|------|------|
| `/eval/create` | POST | 已有，增强：支持 `model_id`, `hyperparams` |
| `/eval/list` | GET | 已有，增强：支持按 `model_repo_id` 过滤 |
| `/eval/{id}/detail` | GET | 新增：返回 eval 详情 + metrics |
| `/eval/{id}/start` | POST | 新增：开始执行评估 |
| `/eval/{id}/stop` | POST | 新增：停止评估 |
| `/eval/delete` | DELETE | 已有 |
| `/eval/list` | GET | 已有 |

**预测**（在 `controller.py` 中）：

| 端点 | 方法 | 说明 |
|------|------|------|
| `/predict/create` | POST | 新增：创建预测任务 |
| `/predict/list` | GET | 新增：预测任务列表 |
| `/predict/{id}/detail` | GET | 新增：详情含结果图片 URL 列表 |
| `/predict/{id}/start` | POST | 新增：开始执行 |
| `/predict/{id}/stop` | POST | 新增：停止 |
| `/predict/delete` | DELETE | 新增 |
| `/predict/upload` | POST | 新增：上传预测用图片 |

### 4. WebSocket 日志广播

评估和预测复用 `ws.py` 的 `broadcast_log(task_id, line)` 机制。需要新增：
- `ws.py` 新增 WebSocket 端点 `/ws/eval/logs?task_id=N` 和 `/ws/predict/logs?task_id=N`
- 或在现有 `/ws/train/logs` 基础上增加 type 参数

推荐：在 `ws.py` 中增加 `broadcast_eval_log` 和 `broadcast_predict_log`，分别维护独立的 client 字典。

### 5. 权限

在 `init_app.py` 中新增：

```
module_train:predict:query   预测查询
module_train:predict:create  预测创建
module_train:predict:delete  预测删除
```

评估的权限已存在：`module_train:eval:query/create/delete`。

### 6. 菜单与路由

新增前端路由：
- `/train/eval/:id` → `module_train/eval/detail`（隐藏菜单）
- `/train/predict` → `module_train/predict/index`
- `/train/predict/:id` → `module_train/predict/detail`（隐藏菜单）

后端注册菜单条目。

## 前端页面

### 1. 评估列表页 `eval/index.vue`（增强现有）

**改动**：
- 搜索：按模型名、数据集、状态筛选
- 创建评估弹窗：选择模型仓库 → 选择具体模型版本 → 选择评估数据集 → 配置超参（imgsz, batch, conf, iou）
- 操作按钮：开始评估、查看详情、删除
- 状态标签 + 进度指示
- `v-hasPerm` 控制按钮显隐

### 2. 评估详情页 `eval/detail.vue`（新建）

类比 `task/detail.vue`：
- 顶部：模型名、数据集名、状态标签、框架标签
- 信息卡：评估参数、时间信息
- 指标卡片（若已有结果）：
  - Precision, Recall, mAP@50, mAP@50:95
  - 如果是每个类别的指标，以表格展示
- 日志区域：500px 黑色背景，WebSocket 实时流，支持自动滚动/清空

### 3. 预测列表页 `predict/index.vue`（新建）

标准 CRUD 列表页：
- 创建预测弹窗：选择模型仓库 → 选择版本 → 选择图片来源（数据集/上传）
- 若选数据集：下拉选择已导出的数据集
- 若选上传：文件上传组件（支持多张图片）
- 配置超参：conf, iou, imgsz
- 表格列：模型名、来源类型、状态、创建时间、操作
- 操作：开始预测、查看详情、删除、下载结果

### 4. 预测详情页 `predict/detail.vue`（新建）

- 顶部信息卡：模型名、框架、状态
- 参数卡：conf, iou, imgsz 等
- 结果网格：4 列网格缩略图，点击放大预览（复用 `el-image` 的预览功能）
- 下载按钮：ZIP 打包下载
- 日志区域：同训练/评估

## Docker 复用

`docker_utils.py` 提供所有 Docker 原语：
- `pull_image(image)` — 拉取镜像
- `run_container(image, cmd, volumes, gpu_id, env)` — 运行容器
- `follow_container_logs(container_id)` — 实时日志
- `wait_container(container_id)` — 等待退出
- `stop_container(container_id)` — 停止
- `remove_container(container_id)` — 清理

评估和预测只需构建不同的 cmd 和 volumes 即可。

### Volume 挂载约定

训练：
```
{data_dir} → /data（数据集）
{export_dir} → /output（输出模型）
```

评估：
```
{data_dir} → /data（数据集）
{model_dir} → /model（模型权重）
{output_dir} → /output（输出）
```

预测：
```
{source_dir} → /data（源图片）
{model_dir} → /model（模型权重）
{output_dir} → /output（输出结果）
```

## 执行计划

按以下顺序实现：

1. **数据模型** — 新增 TrainPredict，增强 TrainEval（加字段）
2. **Schema** — 新增 PredictCreateSchema，增强 EvalCreateSchema
3. **Service** — 新增 predict_service 方法，增强 eval_service
4. **Controller** — 新增 /predict/* 端点，增强 /eval/*
5. **Scheduler** — 新增 eval_scheduler.py 和 predict_executor.py
6. **WebSocket** — 增强 ws.py 支持 eval/predict 日志广播
7. **Frontend API** — 新增 predict API 调用
8. **Frontend Pages** — 增强 eval 页，新建 predict 页
9. **权限/菜单** — 注册预测权限和菜单
