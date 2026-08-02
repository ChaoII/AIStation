"""测试多标签分类数据集导出（YOLO CLS multi-label 格式）。"""
import asyncio
import inspect
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from app.plugin.module_train import exporter
from app.plugin.module_train.exporter import _export_core, _export_yolo_cls


def test_export_yolo_cls_accepts_multi_label_param():
    """_export_yolo_cls 应支持 multi_label 参数（规范参数检查）。"""
    sig = inspect.signature(_export_yolo_cls)
    assert "multi_label" in sig.parameters


def test_export_core_passes_classification_mode():
    """_export_core 应读取 annotation_task.classification_mode 并传给 _export_yolo_cls。"""
    src = inspect.getsource(_export_core)
    assert "classification_mode" in src


class _FakeScalars:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows


class _FakeResult:
    def __init__(self, rows):
        self._rows = rows

    def scalars(self):
        return _FakeScalars(self._rows)


class _FakeSession:
    def __init__(self, images, ann_task=None):
        self._images = images
        self._ann_task = ann_task

    async def execute(self, stmt):
        return _FakeResult(self._images)

    async def get(self, model, pk):
        return self._ann_task


class _FakeDbSession:
    def __init__(self, session):
        self._session = session

    async def __aenter__(self):
        return self._session

    async def __aexit__(self, *exc):
        return False


def _make_ann_task(task_type, classification_mode=None):
    return SimpleNamespace(
        task_type=task_type,
        classification_mode=classification_mode,
        classes=[{"id": 1, "name": "cat"}, {"id": 2, "name": "dog"}],
    )


def _run_export(tmp_path, task_type, classification_mode):
    images = [SimpleNamespace(id=1, filename="a.jpg", object_key="a.jpg", dataset_id=1, height=100, width=100)]
    ann_task = _make_ann_task(task_type, classification_mode)
    session = _FakeDbSession(_FakeSession(images, ann_task))

    with (
        patch.object(exporter, "async_db_session", return_value=session),
        patch.object(exporter, "_export_yolo_cls", new=AsyncMock()) as yolo_cls,
        patch.object(exporter, "_export_yolo", new=AsyncMock()) as yolo,
    ):
        asyncio.run(exporter._export_core(1, 1, "ultralytics", str(tmp_path / "out"), annotation_task_id=7))

    return yolo_cls, yolo


def test_classification_routes_to_export_yolo_cls(tmp_path):
    """task_type='classification' 应路由到 _export_yolo_cls（而非 _export_yolo）。"""
    yolo_cls, yolo = _run_export(tmp_path, "classification", "multi")
    yolo_cls.assert_awaited_once()
    assert yolo_cls.await_args.kwargs["multi_label"] is True
    yolo.assert_not_awaited()


def test_classification_single_mode_passes_multi_label_false(tmp_path):
    """classification + single 模式应传 multi_label=False。"""
    yolo_cls, _ = _run_export(tmp_path, "classification", "single")
    yolo_cls.assert_awaited_once()
    assert yolo_cls.await_args.kwargs["multi_label"] is False


def test_detection_routes_to_export_yolo(tmp_path):
    """task_type='detection' 仍应路由到 _export_yolo。"""
    yolo_cls, yolo = _run_export(tmp_path, "detection", None)
    yolo.assert_awaited_once()
    yolo_cls.assert_not_awaited()
