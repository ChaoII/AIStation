"""RepLKPAN 特征金字塔（PP-OCRv6 medium det neck，自研实现）。

结构对齐 PaddleOCR 的 RepLKPAN（medium 专用 neck，out_channels=256，intracl=True）：
- ins_conv:      1x1 Conv 对齐卷积（P2-P5 → out_channels）
- inp_conv:      DilatedReparamConv（DilatedReparamBlock DW 大核 + PW 1x1 + BN）
- pan_head_conv: 3x3 stride=2 下采样，构建自底向上的 PAN 路径
- pan_lat_conv:  横向卷积（DilatedReparamConv）
- intracl:       可选 IntraCLBlock（跨通道局部建模，作用于 out_channels//4）

forward 输出（与 RepLKFPN 保持一致）：
- 训练模式：dict，含 "fuse"（4×out_channels/4 = out_channels，尺寸=输入/4）
   及 "aux_p4" / "aux_p3" / "aux_p2"（辅助监督特征，通道数=out_channels）。
- eval 模式：单张量 fuse。
"""
import torch
import torch.nn as nn
import torch.nn.functional as F

from .rep_lk_fpn import DilatedReparamBlock


class IntraCLBlock(nn.Module):
    """IntraCLBlock（ViTAE I3CL 跨通道局部建模）。

    用 7/5/3 三档的方形 (c,c)、垂直 (h,1)、水平 (1,w) 卷积分支并行聚合，
    再 1x1 恢复通道 + BN + ReLU 后与输入残差相加。
    """

    def __init__(self, in_channels=96, reduce_factor=4):
        super().__init__()
        hidden = in_channels // reduce_factor
        self.conv1x1_reduce_channel = nn.Conv2d(in_channels, hidden, 1)
        self.conv1x1_return_channel = nn.Conv2d(hidden, in_channels, 1)

        self.v_layer_7x1 = nn.Conv2d(hidden, hidden, (7, 1), padding=(3, 0))
        self.v_layer_5x1 = nn.Conv2d(hidden, hidden, (5, 1), padding=(2, 0))
        self.v_layer_3x1 = nn.Conv2d(hidden, hidden, (3, 1), padding=(1, 0))

        self.q_layer_1x7 = nn.Conv2d(hidden, hidden, (1, 7), padding=(0, 3))
        self.q_layer_1x5 = nn.Conv2d(hidden, hidden, (1, 5), padding=(0, 2))
        self.q_layer_1x3 = nn.Conv2d(hidden, hidden, (1, 3), padding=(0, 1))

        self.c_layer_7x7 = nn.Conv2d(hidden, hidden, (7, 7), padding=(3, 3))
        self.c_layer_5x5 = nn.Conv2d(hidden, hidden, (5, 5), padding=(2, 2))
        self.c_layer_3x3 = nn.Conv2d(hidden, hidden, (3, 3), padding=(1, 1))

        self.bn = nn.BatchNorm2d(in_channels)
        self.relu = nn.ReLU(inplace=True)

    def forward(self, x):
        x_new = self.conv1x1_reduce_channel(x)
        x_7 = self.c_layer_7x7(x_new) + self.v_layer_7x1(x_new) + self.q_layer_1x7(x_new)
        x_5 = self.c_layer_5x5(x_7) + self.v_layer_5x1(x_7) + self.q_layer_1x5(x_7)
        x_3 = self.c_layer_3x3(x_5) + self.v_layer_3x1(x_5) + self.q_layer_1x3(x_5)
        x_rel = self.relu(self.bn(self.conv1x1_return_channel(x_3)))
        return x + x_rel


class DilatedReparamConv(nn.Module):
    """非 depthwise 的大核重参数卷积：DW DilatedReparamBlock → PW 1x1 → BN。"""

    def __init__(self, in_channels, out_channels, kernel_size=9):
        super().__init__()
        self.dw = DilatedReparamBlock(channels=in_channels, kernel_size=kernel_size)
        self.pw = nn.Conv2d(in_channels, out_channels, 1, bias=False)
        self.bn = nn.BatchNorm2d(out_channels)

    def forward(self, x):
        return self.bn(self.pw(self.dw(x)))

    def rep(self):
        """融合 DW 分支与 pw+bn，得到单卷积推理等价。"""
        self.dw.rep()
        fused_weight, fused_bias = DilatedReparamBlock._fuse_bn(self.pw, self.bn)
        conv = nn.Conv2d(self.pw.in_channels, self.pw.out_channels, 1, bias=True)
        conv.weight.data.copy_(fused_weight)
        conv.bias.data.copy_(fused_bias)
        self.pw = conv
        delattr(self, "bn")


