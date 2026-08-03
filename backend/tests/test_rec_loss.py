"""rec 损失测试（MultiLoss = CTCLoss + NRTRLoss）。

契约：
- num_classes = 6906，CTC blank = 0（索引 0 保留给 blank，对齐官方 PP-OCRv6）。
- ``label_ctc``: list[int]（真实字符索引 1..N，trim 到 max_text_length）。
- ``label_gtc``: LongTensor (max_text_length,)，pad token = 0（blank），非真实字符。
- 因此 NRTRLoss 按 ``length`` 掩码 pad 位置（0 = blank 不参与损失）。
"""
import torch
import torch.nn.functional as F

from pytorch_ocr.modeling.losses.rec_loss import CTCLoss, MultiLoss, NRTRLoss

NUM_CLASSES = 6906


def test_multiloss_forward():
    loss = MultiLoss()
    batch = {
        "ctc": torch.randn(2, 20, NUM_CLASSES),
        "nrtr": torch.randn(2, 25, NUM_CLASSES),
    }
    targets = {
        "label_ctc": [torch.tensor([1, 2, 3]), torch.tensor([4, 5])],
        "length": torch.tensor([3, 2]),
        "label_gtc": torch.randint(1, NUM_CLASSES, (2, 25)),
    }
    # 模拟 RecDataset 的 pad：length 之后的位置是 0（blank）
    targets["label_gtc"][0, 3:] = 0
    targets["label_gtc"][1, 2:] = 0
    val = loss(batch, targets)
    assert isinstance(val, torch.Tensor)
    assert val.dim() == 0
    assert torch.isfinite(val)


def test_ctc_blank_is_zero():
    """CTC blank 必须为 0（官方 PP-OCRv6 ctc_blank_idx=0），而非 num_classes-1。"""
    ctc = CTCLoss()
    assert ctc.blank == 0
    pred = torch.randn(2, 20, NUM_CLASSES)
    targets = {
        "label_ctc": [torch.tensor([1, 2, 3]), torch.tensor([4, 5])],
        "length": torch.tensor([3, 2]),
    }
    val = ctc(pred, targets)
    assert val.dim() == 0
    assert torch.isfinite(val)


def test_nrtr_loss_masks_pad_by_length():
    """NRTRLoss 按 length 掩码 pad 位置（0 = blank，不参与损失）。

    length=1 时位置 1-3 是 pad（应忽略），位置 0 是真实字符（索引 1）。
    若实现错误地把所有 0 当 ignore，真实字符位置也会被吞掉。
    正确实现 l1 应等于仅位置 0 的交叉熵。
    """
    loss = NRTRLoss()
    logits = torch.tensor(
        [[[0.0, 10.0, 0.0], [0.0, 0.0, 10.0], [0.0, 0.0, 10.0], [0.0, 0.0, 10.0]]]
    )
    gt = torch.zeros(1, 4, dtype=torch.long)
    gt[0, 0] = 1  # 真实字符（索引 1）
    # length=1: 位置 0 是真实字符，位置 1-3 是 pad
    l1 = loss(logits, {"label_gtc": gt, "length": torch.tensor([1])})
    expected_pos0 = F.cross_entropy(logits[:, 0:1].reshape(-1, 3), gt[:, 0:1].reshape(-1))
    assert torch.isfinite(l1)
    assert torch.isclose(l1, expected_pos0)
    # length=4: 全部位置都是真实字符
    gt4 = gt.clone()
    gt4[0, 1] = 1
    l4 = loss(logits, {"label_gtc": gt4, "length": torch.tensor([4])})
    expected_all = F.cross_entropy(logits.reshape(-1, 3), gt4.reshape(-1))
    assert torch.isclose(l4, expected_all)
    assert l1.item() < l4.item()
