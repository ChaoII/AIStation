"""PPLCNetV4 骨干网络（PP-OCRv6 det/rec 共用，自研实现）。

结构与 PaddleOCR 的 rec_lcnetv4.py（frotms/PaddleOCR2Pytorch 转换）逐层对齐，
保证后续权重转换器可按结构映射 Paddle 权重。
- det=True:  输出 P2-P5 共 4 级多尺度特征（供 RepLKFPN）。
- det=False: 输出自适应池化后的单特征张量 [B, C, 1, W]（供 rec 头）。
"""
import torch
import torch.nn as nn
import torch.nn.functional as F

# ---------------------------------------------------------------------------
# 网络配置表（与 PaddleOCR 一致）
# 每行 block 配置: [dw_size, in_channels, out_channels, stride, use_se]
# ---------------------------------------------------------------------------

NET_CONFIG_DET = {
    "tiny": {
        "stem": (16, 32),
        "blocks_s1": [[3, 32, 32, 1, True], [3, 32, 32, 1, False]],
        "blocks_s2": [
            [3, 32, 48, 2, False],
            [3, 48, 48, 1, True],
            [3, 48, 48, 1, False],
        ],
        "blocks_s3": [
            [3, 48, 64, 2, False],
            [3, 64, 64, 1, True],
            [3, 64, 64, 1, False],
            [3, 64, 64, 1, True],
            [3, 64, 64, 1, False],
        ],
        "blocks_s4": [
            [3, 64, 160, 2, False],
            [3, 160, 160, 1, True],
            [3, 160, 160, 1, False],
        ],
    },
    "small": {
        "stem": (24, 48),
        "blocks_s1": [[3, 48, 48, 1, True], [3, 48, 48, 1, False]],
        "blocks_s2": [
            [3, 48, 96, 2, False],
            [3, 96, 96, 1, True],
            [3, 96, 96, 1, False],
        ],
        "blocks_s3": [
            [3, 96, 192, 2, False],
            [3, 192, 192, 1, True],
            [3, 192, 192, 1, False],
            [3, 192, 192, 1, True],
            [3, 192, 192, 1, False],
        ],
        "blocks_s4": [
            [3, 192, 384, 2, False],
            [3, 384, 384, 1, True],
            [3, 384, 384, 1, False],
        ],
    },
    "medium": {
        "stem": (64, 128),
        "blocks_s1": [[3, 128, 128, 1, True], [3, 128, 128, 1, False]],
        "blocks_s2": [
            [3, 128, 256, 2, False],
            [3, 256, 256, 1, True],
            [3, 256, 256, 1, False],
        ],
        "blocks_s3": [
            [3, 256, 512, 2, False],
            [3, 512, 512, 1, True],
            [3, 512, 512, 1, False],
            [3, 512, 512, 1, True],
            [3, 512, 512, 1, False],
        ],
        "blocks_s4": [
            [3, 512, 896, 2, False],
            [3, 896, 896, 1, True],
            [3, 896, 896, 1, False],
        ],
    },
}


