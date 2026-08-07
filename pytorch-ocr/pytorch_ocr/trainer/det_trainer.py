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
from ..modeling.necks.rep_lk_pan import RepLKPAN
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
        out_channels = config.get("out_channels", 64)
        aux_in = config.get("aux_in_channels", 0)
        self.backbone = PPLCNetV4(model_size=size, det=True)
        neck_name = config.get("neck", "rep_lk_fpn")
        if neck_name == "rep_lk_pan":
            self.fpn = RepLKPAN(in_channels=self.backbone.feat_channels,
                                out_channels=out_channels,
                                intracl=config.get("intracl", False))
        else:
            self.fpn = RepLKFPN(in_channels=self.backbone.feat_channels,
                                out_channels=out_channels,
                                dilated_kernel_size=config.get("dilated_kernel_size", 5))
        self.head = DBHead(in_channels=out_channels,
                           k=config.get("k", 50),
                           aux_in_channels=aux_in)
        self.loss_fn = DBLoss(alpha=config.get("alpha", 5),
                              beta=config.get("beta", 10),
                              main_loss_type=config.get("main_loss_type", "DiceFocalLoss"),
                              aux_weight_p4=config.get("aux_weight_p4", 0.2),
                              aux_weight_p3=config.get("aux_weight_p3", 0.3),
                              aux_weight_p2=config.get("aux_weight_p2", 0.4))
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
        # 预训练权重微调（官方转换的 .pt）
        if self.config.get("pretrained"):
            state = torch.load(self.config["pretrained"], map_location="cpu")
            # 兼容 neck.* -> fpn.* 前缀
            remap = {}
            for k, v in state.items():
                if k.startswith("neck."):
                    remap["fpn." + k[len("neck."):]] = v
                else:
                    remap[k] = v
            r = self.net.load_state_dict(remap, strict=False)
            print(f"[det] loaded pretrained {self.config['pretrained']} "
                  f"(missing={len(r.missing_keys)}, unexpected={len(r.unexpected_keys)})", flush=True)
        # 冻结策略：微调时冻结 backbone+fpn，只训练 head，保留预训练检测能力
        # （官方 PP-OCRv6 det 微调也冻结主干，避免 BN 梯度爆炸 + 灾难性遗忘）
        if self.config.get("freeze_backbone", False) and self.config.get("pretrained"):
            for name, p in self.net.named_parameters():
                if name.startswith("head."):
                    p.requires_grad = True
                else:
                    p.requires_grad = False
            self.frozen = True
            print("[det] freeze backbone+fpn, only head trainable", flush=True)
        else:
            self.frozen = False

    def _train_step(self, batch):
        img, shrink_map, shrink_mask, thresh_map, thresh_mask = [
            b.to(self.device) for b in batch
        ]
        feats = self.backbone(img)
        fused = self.fpn(feats)  # train: dict {fuse, aux_*}; eval: tensor
        maps = self.head(fused)  # dict {maps, aux_maps_p4/p3/p2} 或 (N,3,H,W)
        if isinstance(maps, dict):
            preds = maps
        else:
            preds = {"maps": maps}
        gt = {
            "shrink_map": shrink_map,
            "shrink_mask": shrink_mask,
            "threshold_map": thresh_map,
            "threshold_mask": thresh_mask,
        }
        loss = self.loss_fn(preds, gt)
        return loss

    def train(self, data_dir, num_epochs=100, batch_size=8, output_dir="./output",
              workers=4, lr=0.001):
        dataset = DetDataset(gt_dir=os.path.join(data_dir, "images"),
                             label_path=os.path.join(data_dir, "det_gt.txt"),
                             image_shape=tuple(self.config.get("image_shape", (640, 640))),
                             use_aug=self.config.get("use_aug", True),
                             use_iaa=self.config.get("use_iaa", True),
                             use_color_jitter=self.config.get("use_color_jitter", True),
                             use_perspective=self.config.get("use_perspective", False),
                              copy_paste=self.config.get("copy_paste", False),
                              ext_data_dir=self.config.get("ext_data_dir") or data_dir)
        if len(dataset) == 0:
            raise ValueError("det_gt.txt 无有效标注，数据集为空")
        loader = DataLoader(dataset, batch_size=batch_size, shuffle=True,
                            num_workers=workers)
        optimizer = torch.optim.Adam(
            [p for p in self.net.parameters() if p.requires_grad],
            lr=lr, betas=(0.9, 0.999),
            weight_decay=self.config.get("l2_weight_decay", 1e-5))
        # 官方 PaddleOCR：lr_scheduler 每 batch step，Cosine 全程按总 step 数。
        # T_max = num_epochs * steps_per_epoch；warmup_epochs 前线性升温（也按 step）。
        steps_per_epoch = max(len(loader), 1)
        total_steps = num_epochs * steps_per_epoch
        warmup_epochs = self.config.get("warmup_epochs", 0)
        if warmup_epochs > 0:
            warmup_steps = warmup_epochs * steps_per_epoch
            from torch.optim.lr_scheduler import LinearLR, SequentialLR
            scheduler = SequentialLR(
                optimizer,
                [LinearLR(optimizer, start_factor=1e-3, total_iters=warmup_steps),
                 torch.optim.lr_scheduler.CosineAnnealingLR(
                     optimizer, T_max=max(total_steps - warmup_steps, 1))],
                milestones=[warmup_steps])
        else:
            scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(
                optimizer, T_max=total_steps)
        os.makedirs(output_dir, exist_ok=True)
        # EMA：ema_type="simple"（clone 初始化 + 固定 decay）或 "official"
        # （官方 ModelEMA：zeros + threshold decay + bias correction）
        ema_decay = self.config.get("ema_decay", 0.9998)
        use_ema = ema_decay > 0 and not self.frozen
        ema = None
        ema_simple = None
        if use_ema:
            if self.config.get("ema_type", "simple") == "official":
                from ..trainer.ema import ModelEMA
                ema = ModelEMA(self.net, decay=ema_decay,
                               ema_decay_type=self.config.get("ema_decay_type", "threshold"))
            else:
                ema_simple = {
                    k: v.detach().clone() for k, v in self.net.state_dict().items()
                }
        best_loss = float("inf")
        best_hmean = 0.0
        for epoch in range(1, num_epochs + 1):
            if self.frozen:
                # 冻结时：backbone+fpn 保持 eval（BN running stats 不变），head 训练
                self.net.eval()
                self.head.train()
            else:
                self.net.train()
            total_loss = 0.0
            n_batches = 0
            for batch in loader:
                optimizer.zero_grad()
                loss = self._train_step(batch)
                loss.backward()
                optimizer.step()
                if use_ema:
                    if ema is not None:
                        ema.update(self.net)
                    elif ema_simple is not None:
                        with torch.no_grad():
                            for k, v in self.net.state_dict().items():
                                if k in ema_simple and v.dtype.is_floating_point:
                                    ema_simple[k].mul_(ema_decay).add_(v, alpha=1 - ema_decay)
                scheduler.step()
                total_loss += loss.item()
                n_batches += 1
                print(f"epoch {epoch} batch {n_batches} loss {loss.item():.4f}",
                      flush=True)
            avg = total_loss / max(n_batches, 1)
            print(f"epoch {epoch} avg_loss {avg:.4f} "
                  f"lr {optimizer.param_groups[0]['lr']:.6f}", flush=True)
            # 官方 PaddleOCR：用 EMA 权重做 eval，按 eval hmean 选 best（而非 train loss）。
            # 每 eval_interval epoch 跑一次 eval，控制开销。
            eval_interval = self.config.get("eval_interval", 5)
            if use_ema:
                cand_state = ema.apply() if ema is not None else ema_simple
            else:
                cand_state = self.net.state_dict()
            if epoch % eval_interval == 0 or epoch == num_epochs:
                saved = self.net.state_dict()
                self.net.load_state_dict(cand_state)
                try:
                    m = self.eval(data_dir=data_dir, output_dir=output_dir)
                    cur_hmean = m.get("hmean", 0.0)
                    print(f"epoch {epoch} eval hmean {cur_hmean:.4f}", flush=True)
                    if cur_hmean > best_hmean:
                        best_hmean = cur_hmean
                        torch.save(cand_state, os.path.join(output_dir, "best.pt"))
                    elif not os.path.isfile(os.path.join(output_dir, "best.pt")):
                        # 首个 eval 无 best 时兜底保存（防空 best.pt）
                        torch.save(cand_state, os.path.join(output_dir, "best.pt"))
                finally:
                    self.net.load_state_dict(saved)
            else:
                # 无 eval 时按 loss 兜底保存（防早期无 best）
                if avg < best_loss:
                    best_loss = avg
                    torch.save(cand_state, os.path.join(output_dir, "best.pt"))
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
            for img_name, polys, *_ in dataset.items:
                img = cv2.imread(os.path.join(data_dir, "images", img_name),
                                 cv2.IMREAD_COLOR)
                if img is None:
                    continue
                h, w = img.shape[:2]
                # 官方 PP-OCRv6 DetResizeForTest（默认 limit_side_len=736, limit_type=min，
                # round 到 32 倍数）：min 边 <736 才放大，否则保持近原尺寸
                limit = self.config.get("eval_limit_side_len", 736)
                ratio = 1.0
                if min(h, w) < limit:
                    ratio = float(limit) / min(h, w)
                rh = max(int(round(h * ratio / 32) * 32), 32)
                rw = max(int(round(w * ratio / 32) * 32), 32)
                input_img = cv2.resize(img, (rw, rh))
                input_img = (input_img.astype(np.float32) / 255.0 - _MEAN) / _STD
                input_t = torch.from_numpy(input_img).permute(2, 0, 1)
                input_t = input_t.unsqueeze(0).float().to(self.device)
                feats = self.backbone(input_t)
                fused = self.fpn(feats)
                if isinstance(fused, dict):
                    fused = fused["fuse"]
                maps = self.head(fused)["maps"]
                # postprocess 用 resize 后尺寸，框映射回原图由 compute_det_metrics 处理
                boxes = self.postprocess(maps.cpu(), [[rh, rw]])
                # 预测框在 resize 图坐标，映射回原图坐标以便与 GT IoU 匹配
                box_list = []
                for box in boxes[0] if boxes else []:
                    box = np.asarray(box, dtype=np.float32).reshape(-1, 2)
                    box[:, 0] = box[:, 0] * w / rw
                    box[:, 1] = box[:, 1] * h / rh
                    box_list.append(box)
                pred_boxes.append(box_list)
                gt_boxes.append([p.tolist() for p in polys])
        metrics = compute_det_metrics(pred_boxes, gt_boxes)
        metrics["num_images"] = len(gt_boxes)
        return metrics
