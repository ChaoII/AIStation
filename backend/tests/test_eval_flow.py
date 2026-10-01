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
    """找不到产出该模型的训练任务：配置名回退成**空串**。

    ⚠️ 这里原先断言的是 ``"det"``，改掉是有意的：第二项现在的语义是
    **TorchKiln 配置名**（``configs/`` 下的 model_name），而 ``"det"`` 作为配置名
    根本不存在。返回空串让 :func:`EvalExecutor._execute` 走「找不到配置名」的
    可读报错；返回 ``"det"`` 会被当成真实模型名去 ``resolve_config_path`` 查，
    查不到就原样返回，最终在容器里报一个与真实原因无关的错。
    """
    assert _run_resolve(None, monkeypatch) == (None, "", "tiny")


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
    """TorchKiln 的「规格」就是配置名，必须原样回传给作业 spec 的 ``config_path``。

    这条同时钉住**按版本行 id 匹配**这件事：``TrainTask.model_repo_id`` 字段名有
    误导，存的其实是产出模型行的主键。若改回拿仓库 id 去比，就永远匹配不到，
    恒回退成空配置名，于是评估在提交作业前就被拒。
    """
    task = SimpleNamespace(
        annotation_task_id=8, framework="TORKILN",
        hyperparams={"model": "yolo11-seg"},
    )
    assert _run_resolve(task, monkeypatch) == (8, "yolo11-seg", "tiny")


def test_resolve_eval_context_retired_framework_keeps_mode_semantics(monkeypatch):
    """非 TorchKiln 训练任务仍按 mode/size 语义回退。

    这条通路（Ultralytics/PaddleX）已退场，但**推断函数本身**保留 mode/size
    行为是为了不改动既有分支；调用侧的守卫在 ``ensure_active``。
    """
    task = SimpleNamespace(
        annotation_task_id=7, framework="ULTRALYTICS",
        hyperparams={"mode": "rec", "model_size": "small"},
    )
    assert _run_resolve(task, monkeypatch) == (7, "rec", "small")


# ---------------------------------------------------------------------------
# 指标契约（替代原先的日志正则解析）
# ---------------------------------------------------------------------------

class _FakeClient:
    """只实现 ``metrics()``——``_read_metrics`` 只需要这一个方法。"""

    def __init__(self, events):
        self._events = events
        self.kwargs = None

    async def metrics(self, job_id, offset=-1, limit=5000, kind="train"):
        self.kwargs = {"offset": offset, "limit": limit, "kind": kind}
        return list(self._events)


def _read_metrics(events):
    import asyncio

    c = _FakeClient(events)
    return asyncio.run(es.EvalExecutor._read_metrics(c, "job_x")), c


def test_read_metrics_merges_submetrics_and_main_indicator():
    """评估契约：一条 ``eval`` 事件 = 全量子指标 + 主指标 + fps。

    这些字段原先全靠正则从 ``cur metric, k: v, ...`` 里抠出来。
    """
    got, _c = _read_metrics([
        {"type": "eval", "seq": 0, "main_indicator": "mask_mAP50-95",
         "main_value": 0.83, "fps": 12.3,
         "metrics": {"box_mAP50": 0.87, "box_mAP50-95": 0.6, "mask_mAP50": 0.79}},
        {"type": "end", "seq": 1, "exit_reason": "finished"},
    ])
    assert got["main_indicator"] == "mask_mAP50-95"
    assert got["main_value"] == 0.83
    assert got["fps"] == 12.3
    assert got["box_mAP50"] == 0.87
    assert got["mask_mAP50"] == 0.79


def test_read_metrics_ignores_end_event():
    """``end`` 只是终态标记，不该混进指标字典。"""
    got, _c = _read_metrics([
        {"type": "eval", "seq": 0, "main_value": 0.5, "metrics": {"box_mAP50": 0.5}},
        {"type": "end", "seq": 1, "exit_reason": "finished", "main_value": 0.5},
    ])
    assert "exit_reason" not in got
    assert got["main_value"] == 0.5


