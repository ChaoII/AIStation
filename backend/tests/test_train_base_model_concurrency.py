"""base_model 解析与训练 GPU 并发上限测试。

覆盖：
- resolve_base_model：无 base_model_id → None；有 storage_path → 下载到 <export_dir>/base/ 并返回文件名
- 全局训练信号量：模块级常量 + 三执行器共享同一实例
- 命令接线：ultralytics → model=/base/<name>；PaddleX → Global.pretrained_model=/pretrained/<name>
"""
import asyncio
import io
import os
from types import SimpleNamespace

from app.plugin.module_train import concurrency
from app.plugin.module_train import scheduler as sch


# ---------------------------------------------------------------------------
# resolve_base_model
# ---------------------------------------------------------------------------
class _TaskNoBase:
    base_model_id = None


def test_resolve_base_model_none_without_id():
    assert asyncio.run(sch.resolve_base_model(_TaskNoBase(), "/tmp/x")) is None


class _FakeSessionCtx:
    def __init__(self, model):
        self._model = model

    async def __aenter__(self):
        model = self._model

        class _Session:
            async def get(self, _model_cls, _pk):
                return model

        return _Session()

    async def __aexit__(self, *_exc):
        return False


class _FakeSessionMaker:
    def __init__(self, model):
        self._model = model

    def __call__(self):
        return _FakeSessionCtx(self._model)


class _FakeS3:
    def __init__(self):
        self.calls: list[str] = []

    def download_fileobj(self, object_key, env=None):
        self.calls.append(object_key)
        return io.BytesIO(b"weights-bytes")


def test_resolve_base_model_downloads_and_returns_basename(monkeypatch, tmp_path):
    model = SimpleNamespace(storage_path="train/models/task_1/best.pt")
    monkeypatch.setattr(sch, "async_db_session", _FakeSessionMaker(model))
    fake_s3 = _FakeS3()
    monkeypatch.setattr("app.utils.s3_client.s3_client", fake_s3)

    task = SimpleNamespace(base_model_id=42)
    name = asyncio.run(sch.resolve_base_model(task, str(tmp_path)))

    assert name == "best.pt"
    assert fake_s3.calls == ["train/models/task_1/best.pt"]
    with open(os.path.join(str(tmp_path), "base", "best.pt"), "rb") as f:
        assert f.read() == b"weights-bytes"


def test_resolve_base_model_none_when_row_missing(monkeypatch, tmp_path):
    monkeypatch.setattr(sch, "async_db_session", _FakeSessionMaker(None))
    task = SimpleNamespace(base_model_id=42)
    assert asyncio.run(sch.resolve_base_model(task, str(tmp_path))) is None


def test_resolve_base_model_none_when_no_storage_path(monkeypatch, tmp_path):
    model = SimpleNamespace(storage_path=None)
    monkeypatch.setattr(sch, "async_db_session", _FakeSessionMaker(model))
    task = SimpleNamespace(base_model_id=42)
    assert asyncio.run(sch.resolve_base_model(task, str(tmp_path))) is None


# ---------------------------------------------------------------------------
# 全局训练 GPU 并发
# ---------------------------------------------------------------------------
def test_train_gpu_concurrency_is_module_level():
    assert isinstance(concurrency.TRAIN_GPU_CONCURRENCY, int)
    assert concurrency.TRAIN_GPU_CONCURRENCY >= 1


def test_train_semaphore_is_shared_singleton():
    assert concurrency.get_train_semaphore() is concurrency.get_train_semaphore()


def test_all_executors_use_global_semaphore():
    """TrainExecutor 与 PaddleX 执行器的容器阶段都走全局信号量（三执行器共享）。"""
    import inspect

    from app.plugin.module_train.paddlex_executor import PaddleXOCRExecutor
    from app.plugin.module_train.scheduler import TrainExecutor

    assert "get_train_semaphore" in inspect.getsource(TrainExecutor._execute)
    # det/rec 共用父类 _execute
    assert "get_train_semaphore" in inspect.getsource(PaddleXOCRExecutor._execute)


# ---------------------------------------------------------------------------
# 命令接线
# ---------------------------------------------------------------------------
def test_ultralytics_cmd_uses_base_model():
    cmd = sch._build_ultralytics_cmd(
        {"model": "yolo11n.pt", "epochs": 10}, "/data", "/output", "detection",
        base_model_name="best.pt",
    )
    s = " ".join(cmd)
    assert "model=/base/best.pt" in s
    assert "model=/models/yolo11n.pt" not in s


def test_paddlex_cmd_uses_base_model():
    cmd = sch._build_paddlex_ocr_cmd(
        {"mode": "det", "model_size": "small", "pretrained": False},
        "/data", "/output", mode="det", base_model_name="best_accuracy.pdparams",
    )
    s = " ".join(cmd)
    assert "Global.pretrained_model=/pretrained/best_accuracy.pdparams" in s


def test_default_cmds_unchanged_without_base_model():
    yolo = " ".join(sch._build_ultralytics_cmd({"model": "yolo11n.pt"}, "/data", "/output", "detection"))
    assert "model=/models/yolo11n.pt" in yolo
    pad = " ".join(sch._build_paddlex_ocr_cmd({"mode": "det", "pretrained": True}, "/data", "/output", mode="det"))
    assert "Global.pretrained_model=/pretrained/det.pdparams" in pad
