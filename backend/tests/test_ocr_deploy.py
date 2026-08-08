"""PaddleX 部署测试：server 脚本生成 + 部署框架判定 + rec_model_path 守卫。"""
import asyncio

from app.plugin.module_train.deploy_executor import (
    _execute_deployment,
    _generate_paddlex_server_script,
    _is_paddlex_framework,
)
from app.plugin.module_train.model import TrainFramework


def test_is_paddlex_framework():
    assert _is_paddlex_framework(TrainFramework.PADDLEX) is True
    assert _is_paddlex_framework(TrainFramework.ULTRALYTICS) is False


def test_generate_paddlex_server_script():
    script = _generate_paddlex_server_script(api_key="test_key", device="0")
    assert "paddlex" in script.lower() or "PaddleOCR" in script
    assert "/model/det.pdparams" in script
    assert "/model/rec.pdparams" in script
    assert "X-API-Key" in script or "api_key" in script
    assert "PP-OCRv6" in script


def test_generate_paddlex_server_script_embeds_api_key():
    script = _generate_paddlex_server_script(api_key="secret_abc", device="cpu")
    assert 'API_KEY = "secret_abc"' in script or "API_KEY = 'secret_abc'" in script


def test_execute_deployment_paddlex_requires_rec_model(monkeypatch):
    """PaddleX 部署缺 rec_model_path 必须拒绝（否则推理管线无 rec 权重）。"""
    class FakeDeploy:
        framework = TrainFramework.PADDLEX
        status = "pending"
        model_id = 1
        storage_path = None
        api_key = "k"
        device = "cpu"
        host_port = 0
        hyperparams = {}

    class FakeModel:
        storage_path = "model_repo/x.pdparams"

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

    asyncio.run(_execute_deployment(999))

    assert fake_db.values is not None
    assert fake_db.values.get("status") == "failed"
    assert "rec_model_path" in (fake_db.values.get("error_log") or "")


def test_execute_deployment_paddlex_with_rec_passes_guard(monkeypatch):
    """PaddleX 部署已提供 rec_model_path → 通过守卫，进入 pull_image。"""
    class FakeDeploy:
        framework = TrainFramework.PADDLEX
        status = "pending"
        model_id = 1
        storage_path = None
        api_key = "k"
        device = "cpu"
        host_port = 0
        hyperparams = {"rec_model_path": "model_repo/rec.pdparams"}

    class FakeModel:
        storage_path = "model_repo/x.pdparams"

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

    class Boom(Exception):
        pass

    async def _boom(*a, **k):
        raise Boom("reached pull_image")

    monkeypatch.setattr(de, "pull_image", _boom)

    asyncio.run(_execute_deployment(999))

    assert fake_db.values is not None
    assert fake_db.values.get("status") == "failed"
    assert "rec_model_path" not in (fake_db.values.get("error_log") or "")
    assert "pull_image" in (fake_db.values.get("error_log") or "")
