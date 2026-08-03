"""Paddle→PyTorch 权重转换工具（PP-OCRv6 det）。"""
from .ppocr_v6_det_converter import (
    ConversionReport,
    build_det_model,
    convert_ppocr_v6_det,
    convert_with_report,
    map_param_name,
    ordered_paddle_entries,
    ordered_torch_entries,
    parse_paddle_name,
)

__all__ = [
    "ConversionReport",
    "build_det_model",
    "convert_ppocr_v6_det",
    "convert_with_report",
    "map_param_name",
    "ordered_paddle_entries",
    "ordered_torch_entries",
    "parse_paddle_name",
]
