"""OCR 部署测试：server 脚本生成 + 部署框架判定。"""


from app.plugin.module_train.deploy_executor import (
    _execute_deployment,
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


def test_execute_deployment_rejects_rec_framework(monkeypatch):
    """rec 部署（det+rec 双模型关联未实现）必须以明确错误拒绝，不能产出垃圾权重。"""
    class FakeDeploy:
        framework = TrainFramework.PYTORCH_OCR_REC
        status = "pending"
        model_id = 1
        storage_path = None
        api_key = "k"
        device = "cpu"
        host_port = 0
        hyperparams = {}

    class FakeModel:
        storage_path = "model_repo/x.pt"

    class FakeResult:
        def scalar(self):
            return None

    class FakeDB:
        def __init__(self):
            self.values = None

        async def get(self, model, deploy_id):
            return FakeDeploy() if model.__name__ == "TrainDeploy" else FakeModel()

        async def execute(self, stmt):
            return FakeResult()

    fake_db = FakeDB()

    class FakeSessionCM:
        async def __aenter__(self):
            return fake_db

        async def __aexit__(self, *args):
            return False

    class FakeSessionFactory:
        def __call__(self, *a, **k):
            return FakeSessionCM()

        def begin(self):
            return FakeSessionCM()

    import app.plugin.module_train.deploy_executor as de
    monkeypatch.setattr(de, "async_db_session", FakeSessionFactory())

    class FakeUpdateStmt:
        def where(self, *a, **k):
            return self

        def values(self, **kw):
            fake_db.values = dict(kw)
            return self

    monkeypatch.setattr(de, "update", lambda *a, **k: FakeUpdateStmt())

    import asyncio
    asyncio.run(_execute_deployment(999))

    assert fake_db.values is not None
    assert fake_db.values.get("status") == "failed"
    assert "双模型关联" in (fake_db.values.get("error_log") or "")
