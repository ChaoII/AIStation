"""MultiHead：CTC + NRTR 双头（对齐 PaddleOCR rec_multi_head.py）。

输入 backbone（rec 模式）特征 [B, C, H, W]（H=1），先 reshape 为 [B, W, C]，
再分别送入 CTCHead / NRTRHead。训练输出 dict ``{"ctc": ..., "nrtr": ...}``。
"""
import torch.nn as nn

from .rec_ctc_head import CTCHead
from .rec_nrtr_head import NRTRHead


class FCTranspose(nn.Module):
    """reshape: [B, C, 1, W] -> [B, W, C]（neck）。"""

    def forward(self, x):
        x = x.squeeze(2)  # [B, C, W] after H=1
        return x.permute(0, 2, 1)  # [B, W, C]


class MultiHead(nn.Module):
    def __init__(self, in_channels, out_channels, max_text_length=25,
                 nrtr_dim=384, head_list=None,
                 ctc_out_channels=None, nrtr_out_channels=None):
        super().__init__()
        if head_list is None:
            head_list = [
                {"CTCHead": {"Neck": {"name": "reshape"},
                             "Head": {"mid_channels": 80, "use_guide": True}}},
                {"NRTRHead": {"nrtr_dim": nrtr_dim,
                              "max_text_length": max_text_length}},
            ]
        # 官方 PP-OCRv6 双头词表大小不同：CTCHead=dict 大小，NRTR/GTCHead=dict+4 特殊 token。
        # 单独指定时优先（转换官方权重必需），默认共用 out_channels。
        self.ctc_out_channels = ctc_out_channels or out_channels
        self.nrtr_out_channels = nrtr_out_channels or out_channels
        self.head_list = head_list
        self.ctc_head = None
        self.nrtr_head = None
        for entry in head_list:
            if "CTCHead" in entry:
                args = entry["CTCHead"]
                head_args = args.get("Head", {})
                self.ctc_head = CTCHead(
                    in_channels=in_channels,
                    out_channels=self.ctc_out_channels,
                    mid_channels=head_args.get("mid_channels"),
                    use_guide=head_args.get("use_guide", False),
                )
            elif "NRTRHead" in entry:
                args = entry["NRTRHead"]
                self.nrtr_head = NRTRHead(
                    in_channels=in_channels,
                    out_channels=self.nrtr_out_channels,
                    nrtr_dim=args.get("nrtr_dim", 384),
                    max_text_length=args.get("max_text_length", 25),
                )

    def forward(self, x, targets=None):
        # x: [B, C, H, W] from backbone (rec, H=1)
        x = x.squeeze(2)  # [B, C, W]
        x = x.permute(0, 2, 1)  # [B, W, C]
        res = {}
        if self.ctc_head is not None:
            res["ctc"] = self.ctc_head(x)
        if self.nrtr_head is not None:
            res["nrtr"] = self.nrtr_head(x, targets)
        return res
