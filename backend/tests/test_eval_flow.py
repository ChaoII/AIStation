"""评估链路：规格推断 + 全量确定性导出 + 重启清状态 + 分类指标解析。"""

import asyncio
import inspect
from types import SimpleNamespace
from unittest.mock import patch

from app.plugin.module_train import eval_scheduler as es
from app.plugin.module_train import exporter
from app.plugin.module_train.exporters import dispatch, yolo

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

    async def get(self, model, pk):
        """``resolve_eval_context`` 会先 ``db.get(TrainModel, model_id)`` 取版本行。

        有任务时假装版本行存在（``repo_id`` 给个不可能命中的值，这样兜底分支
        不会被误触发展示成"两次查询都命中"）；无任务时返回 None，走回退分支。
        """
        return SimpleNamespace(id=pk, repo_id=999) if self._task is not None else None


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


def test_resolve_eval_context_torchkiln_returns_config_name(monkeypatch):
    """TorchKiln 的「规格」就是配置名，必须原样回传给 ``tkiln val -c``。

    这条同时钉住**按版本行 id 匹配**这件事：``TrainTask.model_repo_id`` 字段名有
    误导，存的其实是产出模型行的主键。若改回拿仓库 id 去比，就永远匹配不到，
    恒回退成 ``("det", "tiny")``，于是 ``tkiln val -c det`` 必然失败。
    """
    task = SimpleNamespace(
        annotation_task_id=8, framework="TORKILN",
        hyperparams={"model": "yolo11-seg"},
    )
    assert _run_resolve(task, monkeypatch) == (8, "yolo11-seg", "tiny")


# ---------------------------------------------------------------------------
# 指标解析
# ---------------------------------------------------------------------------

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
    # ⚠️ 必须 patch 到**函数真正所在的模块**：`async_db_session` 是各子模块 import
    # 进来的**模块全局**，在 exporter 这个转发层上打补丁完全不会生效（且不报错）——
    # 症状会表现为「DB 真被连上」或计数不对，离原因很远。
    # 查图发生在 dispatch._export_core，导出在 yolo._export_yolo，两处都要 patch。
    monkeypatch.setattr(dispatch, "async_db_session", lambda: _FakeExportDb(imgs))
    monkeypatch.setattr(yolo, "async_db_session", lambda: _FakeExportDb(imgs))
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


def test_prepare_eval_data_for_task_paddleocr_forwards_for_eval(monkeypatch, tmp_path):
    """PaddleOCR 评估路径须把 for_eval=True 透传给 _export_paddle_ocr。"""
    recorded = {}

    async def fake_paddle(*args, **kwargs):
        recorded.update(kwargs)

    imgs = _images(3)
    # _export_core 在 dispatch 里调用 _export_paddle_ocr，故补丁要打在 dispatch 上；
    # 打在 exporter 转发层上不会生效（别名 ≠ 调用点的模块全局）。
    monkeypatch.setattr(dispatch, "async_db_session", lambda: _FakeExportDb(imgs))
    monkeypatch.setattr(dispatch, "_export_paddle_ocr", fake_paddle)
    asyncio.run(
        exporter.prepare_eval_data_for_task(
            1, 1, "paddle-ocr", str(tmp_path / "out"), annotation_task_id=7, ocr_mode="rec"
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
