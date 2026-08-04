# pytorch-ocr 集成指南

> 本文档说明如何将 `pytorch-ocr`（AIStation 自研 PyTorch OCR 库，PP-OCRv6 架构对齐）集成到 AIStation 平台：从数据集标注模板、训练/评估/预测，到模型部署的完整流程。

## 1. 架构总览

```
┌─────────────────────────────────────────────────────────────┐
│                     AIStation 后端 (FastAPI)                  │
│  module_train                                                │
│  ├── TrainFramework.PYTORCH_OCR_DET  ("pytorch-ocr-det")     │
│  ├── TrainFramework.PYTORCH_OCR_REC  ("pytorch-ocr-rec")     │
│  ├── OCRDetExecutor / OCRRecExecutor (TaskExecutor 子类)      │
│  └── exporter._export_pytorch_ocr (det/rec 数据集导出)        │
└──────────────┬──────────────────────────────┬────────────────┘
               │ Docker                       │
               ▼                              ▼
┌──────────────────────┐         ┌──────────────────────┐
│  aistation-ocr:latest │         │   RustFS (模型存储)    │
│  ────────────────────  │         │  train/models/...    │
│  pip install pytorch-ocr│         └──────────────────────┘
│  python -m pytorch_ocr.cli │
│  train-det/train-rec/   │
│  eval-det/eval-rec/     │
│  predict                │
└──────────────────────┘
```

- **独立库**：`pytorch-ocr/` 是 monorepo 根下的独立 Python 库（有 `pyproject.toml`，可 `pip install`），打包进 `aistation-ocr` Docker 镜像。
- **与 ultralytics 同构**：后端只负责数据导出、命令构造、日志跟随、产物收集；训练/评估/预测全部在容器内执行。
- **完全解耦**：后端无 torch/opencv 依赖，不直接 import `pytorch_ocr`（部署 server 脚本通过字符串生成，容器内加载库）。

## 2. 环境准备

### 2.1 构建 aistation-ocr 镜像

```bash
cd pytorch-ocr
docker build -t aistation-ocr:latest .
```

镜像基于 `pytorch/pytorch:2.13.0-cuda13.2-cudnn9-runtime`，使用清华镜像源安装 `opencv-python-headless`/`pyclipper`/`pillow`，然后 `pip install --no-deps .` 安装 `pytorch-ocr` 库（不重复拉 torch）。

### 2.2 后端启动

后端启动时自动拉起 OCR 执行器的恢复循环（`OCRDetExecutor`/`OCRRecExecutor.start_recovery_loop()`）。

### 2.3 DB 迁移

`trainframework` PG 枚举需包含 `PYTORCH_OCR_DET`/`PYTORCH_OCR_REC`（迁移 `1c2d3e4f5a6b`）：

```bash
cd backend
uv run main.py upgrade --env=dev
```

## 3. 数据集模板

pytorch-ocr 的训练数据由后端 `_export_pytorch_ocr` 从标注系统导出。导出目录结构：

```
/data/                      # 容器内挂载点
├── images/                 # 原始图片（det）或裁剪文字行图（rec）
└── det_gt.txt 或 train_list.txt
```

### 3.1 检测任务（det）数据集

`det_gt.txt` 每行格式（**tab 分隔**）：

```
<图片文件名>\t<JSON 四边形数组>
```

- 图片存放在 `images/` 目录
- 四边形为**像素坐标**，4 个角点 `[x, y]`
- 支持单个四边形 `[[x1,y1],[x2,y2],[x3,y3],[x4,y4]]` 或多个四边形 `[[[...],[...]],[...]]`

**示例** `det_gt.txt`：

```
img_0001.jpg	[[[12.8,12.8],[51.2,12.8],[51.2,25.6],[12.8,25.6]]]
img_0002.jpg	[[[5.0,5.0],[95.0,5.0],[95.0,20.0],[5.0,20.0]],[[10.0,30.0],[60.0,30.0],[60.0,45.0],[10.0,45.0]]]
```

对应目录：

```
/data/
├── images/
│   ├── img_0001.jpg
│   └── img_0002.jpg
└── det_gt.txt
```

### 3.2 识别任务（rec）数据集

`train_list.txt` 每行格式（**tab 分隔**）：

```
<裁剪图路径>\t<文字标签>
```

- 裁剪图存放在 `images/` 目录，路径带 `images/` 前缀
- 每张裁剪图是检测阶段从原图按四边形**透视矫正**截取的单行文字
- 文字标签为实际识别目标文本（中英文均可）

**示例** `train_list.txt`：

```
images/img_0001_0.jpg	你好世界
images/img_0001_1.jpg	Hello World
images/img_0002_0.jpg	模型训练
```

对应目录：

```
/data/
├── images/
│   ├── img_0001_0.jpg    # 你好世界的裁剪行
│   ├── img_0001_1.jpg    # Hello World 的裁剪行
│   └── img_0002_0.jpg    # 模型训练的裁剪行
└── train_list.txt
```

