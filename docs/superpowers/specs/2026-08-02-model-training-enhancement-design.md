# 模型训练增强（ultralytics 完善 + PyTorch OCR 全流程）设计

> 创建日期：2026-08-02

## 背景与目标

AIStation 模型训练模块当前支持 `ultralytics` 与 `paddlex` 两个框架。经审查发现：

1. **ultralytics 训练参数不完整**：前端已收集 `optimizer/imgsz/workers/device` 等 8 个参数，但后端 `_build_ultralytics_cmd` 只把 `epochs/batch/lr0/model` 拼进 `yolo train` 命令，其余参数全部丢失。
2. **PaddleX 臃肿**：`paddlecloud/paddlex:3.0` 镜像 22.8GB，覆盖几十种模型。实际只需要两个能力：
   - **多标签分类** —— 经确认 Ultralytics 分类模式原生支持 `multi_label=True`（BCE loss），无需 PaddleX。
   - **OCR 全流程（det 检测 + rec 识别）** —— 需要真正的 OCR 能力，Ultralytics 不覆盖。
3. PaddleX 历史数据均为测试数据，可彻底删除。

目标：
- **子项目 1**：完善 ultralytics 训练参数（白名单映射 + 高级参数折叠 UI）+ 多标签分类支持 + 彻底移除 PaddleX。
- **子项目 2**：新建 PyTorch OCR 全流程（PP-OCRv6 det+rec 对齐），训练/评估/推理全部跑在独立 Docker 容器，与后端解耦，行为与 ultralytics 一致。

## 关键技术决策（已确认）

| 决策点 | 结论 |
|---|---|
| 子项目划分 | 2 个独立子项目，各含独立 spec+plan |
| ultralytics 参数方案 | YOLO 超参白名单映射 + 前端"基础/高级"两级折叠 |
| 多标签分类 | 用 ultralytics `multi_label=True`，不新建框架 |
| PaddleX 处理 | 彻底移除：代码 + 历史测试数据 + 前端入口；枚举值 `PADDLEX` 保留兼容 |
| OCR 运行环境 | 独立 PyTorch Docker 镜像（`aistation-ocr:latest`，目标 <3GB） |
| OCR 模型 | PP-OCRv6（Tiny/Small/Medium 三档），det+rec 完全对齐 |
| OCR 实现方式 | 参考 `frotms/PaddleOCR2Pytorch`（MIT，1198 stars）但自研代码 |
| 权重来源 | 官方预训练 + 用户训练产物，两者都支持 Paddle→PyTorch 转换 |
| 对齐粒度 | 架构对齐 + 权重复用（非严格逐层数值一致） |
| 任务表 | 复用 `TrainTask` 表，新增 `pytorch-ocr-det`/`pytorch-ocr-rec` 枚举值 |

---

## 子项目 1：ultralytics 训练增强

### 组件 A：后端白名单映射（`backend/app/plugin/module_train/scheduler.py`）

新增模块级常量 `_ULTRALYTICS_HP`，映射 hp dict key → (yolo CLI flag, 默认值, 校验 lambda)：

| hp key | yolo CLI | 默认 | 校验 |
|---|---|---|---|
| `model` | `model=` | `yolo11n.pt` | — |
| `epochs` | `epochs=` | `100` | 1..1000 |
| `batch` | `batch=` | `16` | 1..512 |
| `imgsz` | `imgsz=` | `640` | 32..4096 |
| `lr0` | `lr0=` | `0.01` | >0 |
| `lrf` | `lrf=` | `0.01` | 0..1 |
| `momentum` | `momentum=` | `0.937` | 0..1 |
| `weight_decay` | `weight_decay=` | `0.0005` | >=0 |
| `optimizer` | `optimizer=` | `AdamW` | AdamW/SGD/Adam/Adamax/NAdam |
| `patience` | `patience=` | `100` | >=0 |
| `workers` | `workers=` | `8` | 0..32 |
| `device` | `device=` | `0` | — |
| `seed` | `seed=` | `0` | — |
| `hsv_h` | `hsv_h=` | `0.015` | 0..1 |
| `hsv_s` | `hsv_s=` | `0.7` | 0..1 |
| `hsv_v` | `hsv_v=` | `0.4` | 0..1 |
| `fliplr` | `fliplr=` | `0.5` | 0..1 |
| `flipud` | `flipud=` | `0.0` | 0..1 |
| `mosaic` | `mosaic=` | `1.0` | 0..1 |
| `mixup` | `mixup=` | `0.0` | 0..1 |

