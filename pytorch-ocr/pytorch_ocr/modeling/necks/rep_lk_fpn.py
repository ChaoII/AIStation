"""RepLKFPN 特征金字塔（PP-OCRv6 det neck，自研实现）。

结构对齐 frotms/PaddleOCR2Pytorch 的 db_fpn.py 中 RepLKFPN：
- ins_conv:  RSELayer（1x1 Conv + SE，shortcut 可选）
- inp_conv:  DilatedReparamBlock（大核 DW，可重参数化）+ PW Conv(1x1) + SE
- 自顶向下融合（P5→P4→P3→P2），再按各尺度上采样拼接为单尺度 fuse 特征

forward 输出：
- 训练模式：dict，含 "fuse"（供 DBHead，通道数=out_channels，尺寸=输入/4）
  及 "aux_p4" / "aux_p3" / "aux_p2"（辅助监督特征，通道数=out_channels）。
- eval 模式：单张量 fuse。
"""
import torch
import torch.nn as nn
import torch.nn.functional as F


class SEModule(nn.Module):
    """Squeeze-and-Excitation（reduction=4，Hardsigmoid 门控）。"""

    def __init__(self, in_channels, reduction=4):
        super().__init__()
        assert in_channels % reduction == 0
        self.avg_pool = nn.AdaptiveAvgPool2d(1)
        self.conv1 = nn.Conv2d(in_channels, in_channels // reduction, 1, bias=True)
        self.relu = nn.ReLU(inplace=True)
        self.conv2 = nn.Conv2d(in_channels // reduction, in_channels, 1, bias=True)
        self.hardsigmoid = nn.Hardsigmoid()

    def forward(self, x):
        identity = x
        x = self.avg_pool(x)
        x = self.conv1(x)
        x = self.relu(x)
        x = self.hardsigmoid(self.conv2(x))
        return x * identity


class RSELayer(nn.Module):
    """1x1 对齐卷积 + SE（shortcut 可选），用于 ins_conv。"""

    def __init__(self, in_channels, out_channels, kernel_size, shortcut=True):
        super().__init__()
        self.out_channels = out_channels
        self.in_conv = nn.Conv2d(
            in_channels,
            out_channels,
            kernel_size,
            padding=int(kernel_size // 2),
            bias=False,
        )
        self.se_block = SEModule(out_channels)
        self.shortcut = shortcut

    def forward(self, ins):
        x = self.in_conv(ins)
        if self.shortcut:
            out = x + self.se_block(x)
        else:
            out = self.se_block(x)
        return out


class DilatedReparamBlock(nn.Module):
    """Dilated Reparam Block（来自 UniRepLKNet）。

    训练：大核 DW 卷积 + 多个膨胀 DW 卷积分支并行（各带 BN）。
    推理：rep() 将全部分支融合为单个大核 DW 卷积。

    各 kernel_size 的分支：
      - 7:  origin 7x7(dil=1) + 5x5(dil=1) + 3x3(dil=2) + 3x3(dil=3)
      - 5:  origin 5x5(dil=1) + 3x3(dil=1) + 3x3(dil=2)
    """

    def __init__(self, channels, kernel_size=7, deploy=False):
        super().__init__()
        self.channels = channels
        self.kernel_size = kernel_size
        self.is_repped = deploy

        if kernel_size == 9:
            self.kernel_sizes = [5, 5, 3, 3]
            self.dilates = [1, 2, 3, 4]
        elif kernel_size == 7:
            self.kernel_sizes = [5, 3, 3]
            self.dilates = [1, 2, 3]
        elif kernel_size == 5:
            self.kernel_sizes = [3, 3]
            self.dilates = [1, 2]
        elif kernel_size == 11:
            self.kernel_sizes = [5, 5, 3, 3, 3]
            self.dilates = [1, 2, 3, 4, 5]
        elif kernel_size == 13:
            self.kernel_sizes = [5, 7, 3, 3, 3]
            self.dilates = [1, 2, 3, 4, 5]
        else:
            raise ValueError(
                "DilatedReparamBlock requires kernel_size in [5,7,9,11,13], "
                f"but got {kernel_size}"
            )

        if not self.is_repped:
            self.lk_origin = nn.Conv2d(
                in_channels=channels,
                out_channels=channels,
                kernel_size=kernel_size,
                stride=1,
                padding=kernel_size // 2,
                groups=channels,
                bias=False,
            )
            self.origin_bn = nn.BatchNorm2d(channels)

            for k, r in zip(self.kernel_sizes, self.dilates, strict=True):
                equiv_ks = r * (k - 1) + 1
                p = equiv_ks // 2
                conv = nn.Conv2d(
                    in_channels=channels,
                    out_channels=channels,
                    kernel_size=k,
                    stride=1,
                    padding=p,
                    dilation=r,
                    groups=channels,
                    bias=False,
                )
                bn = nn.BatchNorm2d(channels)
                setattr(self, f"dil_conv_k{k}_{r}", conv)
                setattr(self, f"dil_bn_k{k}_{r}", bn)
        else:
            self.lk_origin = nn.Conv2d(
                in_channels=channels,
                out_channels=channels,
                kernel_size=kernel_size,
                stride=1,
                padding=kernel_size // 2,
                groups=channels,
                bias=True,
            )

    def forward(self, x):
        if self.is_repped:
            return self.lk_origin(x)
        out = self.origin_bn(self.lk_origin(x))
        for k, r in zip(self.kernel_sizes, self.dilates, strict=True):
            conv = getattr(self, f"dil_conv_k{k}_{r}")
            bn = getattr(self, f"dil_bn_k{k}_{r}")
            out = out + bn(conv(x))
        return out

    @staticmethod
    def _fuse_bn(conv, bn):
        """Fuse Conv2d + BatchNorm2d into (weight, bias)."""
        kernel = conv.weight
        gamma = bn.weight
        beta = bn.bias
        running_mean = bn.running_mean
        running_var = bn.running_var
        eps = bn.eps
        std = torch.sqrt(running_var + eps)
        fused_weight = kernel * (gamma / std).reshape([-1, 1, 1, 1])
        fused_bias = beta - running_mean * gamma / std
        return fused_weight, fused_bias

    @staticmethod
    def _convert_dilated_to_nondilated(kernel, dilate_rate):
        """Convert dilated conv kernel to equivalent non-dilated (sparse) kernel
        by inserting zeros using transposed convolution."""
        if dilate_rate == 1:
            return kernel
        identity = torch.ones([1, 1, 1, 1], dtype=kernel.dtype, device=kernel.device)
        C = kernel.shape[0]
        result_list = []
        for i in range(C):
            k_i = kernel[i : i + 1]  # (1, 1, kH, kW)
            dilated = F.conv_transpose2d(k_i, identity, stride=dilate_rate)
            result_list.append(dilated)
        return torch.cat(result_list, dim=0)

    @staticmethod
    def _merge_dilated_into_large_kernel(large_kernel, dilated_kernel, dilated_r):
        """Pad dilated equivalent kernel to large kernel size and add."""
        large_k = large_kernel.shape[2]
        dilated_k = dilated_kernel.shape[2]
        equiv_ks = dilated_r * (dilated_k - 1) + 1
        equiv_kernel = DilatedReparamBlock._convert_dilated_to_nondilated(
            dilated_kernel, dilated_r
        )
        rows_to_pad = large_k // 2 - equiv_ks // 2
        if rows_to_pad > 0:
            merged = large_kernel + F.pad(
                equiv_kernel, [rows_to_pad, rows_to_pad, rows_to_pad, rows_to_pad]
            )
        else:
            merged = large_kernel + equiv_kernel
        return merged

    @torch.no_grad()
    def rep(self):
        """Merge all parallel branches into a single large-kernel DW conv."""
        if self.is_repped:
            return
        origin_k, origin_b = self._fuse_bn(self.lk_origin, self.origin_bn)
        for k, r in zip(self.kernel_sizes, self.dilates, strict=True):
            conv = getattr(self, f"dil_conv_k{k}_{r}")
            bn = getattr(self, f"dil_bn_k{k}_{r}")
            branch_k, branch_b = self._fuse_bn(conv, bn)
            origin_k = self._merge_dilated_into_large_kernel(origin_k, branch_k, r)
            origin_b = origin_b + branch_b

        merged_conv = nn.Conv2d(
            in_channels=self.channels,
            out_channels=self.channels,
            kernel_size=self.kernel_size,
            stride=1,
            padding=self.kernel_size // 2,
            groups=self.channels,
            bias=True,
        )
        merged_conv.weight.data.copy_(origin_k)
        merged_conv.bias.data.copy_(origin_b)
        self.lk_origin = merged_conv
        self.is_repped = True

        delattr(self, "origin_bn")
        for k, r in zip(self.kernel_sizes, self.dilates, strict=True):
            delattr(self, f"dil_conv_k{k}_{r}")
            delattr(self, f"dil_bn_k{k}_{r}")


class RepLKFPN(nn.Module):
    """RepLKFPN 特征融合（PP-OCRv6 det neck）。

    RSEFPN 优化版：将 inp_conv 的 3x3 标准卷积替换为
    DilatedReparamBlock（DW 大核）+ PW Conv(1x1) + SE；
    ins_conv 保持 RSELayer（1x1 对齐卷积，无需 DW 分解）。

    Args:
        in_channels: [P2, P3, P4, P5] 输入通道列表。
        out_channels: 融合输出通道数（fuse 通道数）。
        shortcut: inp_conv 是否使用 SE 捷径。
        dilated_kernel_size: DilatedReparamBlock 大核尺寸（5/7/9/11/13）。
    """

    def __init__(
        self, in_channels, out_channels, shortcut=True, dilated_kernel_size=5, **kwargs
    ):
        super().__init__()
        self.out_channels = out_channels
        self.is_repped = False
        self.ins_conv = nn.ModuleList()
        self.inp_conv_dw = nn.ModuleList()
        self.inp_conv_pw = nn.ModuleList()
        self.inp_conv_se = nn.ModuleList()
        self.shortcut = shortcut

        if kwargs.get("intracl") is True:
            raise NotImplementedError(
                "RepLKFPN intracl branch (IntraCLBlock) is not implemented yet."
            )

        for i in range(len(in_channels)):
            self.ins_conv.append(
                RSELayer(in_channels[i], out_channels, kernel_size=1, shortcut=shortcut)
            )

            self.inp_conv_dw.append(
                DilatedReparamBlock(channels=out_channels, kernel_size=dilated_kernel_size)
            )

            self.inp_conv_pw.append(
                nn.Conv2d(
                    in_channels=out_channels,
                    out_channels=out_channels // 4,
                    kernel_size=1,
                    bias=False,
                )
            )

            self.inp_conv_se.append(SEModule(out_channels // 4))

    def _inp_forward(self, x, idx):
        x = self.inp_conv_dw[idx](x)
        x = self.inp_conv_pw[idx](x)
        if self.shortcut:
            x = x + self.inp_conv_se[idx](x)
        else:
            x = self.inp_conv_se[idx](x)
        return x

    def forward(self, x):
        c2, c3, c4, c5 = x

        in5 = self.ins_conv[3](c5)
        in4 = self.ins_conv[2](c4)
        in3 = self.ins_conv[1](c3)
        in2 = self.ins_conv[0](c2)

        out4 = in4 + F.interpolate(in5, scale_factor=2, mode="nearest")  # 1/16
        out3 = in3 + F.interpolate(out4, scale_factor=2, mode="nearest")  # 1/8
        out2 = in2 + F.interpolate(out3, scale_factor=2, mode="nearest")  # 1/4

        p5 = self._inp_forward(in5, 3)
        p4 = self._inp_forward(out4, 2)
        p3 = self._inp_forward(out3, 1)
        p2 = self._inp_forward(out2, 0)

        p5 = F.interpolate(p5, scale_factor=8, mode="nearest")
        p4 = F.interpolate(p4, scale_factor=4, mode="nearest")
        p3 = F.interpolate(p3, scale_factor=2, mode="nearest")

        fuse = torch.cat([p5, p4, p3, p2], dim=1)
        if self.training:
            return {"fuse": fuse, "aux_p4": out4, "aux_p3": out3, "aux_p2": out2}
        return fuse

    def rep(self):
        """Merge DilatedReparamBlock branches for inference deployment."""
        if self.is_repped:
            return
        for i in range(len(self.inp_conv_dw)):
            self.inp_conv_dw[i].rep()
        self.is_repped = True
