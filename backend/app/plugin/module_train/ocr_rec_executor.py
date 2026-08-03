"""OCR rec 训练执行器：复用 OCRTrainExecutor 基类，跑 aistation-ocr 容器 train-rec。"""
from .ocr_executor import OCRTrainExecutor


class OCRRecExecutor(OCRTrainExecutor):
    name = "ocr_rec"
