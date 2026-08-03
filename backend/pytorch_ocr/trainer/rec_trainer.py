"""rec 训练器：MultiLoss + 字符级准确率评估 + best.pt。自研实现。"""
import os

import torch
from torch.utils.data import DataLoader

from ..data.rec_dataset import RecDataset
from ..modeling.backbones.pplcnetv4 import PPLCNetV4, rec_backbone_out_channels
from ..modeling.heads.rec_multi_head import MultiHead
from ..modeling.losses.rec_loss import MultiLoss
from ..postprocess.rec_postprocess import CTCLabelDecode


def compute_rec_metrics(pred_texts, gt_texts):
    """逐样本计算字符级准确率（位置对齐）与整句准确率。

    返回 ``{char_acc, full_acc, total_chars, total_strings}``。
    """
    total_chars = 0
    correct_chars = 0
    total_strings = 0
    correct_strings = 0
    for pred, gt in zip(pred_texts, gt_texts, strict=False):
        total_strings += 1
        if pred == gt:
            correct_strings += 1
        total_chars += len(gt)
        if gt:
            correct_chars += sum(1 for a, b in zip(pred, gt, strict=False) if a == b)
    char_acc = correct_chars / total_chars if total_chars else 0.0
    full_acc = correct_strings / total_strings if total_strings else 0.0
    return {
        "char_acc": char_acc,
        "full_acc": full_acc,
        "total_chars": total_chars,
        "total_strings": total_strings,
    }


class RecTrainer:
    def __init__(self, config: dict, device: str = "cuda:0"):
        self.config = config
        self.device = device if torch.cuda.is_available() or device == "cpu" else "cpu"
        size = config.get("model_size", "tiny")
        num_classes = config.get("num_classes", 100)
        max_text_length = config.get("max_text_length", 25)
        self.backbone = PPLCNetV4(model_size=size, det=False)
        # rec 骨干输出通道（tiny=160 / small=384 / medium=768），按 model_size 推导
        backbone_out = config.get("backbone_out_channels") or rec_backbone_out_channels(size)
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
        """评估：字符级准确率 + 整句准确率（用 CTCHead 解码结果对比 GT 标签）。

        标签文件优先用 ``eval_list.txt``，不存在则回退到 ``train_list.txt``。
        """
        self.net.eval()
        image_shape = tuple(self.config.get("image_shape", (48, 320)))
        label_path = os.path.join(data_dir, "eval_list.txt")
        if not os.path.isfile(label_path):
            label_path = os.path.join(data_dir, "train_list.txt")
        dict_path = self.config.get("dict_path")
        dataset = RecDataset(
            data_dir=data_dir,
            label_path=label_path,
            image_shape=image_shape,
            max_text_length=self.config.get("max_text_length", 25),
            dict_path=dict_path,
        )
        if len(dataset) == 0:
            return {
                "char_acc": 0.0, "full_acc": 0.0,
                "total_chars": 0, "total_strings": 0,
            }
        loader = DataLoader(dataset, batch_size=1, shuffle=False, num_workers=0,
                            collate_fn=self._collate)
        decode = CTCLabelDecode(dict_path=dict_path)
        pred_texts = []
        gt_texts = []
        with torch.no_grad():
            for batch in loader:
                img = batch[0].to(self.device)
                feats = self.backbone(img)
                preds = self.head(feats)  # eval: dict {ctc, nrtr}
                pred_texts.extend(decode(preds["ctc"]))
                for idx, length in zip(batch[1], batch[3], strict=False):
                    chars = [int(i) for i in idx][: int(length)]
                    gt_texts.append(
                        "".join(dataset.char_dict.idx_to_char[i] for i in chars)
                    )
        metrics = compute_rec_metrics(pred_texts, gt_texts)
        return metrics
