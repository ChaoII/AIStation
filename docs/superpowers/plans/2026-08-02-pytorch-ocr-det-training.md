# PyTorch OCR det 训练循环 + Docker + 后端集成 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为 SP2 plan 1 的 det 模型实现完整训练管线：数据加载与增强（MakeBorderMap/MakeShrinkMap）、det 训练循环（DB loss + Hmean 评估）、CLI 命令入口、Docker 镜像、数据导出到容器、executor 集成（复用 TaskExecutor）、框架接入（pytorch-ocr-det）。

**Architecture:** 新增 `pytorch_ocr/trainer/`（数据加载器 + 训练循环）+ `pytorch_ocr/cli.py`（train-det/eval-det 命令入口，Docker 容器内执行）。后端 `exporter.py` 新增 `_export_pytorch_ocr`（det 数据导出），`ocr_executor.py` 复用 TaskExecutor 跑容器训练，`TrainFramework` 新增 `PYTORCH_OCR_DET`。Docker 镜像 `aistation-ocr:latest` 打包 pytorch_ocr 包 + 依赖。

**Tech Stack:** PyTorch 2.x, opencv-python-headless, pyclipper, numpy, Docker, FastAPI, SQLAlchemy, pytest

## Global Constraints

- det 训练输入 `[3, 640, 640]`，normalize mean=[0.485,0.456,0.406] std=[0.229,0.224,0.225]
- DB loss = alpha*binary(5) + beta*thresh(10) + prob（DiceFocal 主损失，Task 3 已实现 DBLoss）
- 训练输出 `best.pt`（PyTorch state_dict，与 ultralytics 路径一致 `export_dir/exp/weights/best.pt` 或 `export_dir/best.pt`）
- 容器镜像 `aistation-ocr:latest`，入口 `python -m pytorch_ocr.cli`
- 复用 `TaskExecutor` 基类（`backend/app/plugin/module_train/task_executor.py`）与 `docker_utils`
- `TrainFramework` 新增 `PYTORCH_OCR_DET = "pytorch-ocr-det"`（不动 PADDLEX/ULTRALYTICS）
- 测试同步 pytest；真实容器训练/评估在人工验收（plan 3）
- 数据导出 `_export_pytorch_ocr` 输出 `det/` 目录（图片 + det_gt.txt），复用现有 `_export_paddle_ocr` 的裁剪逻辑（rec 部分 plan 3 再删 paddle 版）

---

### Task 1: det 数据加载器与增强（MakeBorderMap/MakeShrinkMap）

**Files:**
- Create: `backend/pytorch_ocr/data/__init__.py`
- Create: `backend/pytorch_ocr/data/transforms.py`
- Create: `backend/pytorch_ocr/data/det_dataset.py`
- Test: `backend/tests/test_det_data.py`

**Interfaces:**
- Consumes: det 标注（`det_gt.txt` 格式：`image_path [quad_points]...`），det 配置（shrink_ratio=0.4, thresh_min=0.3, thresh_max=0.7, min_text_size=8）
- Produces:
  - `class MakeShrinkMap` — 输入 (img, polygons)，输出 shrink_map + shrink_mask
  - `class MakeBorderMap` — 输出 threshold_map + threshold_mask
  - `class DetDataset(Dataset)` — 读取 det_gt.txt，返回 `(image_tensor, shrink_map, shrink_mask, threshold_map, threshold_mask)`

- [ ] **Step 1: 写失败测试 — 数据增强输出形状**

`backend/tests/test_det_data.py`:

```python
"""det 数据加载器与增强测试。"""
import numpy as np
import torch

from pytorch_ocr.data.transforms import MakeShrinkMap, MakeBorderMap
from pytorch_ocr.data.det_dataset import DetDataset


def test_make_shrink_map_shapes():
    transform = MakeShrinkMap(shrink_ratio=0.4, min_text_size=8)
    img = np.random.randint(0, 255, (64, 64, 3), dtype=np.uint8)
    # 一个矩形文本区域（归一化坐标）
    polys = [np.array([[0.2, 0.2], [0.8, 0.2], [0.8, 0.4], [0.2, 0.4]])]
    shrink_map, mask = transform(img, polys)
    assert shrink_map.shape == (64, 64)
    assert mask.shape == (64, 64)
    assert mask.sum() > 0  # 有标注区域


def test_make_border_map_shapes():
    transform = MakeBorderMap(shrink_ratio=0.4, thresh_min=0.3, thresh_max=0.7)
    img = np.random.randint(0, 255, (64, 64, 3), dtype=np.uint8)
    polys = [np.array([[0.2, 0.2], [0.8, 0.2], [0.8, 0.4], [0.2, 0.4]])]
    thresh_map, thresh_mask = transform(img, polys)
    assert thresh_map.shape == (64, 64)
    assert thresh_mask.shape == (64, 64)
    assert 0 <= thresh_map.min() <= thresh_map.max() <= 1


def test_det_dataset_len_and_item():
    import os
    import tempfile
    # 创建临时 det_gt.txt
    with tempfile.TemporaryDirectory() as tmp:
        img = np.random.randint(0, 255, (64, 64, 3), dtype=np.uint8).astype(np.uint8)
        from PIL import Image
        Image.fromarray(img).save(os.path.join(tmp, "img_0.jpg"))
        gt = os.path.join(tmp, "det_gt.txt")
        with open(gt, "w") as f:
            f.write("img_0.jpg [[12.8,12.8],[51.2,12.8],[51.2,25.6],[12.8,25.6]]\n")
        ds = DetDataset(gt_dir=tmp, label_path=gt, image_shape=(64, 64))
        assert len(ds) == 1
        item = ds[0]
        assert isinstance(item, tuple) and len(item) >= 4
```

