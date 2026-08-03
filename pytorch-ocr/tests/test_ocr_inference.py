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


def test_ocr_pipeline_loads_split_vocab_rec_weights():
    """OCRPipeline 从 rec 权重推断双头词表（官方 6906/6910）并正确加载。

    官方 PP-OCRv6 rec 权重 NRTR 头词表 = dict+4 特殊 token（6910），
    MultiHead 必须按权重形状构造，否则加载时报 shape mismatch。
    """
    from pytorch_ocr.converter.ppocr_v6_rec_converter import build_rec_model
    from pytorch_ocr.inference.ocr_pipeline import OCRPipeline, _infer_rec_out_channels

    model = build_rec_model("tiny", ctc_out_channels=6906, nrtr_out_channels=6910)
    rec_state = model.state_dict()

    assert _infer_rec_out_channels(rec_state, {"num_classes": 6906}) == (6906, 6910)

    pipe = OCRPipeline(rec_state=rec_state, config={"model_size": "tiny"})
    assert pipe.rec_head.ctc_head.out_channels == 6906
    assert pipe.rec_head.nrtr_head.out_channels == 6910
    result = pipe.rec_net.load_state_dict(rec_state, strict=True)
    assert result.missing_keys == []
    assert result.unexpected_keys == []


def test_ocr_pipeline_loads_shared_vocab_rec_weights():
    """用户训练产物两头顶共用词表（6906/6906），OCRPipeline 亦能正确加载。"""
    from pytorch_ocr.converter.ppocr_v6_rec_converter import build_rec_model
    from pytorch_ocr.inference.ocr_pipeline import OCRPipeline, _infer_rec_out_channels

    model = build_rec_model("tiny")
    rec_state = model.state_dict()

    assert _infer_rec_out_channels(rec_state, {"num_classes": 6906}) == (6906, 6906)

    pipe = OCRPipeline(rec_state=rec_state, config={"model_size": "tiny"})
    result = pipe.rec_net.load_state_dict(rec_state, strict=True)
    assert result.missing_keys == []
    assert result.unexpected_keys == []
