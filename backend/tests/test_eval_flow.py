"""评估链路：规格推断 + 全量确定性导出 + 重启清状态 + 分类指标解析。"""

import asyncio
import inspect
from types import SimpleNamespace
from unittest.mock import patch

from app.plugin.module_train import eval_scheduler as es
from app.plugin.module_train import exporter

# ---------------------------------------------------------------------------
# 规格推断 resolve_eval_context
# ---------------------------------------------------------------------------


def test_resolve_eval_context_exists():
    assert hasattr(es, "resolve_eval_context")


class _FakeSession:
    def __init__(self, task):
        self._task = task

    async def execute(self, stmt):
        return SimpleNamespace(scalar_one_or_none=lambda: self._task)


class _FakeDbSession:
    def __init__(self, session):
        self._session = session

    async def __aenter__(self):
        return self._session

    async def __aexit__(self, *exc):
        return False


def _run_resolve(task, monkeypatch):
    monkeypatch.setattr(es, "async_db_session", lambda: _FakeDbSession(_FakeSession(task)))
    return asyncio.run(es.resolve_eval_context(42))


def test_resolve_eval_context_no_task_defaults(monkeypatch):
    assert _run_resolve(None, monkeypatch) == (None, "det", "tiny")


def test_resolve_eval_context_reads_task_hyperparams(monkeypatch):
    task = SimpleNamespace(
        annotation_task_id=7, hyperparams={"mode": "rec", "model_size": "small"}
    )
    assert _run_resolve(task, monkeypatch) == (7, "rec", "small")


def test_resolve_eval_context_sanitizes_invalid_values(monkeypatch):
    task = SimpleNamespace(
        annotation_task_id=None, hyperparams={"mode": "bogus", "model_size": "huge"}
    )
    assert _run_resolve(task, monkeypatch) == (None, "det", "tiny")


# ---------------------------------------------------------------------------
# 指标解析
# ---------------------------------------------------------------------------

def test_yolo_cls_metrics_parse():
    line = "                 all        100        200      0.912      0.977"
    assert es._parse_yolo_cls_line(line) == {"top1": 0.912, "top5": 0.977}


def test_yolo_cls_metrics_none_on_five_col_non_all():
    line = "                  1          50         100      0.912      0.977"
    assert es._parse_yolo_cls_line(line) is None


def test_accumulate_yolo_metrics_classification():
    """分类 5 列汇总行走 top1/top5 分支。"""
    metrics = {}
    out = es._accumulate_yolo_metrics(
        "                 all        100        200      0.912      0.977", metrics
    )
    assert out == {"top1": 0.912, "top5": 0.977}


def test_accumulate_yolo_metrics_detection_unchanged():
    """检测 7 列汇总行仍走 precision/recall/map50/map5095 分支。"""
    metrics = {}
    out = es._accumulate_yolo_metrics(
        "                 all        100        500      0.801      0.701      0.805      0.601",
        metrics,
    )
    assert out == {
        "precision": 0.801,
        "recall": 0.701,
        "map50": 0.805,
        "map5095": 0.601,
    }


# ---------------------------------------------------------------------------
# 全量确定性导出（for_eval）
# ---------------------------------------------------------------------------

class _FakeS3:
    def download_fileobj(self, key):
        return SimpleNamespace(read=lambda: b"img-bytes")


class _FakeScalars:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows


class _FakeExportSession:
    """按查询主体返回图片列表或空标注记录。"""

    def __init__(self, images):
        self._images = images

    async def execute(self, stmt):
        desc = getattr(stmt, "column_descriptions", None) or []
        entity = desc[0].get("entity") if desc else None
        if entity is not None and entity.__name__ == "AnnotationImageModel":
            return SimpleNamespace(
                scalars=lambda: _FakeScalars(self._images),
                scalar_one_or_none=lambda: None,
            )
        return SimpleNamespace(
            scalars=lambda: _FakeScalars([]), scalar_one_or_none=lambda: None
        )

    async def get(self, model, pk):
        return None


class _FakeExportDb:
    def __init__(self, images):
        self._images = images

    async def __aenter__(self):
        return _FakeExportSession(self._images)

    async def __aexit__(self, *exc):
        return False


def _images(n):
    return [
        SimpleNamespace(
            id=i, filename=f"img_{i}.jpg", object_key=f"k{i}", width=100, height=100
        )
        for i in range(1, n + 1)
    ]


def _run_eval_export(monkeypatch, tmp_path, framework="ultralytics", ocr_mode="det"):
    imgs = _images(3)
    monkeypatch.setattr(exporter, "async_db_session", lambda: _FakeExportDb(imgs))
    with patch("app.utils.s3_client.s3_client", _FakeS3()):
        out = tmp_path / "out"
        asyncio.run(
            exporter.prepare_eval_data_for_task(
                1, 1, framework, str(out), annotation_task_id=7, ocr_mode=ocr_mode
            )
        )
    return out


def test_prepare_eval_data_for_task_puts_all_images_in_val(monkeypatch, tmp_path):
    out = _run_eval_export(monkeypatch, tmp_path)
    val_files = sorted(p.name for p in (out / "images" / "val").glob("*.jpg"))
    train_dir = out / "images" / "train"
    train_files = sorted(p.name for p in train_dir.glob("*.jpg")) if train_dir.exists() else []
    assert val_files == ["img_1.jpg", "img_2.jpg", "img_3.jpg"]
    assert train_files == []


def test_prepare_eval_data_for_task_yaml_path_is_data(monkeypatch, tmp_path):
    """评估导出的 dataset.yaml 基础路径须为 /data，否则容器内 yolo val 找不到数据。"""
    out = _run_eval_export(monkeypatch, tmp_path)
    content = (out / "dataset.yaml").read_text(encoding="utf-8")
    assert "path: /data" in content
    assert "path: ." not in content


def test_prepare_eval_data_for_task_signature():
    sig = inspect.signature(exporter.prepare_eval_data_for_task)
    assert "annotation_task_id" in sig.parameters
    assert "ocr_mode" in sig.parameters


def test_prepare_eval_data_for_task_paddle_forwards_for_eval(monkeypatch, tmp_path):
    """PaddleOCR 评估路径须把 for_eval=True 透传给 _export_paddle_ocr。"""
    recorded = {}

    async def fake_paddle(*args, **kwargs):
        recorded.update(kwargs)

    imgs = _images(3)
    monkeypatch.setattr(exporter, "async_db_session", lambda: _FakeExportDb(imgs))
    monkeypatch.setattr(exporter, "_export_paddle_ocr", fake_paddle)
    asyncio.run(
        exporter.prepare_eval_data_for_task(
            1, 1, "paddlex", str(tmp_path / "out"), annotation_task_id=7, ocr_mode="rec"
        )
    )
    assert recorded.get("for_eval") is True
    assert recorded.get("export_rec") is True


# ---------------------------------------------------------------------------
# start_evaluation 重启清状态
# ---------------------------------------------------------------------------

def test_start_evaluation_clears_state():
    src = inspect.getsource(es.start_evaluation)
    for field in (
        "metrics=None",
        "metrics_log=None",
        "best_metrics=None",
        "last_metrics=None",
        "log=None",
        "error_log=None",
        "finished_at=None",
    ):
        assert field in src, field