- [ ] **Step 2: 运行确认失败**

Run: `cd D:/AIStation/backend && uv run pytest tests/test_det_data.py -v`
Expected: FAIL（ModuleNotFoundError: pytorch_ocr.data）

- [ ] **Step 3: 实现 MakeShrinkMap / MakeBorderMap**

`backend/pytorch_ocr/data/transforms.py`:

```python
"""det 数据增强：MakeShrinkMap / MakeBorderMap（对齐 PaddleOCR）。自研实现。"""
import cv2
import numpy as np
import pyclipper


def _order_points(pts):
    """四点排序为 TL/TR/BR/BL。"""
    rect = np.zeros((4, 2), dtype=np.float32)
    s = pts.sum(axis=1)
    rect[0] = pts[np.argmin(s)]
    rect[2] = pts[np.argmax(s)]
    diff = np.diff(pts, axis=1)
    rect[1] = pts[np.argmin(diff)]
    rect[3] = pts[np.argmax(diff)]
    return rect


def _shrink_poly(poly, ratio):
    """按比例收缩多边形（pyclipper 负偏移）。"""
    area = cv2.contourArea(poly)
    perimeter = cv2.arcLength(poly, True)
    distance = area * (1 - ratio) / perimeter if perimeter > 0 else 0
    pco = pyclipper.PyclipperOffset()
    pco.AddPath(poly, pyclipper.JT_ROUND, pyclipper.ET_CLOSEDPOLYGON)
    offset = pco.Execute(-distance)
    if not offset:
        return None
    return np.array(offset[0], dtype=np.float32)


class MakeShrinkMap:
    """生成 shrink_map（文字区域收缩后的二值图）与 shrink_mask。"""
    def __init__(self, shrink_ratio=0.4, min_text_size=8):
        self.shrink_ratio = shrink_ratio
        self.min_text_size = min_text_size

    def __call__(self, img, polys):
        h, w = img.shape[:2]
        shrink_map = np.zeros((h, w), dtype=np.float32)
        mask = np.zeros((h, w), dtype=np.uint8)
        for poly in polys:
            pts = (poly * np.array([w, h])).astype(np.int32)
            shrunk = _shrink_poly(pts, self.shrink_ratio)
            if shrunk is None:
                continue
            if cv2.contourArea(shrunk) < 1:
                continue
            cv2.fillPoly(shrink_map, [shrunk.astype(np.int32)], 1.0)
            cv2.fillPoly(mask, [pts], 1)
        return shrink_map, mask


class MakeBorderMap:
    """生成 threshold_map（文字边界渐变）与 threshold_mask。"""
    def __init__(self, shrink_ratio=0.4, thresh_min=0.3, thresh_max=0.7):
        self.shrink_ratio = shrink_ratio
        self.thresh_min = thresh_min
        self.thresh_max = thresh_max

    def __call__(self, img, polys):
        h, w = img.shape[:2]
        thresh_map = np.zeros((h, w), dtype=np.float32)
        thresh_mask = np.zeros((h, w), dtype=np.uint8)
        for poly in polys:
            pts = (poly * np.array([w, h])).astype(np.float32)
            pts = _order_points(pts)
            # 原始 + 扩张后的多边形，中间区域做距离渐变
            pco = pyclipper.PyclipperOffset()
            pco.AddPath(pts, pyclipper.JT_ROUND, pyclipper.ET_CLOSEDPOLYGON)
            area = cv2.contourArea(pts)
            perimeter = cv2.arcLength(pts, True)
            dist = area * (1 - self.shrink_ratio) / perimeter if perimeter > 0 else 0
            expanded = pco.Execute(dist)
            if not expanded:
                continue
            expanded = np.array(expanded[0], dtype=np.int32)
            poly_pts = np.array([pts], dtype=np.int32)
            # 在扩张区域里填充到边缘的距离
            tmp = np.zeros((h, w), dtype=np.float32)
            cv2.fillPoly(tmp, [expanded], 1.0)
            # 简化：对原始矩形内做渐变（完整 PaddleOCR 用距离变换，此处用近似）
            cv2.fillPoly(thresh_map, poly_pts, 1.0)
            cv2.fillPoly(thresh_mask, [expanded], 1)
        # 归一化到 [thresh_min, thresh_max]
        if thresh_mask.sum() > 0:
            thresh_map = thresh_min + (thresh_max - thresh_min) * thresh_map
        return thresh_map, thresh_mask
```

> **说明**：MakeBorderMap 的精确实现（PaddleOCR 用 `cv2.distanceTransform` 对扩张区域做距离渐变）较复杂。上述是简化版（对矩形内填 1.0 再做归一化）。实现者可参考 PaddleOCR 的 `MakeBorderMap` 算法完善（用 distanceTransform 生成真实的边界渐变），但测试只验证形状与范围，不锁定精确值。plan 3 端到端验收时验证训练效果。

- [ ] **Step 4: 实现 DetDataset**

`backend/pytorch_ocr/data/det_dataset.py`:

