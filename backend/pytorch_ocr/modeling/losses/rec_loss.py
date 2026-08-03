"""rec 损失：CTCLoss + NRTRLoss 组合（对齐 PaddleOCR MultiLoss）。自研实现。

契约（与 RecDataset / MultiHead 对齐）：
- num_classes = 6906，CTC blank = 6905（字符集最后索引）。
- ``label_ctc``: list[int]（真实字符索引，trim 到 max_text_length）。
- ``label_gtc``: LongTensor (max_text_length,) 张量，pad token = 0。
- ``length``: 每样本真实长度，用于区分 NRTR 的 pad 位置与真实字符 '!'（索引 0）。

NRTR pad 处理：pad 位置与真实字符 '!' 的索引都是 0，因此不能 ``ignore_index=0``
（会吞掉真实 '!'）。这里按 ``length`` 将真正的 pad 位置显式置为 ``-100``，
并用 ``ignore_index=-100`` 计算交叉熵。
"""
import torch
import torch.nn as nn
import torch.nn.functional as F

_CTC_BLANK = 6905  # num_classes - 1
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
        # predicts: [B, W, C] logits -> [W, B, C] for CTCLoss
        pred = predicts.permute(1, 0, 2)
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
    """NRTR 交叉熵损失：按 length 掩码 pad 位置，保留真实 '!'（索引 0）。"""

    def forward(self, predicts, batch):
        # predicts: [B, T, C]
        targets = batch["label_gtc"].long().clone()
        lengths = batch.get("length")
        if lengths is not None:
            # 只有 t >= length[i] 的位置是 pad；真实 '!'（idx 0）参与损失
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
