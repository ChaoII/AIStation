"""MultiHead：CTC + NRTR 双头（对齐 PaddleOCR rec_multi_head.py）。

输入 backbone（rec 模式）特征 [B, C, H, W]（H=1），先 reshape 为 [B, W, C]，
再分别送入 CTCHead / NRTRHead。训练输出 dict ``{"ctc": ..., "nrtr": ...}``。

CTCHead 的 Neck 支持两种：
- ``{"name": "reshape"}``：tiny，直接 reshape + CTCHead（use_guide/mid_channels）。
- ``{"name": "lightsvtr", ...}``：small/medium，先经 ``LightSVTR`` neck 提特征，
  再由 ``nn.Linear(dims, out_channels)`` 映射到 CTC 字符类别（PP-OCRv6
  small/medium 的官方结构）。
"""
import torch
import torch.nn as nn

from ..necks.rec_lightsvtr import LightSVTR
from .rec_ctc_head import CTCHead
from .rec_nrtr_head import NRTRHead

# PP-OCRv6 lightsvtr neck 官方配置（PP-OCRv6_small/medium_rec.yml）
_LIGHTSVTR_PRESET = {
    "small": {"dims": 120, "depth": 2, "mlp_ratio": 2.0, "local_kernel": 7},
    "medium": {"dims": 192, "depth": 2, "mlp_ratio": 4.0, "local_kernel": 7},
}
_NRTR_DIM_PRESET = {"small": 384, "medium": 512}


def build_default_head_list(model_size="tiny", nrtr_dim=None, max_text_length=25):
    """按 model_size 构建默认 rec 双头 head_list。

    tiny → reshape neck（CTCHead use_guide + mid_channels=80，现有行为）；
    small/medium → lightsvtr neck（官方 dims/depth/mlp_ratio/local_kernel）。
    """
    if nrtr_dim is None:
        nrtr_dim = _NRTR_DIM_PRESET.get(model_size, 384)
    if model_size in _LIGHTSVTR_PRESET:
        neck = {"name": "lightsvtr", **_LIGHTSVTR_PRESET[model_size]}
        head = {}
    else:
        neck = {"name": "reshape"}
        head = {"mid_channels": 80, "use_guide": True}
    return [
        {"CTCHead": {"Neck": neck, "Head": head}},
        {"NRTRHead": {"nrtr_dim": nrtr_dim, "max_text_length": max_text_length}},
    ]


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
        self.ctc_neck = None
        for entry in head_list:
            if "CTCHead" in entry:
                args = entry["CTCHead"]
                head_args = args.get("Head", {})
                neck_args = args.get("Neck", {"name": "reshape"})
                neck_name = neck_args.get("name", "reshape")
                if neck_name == "lightsvtr":
                    # LightSVTR neck + Linear：PP-OCRv6 small/medium CTCHead 结构
                    self.ctc_neck = LightSVTR(
                        in_channels=in_channels,
                        dims=neck_args.get("dims", 120),
                        depth=neck_args.get("depth", 2),
                        mlp_ratio=neck_args.get("mlp_ratio", 2.0),
                        local_kernel=neck_args.get("local_kernel", 7),
                        use_guide=neck_args.get("use_guide", False),
                    )
                    self.ctc_head = nn.Linear(
                        self.ctc_neck.out_channels, self.ctc_out_channels
                    )
                else:
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
            if self.ctc_neck is not None:
                ctc = self.ctc_neck(x)  # [B, W, dims]
                ctc = self.ctc_head(ctc)  # [B, W, out]
                if not self.training:
                    ctc = torch.softmax(ctc, dim=2)
                res["ctc"] = ctc
            else:
                res["ctc"] = self.ctc_head(x)
        if self.nrtr_head is not None:
            res["nrtr"] = self.nrtr_head(x, targets)
        return res