class RepLKPAN(nn.Module):
    """RepLKPAN 特征融合（PP-OCRv6 medium det neck）。

    自顶向下融合（P5→P4→P3→P2）后，再由自底向上 pan_head_conv 聚合
    相邻低层信息，最后横向卷积（pan_lat_conv）得到各尺度输出。
    可选 intracl 做跨通道建模。

    Args:
        in_channels: [P2, P3, P4, P5] 输入通道列表。
        out_channels: 融合输出通道数（fuse 通道数，须被 4 整除）。
        mode: 保留接口（未使用，与官方签名对齐）。
        intracl: 是否启用 IntraCLBlock（medium 默认 True）。
    """

    def __init__(self, in_channels, out_channels, mode="large", **kwargs):
        super().__init__()
        assert out_channels % 4 == 0
        self.out_channels = out_channels
        self.is_repped = False

        self.ins_conv = nn.ModuleList(
            nn.Conv2d(c, out_channels, 1, bias=False) for c in in_channels
        )
        self.inp_conv = nn.ModuleList(
            DilatedReparamConv(out_channels, out_channels // 4, kernel_size=9)
            for _ in in_channels
        )
        self.pan_head_conv = nn.ModuleList(
            nn.Conv2d(
                out_channels // 4, out_channels // 4, 3, stride=2, padding=1, bias=False
            )
            for _ in range(3)
        )
        self.pan_lat_conv = nn.ModuleList(
            DilatedReparamConv(out_channels // 4, out_channels // 4, kernel_size=9)
            for _ in in_channels
        )

        self.intracl = bool(kwargs.get("intracl", False))
        if self.intracl:
            self.incl1 = IntraCLBlock(out_channels // 4, reduce_factor=2)
            self.incl2 = IntraCLBlock(out_channels // 4, reduce_factor=2)
            self.incl3 = IntraCLBlock(out_channels // 4, reduce_factor=2)
            self.incl4 = IntraCLBlock(out_channels // 4, reduce_factor=2)

    def forward(self, x):
        c2, c3, c4, c5 = x

        in5 = self.ins_conv[3](c5)
        in4 = self.ins_conv[2](c4)
        in3 = self.ins_conv[1](c3)
        in2 = self.ins_conv[0](c2)

        out4 = in4 + F.interpolate(in5, scale_factor=2, mode="nearest")  # 1/16
        out3 = in3 + F.interpolate(out4, scale_factor=2, mode="nearest")  # 1/8
        out2 = in2 + F.interpolate(out3, scale_factor=2, mode="nearest")  # 1/4

        f5 = self.inp_conv[3](in5)
        f4 = self.inp_conv[2](out4)
        f3 = self.inp_conv[1](out3)
        f2 = self.inp_conv[0](out2)

        pan3 = f3 + self.pan_head_conv[0](f2)
        pan4 = f4 + self.pan_head_conv[1](pan3)
        pan5 = f5 + self.pan_head_conv[2](pan4)

        p2 = self.pan_lat_conv[0](f2)
        p3 = self.pan_lat_conv[1](pan3)
        p4 = self.pan_lat_conv[2](pan4)
        p5 = self.pan_lat_conv[3](pan5)

        if self.intracl:
            p5 = self.incl4(p5)
            p4 = self.incl3(p4)
            p3 = self.incl2(p3)
            p2 = self.incl1(p2)

        p5 = F.interpolate(p5, scale_factor=8, mode="nearest")
        p4 = F.interpolate(p4, scale_factor=4, mode="nearest")
        p3 = F.interpolate(p3, scale_factor=2, mode="nearest")

        fuse = torch.cat([p5, p4, p3, p2], dim=1)
        if self.training:
            return {"fuse": fuse, "aux_p4": out4, "aux_p3": out3, "aux_p2": out2}
        return fuse

    def rep(self):
        """合并 DilatedReparamConv 分支（DW + pw/bn 融合）用于推理部署。"""
        if self.is_repped:
            return
        for block in list(self.inp_conv) + list(self.pan_lat_conv):
            block.rep()
        self.is_repped = True