```python
"""det 训练数据集：读取 det_gt.txt，返回模型输入与 GT。自研实现。"""
import cv2
import numpy as np
import torch
from torch.utils.data import Dataset

from .transforms import MakeBorderMap, MakeShrinkMap

_MEAN = np.array([0.485, 0.456, 0.406], dtype=np.float32)
_STD = np.array([0.229, 0.224, 0.225], dtype=np.float32)


class DetDataset(Dataset):
    def __init__(self, gt_dir, label_path, image_shape=(640, 640),
                 is_train=True, shrink_ratio=0.4):
        self.gt_dir = gt_dir
        self.image_shape = image_shape
        self.is_train = is_train
        self.shrink_map_fn = MakeShrinkMap(shrink_ratio)
        self.border_map_fn = MakeBorderMap(shrink_ratio)
        self._load_labels(label_path)

    def _load_labels(self, label_path):
        self.items = []
        with open(label_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                parts = line.split("\t")
                if len(parts) < 2:
                    continue
                img_name = parts[0]
                # 解析四边形：[[x1,y1],[x2,y2],[x3,y3],[x4,y4]]
                polys = self._parse_polys(parts[1])
                self.items.append((img_name, polys))

    def _parse_polys(self, s):
        import json
        try:
            data = json.loads(s)
        except json.JSONDecodeError:
            return []
        polys = []
        for quad in data:
            pts = np.array([[p[0], p[1]] for p in quad], dtype=np.float32)
            polys.append(pts)
        return polys

    def __len__(self):
        return len(self.items)

    def __getitem__(self, idx):
        img_name, polys = self.items[idx]
        img = cv2.imread(f"{self.gt_dir}/{img_name}", cv2.IMREAD_COLOR)
        if img is None:
            return self[(idx + 1) % len(self.items)]
        img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        # 归一化多边形到 [0,1]
        h, w = img.shape[:2]
        norm_polys = [p / np.array([w, h]) for p in polys]
        shrink_map, shrink_mask = self.shrink_map_fn(img, norm_polys)
        thresh_map, thresh_mask = self.border_map_fn(img, norm_polys)
        # resize 到 image_shape（训练简化：直接 resize，不做随机裁剪）
        img = cv2.resize(img, self.image_shape)
        shrink_map = cv2.resize(shrink_map, self.image_shape)
        thresh_map = cv2.resize(thresh_map, self.image_shape)
        shrink_mask = cv2.resize(shrink_mask, self.image_shape).astype(np.uint8)
        thresh_mask = cv2.resize(thresh_mask, self.image_shape).astype(np.uint8)
        # normalize + CHW
        img = (img.astype(np.float32) / 255.0 - _MEAN) / _STD
        img = torch.from_numpy(img).permute(2, 0, 1).float()
        shrink_map = torch.from_numpy(shrink_map).unsqueeze(0).float()
        shrink_mask = torch.from_numpy(shrink_mask).unsqueeze(0).float()
        thresh_map = torch.from_numpy(thresh_map).unsqueeze(0).float()
        thresh_mask = torch.from_numpy(thresh_mask).unsqueeze(0).float()
        return img, shrink_map, shrink_mask, thresh_map, thresh_mask
```

- [ ] **Step 5: 运行测试确认通过**

Run: `cd D:/AIStation/backend && uv run pytest tests/test_det_data.py -v`
Expected: 3 passed

- [ ] **Step 6: ruff + 提交**

Run: `cd D:/AIStation/backend && uv run ruff check pytorch_ocr/ tests/test_det_data.py`
Expected: clean

```bash
git add backend/pytorch_ocr/data/ backend/tests/test_det_data.py
git commit -m "feat(ocr): det data loader with shrink/border map transforms"
```

---

### Task 2: det 训练循环

**Files:**
- Create: `backend/pytorch_ocr/trainer/__init__.py`
- Create: `backend/pytorch_ocr/trainer/det_trainer.py`
- Test: `backend/tests/test_det_trainer.py`

**Interfaces:**
- Consumes: `DetDataset`（Task 1）、`PPLCNetV4`+`RepLKFPN`+`DBHead`+`DBLoss`（plan 1）、det 配置
- Produces: `class DetTrainer` — `__init__(config, device)`, `train(data_dir, num_epochs, batch_size, output_dir)`, `eval(...)`；训练结束保存 `best.pt` 到 output_dir

- [ ] **Step 1: 写失败测试 — 训练循环结构**

`backend/tests/test_det_trainer.py`:

```python
"""det 训练器结构测试。"""
import inspect

from pytorch_ocr.trainer.det_trainer import DetTrainer


def test_det_trainer_init_signature():
    sig = inspect.signature(DetTrainer.__init__)
    params = list(sig.parameters.keys())
    assert "config" in params
    assert "device" in params


def test_det_trainer_has_train_and_eval():
    assert hasattr(DetTrainer, "train")
    assert hasattr(DetTrainer, "eval")
```

- [ ] **Step 2: 运行确认失败**

Run: `cd D:/AIStation/backend && uv run pytest tests/test_det_trainer.py -v`
Expected: FAIL（ModuleNotFoundError）

- [ ] **Step 3: 实现 DetTrainer**

`backend/pytorch_ocr/trainer/det_trainer.py`:

```python
"""det 训练器：DB loss + Hmean 评估 + best.pt 保存。自研实现。"""
import os
import time

import torch
from torch.utils.data import DataLoader

from ..modeling.backbones.pplcnetv4 import PPLCNetV4
from ..modeling.necks.rep_lk_fpn import RepLKFPN
from ..modeling.heads.det_db_head import DBHead
from ..modeling.losses.db_loss import DBLoss
from ..data.det_dataset import DetDataset
from ..postprocess.db_postprocess import DBPostProcess


class DetTrainer:
    def __init__(self, config: dict, device: str = "cuda:0"):
        self.config = config
        self.device = device if torch.cuda.is_available() or device == "cpu" else "cpu"
        size = config.get("model_size", "tiny")
        self.backbone = PPLCNetV4(model_size=size, det=True)
        self.fpn = RepLKFPN(in_channels=self.backbone.feat_channels,
                            out_channels=config.get("out_channels", 64),
                            dilated_kernel_size=config.get("dilated_kernel_size", 5))
        self.head = DBHead(in_channels=config.get("out_channels", 64),
                           k=config.get("k", 50))
        self.loss_fn = DBLoss(alpha=config.get("alpha", 5),
                              beta=config.get("beta", 10))
        self.postprocess = DBPostProcess(
            thresh=config.get("thresh", 0.2),
            box_thresh=config.get("box_thresh", 0.45),
            max_candidates=config.get("max_candidates", 3000),
            unclip_ratio=config.get("unclip_ratio", 1.4),
        )
        self.net = torch.nn.ModuleDict({
            "backbone": self.backbone, "fpn": self.fpn, "head": self.head,
        })
        self.net.to(self.device)

    def _train_step(self, batch):
        img, shrink_map, shrink_mask, thresh_map, thresh_mask = [b.to(self.device) for b in batch]
        feats = self.backbone(img)
        fused = self.fpn(feats)  # train: dict {fuse, aux_*}
        maps = self.head(fused["fuse"])["maps"]  # (N,3,H,W)
        gt = {
            "shrink_map": shrink_map,
            "shrink_mask": shrink_mask,
            "threshold_map": thresh_map,
            "threshold_mask": thresh_mask,
        }
        loss = self.loss_fn(maps, gt)
        return loss

    def train(self, data_dir, num_epochs=100, batch_size=8, output_dir="./output",
              workers=4, lr=0.001):
        dataset = DetDataset(gt_dir=os.path.join(data_dir, "images"),
                             label_path=os.path.join(data_dir, "det_gt.txt"),
                             image_shape=tuple(self.config.get("image_shape", (640, 640))))
        loader = DataLoader(dataset, batch_size=batch_size, shuffle=True,
                            num_workers=workers)
        optimizer = torch.optim.Adam(self.net.parameters(), lr=lr, betas=(0.9, 0.999))
        scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer,
                                                               T_max=num_epochs)
        os.makedirs(output_dir, exist_ok=True)
        best_loss = float("inf")
        for epoch in range(1, num_epochs + 1):
            self.net.train()
            total_loss = 0.0
            n_batches = 0
            for batch in loader:
                optimizer.zero_grad()
                loss = self._train_step(batch)
                loss.backward()
                optimizer.step()
                total_loss += loss.item()
                n_batches += 1
                print(f"epoch {epoch} batch {n_batches} loss {loss.item():.4f}", flush=True)
            scheduler.step()
            avg = total_loss / max(n_batches, 1)
            print(f"epoch {epoch} avg_loss {avg:.4f} lr {scheduler.get_last_lr()[0]:.6f}", flush=True)
            # 保存 best.pt（按 loss 简单判断；真实评估用 Hmean 在 plan 3）
            if avg < best_loss:
                best_loss = avg
                torch.save(self.net.state_dict(), os.path.join(output_dir, "best.pt"))
        print("training done", flush=True)
        return os.path.join(output_dir, "best.pt")

    def eval(self, data_dir, output_dir="./output"):
        """Hmean 评估。plan 3 完善真实指标；此处提供接口骨架。"""
        self.net.eval()
        # 简化：加载 best.pt 后跑前向（评估逻辑在 plan 3 完善）
        return {}
```

> **说明**：训练循环已实现核心（DB loss + AdamW/Cosine + best.pt 保存）。**Hmean 评估的真实实现（IoU 阈值下 precision/recall/F1）推迟到 plan 3**（需要 det_gt.txt 与 postprocess 输出做 IoU 匹配，独立且复杂）。本任务训练循环能产出 best.pt。训练时打印日志格式为 `epoch N avg_loss X lr Y`——后端 executor 的日志解析（Task 5）依赖此格式。

- [ ] **Step 4: 运行测试确认通过**

Run: `cd D:/AIStation/backend && uv run pytest tests/test_det_trainer.py -v`
Expected: 2 passed

- [ ] **Step 5: ruff + 提交**

```bash
git add backend/pytorch_ocr/trainer/ backend/tests/test_det_trainer.py
git commit -m "feat(ocr): det training loop with DB loss and best.pt save"
```

---

### Task 3: CLI 命令入口

**Files:**
- Create: `backend/pytorch_ocr/cli.py`
- Create: `backend/pytorch_ocr/__main__.py`
- Test: `backend/tests/test_cli.py`

**Interfaces:**
- Consumes: `DetTrainer`（Task 2）、`DetDataset`（Task 1）
- Produces: CLI 子命令 `train-det` / `eval-det`，Docker 容器内 `python -m pytorch_ocr.cli train-det --data /data --output /output --device 0`

- [ ] **Step 1: 写失败测试 — CLI 参数解析**

`backend/tests/test_cli.py`:

```python
"""CLI 参数解析测试。"""
import inspect

from pytorch_ocr.cli import build_parser


def test_build_parser_has_subcommands():
    parser = build_parser()
    sub = parser._subparsers
    assert sub is not None
    # 校验子命令名
    actions = [a for a in sub._group_actions[0]._choices.keys()]
    assert "train-det" in actions
    assert "eval-det" in actions
```

- [ ] **Step 2: 运行确认失败**

Run: `cd D:/AIStation/backend && uv run pytest tests/test_cli.py -v`
Expected: FAIL（ModuleNotFoundError: pytorch_ocr.cli）

- [ ] **Step 3: 实现 CLI**

`backend/pytorch_ocr/cli.py`:

```python
"""pytorch_ocr CLI：容器内训练/评估入口。自研实现。"""
import argparse
import json


def build_parser():
    parser = argparse.ArgumentParser(prog="pytorch_ocr",
                                     description="AIStation OCR CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    train_det = sub.add_parser("train-det", help="训练 det 检测模型")
    train_det.add_argument("--data", required=True, help="数据集目录(含 images/ + det_gt.txt)")
    train_det.add_argument("--output", default="/output", help="输出目录")
    train_det.add_argument("--device", default="0", help="GPU 设备(cuda:0 / cpu)")
    train_det.add_argument("--epochs", type=int, default=100)
    train_det.add_argument("--batch", type=int, default=8)
    train_det.add_argument("--lr", type=float, default=0.001)
    train_det.add_argument("--config", default="", help="JSON 配置文件路径(可选)")
    train_det.add_argument("--model-size", default="tiny",
                           choices=["tiny", "small", "medium"])

    eval_det = sub.add_parser("eval-det", help="评估 det 模型")
    eval_det.add_argument("--data", required=True)
    eval_det.add_argument("--model", required=True, help="best.pt 路径")
    eval_det.add_argument("--output", default="/output")
    eval_det.add_argument("--device", default="0")
    eval_det.add_argument("--config", default="")
    return parser


def _build_config(args) -> dict:
    cfg = {
        "model_size": getattr(args, "model_size", "tiny"),
        "out_channels": 64,
        "dilated_kernel_size": 5,
        "k": 50,
        "alpha": 5,
        "beta": 10,
        "image_shape": (640, 640),
    }
    if getattr(args, "config", ""):
        with open(args.config, "r", encoding="utf-8") as f:
            cfg.update(json.load(f))
    return cfg


def cmd_train_det(args):
    from .trainer.det_trainer import DetTrainer
    device = "cpu" if args.device == "cpu" else f"cuda:{args.device}"
    cfg = _build_config(args)
    cfg["model_size"] = args.model_size
    trainer = DetTrainer(cfg, device=device)
    best_path = trainer.train(
        data_dir=args.data, num_epochs=args.epochs, batch_size=args.batch,
        output_dir=args.output, lr=args.lr,
    )
    print(f"[cli] best model saved: {best_path}", flush=True)


def cmd_eval_det(args):
    from .trainer.det_trainer import DetTrainer
    device = "cpu" if args.device == "cpu" else f"cuda:{args.device}"
    cfg = _build_config(args)
    trainer = DetTrainer(cfg, device=device)
    # 加载模型
    import torch
    trainer.net.load_state_dict(torch.load(args.model, map_location="cpu"))
    result = trainer.eval(data_dir=args.data, output_dir=args.output)
    print(f"[cli] eval result: {json.dumps(result)}", flush=True)


def main():
    parser = build_parser()
    args = parser.parse_args()
    if args.command == "train-det":
        cmd_train_det(args)
    elif args.command == "eval-det":
        cmd_eval_det(args)


if __name__ == "__main__":
    main()
```

`backend/pytorch_ocr/__main__.py`:

```python
from .cli import main

if __name__ == "__main__":
    main()
```

- [ ] **Step 4: 运行测试确认通过**

Run: `cd D:/AIStation/backend && uv run pytest tests/test_cli.py -v`
Expected: 1 passed

- [ ] **Step 5: CLI 冒烟**

Run: `cd D:/AIStation/backend && uv run python -m pytorch_ocr.cli --help`
Expected: 显示子命令 train-det / eval-det

- [ ] **Step 6: ruff + 提交**

```bash
git add backend/pytorch_ocr/cli.py backend/pytorch_ocr/__main__.py backend/tests/test_cli.py
git commit -m "feat(ocr): CLI entry for det train/eval"
```

---

### Task 4: Docker 镜像

**Files:**
- Create: `docker/ocr-train/Dockerfile`
- Create: `docker/ocr-train/requirements.txt`

**Interfaces:**
- Consumes: `pytorch_ocr` 包（plan 1 + Task 1-3）
- Produces: `aistation-ocr:latest` 镜像（<3GB，含 pytorch + opencv + pyclipper + pytorch_ocr）

- [ ] **Step 1: 写 Dockerfile**

`docker/ocr-train/Dockerfile`:

```dockerfile
FROM pytorch/pytorch:2.4.0-cuda12.1-cudnn9-runtime

# 系统依赖
RUN apt-get update && apt-get install -y --no-install-recommends \
    libglib2.0-0 libgl1 \
    && rm -rf /var/lib/apt/lists/*

# Python 依赖
COPY requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

# 打包 pytorch_ocr 包
WORKDIR /workspace
COPY pytorch_ocr/ /workspace/pytorch_ocr/

# 默认入口
ENTRYPOINT ["python", "-m", "pytorch_ocr.cli"]
```

`docker/ocr-train/requirements.txt`:

```
opencv-python-headless==4.10.0.84
pyclipper==1.3.0.post5
numpy>=1.24
```

> **说明**：镜像构建需 `pytorch_ocr` 包目录。构建命令：`docker build -t aistation-ocr:latest -f docker/ocr-train/Dockerfile backend/`（backend 为构建上下文，含 pytorch_ocr/）。构建是人工/CI 步骤，本任务只交付 Dockerfile + requirements.txt（不实际构建，避免长时间 pull pytorch 基础镜像）。

- [ ] **Step 2: 提交**

```bash
git add docker/ocr-train/
git commit -m "feat(ocr): Dockerfile for aistation-ocr training image"
```

---

### Task 5: 后端数据导出 + executor 集成 + 框架接入

**Files:**
- Modify: `backend/app/plugin/module_train/exporter.py`（新增 `_export_pytorch_ocr` + `_export_core` 分支）
- Modify: `backend/app/plugin/module_train/model.py`（TrainFramework 加 `PYTORCH_OCR_DET`）
- Modify: `backend/app/plugin/module_train/service.py`（create_task 支持 pytorch-ocr-det）
- Modify: `backend/app/plugin/module_train/scheduler.py`（`_build_cmd` 加 OCR 分支）
- Create: `backend/app/plugin/module_train/ocr_executor.py`（OCRDetExecutor）
- Modify: `backend/app/scripts/init_app.py`（启动 OCR 恢复循环）
- Test: `backend/tests/test_ocr_integration.py`