### 3.3 字符集

rec 训练使用 PP-OCRv6 官方字符集（`pytorch-ocr/pytorch_ocr/utils/dict/ppocrv6_tiny_dict.txt`，6904 字符）。字符编码规则：

- 字符索引从 1 开始（`i + 1`），索引 0 保留为 **CTC blank**
- `num_classes = 6905（字符）+ 1（blank）= 6906`
- 训练超参 `num_classes=6906`、`max_text_length=25`

### 3.4 标注系统对接

在 AIStation 标注工作台创建 **OCR 任务**（`task_type = "ocr"`），标注时：
- 每个文字区域画 **polygon**（至少 4 点），标注类型 `polygon`/`ocr`
- 每个 polygon 填写 **text** 属性（该区域的文字内容）
- 导出时 `_export_pytorch_ocr` 自动将 polygon + text 转成 det_gt.txt / train_list.txt

> 注意：det 任务取 polygon 前 4 个点作为四边形；rec 任务对每个带 text 的 polygon 做透视矫正裁剪。

## 4. 训练

### 4.1 前端创建任务

任务表单 framework 下拉选择 **PyTorch OCR (det)** 或 **PyTorch OCR (rec)**。

**det 超参**（前端表单 → 后端 hyperparams → 容器 CLI）：

| 参数 | 默认 | 说明 |
|------|------|------|
| `model_size` | `tiny` | tiny / small / medium（PPLCNetV4 三档） |
| `epochs` | `100` | 训练轮数 |
| `batch` | `8` | 批大小 |
| `lr` | `0.001` | 学习率 |
| `device` | `0` | GPU 设备 |

**rec 超参**：

| 参数 | 默认 | 说明 |
|------|------|------|
| `model_size` | `tiny` | tiny / small / medium |
| `epochs` | `100` | 训练轮数 |
| `batch` | `128` | 批大小 |
| `lr` | `0.001` | 学习率 |
| `device` | `0` | GPU 设备 |

### 4.2 训练流程（后端）

1. `create_task` 创建 `TrainTask`，`framework` 为 `pytorch-ocr-det`/`pytorch-ocr-rec`，`docker_image` 固定 `aistation-ocr:latest`
2. 用户点击"开始训练" → `start_training` 分发到 `OCRDetExecutor`/`OCRRecExecutor`
3. Executor：
   - 导出数据集到 `%TEMP%/train_output/<task_id>/data`（det: images+det_gt.txt；rec: images+train_list.txt）
   - 挂载到容器 `/data`、`/output`
   - 运行 `train-det`/`train-rec` 命令
   - 跟随日志（解析 `epoch N avg_loss X lr Y` 更新进度）
   - 收集 `best.pt` → `export_model` → 创建 `TrainModel` 版本 → RustFS
4. 训练产物：`best.pt`（PyTorch state_dict）

### 4.3 CLI 直接运行（容器内）

```bash
# det 训练
python -m pytorch_ocr.cli train-det --data /data --output /output --device 0 --epochs 100 --batch 8 --model-size tiny

# rec 训练
python -m pytorch_ocr.cli train-rec --data /data --output /output --device 0 --epochs 100 --batch 128 --model-size tiny
```

## 5. 评估

### 5.1 det 评估（Hmean）

`eval-det` 在 `det_gt.txt` 上评估：
- 检测框与 GT 四边形 IoU ≥ 0.5 判定为 TP
- 输出 `{hmean, precision, recall, tp, fp, fn, num_images}`

```bash
python -m pytorch_ocr.cli eval-det --data /data --model /model/best.pt --output /output --device 0
```

### 5.2 rec 评估（字符准确率）

`eval-rec` 在 `train_list.txt`（或 `eval_list.txt`，若存在）上评估：
- 逐字符对比（忽略空白/顺序）
- 输出 `{char_acc, full_acc, total_chars, total_strings}`

```bash
python -m pytorch_ocr.cli eval-rec --data /data --model /model/best.pt --output /output --device 0
```

## 6. 预测（OCR 推理管线）

`predict` 串联 det（检测文字框）+ rec（识别文字），输出：

```json
[
  {"text": "模型训练测试123", "confidence": 0.985, "box": [[x1,y1],[x2,y1],[x2,y2],[x1,y2]]},
  {"text": "Hello World", "confidence": 0.963, "box": [...]}
]
```

```bash
python -m pytorch_ocr.cli predict \
  --image /input/img.jpg \
  --det-model /model/det.pt \
  --rec-model /model/rec.pt \
  --output /output/result.json \
  --device 0
```

**推理管线结构**（`pytorch_ocr/inference/ocr_pipeline.py`）：
1. det：PPLCNetV4 → RepLKFPN → DBHead → DBPostProcess（检测文字框，坐标映射回原图）
2. 每框透视矫正裁剪
3. rec：PPLCNetV4 → MultiHead(CTCHead) → CTCLabelDecode（识别文本）

