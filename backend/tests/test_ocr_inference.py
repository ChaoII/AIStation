"""OCR 推理管线测试：det→rec 串联结构 + 合成图 smoke。"""
import numpy as np

from pytorch_ocr.inference.ocr_pipeline import OCRPipeline


def test_ocr_pipeline_constructs():
    pipe = OCRPipeline()
    assert pipe is not None
    assert hasattr(pipe, "det_net")
    assert hasattr(pipe, "rec_net")


def test_ocr_pipeline_call_returns_list():
    pipe = OCRPipeline()
    # 纯黑图：管线应返回列表（可能为空）
    img = np.zeros((640, 640, 3), dtype=np.uint8)
    result = pipe(img)
    assert isinstance(result, list)
    # 每项有 text/confidence/box
    if result:
        assert "text" in result[0]
        assert "confidence" in result[0]
        assert "box" in result[0]


def test_ocr_pipeline_smoke_synthetic_image():
    """随机权重管线在带亮色矩形的合成图上运行：返回列表，
    非空项必须包含 text/confidence/box 键（不要求检出）。"""
    pipe = OCRPipeline()
    img = np.zeros((640, 640, 3), dtype=np.uint8)
    img[200:440, 150:500] = (255, 255, 255)
    result = pipe(img)
    assert isinstance(result, list)
    for item in result:
        assert "text" in item
        assert "confidence" in item
        assert "box" in item