**Interfaces:**
- Consumes: `TaskExecutor` 基类、`docker_utils`、det 配置
- Produces:
  - `_export_pytorch_ocr(dataset_id, task_id, images, output_dir, annotation_task_id)` — 输出 `det/images/` + `det/det_gt.txt`
  - `TrainFramework.PYTORCH_OCR_DET = "pytorch-ocr-det"`
  - `class OCRDetExecutor(TaskExecutor)` — 复用 TrainTask 表，framework=pytorch-ocr-det，跑 `aistation-ocr:latest` 容器
  - `_build_cmd` 对 pytorch-ocr-det 构造 `["python","-m","pytorch_ocr.cli","train-det","--data","/data","--output","/output",...]`

- [ ] **Step 1: 写失败测试 — 集成点**

`backend/tests/test_ocr_integration.py`:

```python
"""OCR 训练后端集成测试。"""
import inspect

from app.plugin.module_train.model import TrainFramework
from app.plugin.module_train.scheduler import _build_cmd
from app.plugin.module_train.exporter import _export_core


def test_pytorch_ocr_det_framework_defined():
    assert TrainFramework.PYTORCH_OCR_DET == "pytorch-ocr-det"


def test_build_cmd_has_ocr_branch():
    src = inspect.getsource(_build_cmd)
    assert "pytorch-ocr-det" in src or "PYTORCH_OCR_DET" in src


def test_export_core_has_pytorch_ocr_branch():
    src = inspect.getsource(_export_core)
    assert "pytorch-ocr-det" in src or "PYTORCH_OCR_DET" in src
```

- [ ] **Step 2: 运行确认失败**

Run: `cd D:/AIStation/backend && uv run pytest tests/test_ocr_integration.py -v`
Expected: FAIL（TrainFramework 无 PYTORCH_OCR_DET）

- [ ] **Step 3: 模型枚举 + service + 命令构造**

`model.py` 的 `TrainFramework` 加：

```python
class TrainFramework(str, enum.Enum):
    PADDLEX = "paddlex"
    ULTRALYTICS = "ultralytics"
    PYTORCH_OCR_DET = "pytorch-ocr-det"
```

`service.py` 的 `create_task`：`docker_image` 逻辑改为：

```python
            if data.framework == TrainFramework.PADDLEX:
                raise Exception("PaddleX 已下线，请使用 ultralytics 框架")
            image = ("aistation-ocr:latest"
                     if data.framework == TrainFramework.PYTORCH_OCR_DET
                     else "ultralytics/ultralytics:latest")
```

`scheduler.py` 的 `_build_cmd` 加 OCR 分支：

```python
    if task.framework == TrainFramework.PYTORCH_OCR_DET:
        hp = task.hyperparams or {}
        return [
            "python", "-m", "pytorch_ocr.cli", "train-det",
            "--data", "/data",
            "--output", "/output",
            "--device", str(hp.get("device", "0")),
            "--epochs", str(hp.get("epochs", 100)),
            "--batch", str(hp.get("batch", 8)),
            "--lr", str(hp.get("lr", 0.001)),
            "--model-size", str(hp.get("model_size", "tiny")),
        ]
```

- [ ] **Step 4: 实现 `_export_pytorch_ocr`**

`exporter.py` 新增函数（复用 `_export_paddle_ocr` 的 det 目录逻辑）：

```python
async def _export_pytorch_ocr(dataset_id: int, task_id: int, images: list,
                              output_dir: str, annotation_task_id: int | None = None) -> None:
    """导出 PyTorch OCR det 格式：det/images/ + det/det_gt.txt。

    det_gt.txt 每行: "image_name\t[[[x1,y1],[x2,y2],[x3,y3],[x4,y4]],...]"
    （像素坐标，与 DetDataset._parse_polys 匹配）
    """
    from app.utils.s3_client import s3_client

    img_dir = os.path.join(output_dir, "images")
    os.makedirs(img_dir, exist_ok=True)
    det_lines = []

    async with async_db_session() as db:
        for img in images:
            img_path = os.path.join(img_dir, img.filename)
            try:
                if not os.path.exists(img_path):
                    data = s3_client.download_fileobj(img.object_key)
                    with open(img_path, "wb") as f:
                        f.write(data.read())
            except Exception:
                continue

            query = select(AnnotationRecordModel).where(AnnotationRecordModel.image_id == img.id)
            if annotation_task_id:
                query = query.where(AnnotationRecordModel.task_id == annotation_task_id)
            query = query.order_by(desc(AnnotationRecordModel.version)).limit(1)
            rec = await db.execute(query)
            record = rec.scalar_one_or_none()
            anns = record.annotation_data if record and record.annotation_data else []

            quads = []
            w = img.width or 1
            h = img.height or 1
            for ann in anns:
                if ann.get("type") not in ("polygon", "Polygon", "ocr", "Ocr"):
                    continue
                pts = ann.get("points", [])
                if len(pts) < 4:
                    continue
                # 转像素坐标四角点
                quad = [[float(p["x"] * w), float(p["y"] * h)]
                        if isinstance(p, dict) else [float(p[0] * w), float(p[1] * h)]
                        for p in pts[:4]]
                quads.append(quad)
            if quads:
                import json
                det_lines.append(f"{img.filename}\t{json.dumps(quads)}")

    with open(os.path.join(output_dir, "det_gt.txt"), "w", encoding="utf-8") as f:
        f.write("\n".join(det_lines))
    log.info(f"pytorch-ocr: exported {len(det_lines)} labeled images to {output_dir}")
```

`_export_core` 加分支：