改造 `_build_ultralytics_cmd(hp, data_dir, export_dir, task_type)`：
- 遍历 `_ULTRALYTICS_HP`，仅当 key 在 hp dict 且值非 None 时拼入命令
- `model` 特殊处理：`/models/` 前缀 + `rotated_detection` 自动 `-obb.pt` 后缀（保留现有逻辑）
- 校验失败的键跳过 + `log.warning`（不中断训练）；未知键忽略
- `train_ratio` 不进 CLI（数据导出已用）

### 组件 B：前端超参表单（`frontend/web/src/views/module_train/task/index.vue`）

- 基础参数区（现有）：model / epochs / batch / lr0 / imgsz / optimizer / device
- 新增"高级参数"折叠区（`el-collapse`）：lrf / momentum / weight_decay / patience / workers / seed / hsv_h / hsv_s / hsv_v / fliplr / flipud / mosaic / mixup
- `hpForm` 默认值对齐白名单表；`buildHyperparams()` 返回整个 hpForm（`train_ratio` 保留 /100 换算）
- `dockerCmdPreview` 用同一白名单生成预览命令（保证与真实命令一致）

### 组件 C：多标签分类支持

- **数据来源确认**：标注任务 `classification_mode` 字段已有 `single`/`multi` 值（前端工作台已支持），`exporter._export_yolo_cls` 读取 `annotation_task.classification_mode` 判断导出格式
- `exporter.py::_export_yolo_cls` 改造：
  - `single` 模式：保持现有"单标签目录结构"（`train/<cls>/img.jpg`）
  - `multi` 模式：改为"多标签 label 文件格式"（每行一个 class id，支持多标签），目录结构 `train/`（不分 class 子目录）
- 前端分类任务超参表单增加 `multi_label: true` 开关（仅 `task_type=classification` 且 `classification_mode=multi` 时显示）
- `_build_ultralytics_cmd` 对分类任务且 `multi_label=true` 时追加 `multi_label=True`
- 分类评估走 YOLO cls 的 val（top-k accuracy / mAP）

### 组件 D：PaddleX 彻底移除

**后端：**
- `scheduler.py`：删 `_build_paddlex_cmd`；`_build_cmd` 删 PADDLEX 分支
- `exporter.py`：删 `_export_paddlex`（通用 paddlex 检测导出）；**保留** `_export_paddle_ocr`/`_export_paddle_mlcls`（子项目 2 的 PyTorch 版导出器完成后替换再删）
- `model.py`：`TrainFramework.PADDLEX` 枚举值保留（历史数据兼容），但 `create_task` 校验拒绝新建 paddlex 任务
- `service.py`：`create_task` 对 `framework == paddlex` 抛错"PaddleX 已下线"

**前端：**
- `task/index.vue` framework 下拉移除 paddlex，仅剩 ultralytics（PyTorch OCR 后续加入）

**数据清理：**
- 清空 DB 中 `framework='paddlex'` 的 `train_models` / `train_tasks` / `train_evals` / `train_predicts` / `train_deploys`（均为测试数据）
- 提供一次性清理脚本或迁移（需确认表中是否有非 paddlex 关联）

### 测试（子项目 1）

- 后端单测：`_build_ultralytics_cmd` 参数映射 / 缺省不出现 / 校验失败跳过 / OBB 后缀 / 分类 multi_label
- 数据导出单测：多标签 label 文件格式
- 前端：type-check + build
- paddlex 清理验证

---

## 子项目 2：PyTorch OCR 全流程（PP-OCRv6 对齐）

### 架构总览

