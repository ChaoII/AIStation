"""det 训练器：DB loss + Hmean 评估 + best.pt 保存。自研实现。"""
import os

import torch
from torch.utils.data import DataLoader

from ..data.det_dataset import DetDataset
from ..modeling.backbones.pplcnetv4 import PPLCNetV4
from ..modeling.heads.det_db_head import DBHead
from ..modeling.losses.db_loss import DBLoss
from ..modeling.necks.rep_lk_fpn import RepLKFPN
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
        """Hmean 评估。plan 3 完善真实指标；此处提供接口骨架。"""
        self.net.eval()
        # 简化：加载 best.pt 后跑前向（评估逻辑在 plan 3 完善）
        return {}
