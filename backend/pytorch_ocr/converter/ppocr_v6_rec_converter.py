"""PP-OCRv6 rec 权重转换：Paddle .pdparams → PyTorch state_dict。

复用 plan 1 的位置对应法（``ppocr_v6_det_converter.convert_with_report``）：
Paddle 保存序 ↔ 自研模型注册序，kind+shape 双校验。

rec 网络：``PPLCNetV4(det=False)``（单特征 [B, C, 1, W]）+ ``MultiHead``
（CTCHead + NRTRHead 双头）。

.. note::
    head 内 ``Linear`` / ``Embedding`` / ``LayerNorm`` / ``Conv1d`` 等参数在
    Paddle 侧的命名与 det 的 ``conv2d_N``/``batch_norm_N`` 不同，位置对应法
    目前只能覆盖 backbone 的 ``conv2d``/``batch_norm``（det 转换器已解析的
    两类）。NRTRHead 的 Transformer 层序对齐（attention QKV/FFN/embedding）
    需在 plan 3b（paddlex 容器）以真实权重核对。
"""
import logging

import torch.nn as nn

from ..modeling.backbones.pplcnetv4 import PPLCNetV4
from ..modeling.heads.rec_multi_head import MultiHead
from .ppocr_v6_det_converter import ConversionReport, convert_with_report

logger = logging.getLogger(__name__)

__all__ = ["ConversionReport", "build_rec_model", "convert_ppocr_v6_rec"]


def build_rec_model(
    model_size: str = "tiny",
    out_channels: int = 6906,
    backbone_out_channels: int = 160,
    max_text_length: int = 25,
    nrtr_dim: int = 384,
) -> nn.Module:
    """构建自研 PP-OCRv6 rec 模型（PPLCNetV4(rec) + MultiHead）。

    参数路径前缀固定为 ``backbone.*`` / ``head.*``，与转换结果保持一致。
    ``out_channels`` 默认 6906（官方 ppocrv6_tiny_dict.txt 词表 + blank）。
    """
    backbone = PPLCNetV4(model_size=model_size, det=False)
    head = MultiHead(
        in_channels=backbone_out_channels,
        out_channels=out_channels,
        max_text_length=max_text_length,
        nrtr_dim=nrtr_dim,
    )
    model = nn.Module()
    model.backbone = backbone
    model.head = head
    model.eval()
    return model


def convert_ppocr_v6_rec(
    paddle_state: dict,
    model_size: str = "tiny",
    out_channels: int = 6906,
    backbone_out_channels: int = 160,
    max_text_length: int = 25,
    nrtr_dim: int = 384,
) -> dict:
    """转换 Paddle state dict 为 PyTorch state dict。

    ``paddle_state``: {paddle_param_name: np.ndarray}（Paddle .pdparams 内容）
    返回 ``{pytorch_param_name: torch.Tensor}``，可 ``strict=False`` 加载进
    ``build_rec_model(model_size)`` 构造的模型。
    """
    model = build_rec_model(
        model_size,
        out_channels=out_channels,
        backbone_out_channels=backbone_out_channels,
        max_text_length=max_text_length,
        nrtr_dim=nrtr_dim,
    )
    state, report = convert_with_report(paddle_state, model)
    for warning in report.warnings:
        logger.warning("weight converter (rec): %s", warning)
    if report.matched == 0:
        raise ValueError("no parameters mapped — check Paddle param name format")
    return state