NET_CONFIG_REC = {
    "tiny": {
        "stem": (24, 48),
        "stem_type": "simple",
        "blocks2": [[3, 48, 48, 1, True]],
        "blocks3": [[3, 48, 48, 1, False]],
        "blocks4": [
            [3, 48, 96, (2, 1), False],
            [3, 96, 96, 1, True],
            [3, 96, 96, 1, False],
        ],
        "blocks5": [
            [3, 96, 160, (2, 1), False],
            [3, 160, 160, 1, True],
            [3, 160, 160, 1, False],
            [3, 160, 160, 1, False],
        ],
        "blocks6": [],
    },
    "small": {
        "stem": (48, 96),
        "stem_type": "branch",
        "blocks2": [[3, 96, 96, 1, True]],
        "blocks3": [[3, 96, 96, 1, False], [3, 96, 96, 1, False]],
        "blocks4": [
            [3, 96, 192, (2, 1), False],
            [3, 192, 192, 1, True],
            [3, 192, 192, 1, False],
            [3, 192, 192, 1, True],
            [3, 192, 192, 1, False],
            [3, 192, 192, 1, True],
            [3, 192, 192, 1, False],
        ],
        "blocks5": [
            [3, 192, 384, (2, 1), False],
            [3, 384, 384, 1, True],
            [3, 384, 384, 1, False],
        ],
        "blocks6": [],
    },
    "medium": {
        "stem": (64, 128),
        "stem_type": "branch",
        "blocks2": [[3, 128, 128, 1, True]],
        "blocks3": [
            [3, 128, 256, 1, False],
            [3, 256, 256, 1, False],
            [3, 256, 256, 1, True],
        ],
        "blocks4": [
            [3, 256, 512, (2, 1), False],
            [3, 512, 512, 1, True],
            [3, 512, 512, 1, False],
            [3, 512, 512, 1, True],
            [3, 512, 512, 1, False],
            [3, 512, 512, 1, True],
            [3, 512, 512, 1, False],
        ],
        "blocks5": [
            [3, 512, 768, (2, 1), False],
            [3, 768, 768, 1, True],
            [3, 768, 768, 1, False],
        ],
        "blocks6": [],
    },
}


# ---------------------------------------------------------------------------
# 基础构建块
# ---------------------------------------------------------------------------


def _same_asymmetric_pads(kernel_size):
    """返回 PyTorch ``padding="same"`` 的每维填充量 ``(left, right, top, bottom)``。

    PyTorch 原生 ``"same"`` 对偶数核采用**非对称**填充（右/下各多补 1）；
    ``F.pad(x, (left, right, top, bottom))`` 即按该顺序取值。
    """
    if isinstance(kernel_size, int):
        kh = kw = kernel_size
    else:
        kh, kw = kernel_size
    left = (kw - 1) // 2
    right = kw - 1 - left
    top = (kh - 1) // 2
    bottom = kh - 1 - top
    return left, right, top, bottom


class _SamePadConv2d(nn.Module):
    """等价于 ``nn.Conv2d(padding="same")`` 的包装：显式非对称 ``F.pad`` + 零填充卷积。

    仅用于**偶数核** ``"same"`` 卷积的 ``rep()``/``fuse()`` 融合结果，以复现
    PyTorch 原生 ``"same"`` 的右/下非对称填充。``nn.Conv2d`` 会把 2 元组
    padding ``(left, total - left)`` 解释成**每维对称**填充，无法表达非对称。
    """

    def __init__(self, conv, pads):
        super().__init__()
        self.conv = conv
        self.pads = tuple(pads)

    def forward(self, x):
        return self.conv(F.pad(x, self.pads))


def _build_fused_conv(weight, bias, kernel_size, stride, groups, padding, dilation=1):
    """构建 BN 融合后的单个卷积。

    - 数值 padding / 奇数核 ``"same"``（对称）：返回 ``nn.Conv2d``。
    - 偶数核 ``"same"``（非对称）：返回 ``_SamePadConv2d``（``F.pad`` + 零填充）。
    """
    if isinstance(padding, str):
        if padding.lower() == "valid":
            padding = 0
        else:  # "same"
            pads = _same_asymmetric_pads(kernel_size)
            left, right, top, bottom = pads
            if left == right and top == bottom:  # 奇数核对称
                return nn.Conv2d(
                    weight.shape[1] * groups,
                    weight.shape[0],
                    weight.shape[2:],
                    stride=stride,
                    padding=(top, left),
                    dilation=dilation,
                    groups=groups,
                )
            conv = nn.Conv2d(
                weight.shape[1] * groups,
                weight.shape[0],
                weight.shape[2:],
                stride=stride,
                padding=0,
                dilation=dilation,
                groups=groups,
            )
            return _SamePadConv2d(conv, pads)
    return nn.Conv2d(
        weight.shape[1] * groups,
        weight.shape[0],
        weight.shape[2:],
        stride=stride,
        padding=padding,
        dilation=dilation,
        groups=groups,
    )


