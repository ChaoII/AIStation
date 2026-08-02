"""PPLCNetV4 骨干网络形状测试。"""
import torch

from pytorch_ocr.modeling.backbones.pplcnetv4 import PPLCNetV4, StemBlock


def test_pplcnetv4_tiny_forward_shapes():
    net = PPLCNetV4(model_size="tiny", det=True)
    x = torch.randn(1, 3, 640, 640)
    outs = net(x)
    assert isinstance(outs, list)
    # det 模式输出 P2-P5 共 4 级多尺度特征
    assert len(outs) == 4
    shapes = [tuple(o.shape) for o in outs]
    for o in outs:
        assert o.dim() == 4
        assert o.shape[0] == 1 and o.shape[1] > 0
    # 通道数逐级递增、分辨率逐级减半
    chans = [s[1] for s in shapes]
    assert chans == sorted(chans) and len(set(chans)) == 4
    assert all(shapes[i][2] == shapes[i + 1][2] * 2 for i in range(3))


def test_pplcnetv4_model_sizes_construct():
    for size in ("tiny", "small", "medium"):
        net = PPLCNetV4(model_size=size, det=True)
        assert net is not None
        assert len(net.out_channels) == 4


def test_pplcnetv4_det_flag():
    # det=True 时输出多尺度特征；det=False（rec 用）输出单特征
    net_det = PPLCNetV4(model_size="tiny", det=True)
    outs_det = net_det(torch.randn(1, 3, 640, 640))
    assert len(outs_det) == 4
    net_rec = PPLCNetV4(model_size="tiny", det=False)
    outs_rec = net_rec(torch.randn(1, 3, 48, 320))
    assert isinstance(outs_rec, torch.Tensor)


def test_stem_rep_equivalence():
    """stem 含 kernel=2 'SAME' 卷积，rep() 前后前向输出必须逐位一致。

    偶数核 ``"same"`` 是非对称填充（右/下各补 1），此前 fuse 会把
    ``padding=(0, 1)`` 按每维对称解释，导致形状与数值双双错误。
    """
    stem = StemBlock()
    stem.eval()
    x = torch.randn(2, 3, 64, 64)
    with torch.no_grad():
        before = stem(x)
        stem.rep()
        after = stem(x)
    assert torch.max(torch.abs(before - after)) < 1e-4


def test_pplcnetv4_tiny_rep_equivalence():
    """tiny det 整网 rep() 前后 4 级多尺度特征必须逐位一致。"""
    net = PPLCNetV4(model_size="tiny", det=True)
    net.eval()
    x = torch.randn(1, 3, 128, 128)
    with torch.no_grad():
        before = [o.clone() for o in net(x)]
        net.rep()
        after = [o.clone() for o in net(x)]
    assert len(before) == len(after) == 4
    for b, a in zip(before, after, strict=True):
        assert torch.max(torch.abs(b - a)) < 1e-4
