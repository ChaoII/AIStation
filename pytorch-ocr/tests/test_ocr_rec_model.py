"""rec 模型端到端前向（PPLCNetV4(rec) → MultiHead → MultiLoss）。

模式差异（真实接口）：
- eval: PPLCNetV4(tiny,det=False) 对 48×320 输入输出 [B,160,1,40]；
  MultiHead 无 targets 前向输出 {"ctc": [B,W,6906], "nrtr": [B,T,6906]}。
- train: 需传 targets（NRTR 教师强制），MultiLoss 返回标量损失。
"""
import torch

from pytorch_ocr.modeling.backbones.pplcnetv4 import PPLCNetV4
from pytorch_ocr.modeling.heads.rec_multi_head import MultiHead
from pytorch_ocr.modeling.losses.rec_loss import MultiLoss

NUM_CLASSES = 6906
MAX_TEXT_LENGTH = 25


def test_rec_model_full_pipeline():
    """eval 前向：backbone → MultiHead，无 targets，输出双头 logits。"""
    backbone = PPLCNetV4(model_size="tiny", det=False)
    head = MultiHead(in_channels=160, out_channels=NUM_CLASSES, max_text_length=25)
    backbone.eval()
    head.eval()
    x = torch.randn(2, 3, 48, 320)
    with torch.no_grad():
        feats = backbone(x)
        preds = head(feats)
    assert feats.shape == (2, 160, 1, 40)
    assert set(preds) == {"ctc", "nrtr"}
    assert preds["ctc"].shape == (2, 40, NUM_CLASSES)
    assert preds["nrtr"].shape == (2, MAX_TEXT_LENGTH, NUM_CLASSES)


def test_rec_model_train_with_loss():
    """train 前向：带 targets 前向 + MultiLoss，返回有限标量。"""
    backbone = PPLCNetV4(model_size="tiny", det=False)
    head = MultiHead(in_channels=160, out_channels=NUM_CLASSES, max_text_length=25)
    loss_fn = MultiLoss()
    backbone.train()
    head.train()
    x = torch.randn(2, 3, 48, 320)
    feats = backbone(x)
    assert feats.shape == (2, 160, 1, 40)
    batch = {
        "label_ctc": [torch.tensor([1, 2])] * 2,
        "length": torch.tensor([2, 2]),
        "label_gtc": torch.randint(0, NUM_CLASSES, (2, MAX_TEXT_LENGTH)),
    }
    preds = head(feats, batch)
    assert set(preds) == {"ctc", "nrtr"}
    assert preds["ctc"].shape == (2, 40, NUM_CLASSES)
    assert preds["nrtr"].shape == (2, MAX_TEXT_LENGTH, NUM_CLASSES)
    loss = loss_fn(preds, batch)
    assert isinstance(loss, torch.Tensor)
    assert loss.dim() == 0
    assert torch.isfinite(loss)
