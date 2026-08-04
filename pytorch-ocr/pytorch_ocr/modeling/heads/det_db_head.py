"""DBHead（可微分二值化检测头，自研实现）。

结构对齐 PaddleOCR det_db_head.py 中的 DBHead：
- binarize / thresh 各为一个 Head 子网络（3x3 conv + 2x ConvTranspose stride=2）。
- 输入 fuse 特征（640 输入 -> FPN P2 = 160），经 2 次 stride=2 转置卷积
  上采样 4× 到原图分辨率（160 -> 320 -> 640）。
- aux_in_channels>0 时为每个 FPN 辅助尺度（aux_p4/p3/p2）创建独立
  binarize+thresh Head 对，生成多尺度辅助监督（官方 aux_weight 加权）。

训练输出 3 通道 (shrink_map, threshold_map, binary_map) + aux_maps_*。
推理输出 1 通道 shrink_map。
"""
import torch
import torch.nn as nn

from ..common import Activation


class DBHead(nn.Module):
    """Differentiable Binarization head.

    训练输出 3 通道 (shrink_map, threshold_map, binary_map)，
    含 aux_in_channels 时附加多尺度辅助 maps。推理输出 1 通道 shrink_map。
    """

    def __init__(self, in_channels, k=50, aux_in_channels=0):
        super().__init__()
        self.k = k
        self.aux_in_channels = aux_in_channels
        self.binarize = self._make_head(in_channels)
        self.thresh = self._make_head(in_channels)
        if aux_in_channels > 0:
            # 对齐官方：aux_p4(1/16)->x4, aux_p3(1/8)->x2, aux_p2(1/4)->x1
            self._aux_upsample_scale = {
                "aux_p4": 4,
                "aux_p3": 2,
                "aux_p2": 1,
            }
            for level in ("p4", "p3", "p2"):
                setattr(self, f"aux_binarize_{level}",
                        self._make_head(aux_in_channels))
                setattr(self, f"aux_thresh_{level}",
                        self._make_head(aux_in_channels))

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
        # 兼容 dict（训练，含 fuse + aux_p4/p3/p2）或 tensor（推理 fuse）
        if isinstance(x, dict):
            fuse = x["fuse"]
            aux_feats = {k: x[k] for k in ("aux_p4", "aux_p3", "aux_p2") if k in x}
        else:
            fuse = x
            aux_feats = {}

        shrink_maps = torch.sigmoid(self.binarize(fuse))
        if not self.training:
            return {"maps": shrink_maps}

        threshold_maps = torch.sigmoid(self.thresh(fuse))
        binary_maps = self.step_function(shrink_maps, threshold_maps)
        y = torch.cat([shrink_maps, threshold_maps, binary_maps], dim=1)
        result = {"maps": y}

        if self.aux_in_channels > 0 and aux_feats:
            for key, feat in aux_feats.items():
                level = key[4:]  # 'p4'/'p3'/'p2'
                scale = self._aux_upsample_scale[key]
                if scale > 1:
                    feat = nn.functional.interpolate(
                        feat, scale_factor=scale, mode="bilinear",
                        align_corners=False)
                aux_binarize = getattr(self, "aux_binarize_" + level)
                aux_thresh = getattr(self, "aux_thresh_" + level)
                aux_shrink = torch.sigmoid(aux_binarize(feat))
                aux_thr = torch.sigmoid(aux_thresh(feat))
                aux_binary = self.step_function(aux_shrink, aux_thr)
                result[f"aux_maps_{level}"] = torch.cat(
                    [aux_shrink, aux_thr, aux_binary], dim=1)
        return result
