"""PPLCNetV4 骨干网络形状测试。"""
import torch

from pytorch_ocr.modeling.backbones.pplcnetv4 import PPLCNetV4


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
