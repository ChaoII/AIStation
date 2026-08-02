"""RepLKFPN 特征融合形状测试。

说明：DBHead 端到端测试（fuse -> DBHead 输出 160x160x3）在 Task 3 实现
DBHead 后补充，此处仅验证 neck 自身的前向形状。
"""
import torch

from pytorch_ocr.modeling.backbones.pplcnetv4 import PPLCNetV4
from pytorch_ocr.modeling.necks.rep_lk_fpn import RepLKFPN


def test_rep_lk_fpn_forward_shapes():
    backbone = PPLCNetV4(model_size="tiny", det=True)
    fpn = RepLKFPN(in_channels=backbone.feat_channels, out_channels=64)
    feats = backbone(torch.randn(1, 3, 640, 640))
    # 训练模式：返回 dict，含 fuse 主特征（供 DBHead）与 aux 辅助特征
    out = fpn(feats)
    assert isinstance(out, dict)
    assert "fuse" in out
    assert out["fuse"].shape == (1, 64, 160, 160)
    assert out["aux_p4"].shape == (1, 64, 40, 40)
    assert out["aux_p3"].shape == (1, 64, 80, 80)
    assert out["aux_p2"].shape == (1, 64, 160, 160)
    # eval 模式：返回单张量（供推理/权重导出）
    fpn.eval()
    out = fpn(feats)
    assert isinstance(out, torch.Tensor)
    assert out.shape == (1, 64, 160, 160)
