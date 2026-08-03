"""OCR 部署测试：server 脚本生成 + 部署框架判定。"""

from app.plugin.module_train.deploy_executor import (
    _generate_ocr_server_script,
    _is_ocr_framework,
)
from app.plugin.module_train.model import TrainFramework


def test_is_ocr_framework():
    assert _is_ocr_framework(TrainFramework.PYTORCH_OCR_DET) is True
    assert _is_ocr_framework(TrainFramework.PYTORCH_OCR_REC) is True
    assert _is_ocr_framework(TrainFramework.ULTRALYTICS) is False
    assert _is_ocr_framework(TrainFramework.PADDLEX) is False


def test_generate_ocr_server_script():
    script = _generate_ocr_server_script(api_key="test_key", device="0")
    assert "OCRPipeline" in script
    assert "det.pt" in script or "det" in script
    assert "rec.pt" in script or "rec" in script
    assert "X-API-Key" in script or "api_key" in script
    assert "sys.path.insert(0, \"/workspace\")" in script
    assert "/model/det.pt" in script


def test_generate_ocr_server_script_embeds_api_key():
    script = _generate_ocr_server_script(api_key="secret_abc", device="cpu")
    assert 'API_KEY = "secret_abc"' in script