def _copy_fused_params(m, weight, bias):
    """将融合权重/偏置写入卷积（自动解包 ``_SamePadConv2d``）。"""
    conv = m.conv if isinstance(m, _SamePadConv2d) else m
    conv.weight.data.copy_(weight)
    conv.bias.data.copy_(bias)


class Conv2D_BN(nn.Sequential):
    """Conv2D + BatchNorm2d（bias=False）。推理时可用 fuse() 融合。"""

    def __init__(
        self,
        in_channels,
        out_channels,
        kernel_size=1,
        stride=1,
        padding=0,
        groups=1,
        bn_weight_init=1.0,
    ):
        super().__init__()
        self.add_module(
            "conv",
            nn.Conv2d(
                in_channels,
                out_channels,
                kernel_size,
                stride,
                padding,
                groups=groups,
                bias=False,
            ),
        )
        bn = nn.BatchNorm2d(out_channels)
        nn.init.constant_(bn.weight, 1.0 if bn_weight_init == 1.0 else 0.0)
        nn.init.constant_(bn.bias, 0.0)
        self.add_module("bn", bn)

    @torch.no_grad()
    def fuse(self):
        """将 Conv2D 与 BN 融合为单个 Conv2D（bias=True）。

        偶数核 ``"same"`` 的填充是非对称的（右/下），此处返回
        ``_SamePadConv2d`` 包装以保证融合前后数学等价。
        """
        conv, bn = self.conv, self.bn
        scale = bn.weight / torch.sqrt(bn.running_var + bn.eps)
        w = conv.weight * scale[:, None, None, None]
        b = bn.bias - bn.running_mean * scale
        m = _build_fused_conv(
            w, b, conv.kernel_size, conv.stride, conv.groups, conv.padding, conv.dilation
        )
        _copy_fused_params(m, w, b)
        return m


class ConvBNAct(nn.Module):
    """Conv2d + BN + ReLU（可选）。推理时可用 rep() 融合为单个 Conv2d。"""

    def __init__(self, in_channels, out_channels, kernel_size=3, stride=1,
                 padding=1, groups=1, use_act=True):
        super().__init__()
        self.use_act = use_act
        self.is_repped = False
        if isinstance(padding, str) and padding.upper() == "SAME":
            padding = "same"
        self.conv = nn.Conv2d(
            in_channels,
            out_channels,
            kernel_size,
            stride,
            padding=padding,
            groups=groups,
            bias=False,
        )
        self.bn = nn.BatchNorm2d(out_channels)
        if self.use_act:
            self.act = nn.ReLU(inplace=True)

    def forward(self, x):
        x = self.conv(x)
        if not self.is_repped:
            x = self.bn(x)
        if self.use_act:
            x = self.act(x)
        return x

    @torch.no_grad()
    def rep(self):
        """将 Conv2d 与 BN 融合为单个 Conv2d（bias=True）。

        偶数核 ``"same"`` 的填充是非对称的（右/下），此处用
        ``_SamePadConv2d`` 包装以保证 rep() 前后数学等价。
        """
        if self.is_repped:
            return
        conv, bn = self.conv, self.bn
        scale = bn.weight / torch.sqrt(bn.running_var + bn.eps)
        fused_w = conv.weight * scale[:, None, None, None]
        fused_b = bn.bias - bn.running_mean * scale
        m = _build_fused_conv(
            fused_w, fused_b, conv.kernel_size, conv.stride, conv.groups, conv.padding,
            conv.dilation,
        )
        _copy_fused_params(m, fused_w, fused_b)
        self.conv = m
        del self.bn
        self.is_repped = True


