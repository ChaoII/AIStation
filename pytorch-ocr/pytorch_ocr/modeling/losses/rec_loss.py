"""rec 损失：CTCLoss + NRTRLoss 组合（对齐 PaddleOCR MultiLoss）。自研实现。

契约（与 RecDataset / MultiHead 对齐）：
- num_classes = 6906，CTC blank = 0（索引 0 保留给 blank，对齐官方
  PP-OCRv6 ``ctc_blank_idx=0``）。
- ``label_ctc``: list[int]（真实字符索引 1..N，trim 到 max_text_length）。
- ``label_gtc``: LongTensor (max_text_length,) 张量，pad token = 0（blank）。
- ``length``: 每样本真实长度，用于区分 NRTR 的 pad（0 = blank）与真实字符。

NRTR pad 处理：真实字符索引为 1..N，pad token 0 即 blank（非真实字符），
按 ``length`` 将真正的 pad 位置显式置为 ``-100``，用 ``ignore_index=-100``
计算交叉熵。
"""
import torch
import torch.nn as nn
import torch.nn.functional as F

_CTC_BLANK = 0  # 官方 PP-OCRv6 ctc_blank_idx=0
_IGNORE_INDEX = -100


def _as_index_list(label):
    """label_ctc 元素可能是 list[int] 或 tensor，统一为 list[int]。"""
    if isinstance(label, torch.Tensor):
        return label.tolist()
    return label


class CTCLoss(nn.Module):
    def __init__(self, blank=_CTC_BLANK, use_focal_loss=False):
        super().__init__()
        self.blank = blank
        self.use_focal_loss = use_focal_loss

    def forward(self, predicts, batch):
        # predicts: [B, W, C] logits -> log_softmax -> [W, B, C] for CTCLoss
        # F.ctc_loss 期望输入是 log-probs，因此必须显式 log_softmax（不能传 raw logits）
        pred = F.log_softmax(predicts, dim=-1).permute(1, 0, 2)
        label_ctc = batch["label_ctc"]
        lengths = batch.get("length")
        batch_size, max_len = pred.shape[1], pred.shape[0]

        padded = torch.zeros((batch_size, max_len), dtype=torch.long, device=pred.device)
        target_lengths = torch.zeros(batch_size, dtype=torch.long, device=pred.device)
        for i, label in enumerate(label_ctc):
            idx = _as_index_list(label)
            n = int(lengths[i]) if lengths is not None else len(idx)
            n = min(n, len(idx), max_len)
            if n > 0:
                padded[i, :n] = torch.tensor(idx[:n], dtype=torch.long, device=pred.device)
            target_lengths[i] = n
        input_lengths = torch.full((batch_size,), max_len, dtype=torch.long, device=pred.device)
        return F.ctc_loss(pred, padded, input_lengths, target_lengths, blank=self.blank)


class NRTRLoss(nn.Module):
    """NRTR 交叉熵损失：按 length 掩码 pad 位置（0 = blank，非真实字符）。"""

    def forward(self, predicts, batch):
        # predicts: [B, T, C]
        targets = batch["label_gtc"].long().clone()
        lengths = batch.get("length")
        if lengths is not None:
            # 只有 t >= length[i] 的位置是 pad；真实字符索引为 1..N
            for i in range(targets.shape[0]):
                targets[i, int(lengths[i]):] = _IGNORE_INDEX
        else:
            targets[targets == 0] = _IGNORE_INDEX
        return F.cross_entropy(
            predicts.reshape(-1, predicts.shape[-1]),
            targets.reshape(-1),
            ignore_index=_IGNORE_INDEX,
        )


class MultiLoss(nn.Module):
    """CTCLoss + NRTRLoss 组合。"""

    def __init__(self, blank=_CTC_BLANK):
        super().__init__()
        self.ctc_loss = CTCLoss(blank=blank)
        self.nrtr_loss = NRTRLoss()

    def forward(self, predicts: dict, batch: dict):
        total = None
        if "ctc" in predicts:
            total = self.ctc_loss(predicts["ctc"], batch)
        if "nrtr" in predicts:
            nrtr = self.nrtr_loss(predicts["nrtr"], batch)
            total = nrtr if total is None else total + nrtr
        return total
