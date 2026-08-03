"""det 训练器：DB loss + Hmean 评估 + best.pt 保存。自研实现。"""
import os

import cv2
import numpy as np
import torch
from torch.utils.data import DataLoader

from ..data.det_dataset import DetDataset
from ..modeling.backbones.pplcnetv4 import PPLCNetV4
from ..modeling.heads.det_db_head import DBHead
from ..modeling.losses.db_loss import DBLoss
from ..modeling.necks.rep_lk_fpn import RepLKFPN
from ..postprocess.db_postprocess import DBPostProcess

_MEAN = np.array([0.485, 0.456, 0.406], dtype=np.float32)
_STD = np.array([0.229, 0.224, 0.225], dtype=np.float32)

_DET_IOU_THRESH = 0.5


def polygon_iou(pred, gt):
    """四边形 IoU（cv2.intersectConvexConvex 求交集面积）。

    ``pred``/``gt`` 为 4×2 点序列（list/ndarray），返回 [0, 1] 的 IoU。
    ``intersectConvexConvex`` 第一返回值即交集面积，无交集时为 0。
    """
    p = np.asarray(pred, dtype=np.float32).reshape(-1, 2)
    g = np.asarray(gt, dtype=np.float32).reshape(-1, 2)
    area_p = abs(cv2.contourArea(p))
    area_g = abs(cv2.contourArea(g))
    ret, _pts = cv2.intersectConvexConvex(p, g)
    inter = float(ret) if ret > 0 else 0.0
    union = area_p + area_g - inter
    return inter / union if union > 0 else 0.0


def compute_det_metrics(pred_boxes, gt_boxes, iou_thresh=_DET_IOU_THRESH):
    """det 评估指标：逐图预测框 vs GT 四边形做 IoU 匹配（一个 GT 只匹配一次）。

    ``pred_boxes``/``gt_boxes``: 逐图四边形列表（list[list[4×2]]）。
    返回 ``{hmean, precision, recall, tp, fp, fn}``。
    """
    tp = 0
    fp = 0
    fn = 0
    for preds, gts in zip(pred_boxes, gt_boxes, strict=False):
        matched = set()
        for p in preds:
            best_iou = 0.0
            best_idx = -1
            for j, g in enumerate(gts):
                if j in matched:
                    continue
                iou = polygon_iou(p, g)
                if iou > best_iou:
                    best_iou = iou
                    best_idx = j
            if best_iou >= iou_thresh and best_idx >= 0:
                tp += 1
                matched.add(best_idx)
            else:
                fp += 1
        fn += len(gts) - len(matched)
    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    hmean = (2 * precision * recall / (precision + recall)
             if (precision + recall) else 0.0)
    return {
        "hmean": hmean,
        "precision": precision,
        "recall": recall,
        "tp": tp,
        "fp": fp,
        "fn": fn,
    }


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
        img, shrink_map, shrink_mask, thresh_map, thresh_mask = [
            b.to(self.device) for b in batch
        ]
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
        if len(dataset) == 0:
            raise ValueError("det_gt.txt 无有效标注，数据集为空")
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
                print(f"epoch {epoch} batch {n_batches} loss {loss.item():.4f}",
                      flush=True)
            scheduler.step()
            avg = total_loss / max(n_batches, 1)
            print(f"epoch {epoch} avg_loss {avg:.4f} "
                  f"lr {scheduler.get_last_lr()[0]:.6f}", flush=True)
            # 保存 best.pt（按 loss 简单判断；真实评估用 Hmean 在 plan 3）
            if avg < best_loss:
                best_loss = avg
                torch.save(self.net.state_dict(), os.path.join(output_dir, "best.pt"))
        print("training done", flush=True)
        return os.path.join(output_dir, "best.pt")

    def eval(self, data_dir, output_dir="./output"):
        """Hmean 评估：跑 det 前向 → DBPostProcess → 与 GT 四边形 IoU 匹配。

        GT 从 ``data_dir/det_gt.txt`` 读取（DetDataset 解析格式），预测框由
        DBPostProcess 缩放回原图坐标系。返回 ``{hmean, precision, recall, ...}``。
        """
        self.net.eval()
        image_shape = tuple(self.config.get("image_shape", (640, 640)))
        dataset = DetDataset(
            gt_dir=os.path.join(data_dir, "images"),
            label_path=os.path.join(data_dir, "det_gt.txt"),
            image_shape=image_shape,
        )
        if len(dataset) == 0:
            return {"hmean": 0.0, "precision": 0.0, "recall": 0.0,
                    "tp": 0, "fp": 0, "fn": 0, "num_images": 0}
        pred_boxes = []
        gt_boxes = []
        with torch.no_grad():
            for img_name, polys in dataset.items:
                img = cv2.imread(os.path.join(data_dir, "images", img_name),
                                 cv2.IMREAD_COLOR)
                if img is None:
                    continue
                h, w = img.shape[:2]
                input_img = cv2.resize(img, image_shape)
                input_img = (input_img.astype(np.float32) / 255.0 - _MEAN) / _STD
                input_t = torch.from_numpy(input_img).permute(2, 0, 1)
                input_t = input_t.unsqueeze(0).float().to(self.device)
                feats = self.backbone(input_t)
                fused = self.fpn(feats)
                if isinstance(fused, dict):
                    fused = fused["fuse"]
                maps = self.head(fused)["maps"]
                boxes = self.postprocess(maps.cpu(), [[h, w]])
                pred_boxes.append(boxes[0] if boxes else [])
                gt_boxes.append([p.tolist() for p in polys])
        metrics = compute_det_metrics(pred_boxes, gt_boxes)
        metrics["num_images"] = len(gt_boxes)
        return metrics