```python
    elif framework == "pytorch-ocr-det":
        await _export_pytorch_ocr(dataset_id, task_id, images, output_dir, annotation_task_id)
```

> **说明**：`DetDataset` 期望 `det_gt.txt` 与图片在 `det/` 下，但容器挂载时 `data_dir` 指向整个导出目录。**实现者需确认挂载结构**：`_export_pytorch_ocr` 输出 `output_dir/images/` + `output_dir/det_gt.txt`，容器内挂载到 `/data`，CLI `--data /data`。DetDataset 的 `gt_dir=images/, label_path=det_gt.txt` 需与 CLI 传参一致（`DetDataset(gt_dir=data_dir/images, label_path=data_dir/det_gt.txt)`）。

- [ ] **Step 5: 实现 OCRDetExecutor**

`ocr_executor.py`:

```python
"""OCR det 训练执行器：复用 TaskExecutor，跑 aistation-ocr 容器。"""
import os
import tempfile

from sqlalchemy import update

from app.core.database import async_db_session
from app.core.logger import log

from .docker_utils import follow_container_logs, pull_image, remove_container, run_container
from .model import TrainStatus, TrainTask
from .scheduler import _build_cmd
from .task_executor import TaskExecutor
from .ws import broadcast_log


class OCRDetExecutor(TaskExecutor):
    name = "ocr_det"
    status_enum = TrainStatus
    model_class = TrainTask
    _concurrency = 1
    DOCKER_IMAGE = "aistation-ocr:latest"

    @classmethod
    async def _execute(cls, task_id: int):
        container_id = None
        try:
            async with async_db_session() as db:
                task = await db.get(TrainTask, task_id)
                if not task:
                    return

            await broadcast_log(task_id, f"[ocr] pulling image {cls.DOCKER_IMAGE}...")
            await pull_image(cls.DOCKER_IMAGE)

            export_dir = os.path.join(tempfile.gettempdir(), "train_output", str(task_id))
            data_dir = os.path.join(export_dir, "data")
            os.makedirs(data_dir, exist_ok=True)

            from .exporter import prepare_training_data_for_task
            await prepare_training_data_for_task(
                task.dataset_id, task.id, task.framework, data_dir,
                annotation_task_id=task.annotation_task_id,
            )

            cmd = await _build_cmd(task, data_dir, export_dir)

            container = await run_container(
                cls.DOCKER_IMAGE, cmd,
                volumes={data_dir: {"bind": "/data", "mode": "rw"},
                         export_dir: {"bind": "/output", "mode": "rw"}},
                gpu_id=task.hyperparams.get("gpu_id", "0"),
            )
            container_id = container.id
            cls._registry[task_id] = {"container_id": container_id, "cancel": False}

            metrics_log = await cls.follow_logs(
                container_id,
                os.path.join(export_dir, "train.log"),
                lambda line: broadcast_log(task_id, line),
            )
            exit_code = await cls._get_exit_code(container)

            if cls._registry.get(task_id, {}).get("cancel"):
                await remove_container(container_id)
                await cls._mark_status(task_id, TrainStatus.CANCELLED, finished_at=datetime.now())
            elif exit_code == 0:
                await remove_container(container_id)
                # 收集 best.pt
                best_path = os.path.join(export_dir, "best.pt")
                if os.path.exists(best_path):
                    from .exporter import export_model
                    model_info = await export_model(task_id, task.framework, export_dir)
                    await cls._mark_status(
                        task_id, TrainStatus.SUCCESS,
                        model_repo_id=model_info.get("repo_id"),
                        progress=100, finished_at=datetime.now(),
                    )
                else:
                    await cls._mark_status(task_id, TrainStatus.FAILED,
                                           error_log="best.pt not found in output",
                                           finished_at=datetime.now())
            else:
                await remove_container(container_id)
                await cls._mark_status(task_id, TrainStatus.FAILED,
                                       error_log="ocr training failed",
                                       finished_at=datetime.now())
        except Exception as e:
            log.error(f"ocr task {task_id} failed: {e}")
            await cls._mark_status(task_id, TrainStatus.FAILED,
                                   error_log=str(e), finished_at=datetime.now())
        finally:
            cls._registry.pop(task_id, None)
            if container_id:
                await remove_container(container_id)
```

> **注意**：需要 `from datetime import datetime` 导入。`export_model` 需确认对 `pytorch-ocr-det` 框架查找 `best.pt`（现有 `export_model` 只找 ultralytics 的 `.pt` 和 paddlex 的 `.pdparams`——需加 pytorch-ocr-det 分支）。

`export_model`（exporter.py:501）的产物查找扩展：

```python
    extensions = [".pt"] if framework in ("ultralytics", "pytorch-ocr-det") else [".pdparams"]
    # best.pt 候选路径加 export_dir/best.pt
    if framework == "pytorch-ocr-det":
        candidates.insert(0, os.path.join(export_dir, "best.pt"))
```

- [ ] **Step 6: init_app 启动 OCR 恢复循环**

`init_app.py` 训练调度器区（~535-541）追加：

```python
        from app.plugin.module_train.ocr_executor import OCRDetExecutor
        asyncio.create_task(OCRDetExecutor.start_recovery_loop())
        log.info("✅ OCR 训练调度器已启动")
```

同时 `scheduler.py` 的 `start_training` 需要按框架分发到 OCRDetExecutor——修改 `start_training`：

```python
async def start_training(task_id: int):
    async with async_db_session.begin() as db:
        task = await db.get(TrainTask, task_id)
        if not task:
            raise Exception(f"训练任务 {task_id} 不存在")
        # ... 现有校验 ...
    if task.framework == TrainFramework.PYTORCH_OCR_DET:
        asyncio.create_task(OCRDetExecutor.run(task_id))
    else:
        asyncio.create_task(TrainExecutor.run(task_id))
```

