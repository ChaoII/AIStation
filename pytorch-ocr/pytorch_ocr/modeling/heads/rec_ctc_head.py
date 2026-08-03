"""CTCHead（自研，对齐 PaddleOCR rec_ctc_head.py）。

输入 [B, W, C] 特征，输出字符分类 logits [B, W, num_classes]。
- ``use_guide=True`` 时先用逐通道 Conv1d 引导层（depthwise conv + BN + Hardswish）。
- ``mid_channels`` 非空时经两层 Linear（in -> mid -> out）映射到字符数。
- 训练模式返回 logits；推理模式返回 softmax 概率。
"""
import torch
import torch.nn as nn


class CTCHead(nn.Module):
    def __init__(
        self,
        in_channels,
        out_channels=6625,
        mid_channels=None,
        use_guide=False,
    ):
        super().__init__()
        self.use_guide = use_guide
        if use_guide:
            self.guide_layer = nn.Sequential(
                nn.Conv1d(
                    in_channels,
                    in_channels,
                    5,
                    padding=2,
                    groups=in_channels,
                    bias=False,
                ),
                nn.BatchNorm1d(in_channels),
                nn.Hardswish(),
                nn.Conv1d(in_channels, in_channels, 1, bias=False),
                nn.BatchNorm1d(in_channels),
                nn.Hardswish(),
            )
        if mid_channels is None:
            self.fc = nn.Linear(in_channels, out_channels, bias=True)
        else:
            self.fc1 = nn.Linear(in_channels, mid_channels, bias=True)
            self.fc2 = nn.Linear(mid_channels, out_channels, bias=True)
        self.mid_channels = mid_channels
        self.out_channels = out_channels

    def forward(self, x):
        # x: [B, W, C]
        if self.use_guide:
            x = x.permute(0, 2, 1)  # [B, C, W]
            x = self.guide_layer(x)
            x = x.permute(0, 2, 1)  # [B, W, C]
        if self.mid_channels is None:
            predicts = self.fc(x)
        else:
            x = self.fc1(x)
            predicts = self.fc2(x)
        if not self.training:
            predicts = torch.softmax(predicts, dim=2)
        return predicts
