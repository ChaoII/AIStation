"""DBHead（可微分二值化检测头，自研实现）。

结构对齐 pytorchocr/modeling/heads/det_db_head.py 中的 DBHead：
- binarize / thresh 各为一个 Head 子网络（3x3 conv + 2x ConvTranspose stride=2）。
- 输入 fuse 特征（640 输入 -> FPN P2 = 160），经 2 次 stride=2 转置卷积
  上采样 4× 到原图分辨率（160 -> 320 -> 640）。

训练输出 3 通道 (shrink_map, threshold_map, binary_map)。
推理输出 1 通道 shrink_map。
"""
import torch
import torch.nn as nn

from ..common import Activation


class DBHead(nn.Module):
    """Differentiable Binarization head.

    训练输出 3 通道 (shrink_map, threshold_map, binary_map)。
    推理输出 1 通道 shrink_map。
    """

    def __init__(self, in_channels, k=50):
        super().__init__()
        self.k = k
        self.binarize = self._make_head(in_channels)
        self.thresh = self._make_head(in_channels)

    def _make_head(self, in_channels):
        return nn.Sequential(
            nn.Conv2d(in_channels, in_channels // 4, 3, 1, 1, bias=False),
            nn.BatchNorm2d(in_channels // 4),
            Activation("relu"),
            nn.ConvTranspose2d(in_channels // 4, in_channels // 4, 2, 2),
            nn.BatchNorm2d(in_channels // 4),
            Activation("relu"),
            nn.ConvTranspose2d(in_channels // 4, 1, 2, 2),
        )

    def step_function(self, x, y):
        return torch.reciprocal(1 + torch.exp(-self.k * (x - y)))

    def forward(self, x):
        shrink_maps = torch.sigmoid(self.binarize(x))
        if not self.training:
            return {"maps": shrink_maps}
        threshold_maps = torch.sigmoid(self.thresh(x))
        binary_maps = self.step_function(shrink_maps, threshold_maps)
        y = torch.cat([shrink_maps, threshold_maps, binary_maps], dim=1)
        return {"maps": y}
