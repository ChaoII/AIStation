"""rec 双头（CTCHead + NRTRHead + MultiHead）测试。"""
import torch

from pytorch_ocr.modeling.backbones.pplcnetv4 import PPLCNetV4
from pytorch_ocr.modeling.heads.rec_ctc_head import CTCHead
from pytorch_ocr.modeling.heads.rec_multi_head import MultiHead
from pytorch_ocr.modeling.heads.rec_nrtr_head import NRTRHead


def test_ctc_head_forward():
    head = CTCHead(in_channels=80, out_channels=100, mid_channels=80)
    x = torch.randn(2, 20, 80)  # [B, W, C]
    out = head(x)
    assert out.shape == (2, 20, 100)


def test_multi_head_constructs():
    head = MultiHead(
        in_channels=80, out_channels=100, max_text_length=25, nrtr_dim=384
    )
    assert head is not None
    assert head.ctc_head is not None
    assert head.nrtr_head is not None


def test_multi_head_split_out_channels():
    """MultiHead 支持 ctc/nrtr 分开指定词表（官方 PP-OCRv6 双头 6906/6910）。"""
    head = MultiHead(
        in_channels=160,
        out_channels=6906,
        max_text_length=25,
        nrtr_dim=384,
        ctc_out_channels=6906,
        nrtr_out_channels=6910,
    )
    assert head.ctc_head.out_channels == 6906
    assert head.nrtr_head.out_channels == 6910
    assert head.nrtr_head.transformer.out_channels == 6910
    assert head.nrtr_head.transformer.tgt_word_prj.weight.shape[0] == 6910
    assert head.nrtr_head.transformer.embedding.embedding.weight.shape[0] == 6910


def test_multi_head_out_channels_default_to_shared():
    """未显式指定时 ctc/nrtr 共用 out_channels（用户训练产物 6906/6906）。"""
    head = MultiHead(in_channels=160, out_channels=6906, max_text_length=25)
    assert head.ctc_head.out_channels == 6906
    assert head.nrtr_head.out_channels == 6906
    assert head.nrtr_head.transformer.out_channels == 6906


def test_nrtr_head_forward_eval_logits():
    """NRTRHead 推理（贪心解码）输出 logits [B, max_text_length, num_classes]。"""
    head = NRTRHead(in_channels=80, out_channels=100, nrtr_dim=384, max_text_length=25)
    head.eval()
    x = torch.randn(2, 20, 80)  # [B, W, C]
    with torch.no_grad():
        out = head(x)
    assert isinstance(out, torch.Tensor)
    assert out.shape == (2, 25, 100)


def test_multi_head_end_to_end_shapes():
    """PPLCNetV4(rec) -> MultiHead 端到端：ctc [B, W, 6906]、nrtr [B, T, 6906]。"""
    backbone = PPLCNetV4(model_size="tiny", det=False)
    head = MultiHead(
        in_channels=160, out_channels=6906, max_text_length=25, nrtr_dim=384
    )
    backbone.eval()
    head.eval()
    x = torch.randn(2, 3, 48, 320)
    with torch.no_grad():
        feats = backbone(x)
        preds = head(feats)
    assert feats.shape == (2, 160, 1, 40)
    assert set(preds) == {"ctc", "nrtr"}
    assert preds["ctc"].shape == (2, 40, 6906)
    assert preds["nrtr"].shape == (2, 25, 6906)
