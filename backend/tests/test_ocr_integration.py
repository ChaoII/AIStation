"""OCR 训练后端集成测试。"""
import inspect

from app.plugin.module_train.exporter import _export_core
from app.plugin.module_train.model import TrainFramework
from app.plugin.module_train.scheduler import _build_cmd


def test_pytorch_ocr_det_framework_defined():
    assert TrainFramework.PYTORCH_OCR_DET == "pytorch-ocr-det"


def test_pytorch_ocr_rec_framework_defined():
    assert TrainFramework.PYTORCH_OCR_REC == "pytorch-ocr-rec"


def test_build_cmd_has_ocr_branch():
    src = inspect.getsource(_build_cmd)
    assert "pytorch-ocr-det" in src or "PYTORCH_OCR_DET" in src


def test_build_cmd_has_rec_branch():
    src = inspect.getsource(_build_cmd)
    assert "pytorch-ocr-rec" in src or "PYTORCH_OCR_REC" in src


def test_export_core_has_pytorch_ocr_branch():
    src = inspect.getsource(_export_core)
    assert "pytorch-ocr-det" in src or "PYTORCH_OCR_DET" in src
