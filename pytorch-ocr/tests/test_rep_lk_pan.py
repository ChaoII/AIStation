"""RepLKPAN 特征融合形状测试。"""
import torch

from pytorch_ocr.modeling.backbones.pplcnetv4 import PPLCNetV4
from pytorch_ocr.modeling.necks.rep_lk_pan import IntraCLBlock, RepLKPAN
from pytorch_ocr.trainer.det_trainer import DetTrainer


def test_rep_lk_pan_forward_shapes():
    """tiny backbone → RepLKPAN(out_channels=256, intracl=True) 前向形状。"""
    backbone = PPLCNetV4(model_size="tiny", det=True)
    pan = RepLKPAN(in_channels=backbone.feat_channels, out_channels=256, intracl=True)
    feats = backbone(torch.randn(1, 3, 640, 640))
    # 训练模式：返回 dict，fuse 通道数=out_channels（4×out/4）
    out = pan(feats)
    assert isinstance(out, dict)
    assert "fuse" in out
    assert out["fuse"].shape == (1, 256, 160, 160)
    assert out["aux_p4"].shape == (1, 256, 40, 40)
    assert out["aux_p3"].shape == (1, 256, 80, 80)
    assert out["aux_p2"].shape == (1, 256, 160, 160)
    # eval 模式：返回单张量（供推理/权重导出）
    pan.eval()
    out = pan(feats)
    assert isinstance(out, torch.Tensor)
    assert out.shape == (1, 256, 160, 160)


def test_rep_lk_pan_default_no_intracl():
    """intracl 缺省为 False，不构造 IntraCLBlock。"""
    pan = RepLKPAN(in_channels=[32, 48, 64, 160], out_channels=64)
    assert pan.intracl is False
    assert not hasattr(pan, "incl1")


def test_det_trainer_medium_neck_constructs():
    """medium 配置（RepLKPAN + intracl + DBHead aux）CPU 上可正常构造。"""
    config = {
        "model_size": "medium",
        "neck": "rep_lk_pan",
        "out_channels": 256,
        "aux_in_channels": 256,
        "intracl": True,
    }
    trainer = DetTrainer(config, device="cpu")
    assert isinstance(trainer.fpn, RepLKPAN)
    assert trainer.fpn.out_channels == 256
    assert trainer.fpn.intracl is True
    # 端到端前向：fuse(256) -> DBHead；aux 输入通道须等于 aux_in_channels
    feats = trainer.backbone(torch.randn(1, 3, 128, 128))
    fused = trainer.fpn(feats)
    maps = trainer.head(fused)
    assert maps["maps"].shape == (1, 3, 128, 128)
    assert maps["aux_maps_p4"].shape == (1, 3, 128, 128)
    assert maps["aux_maps_p3"].shape == (1, 3, 128, 128)
    assert maps["aux_maps_p2"].shape == (1, 3, 128, 128)


def test_intracl_block_shapes():
    """IntraCLBlock 输入输出形状一致。"""
    block = IntraCLBlock(in_channels=64, reduce_factor=2)
    x = torch.randn(1, 64, 40, 40)
    out = block(x)
    assert out.shape == (1, 64, 40, 40)
