# Phase 2：模型训练 + 模型评估 设计

> 创建日期：2026-09-12
> 状态：已确认（用户认可范围与关键决策）
> 所属程序：`2026-09-11-pipeline-optimization-program-design.md`

## 背景

模型训练（`backend/app/plugin/module_train/`）与评估是端到端链路的中段。审查发现：定时训练必失败、重启后容器变孤儿/产物丢失、评估只评 20% 随机数据不可复现、各框架指标解析不全、评估关联错模型 id、模型仓库两套数据模型并存等。这些问题会直接导致"训练看着成功但没用"或"评估结果不可信"。

## 范围

**做：**
1. 定时训练执行器修复 + `schedule/list` 序列化 500。
2. 训练执行器：重启恢复（按容器 label 重连）、取消、删除运行中任务、并发/资源、`base_model_id` 接线。
3. 指标：各框架（ultralytics det/seg/obb/pose/cls、PaddleX det/rec）指标解析；单一最优指标策略；产物为空不标成功。
4. 评估：全量且确定性评估、模型规格推断、模型 id 语义修复、按框架展示指标、重启清状态。
5. 模型仓库/版本/导出/下载的可观察一致性。

**不做（归 Phase 5）：** 定时训练前端 UI、模型仓库分组/版本 UI 等界面补全。

## 关键决策（已确认）

| 决策点 | 结论 |
|---|---|
| 重启恢复 | 按 Docker label 重连存活容器（train/predict/deploy）；重连失败超时后标 FAILED 并清理；eval 重启标记 FAILED 可重跑 |
| 定时训练 | Phase 2 只修执行器/scheduler bug 与 `schedule/list` 500；UI 归 Phase 5 |
| 评估数据集 | 全量、确定性导出（不随机切分），保证可复现 |
| 评估模型规格 | 从模型行/训练任务推断 `mode`+`model_size`，不依赖评估 hyperparams |
| 最优指标 | 单一 `best_metric` 策略，按框架选主指标（det: hmean/mAP、rec: acc、cls: top1） |
| 模型仓库 | 不做全量重构；统一 UI 用到的路径与模型 id 语义，修导出/下载/编辑不一致 |

## 组件设计

### A. 训练调度与执行器
- `scheduler.py` 的定时任务构造补齐 `base_model_id`（及 scheduler mock 对象与 `create_task` 契约一致）；失败也推进 `last_run_at`，避免 30s 重刷。
- `schedule_service.list` 返回可序列化 dict（去掉 `_sa_instance_state`）。
- `TaskExecutor`：容器统一打 label（task_id + 类型）；启动/恢复时按 label 查找存活容器并重连日志跟随与产物收集；`stop`/`delete` 对运行中任务先停容器；`delete` 拒绝或先停运行中任务。
- 并发：训练执行器共享一个 GPU 信号量或全局并发上限，避免 3 作业抢卡。
- `base_model_id`：`create_task` 读取并作为预训练/base 权重传入命令构造（各框架按支持度实现；不支持时明确忽略并记录）。

### B. 指标
- 统一 `_parse_*` 产出 `{epoch, ..., best?}`；`best_metric(metrics_log, framework, task_type)` 单点决定主指标。
- ultralytics cls 解析 top1/top5；PaddleX det 解析 hmean、rec 解析 acc。
- `export_model` 无产物时返回空且调用方标 FAILED。

### C. 评估链路
- 评估导出走确定性全量路径（新增 `for_eval`/复用 `for_training=False` 但固定 split=1.0，或专用导出）。
- 从模型行/训练任务推断 `mode`/`model_size`。
- 修复 `eval/index.vue` 创建评估传 `model_repo_id`、`eval/detail.vue` 导出绑定 id。
- 评估详情按 `framework`/`task_type` 渲染指标；重启清空旧 `metrics`/`error_log`/`log` 并推进进度。
- YOLO cls 评估解析 top-k。

### D. 仓库/导出/下载
- 统一 `TrainTask.model_repo_id`/`TrainModel.id` 语义（版本 id）并在 UI 与后端命名一致。
- 导出产物落库并可按 id 下载；`download_model` 的文件与 format 一致。
- 模型下拉分页（eval/predict/deploy）取全量或分页加载。

## 验收标准

- det/seg/OBB/pose/cls/OCR-det/OCR-rec 均能训练出产物；无产物不标成功。
- 重启后可恢复（重连）或正确回收；取消/删除不留孤儿容器。
- 评估全量可复现，指标按框架正确显示；关联模型 id 正确；导出可下载。
- 均有 pytest 覆盖；训练详情/评估页有 Playwright 冒烟。

## 实施顺序（拆多个 plan）
1. **2A 训练调度与执行器**（恢复/取消/删除/并发/base_model）
2. **2B 指标解析与训练详情**
3. **2C 评估链路**
4. **2D 仓库/导出/下载一致性**
