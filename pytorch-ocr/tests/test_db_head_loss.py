"""DBHead 与 DBLoss 测试。

DBHead 输出分辨率（对齐参考 pytorchocr/modeling/heads/det_db_head.py）：
DBHead 输入 fuse 特征 H×W（640 输入 → FPN P2 = 160）。binarize/thresh 两个
Head 子网络各含 2 次 stride=2 的 ConvTranspose2d（kernel=2），故输出被上采样
4×：160 → conv1(160) → convT1(320) → convT2(640)。

本文件按真实参考行为断言 160 → 640（修正计划占位的 160）。
"""
import torch

from pytorch_ocr.modeling.backbones.pplcnetv4 import PPLCNetV4
from pytorch_ocr.modeling.heads.det_db_head import DBHead
from pytorch_ocr.modeling.losses.db_loss import DBLoss
from pytorch_ocr.modeling.necks.rep_lk_fpn import RepLKFPN


def test_dbhead_train_outputs_3_channels():
    head = DBHead(in_channels=64, k=50)
    head.train()
    x = torch.randn(2, 64, 160, 160)
    out = head(x)
    assert "maps" in out
    # 参考行为：2 次 stride=2 ConvTranspose 上采样 4×
    assert out["maps"].shape == (2, 3, 640, 640)


def test_dbhead_eval_outputs_1_channel():
    head = DBHead(in_channels=64, k=50)
    head.eval()
    x = torch.randn(2, 64, 160, 160)
    out = head(x)
    assert out["maps"].shape == (2, 1, 640, 640)


def test_dbhead_outputs_are_probabilities():
    head = DBHead(in_channels=64, k=50)
    head.train()
    x = torch.randn(1, 64, 16, 16)
    out = head(x)
    maps = out["maps"]
    assert torch.isfinite(maps).all()
    assert maps.min() >= 0.0 and maps.max() <= 1.0


def test_dbloss_forward():
    loss = DBLoss(alpha=5, beta=10, main_loss_type="DiceFocalLoss")
    pred = torch.rand(2, 3, 32, 32).clamp(1e-4, 1 - 1e-4)
    gt = {
        "shrink_map": torch.randint(0, 2, (2, 1, 32, 32)).float(),
        "shrink_mask": torch.ones(2, 1, 32, 32),
        "threshold_map": torch.rand(2, 1, 32, 32),
        "threshold_mask": torch.ones(2, 1, 32, 32),
    }
    loss_val = loss(pred, gt)
    assert isinstance(loss_val, torch.Tensor)
    assert loss_val.dim() == 0
    assert torch.isfinite(loss_val)


def test_dbloss_with_real_dbhead_output():
    """DBLoss 在真实 DBHead 训练输出（640x640）上前向为标量。"""
    head = DBHead(in_channels=64, k=50)
    loss = DBLoss(alpha=5, beta=10, main_loss_type="DiceFocalLoss")
    head.train()
    pred = head(torch.randn(2, 64, 160, 160))
    gt = {
        "shrink_map": torch.randint(0, 2, (2, 1, 640, 640)).float(),
        "shrink_mask": torch.ones(2, 1, 640, 640),
        "threshold_map": torch.rand(2, 1, 640, 640),
        "threshold_mask": torch.ones(2, 1, 640, 640),
    }
    loss_val = loss(pred["maps"], gt)
    assert isinstance(loss_val, torch.Tensor)
    assert loss_val.dim() == 0
    assert torch.isfinite(loss_val)


def test_dbhead_end_to_end_pplcnetv4_fpn_dbhead():
    """Task 2 延后的端到端测试：PPLCNetV4 -> RepLKFPN -> DBHead 全链路形状。"""
    backbone = PPLCNetV4(model_size="tiny", det=True)
    fpn = RepLKFPN(in_channels=backbone.feat_channels, out_channels=64)
    head = DBHead(in_channels=64, k=50)
    backbone.train()
    fpn.train()
    head.train()
    x = torch.randn(1, 3, 640, 640)
    feats = backbone(x)
    fused = fpn(feats)
    assert isinstance(fused, dict)
    assert fused["fuse"].shape == (1, 64, 160, 160)
    maps = head(fused["fuse"])["maps"]
    assert maps.shape == (1, 3, 640, 640)