def test_read_metrics_returns_none_when_no_eval_event():
    """没有 eval 事件 → 返回 None（调用方据此不写 metrics）。

    这个区别很重要：返回 ``{}`` 会被当作「评估成功但指标全 0」，
    而 None 会让上层看到「没拿到指标」。
    """
    got, _c = _read_metrics([{"type": "end", "seq": 0, "exit_reason": "no_end_event"}])
    assert got is None


def test_read_metrics_returns_none_on_empty():
    assert _read_metrics([])[0] is None


def test_read_metrics_uses_eval_namespace():
    """必须带 ``kind="eval"`` —— 否则会查训练命名空间。

    job_id 全局唯一，所以查错命名空间**不会 404**，只会拿到另一个作业的信息：
    一种非常安静的串台。
    """
    _got, c = _read_metrics([])
    assert c.kwargs["kind"] == "eval"


def test_read_metrics_later_eval_event_wins():
    """多条 eval 事件时后者覆盖前者（增量评估场景）。"""
    got, _c = _read_metrics([
        {"type": "eval", "seq": 0, "main_value": 0.1, "metrics": {"box_mAP50": 0.1}},
        {"type": "eval", "seq": 1, "main_value": 0.9, "metrics": {"box_mAP50": 0.9}},
    ])
    assert got["main_value"] == 0.9
    assert got["box_mAP50"] == 0.9


def test_read_metrics_skips_none_values():
    """值为 None 的键不该写入（契约里 None 表示"没这项"）。"""
    got, _c = _read_metrics([
        {"type": "eval", "seq": 0, "main_indicator": "hmean", "main_value": None,
         "metrics": {"box_mAP50": 0.5}},
    ])
    assert "main_value" not in got
    assert got["main_indicator"] == "hmean"


# ---------------------------------------------------------------------------
# 作业 spec 组装
# ---------------------------------------------------------------------------

def test_build_eval_spec_shape():
    spec = es.build_eval_spec(
        config_path="configs/yolo/yolo11-seg.yml",
        weights_path="/workspace/model/best.pth",
        data_dir="/workspace/data",
        val_list="/workspace/data/val.txt",
        params={"Global.conf": 0.001},
        resources={"gpu": 1, "gpu_memory_gb": 6},
    )
    assert spec["kind"] == "eval"
    assert spec["config_path"] == "configs/yolo/yolo11-seg.yml"
    assert spec["weights_path"] == "/workspace/model/best.pth"
    assert spec["dataset"] == {"data_dir": "/workspace/data",
                               "val_list": "/workspace/data/val.txt"}
    assert spec["params"] == {"Global.conf": 0.001}
    assert spec["resources"] == {"gpu": 1, "gpu_memory_gb": 6}


def test_build_eval_spec_omits_train_list():
    """不给 train_list：服务端会把 val_list 同时注入 Train/Eval 两个 dataset。

    这里多给一份 train_list 反而要求调用方导出第二份清单，而评估导出是
    ``for_eval=True``（全量进 val），本来就没有 train.txt。
    """
    spec = es.build_eval_spec("c.yml", "/w/model/b.pth", "/w/data", "/w/data/val.txt")
    assert "train_list" not in spec["dataset"]
    assert spec["dataset"].get("train_list") is None


def test_build_eval_spec_omits_resources_when_absent():
    spec = es.build_eval_spec("c.yml", "/w/m/b.pth", "/w/data", "/w/data/val.txt")
    assert "resources" not in spec


def test_build_eval_spec_uses_posix_paths():
    """路径不能带反斜杠——本项目在 Windows 上跑而容器是 Linux。

    ``/workspace\\data` 在宿主上看着完全正常，传进容器就找不到文件了。
    """
    from app.plugin.module_train import tk_job_container as tkjc

    spec = es.build_eval_spec(
        "c.yml",
        tkjc.container_path("model", "best_accuracy.pth"),
        tkjc.container_path("data"),
        tkjc.container_path("data", "val.txt"),
    )
    blob = f"{spec['weights_path']} {spec['dataset']['data_dir']} {spec['dataset']['val_list']}"
    assert "\\" not in blob, f"路径里有反斜杠: {blob}"


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