## 7. 模型部署

部署 OCR 模型时，容器运行推理 server（`aistation-ocr:latest` + 生成的 server 脚本）：

- 挂载 `det.pt`/`rec.pt` 到 `/model/`
- `POST /predict`：传图 → `{detections: [{text, confidence, box}], inference_time_ms}`
- `GET /health`：健康检查
- 认证：`X-API-Key` header

> **注意**：OCR 部署要求同时提供 det + rec 模型（`rec_model_path` 超参必须指定）。若缺少 rec 模型，部署会被拒绝："OCR 部署需要提供 rec_model_path"。

## 8. 权重转换（Paddle → PyTorch）

官方 PP-OCRv6 预训练权重（`.pdparams`）可转换为 PyTorch `.pt`：

```bash
# 在含 Paddle 的环境（paddlex 容器或安装了 Paddle 的机器）
python -m pytorch_ocr.converter.verify_conversion --paddle /weights/PP-OCRv6_tiny_det_pretrained.pdparams --pytorch /out/det.pt
python -m pytorch_ocr.converter.verify_conversion --rec --paddle /weights/PP-OCRv6_tiny_rec_pretrained.pdparams --pytorch /out/rec.pt
```

已验证：
- det 转换：MSE 1.68e-11（486 参数与 Paddle 完全一致）
- rec 转换：官方 GTC 双头（CTC vocab 6906 / NRTR vocab 6910）严格加载 0 missing

权重下载地址（PaddleX 官方 BOS）：

```
https://paddle-model-ecology.bj.bcebos.com/paddlex/official_pretrained_model/PP-OCRv6_tiny_det_pretrained.pdparams
https://paddle-model-ecology.bj.bcebos.com/paddlex/official_pretrained_model/PP-OCRv6_tiny_rec_pretrained.pdparams
```

## 9. 目录结构

```
pytorch-ocr/
├── pyproject.toml          # 独立库（pip install，含 torch/opencv/pyclipper/pillow）
├── Dockerfile              # aistation-ocr 镜像（清华源 + pip install）
├── README.md
├── pytorch_ocr/
│   ├── cli.py              # 命令行入口（train-det/eval-det/train-rec/eval-rec/predict）
│   ├── __main__.py         # python -m pytorch_ocr
│   ├── modeling/           # PPLCNetV4 / RepLKFPN / DBHead / CTCHead / NRTRHead / MultiHead
│   │   ├── backbones/pplcnetv4.py
│   │   ├── necks/rep_lk_fpn.py
│   │   ├── heads/det_db_head.py, rec_ctc_head.py, rec_nrtr_head.py, rec_multi_head.py
│   │   └── losses/db_loss.py, rec_loss.py
│   ├── data/               # DetDataset / RecDataset / CharacterDict / transforms
│   ├── trainer/            # DetTrainer / RecTrainer
│   ├── inference/          # OCRPipeline（det→rec）
│   ├── postprocess/        # DBPostProcess / CTCLabelDecode
│   ├── converter/          # Paddle→PyTorch 权重转换 + verify_conversion
│   └── utils/dict/         # ppocrv6_tiny_dict.txt（官方字符集）
└── tests/                  # 89 个库内单元测试
```

## 10. 常见问题

### Q1: 训练时 det 检测不到文字 / rec 识别全乱码
- 检查是否为**官方权重**：官方权重 rec 输入需 `[-1,1]` 归一化（mean=std=0.5），CTC blank 索引为 0。自研库已默认对齐。
- 检查 `det_gt.txt`/`train_list.txt` 格式是否为 tab 分隔、像素坐标。

### Q2: rec 训练 small/medium 报错
- `backbone_out_channels` 已按 model_size 派生（tiny=160/small=384/medium=768），确认 CLI 传对 `--model-size`。

### Q3: 部署失败 "OCR 部署需要提供 rec_model_path"
- OCR 部署需同时提供 det + rec 模型。在部署 hyperparams 中指定 `rec_model_path`。

### Q4: 训练产物 best.pt 能否直接下载
- 可以。训练成功后 `TrainModel` 版本生成，`storage_path` 指向 RustFS，模型仓库页可下载/导出/部署。

## 11. 相关文档

- 设计规格：`docs/superpowers/specs/2026-08-02-model-training-enhancement-design.md`
- 实现计划：
  - `docs/superpowers/plans/2026-08-02-pytorch-ocr-det-model.md`
  - `docs/superpowers/plans/2026-08-02-pytorch-ocr-det-training.md`
  - `docs/superpowers/plans/2026-08-02-pytorch-ocr-rec-model.md`
  - `docs/superpowers/plans/2026-08-02-pytorch-ocr-inference-deploy.md`