class StemBlock(nn.Module):
    """入口 Stem：多分支结构，总 stride 4（stem1 stride=2 + stem3 stride=2）。"""

    def __init__(self, in_channels=3, mid_channels=48, out_channels=96):
        super().__init__()
        self.is_repped = False
        self.stem1 = ConvBNAct(in_channels, mid_channels, 3, 2)
        self.stem2a = ConvBNAct(mid_channels, mid_channels // 2, 2, 1, padding="SAME")
        self.stem2b = ConvBNAct(mid_channels // 2, mid_channels, 2, 1, padding="SAME")
        self.stem3 = ConvBNAct(mid_channels * 2, mid_channels, 3, 2)
        self.stem4 = ConvBNAct(mid_channels, out_channels, 1, 1, padding=0)
        self.pool = nn.MaxPool2d(kernel_size=2, stride=1)

    def forward(self, x):
        x = self.stem1(x)
        x2 = self.stem2b(self.stem2a(x))
        # kernel=2, stride=1, "SAME" -> 仅右下各补 1
        x1 = self.pool(F.pad(x, [0, 1, 0, 1]))
        x = self.stem4(self.stem3(torch.cat([x1, x2], dim=1)))
        return x

    def rep(self):
        if self.is_repped:
            return
        for attr in ("stem1", "stem2a", "stem2b", "stem3", "stem4"):
            getattr(self, attr).rep()
        self.is_repped = True


class SELayer(nn.Module):
    """Squeeze-and-Excitation（reduction=4，Hardsigmoid 门控）。"""

    def __init__(self, channel, reduction=4):
        super().__init__()
        self.conv1 = nn.Conv2d(channel, channel // reduction, 1)
        self.relu = nn.ReLU(inplace=True)
        self.conv2 = nn.Conv2d(channel // reduction, channel, 1)
        self.hardsigmoid = nn.Hardsigmoid()

    def forward(self, x):
        identity = x
        x = self.conv1(x.mean(dim=[2, 3], keepdim=True))
        x = self.relu(x)
        x = self.hardsigmoid(self.conv2(x))
        return x * identity


class RepDWConv(nn.Module):
    """可重参数化深度卷积。

    训练：3 分支（3x3 DW + 1x1 DW + identity BN）；
    推理：rep() 融合为单个 3x3 DW Conv。
    """

    def __init__(self, channels, kernel_size=3):
        super().__init__()
        self.channels = channels
        self.kernel_size = kernel_size
        padding = (kernel_size - 1) // 2
        self.conv = Conv2D_BN(channels, channels, kernel_size, 1, padding,
                              groups=channels)
        self.conv1 = nn.Conv2d(channels, channels, 1, 1, 0, groups=channels,
                               bias=False)
        self.bn = nn.BatchNorm2d(channels)
        nn.init.constant_(self.bn.weight, 1.0)
        nn.init.constant_(self.bn.bias, 0.0)
        self.is_repped = False
        self.reparam_conv = None

    def forward(self, x):
        if self.is_repped:
            return self.reparam_conv(x)
        return self.bn(self.conv(x) + self.conv1(x) + x)

    @torch.no_grad()
    def _fuse_conv(self):
        conv = self.conv.fuse()
        pad = self.kernel_size // 2
        conv1_w = F.pad(self.conv1.weight, [pad, pad, pad, pad])
        identity = F.pad(
            torch.ones(
                self.conv1.weight.shape[0:2] + (1, 1),
                device=self.conv1.weight.device,
                dtype=self.conv1.weight.dtype,
            ),
            [pad, pad, pad, pad],
        )
        w = conv.weight + conv1_w + identity
        conv.weight.data.copy_(w)
        scale = self.bn.weight / torch.sqrt(self.bn.running_var + self.bn.eps)
        conv.weight.data.copy_(conv.weight * scale[:, None, None, None])
        conv.bias.data.copy_(self.bn.bias + (conv.bias - self.bn.running_mean) * scale)
        return conv

    def rep(self):
        if self.is_repped:
            return
        fused = self._fuse_conv()
        padding = (self.kernel_size - 1) // 2
        self.reparam_conv = nn.Conv2d(
            self.channels,
            self.channels,
            self.kernel_size,
            1,
            padding,
            groups=self.channels,
        )
        self.reparam_conv.weight.data.copy_(fused.weight)
        self.reparam_conv.bias.data.copy_(fused.bias)
        del self.conv
        del self.conv1
        del self.bn
        self.is_repped = True


class LCNetV4Block(nn.Module):
    """LCNetV4 基础块（det/rec 共用）。

    Token mixer: stride=1 且 in==out 时用 RepDWConv，否则用普通 DW Conv（可选 SE）。
    Channel mixer: expand -> act -> compress（stride=1 且 in==out 时含残差）。
    rep() 融合所有 Conv2D_BN 层（数学等价，不损失精度）。
    """

    def __init__(self, in_channels, out_channels, stride, dw_size,
                 use_se=False, expand_ratio=2, act_type="gelu"):
        super().__init__()
        self.is_repped = False
        self.has_residual = in_channels == out_channels and stride == 1
        self.use_rep_dw = stride == 1 and in_channels == out_channels

        self.token_mixer = nn.Sequential()
        if self.use_rep_dw:
            self.token_mixer.add_module("rep_dw", RepDWConv(in_channels, dw_size))
        else:
            padding = (dw_size - 1) // 2
            self.token_mixer.add_module(
                "dw_conv",
                Conv2D_BN(in_channels, in_channels, dw_size, stride, padding,
                          groups=in_channels),
            )
        if use_se:
            self.token_mixer.add_module("se", SELayer(in_channels))

        hidden_channels = int(in_channels * expand_ratio)
        compress_bn_init = 0.0 if self.has_residual else 1.0
        self.channel_mixer = nn.Sequential()
        self.channel_mixer.add_module(
            "expand", Conv2D_BN(in_channels, hidden_channels, 1, 1, 0)
        )
        if act_type == "gelu":
            self.channel_mixer.add_module("act", nn.GELU())
        elif act_type == "hswish":
            self.channel_mixer.add_module("act", nn.Hardswish())
        elif act_type == "relu":
            self.channel_mixer.add_module("act", nn.ReLU(inplace=True))
        else:
            raise ValueError(f"unsupported activation: {act_type}")
        self.channel_mixer.add_module(
            "compress",
            Conv2D_BN(hidden_channels, out_channels, 1, 1, 0,
                      bn_weight_init=compress_bn_init),
        )

    def forward(self, x):
        x = self.token_mixer(x)
        if self.has_residual:
            return x + self.channel_mixer(x)
        return self.channel_mixer(x)

    def rep(self):
        if self.is_repped:
            return
        if self.use_rep_dw:
            self.token_mixer.rep_dw.rep()
        else:
            self.token_mixer.dw_conv = self.token_mixer.dw_conv.fuse()
        for name in ("expand", "compress"):
            m = getattr(self.channel_mixer, name, None)
            if isinstance(m, Conv2D_BN):
                setattr(self.channel_mixer, name, m.fuse())
        self.is_repped = True


# ---------------------------------------------------------------------------
# PPLCNetV4 骨干
# ---------------------------------------------------------------------------


class PPLCNetV4(nn.Module):
    """PPLCNetV4 骨干网络（det/rec 共用）。

    det=True:  返回 [s1, s2, s3, s4] 4 级多尺度特征。
    det=False: 返回池化后特征张量 [B, C, 1, W]（training 时自适应池化到宽 40）。
    """

    def __init__(self, model_size="tiny", det=True, in_channels=3):
        super().__init__()
        self.det = det
        self.is_repped = False

        if det:
            assert model_size in NET_CONFIG_DET, (
                f"det model_size must be one of {list(NET_CONFIG_DET)} "
                f"but got '{model_size}'"
            )
            cfg = NET_CONFIG_DET[model_size]
            stem_mid, stem_out = cfg["stem"]
            self.stem = StemBlock(in_channels, stem_mid, stem_out)

            def make_stage(key):
                return nn.Sequential(
                    *[
                        LCNetV4Block(in_c, out_c, s, k, se, expand_ratio=2)
                        for k, in_c, out_c, s, se in cfg[key]
                    ]
                )

            self.blocks_s1 = make_stage("blocks_s1")
            self.blocks_s2 = make_stage("blocks_s2")
            self.blocks_s3 = make_stage("blocks_s3")
            self.blocks_s4 = make_stage("blocks_s4")
            self.out_channels = [
                cfg["blocks_s1"][-1][2],
                cfg["blocks_s2"][-1][2],
                cfg["blocks_s3"][-1][2],
                cfg["blocks_s4"][-1][2],
            ]
        else:
            assert model_size in NET_CONFIG_REC, (
                f"rec model_size must be one of {list(NET_CONFIG_REC)} "
                f"but got '{model_size}'"
            )
            cfg = NET_CONFIG_REC[model_size]
            stem_mid, stem_out = cfg["stem"]
            if cfg["stem_type"] == "branch":
                self.conv1 = StemBlock(in_channels, stem_mid, stem_out)
            else:
                self.conv1 = nn.Sequential(
                    Conv2D_BN(in_channels, stem_mid, 3, 2, 1),
                    nn.GELU(),
                    Conv2D_BN(stem_mid, stem_out, 3, 2, 1),
                )

            def make_stage(name):
                return nn.Sequential(
                    *[
                        LCNetV4Block(in_c, out_c, s, k, se, expand_ratio=2)
                        for k, in_c, out_c, s, se in cfg.get(name, [])
                    ]
                )

            self.blocks2 = make_stage("blocks2")
            self.blocks3 = make_stage("blocks3")
            self.blocks4 = make_stage("blocks4")
            self.blocks5 = make_stage("blocks5")
            self.blocks6 = make_stage("blocks6")
            for sname in reversed(["blocks2", "blocks3", "blocks4", "blocks5", "blocks6"]):
                if cfg.get(sname):
                    self.out_channels = cfg[sname][-1][2]
                    break

    def forward(self, x):
        if self.det:
            x = self.stem(x)
            o1 = self.blocks_s1(x)
            o2 = self.blocks_s2(o1)
            o3 = self.blocks_s3(o2)
            o4 = self.blocks_s4(o3)
            return [o1, o2, o3, o4]
        x = self.conv1(x)
        x = self.blocks2(x)
        x = self.blocks3(x)
        x = self.blocks4(x)
        x = self.blocks5(x)
        x = self.blocks6(x)
        if self.training:
            x = F.adaptive_avg_pool2d(x, [1, 40])
        else:
            assert x.shape[2] >= 3, f"Feature height {x.shape[2]} < pool kernel 3."
            x = F.avg_pool2d(x, [3, 2])
        return x

    def rep(self):
        if self.is_repped:
            return
        if self.det:
            self.stem.rep()
            for stage in (self.blocks_s1, self.blocks_s2, self.blocks_s3, self.blocks_s4):
                for block in stage:
                    block.rep()
        else:
            if hasattr(self.conv1, "rep"):
                self.conv1.rep()
            for stage in (self.blocks2, self.blocks3, self.blocks4, self.blocks5, self.blocks6):
                for block in stage:
                    block.rep()
        self.is_repped = True

    @property
    def feat_channels(self):
        """det 模式各 stage 输出通道数（P2-P5），rec 模式为单元素列表。"""
        if isinstance(self.out_channels, int):
            return [self.out_channels]
        return list(self.out_channels)
