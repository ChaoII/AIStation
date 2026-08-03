"""OCR 推理管线：det 检测 → rec 识别 → 聚合。"""
from .ocr_pipeline import OCRPipeline

__all__ = ["OCRPipeline"]