```
标注系统 (OCR 任务: polygon + text)
  → exporter (_export_pytorch_ocr: det/rec 数据集导出)
  → aistation-ocr Docker 容器 (train-det / train-rec / eval / predict)
  → 模型产物 (best.pt) → RustFS → 部署推理服务
```

与 ultralytics 完全同构：后端只负责数据导出、命令构造、日志跟随、产物收集；训练/评估/推理全在容器内。复用 `TaskExecutor` + `docker_utils`。

### 组件 A：模型实现（自研 PyTorch，参考 frotms/PaddleOCR2Pytorch）

新包 `backend/pytorch_ocr/`（vendored 进 Docker 镜像）：

**det 检测：**
- 骨干：`PPLCNetV4`（tiny/small/medium 三档，`depth_mult` 控制），参考 `rec_lcnetv4.py`
- Neck：`RepLKFPN`
- Head：`DBHead`（可微分二值化，输出概率图 + 阈值图）
- 后处理：DB 二值化 → 连通域 → `cv2.minAreaRect` 最小外接矩形

**rec 识别：**
- 骨干：`PPLCNetV4`
- Neck：`LightSVTR`（encoder），参考 `rec_svtrnet.py`
- Head：`CTCHead`
- 后处理：CTC 解码（贪心 / beam search），字符集含中英文 + 特殊字符

### 组件 B：权重转换工具（`pytorch_ocr/converter/`）

参考 `ppocr_v6_det_converter.py` / `ppocr_v6_rec_converter.py`：
- 输入：Paddle 动态图权重（`.pdparams`）或官方预训练下载
- 映射：Paddle 参数名 → PyTorch 参数名（`conv2d_0.w_0` → `conv.weight` 等）
- 输出：`.pt`（PyTorch state_dict），存 RustFS
- 校验：转换后加载 + 逐层输出对比（参考 frotms 校验方法）
- 运行环境：**Paddle 环境** —— 用 `paddlex:latest` 容器跑转换脚本，输出 `.pt`（paddlex 镜像保留到转换工具完成）
- 支持官方预训练权重 + 用户训练产物两种来源

### 组件 C：数据导出（`exporter.py` 扩展）

新增独立函数 `_export_pytorch_ocr(dataset_id, task_id, images, output_dir, annotation_task_id)`（PyTorch OCR 专用，与现有 `_export_paddle_ocr` 独立）：
- **det**：`det/` 目录 + `det_gt.txt`（每行：图片路径 + 四角点坐标）
- **rec**：`rec/` 目录，裁剪文字行（透视变换）+ `rec_gt.txt`（图片路径 + 文本）
- 裁剪/透视变换复用现有 `_export_paddle_ocr` 的 cv2/PIL 逻辑（无 Paddle 依赖）
- 现有 `_export_paddle_ocr`/`_export_paddle_mlcls` 在子项目 2 的 PyTorch 版训练链路就绪后删除（见组件 H）

### 组件 D：训练循环（`pytorch_ocr/trainer/`）

**det 训练：**
- loss：DB loss（prob loss + thresh loss + binary loss）
- 优化器：AdamW + CosineAnnealingLR
- 评估：Hmean（IoU 阈值下 precision/recall/F1）

**rec 训练：**
- loss：CTC loss（`torch.nn.CTCLoss`）
- 优化器：AdamW + CosineAnnealingLR
- 评估：字符级/词级准确率

### 组件 E：推理管线（`pytorch_ocr/inference/`）

`ocr_pipeline(image) -> [{text, confidence, box}]`：
1. det 检测文字框
2. 逐框透视矫正 → 裁剪
3. rec 识别文本
4. 聚合返回

### 组件 F：Docker 镜像（`docker/ocr-train/Dockerfile`）

- Base：`pytorch/pytorch:2.4.0-cuda12.1-cudnn9-runtime`
- 依赖：`opencv-python-headless` + 自研 `pytorch_ocr` 包（`COPY` 进镜像）
- 入口：`python -m pytorch_ocr.cli`，子命令 `train-det` / `train-rec` / `eval-det` / `eval-rec` / `predict`
- 命令示例：`python -m pytorch_ocr.cli train-det --data /data --config /config.yaml --output /output --device 0`
- 目标体积 <3GB