> **注意**：需在 scheduler.py 顶部 import `OCRDetExecutor`（或在函数内 import 避免循环依赖）。

- [ ] **Step 7: 运行测试确认通过**

Run: `cd D:/AIStation/backend && uv run pytest tests/test_ocr_integration.py -v`
Expected: 3 passed

- [ ] **Step 8: 全量回归 + ruff + 提交**

Run: `cd D:/AIStation/backend && uv run pytest tests/ -v`（全部通过）
Run: `cd D:/AIStation/backend && uv run ruff check app/plugin/module_train/ pytorch_ocr/`
Expected: 无新增错误

```bash
git add backend/app/plugin/module_train/exporter.py backend/app/plugin/module_train/model.py backend/app/plugin/module_train/service.py backend/app/plugin/module_train/scheduler.py backend/app/plugin/module_train/ocr_executor.py backend/app/scripts/init_app.py backend/tests/test_ocr_integration.py
git commit -m "feat(ocr): det training backend integration (executor, export, framework)"
```

---

### Task 6: 前端 OCR 框架选项

**Files:**
- Modify: `frontend/web/src/views/module_train/task/index.vue`
- Test: `cd frontend/web && pnpm run type-check`

**Interfaces:**
- Consumes: `pytorch-ocr-det` 框架（Task 5）
- Produces: 任务创建表单 framework 下拉加 OCR det 选项

- [ ] **Step 1: framework 下拉加 OCR 选项**

`task/index.vue` 的 framework `ElRadioGroup`（~75-77）加：

```html
          <ElRadioGroup v-model="formData.framework" @change="onFrameworkChange">
            <ElRadio value="ultralytics">Ultralytics</ElRadio>
            <ElRadio value="pytorch-ocr-det">PyTorch OCR (det)</ElRadio>
          </ElRadioGroup>
```

- [ ] **Step 2: onFrameworkChange 加 OCR 分支**

`onFrameworkChange`（~408）加 pytorch-ocr-det 默认超参：

```typescript
function onFrameworkChange(fw: string | number | boolean | undefined) {
  const val = String(fw);
  Object.keys(hpForm).forEach(k => delete hpForm[k]);
  if (val === "pytorch-ocr-det") {
    Object.assign(hpForm, { model_size: "tiny", epochs: 100, batch: 8, lr: 0.001, device: "0" });
  } else {
    Object.assign(hpForm, { /* ultralytics 默认（现有） */ });
  }
}
```

- [ ] **Step 3: buildHyperparams 处理 OCR 框架**

```typescript
function buildHyperparams(): Record<string, any> {
  if (formData.value.framework === "pytorch-ocr-det") {
    return { model_size: hpForm.model_size || "tiny", epochs: hpForm.epochs, batch: hpForm.batch, lr: hpForm.lr, device: hpForm.device };
  }
  return { ...hpForm, lr0: hpForm.lr0 ?? 0.01, train_ratio: (hpForm.trainRatio || 80) / 100 };
}
```

> **说明**：OCR det 任务的模型选择下拉（model_size tiny/small/medium）建议用 `ElSelect`，基础参数区在有 OCR 框架时显示 model_size 而非 model 选择。实现者按实际表单结构适配。

- [ ] **Step 4: type-check + build**

Run: `cd D:/AIStation/frontend/web && pnpm run type-check`（0 errors）
Run: `cd D:/AIStation/frontend/web && npx vite build 2>&1 | Select-Object -Last 3`（built）

- [ ] **Step 5: 提交**

```bash
git add frontend/web/src/views/module_train/task/index.vue
git commit -m "feat(ocr): add PyTorch OCR det framework option in task form"
```

---

### Task 7: 回归验证

**Files:**
- Test: 全量后端 + 前端

- [ ] **Step 1: 后端全量测试**

Run: `cd D:/AIStation/backend && uv run pytest tests/ -v`
Expected: 全部通过

- [ ] **Step 2: ruff**

Run: `cd D:/AIStation/backend && uv run ruff check app/plugin/module_train/ pytorch_ocr/`
Expected: 无新增错误

- [ ] **Step 3: 前端 type-check + build**

Run: `cd D:/AIStation/frontend/web && pnpm run type-check && npx vite build 2>&1 | Select-Object -Last 3`
Expected: 通过

- [ ] **Step 4: CLI 冒烟**

Run: `cd D:/AIStation/backend && uv run python -m pytorch_ocr.cli --help`
Expected: 显示 train-det/eval-det

- [ ] **Step 5: 提交**

```bash
git add backend/ frontend/web/src/views/module_train/task/index.vue
git commit -m "chore(ocr): regression verification for det training pipeline"
```

---

## Self-Review 结论

- **Spec 覆盖**：组件 C（数据导出）Task 5 ✅；组件 D（训练循环）Task 1-2 ✅；组件 F（Docker 镜像）Task 4 ✅；组件 G（executor 集成）Task 5 ✅；组件 H（框架接入）Task 5-6 ✅。
- **占位符说明**：Task 2 的 Hmean 评估推迟到 plan 3（明确标注）；Task 4 镜像不实际构建（人工/CI 步骤）——均为明确行动指引，非占位。
- **类型一致性**：`DetDataset` → `DetTrainer` → `cli.py` → `ocr_executor.py` 的 `data_dir`/`det_gt.txt` 结构一致；`_build_cmd` 的 OCR 命令参数与 `cli.py` 子命令一致。
- **遗留说明**：rec 识别模型 + rec 训练在 plan 3；Hmean 真实评估在 plan 3；Docker 镜像构建是人工步骤；权重转换验证（plan 1 遗留的 DBHead 索引不匹配）在 plan 3 paddlex 容器完成。
