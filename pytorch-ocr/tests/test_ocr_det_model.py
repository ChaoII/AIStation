"""det 模型端到端前向（骨架+FPN+Head，含 DBPostProcess 后处理接缝）。

全链路：PPLCNetV4(tiny,det) → RepLKFPN → DBHead → DBPostProcess。

模式差异（真实接口）：
- eval: RepLKFPN 返回单张量 fuse (1,64,160,160)；DBHead 输出 1 通道
  shrink_map {"maps": (N,1,640,640)}。
- train: RepLKFPN 返回 dict {fuse, aux_p2, aux_p3, aux_p4}；
  DBHead 需喂 fuse 张量，输出 3 通道 {"maps": (N,3,640,640)}。
"""
import torch

from pytorch_ocr.modeling.backbones.pplcnetv4 import PPLCNetV4
from pytorch_ocr.modeling.heads.det_db_head import DBHead
from pytorch_ocr.modeling.necks.rep_lk_fpn import RepLKFPN
from pytorch_ocr.postprocess.db_postprocess import DBPostProcess


def _build_chain():
    backbone = PPLCNetV4(model_size="tiny", det=True)
    fpn = RepLKFPN(in_channels=backbone.feat_channels, out_channels=64)
    head = DBHead(in_channels=64, k=50)
    return backbone, fpn, head


def test_det_model_full_pipeline_eval():
    """eval 前向：fuse 单张量 → DBHead 单通道 shrink_map → 后处理。"""
    backbone, fpn, head = _build_chain()
    backbone.eval()
    fpn.eval()
    head.eval()
    x = torch.randn(1, 3, 640, 640)
    with torch.no_grad():
        feats = backbone(x)
        assert isinstance(feats, list) and len(feats) == 4
        fused = fpn(feats)
        assert isinstance(fused, torch.Tensor)
        assert fused.shape == (1, 64, 160, 160)
        out = head(fused)
    assert out["maps"].shape[0] == 1
    assert out["maps"].shape[1] == 1  # eval 单通道
    assert out["maps"].shape[2:] == (640, 640)
    # 后处理接缝：eval maps + shape_list 返回每图四边形列表
    boxes = DBPostProcess()(out["maps"], [[640, 640]])
    assert isinstance(boxes, list)
    assert len(boxes) == 1


def test_det_model_training_shape():
    """train 前向：fuse dict → DBHead 输出三通道 (shrink/thresh/binary)。"""
    backbone, fpn, head = _build_chain()
    backbone.train()
    fpn.train()
    head.train()
    x = torch.randn(2, 3, 640, 640)
    feats = backbone(x)
    fused = fpn(feats)
    assert isinstance(fused, dict)
    assert fused["fuse"].shape == (2, 64, 160, 160)
    out = head(fused["fuse"])
    assert out["maps"].shape == (2, 3, 640, 640)  # train 三通道