### 组件 G：执行器集成（复用 TaskExecutor）

新增 `backend/app/plugin/module_train/ocr_executor.py`：

```python
class OCRDetExecutor(TaskExecutor):
    name = "ocr_det"
    status_enum = TrainStatus
    model_class = TrainTask  # 复用
    _concurrency = 1

    async def _execute(self, task_id):
        # 1. export det dataset → /data
        # 2. run_container(aistation-ocr:latest, ["python","-m","pytorch_ocr.cli","train-det",...])
        # 3. follow_logs + parse epoch/hmean
        # 4. collect best.pt → RustFS → export_model

class OCRRecExecutor(TaskExecutor):
    # 同构，train-rec
```

评估/推理复用 `EvalExecutor`/`PredictExecutor` 容器模式（framework 分支）。

### 组件 H：框架接入

- `TrainFramework` 枚举新增 `PYTORCH_OCR_DET = "pytorch-ocr-det"`、`PYTORCH_OCR_REC = "pytorch-ocr-rec"`
- `TrainService.create_task`：这两个框架的 `docker_image` 固定 `aistation-ocr:latest`
- `_build_cmd` 按框架分发到 OCR 命令构造
- `exporter._export_core` 增加两个框架分支
- `export_model` 产物查找：OCR 输出 `best.pt`（与 ultralytics 路径一致）

### 组件 I：部署集成

OCR 推理服务（复用 `deploy_executor` 模式）：
- server 脚本加载 det + rec 两个 `.pt`，`/predict`（传图 → `[{text, confidence, box}]`）
- 容器 `aistation-ocr:latest` 跑 uvicorn server，复用端口预留 / 健康检查 / 孤儿恢复

### 测试（子项目 2）

| 层 | 测试 |
|---|---|
| 单元 | `pytorch_ocr/modeling` 各模块前向/形状；converter 参数名映射；`_build_cmd` OCR 分支；数据导出格式 |
| 转换校验 | 转换 PP-OCRv6 官方权重 → 加载 + 逐层输出与参考对比 |
| 集成 | pytest 全量回归（OCR 数据导出 + 命令构造，不跑真实容器） |
| 端到端 | 真实 Docker：det 训练小数据 → rec 训练 → 推理，人工验收 |

---

## 实施顺序

1. **子项目 1**（独立 spec + plan，先做）：
   - ultralytics 白名单映射 + 前端高级参数
   - 多标签分类支持
   - PaddleX 彻底移除（代码 + 数据清理 + 前端）
2. **子项目 2**（独立 spec + plan）：
   - `pytorch_ocr` 包（modeling / converter / trainer / inference / cli）
   - Docker 镜像
   - 数据导出 / 命令构造 / executor 集成
   - 权重转换 + 校验
   - 部署服务

每个子项目完成后独立测试 + 人工验收。

## 风险与说明

- **Paddle→PyTorch 权重转换**是 OCR 子项目最大风险：Paddle 参数名与 PyTorch 映射复杂（`rec_lcnetv4` 含 RepLK 结构）。缓解：参考 frotms 已实现且验证过的 converter；用官方权重做逐层输出对比校验。
- **paddlex 镜像的保留**：`paddlex:latest` 镜像（22.8GB）仅在权重转换阶段使用（跑 Paddle 环境转换脚本），转换工具完成后可删除；不影响训练镜像 `aistation-ocr:latest` 的独立性。
- **OCR 训练效果**依赖训练循环正确复刻 DB loss / CTC loss。缓解：用公开小数据集（如 ICDAR2015 子集）做端到端 sanity check。
- **PaddleX 移除的先后**：`exporter.py` 的 `_export_paddle_ocr`/`_export_paddle_mlcls` 推迟到子项目 2 的 PyTorch 版就绪后删除，避免空窗期功能缺失。
- **多标签数据导出**需要与现有标注系统 `classification_mode` 字段核对（确认多标签标注的存储格式）。
- **OCR 检测的框格式**需与标注系统 polygon 存储对齐（现有 `_export_paddle_ocr` 已处理 polygon→四角点转换，可复用）。
