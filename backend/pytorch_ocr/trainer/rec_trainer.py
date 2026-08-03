"""rec 训练器：MultiLoss + 字符级准确率评估 + best.pt。自研实现。"""
import os

import torch
from torch.utils.data import DataLoader

from ..data.rec_dataset import RecDataset
from ..modeling.backbones.pplcnetv4 import PPLCNetV4
from ..modeling.heads.rec_multi_head import MultiHead
from ..modeling.losses.rec_loss import MultiLoss


class RecTrainer:
    def __init__(self, config: dict, device: str = "cuda:0"):
        self.config = config
        self.device = device if torch.cuda.is_available() or device == "cpu" else "cpu"
        size = config.get("model_size", "tiny")
        num_classes = config.get("num_classes", 100)
        max_text_length = config.get("max_text_length", 25)
        self.backbone = PPLCNetV4(model_size=size, det=False)
        # rec 骨干输出通道（plan 1：tiny rec 单特征，需确认通道数）
        backbone_out = config.get("backbone_out_channels", 160)
        self.head = MultiHead(
            in_channels=backbone_out,
            out_channels=num_classes,
            max_text_length=max_text_length,
            nrtr_dim=config.get("nrtr_dim", 384),
        )
        self.loss_fn = MultiLoss(blank=num_classes - 1)
        self.net = torch.nn.ModuleDict({"backbone": self.backbone, "head": self.head})
        self.net.to(self.device)

    def _train_step(self, batch):
        img, label_ctc, label_gtc, length = [
            b.to(self.device) if isinstance(b, torch.Tensor) else b for b in batch
        ]
        feats = self.backbone(img)  # rec: [B,C,1,W]
        targets = {
            "label_ctc": label_ctc,
            "length": length,
            "label_gtc": label_gtc,
        }
        preds = self.head(feats, targets)  # NRTR 训练需要 targets 做 teacher forcing
        loss = self.loss_fn(preds, targets)
        return loss

    def train(self, data_dir, num_epochs=100, batch_size=128, output_dir="./output",
              workers=0, lr=0.001):
        dataset = RecDataset(
            data_dir=data_dir,
            label_path=os.path.join(data_dir, "train_list.txt"),
            image_shape=tuple(self.config.get("image_shape", (48, 320))),
            max_text_length=self.config.get("max_text_length", 25),
        )
        if len(dataset) == 0:
            raise ValueError("train_list.txt 无有效数据，数据集为空")
        loader = DataLoader(dataset, batch_size=batch_size, shuffle=True,
                            num_workers=workers, collate_fn=self._collate)
        optimizer = torch.optim.Adam(self.net.parameters(), lr=lr, betas=(0.9, 0.999))
        scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=num_epochs)
        os.makedirs(output_dir, exist_ok=True)
        best_loss = float("inf")
        for epoch in range(1, num_epochs + 1):
            self.net.train()
            total = 0.0
            n = 0
            for batch in loader:
                optimizer.zero_grad()
                loss = self._train_step(batch)
                loss.backward()
                optimizer.step()
                total += loss.item()
                n += 1
            scheduler.step()
            avg = total / max(n, 1)
            print(f"epoch {epoch} avg_loss {avg:.4f} "
                  f"lr {scheduler.get_last_lr()[0]:.6f}", flush=True)
            if avg < best_loss:
                best_loss = avg
                torch.save(self.net.state_dict(), os.path.join(output_dir, "best.pt"))
        print("training done", flush=True)
        return os.path.join(output_dir, "best.pt")

    def _collate(self, batch):
        """RecDataset 返回 (image, label_ctc, label_gtc[25], length) 4 元组。"""
        images = torch.stack([b[0] for b in batch])
        label_ctc = [b[1] for b in batch]
        label_gtc = torch.stack([b[2] for b in batch])
        lengths = torch.tensor([b[3] for b in batch], dtype=torch.long)
        return images, label_ctc, label_gtc, lengths

    def eval(self, data_dir, output_dir="./output"):
        """评估：字符级准确率。plan 3b 完善真实指标。"""
        return {}
