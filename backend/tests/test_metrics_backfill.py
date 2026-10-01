"""指标回流测试：训练最优指标写回模型版本。

- export_model 创建的版本行必须携带训练最优指标（best_metrics）
- best_metric 统一最优指标策略（见 test_train_metrics.py）
"""

import asyncio
import inspect
from types import SimpleNamespace

from app.plugin.module_train import model_persist
from app.plugin.module_train.exporter import export_model
from app.plugin.module_train.metrics import best_metric
from app.plugin.module_train.scheduler import (
    _resolve_task_type,
)


def test_export_model_passes_best_metrics():
    """export_model 创建 TrainModel 时写入 metrics（优先用传入的 best_metrics，兜底 task.best_metrics）。"""
    src = inspect.getsource(export_model)
    assert "best_metrics" in src
    assert "task.best_metrics" in src


def test_best_metric_picks_highest_map50():
    log = [
        {"epoch": 1, "precision": 0.5, "recall": 0.4, "map50": 0.3, "map5095": 0.1},
        {"epoch": 2, "precision": 0.7, "recall": 0.6, "map50": 0.6, "map5095": 0.3},
        {"epoch": 3, "precision": 0.6, "recall": 0.5, "map50": 0.4, "map5095": 0.2},
    ]
    best = best_metric(log, "ultralytics", "detection")
    assert best["map50"] == 0.6
    assert best["epoch"] == 2


def test_best_metric_returns_none_for_empty_log():
    assert best_metric([], "ultralytics", "detection") is None
    assert best_metric(None, "ultralytics", "detection") is None


def test_best_metric_ignores_none_entries():
    log = [None, {"epoch": 1, "precision": 0.5, "recall": 0.4, "map50": 0.3, "map5095": 0.1}]
    assert best_metric(log, "ultralytics", "detection")["map50"] == 0.3


def test_best_metric_falls_back_to_last_when_all_rows_empty():
    """全行均无主指标字段时（含空行），退回最后一轮且不返回 None。"""
    log = [{}, {"epoch": 5}]
    assert best_metric(log, "ultralytics", "detection") == {"epoch": 5}


def test_best_metric_no_primary_falls_back_to_last_row():
    """无任何主指标时统一退最后一轮（不再按字段数量排序）。"""
    log = [
        {"epoch": 1, "precision": 0.7, "recall": 0.6, "map5095": 0.3},
        {"epoch": 2},
    ]
    assert best_metric(log, "ultralytics", "detection") == log[1]


def test_resolve_task_type_defaults_to_detection():
    """无标注任务时 task_type 回退 detection。"""
    task = SimpleNamespace(annotation_task_id=None)
    assert asyncio.run(_resolve_task_type(task)) == "detection"


def test_export_model_no_artifact_skips_db(tmp_path, monkeypatch):
    """无训练产物时不插入 TrainModel，避免仓库出现无权重的最新版本。"""
    calls = {"begin": 0, "add": []}

    class FakeSession:
        def add(self, obj):
            calls["add"].append(obj)

    class FakeBegin:
        async def __aenter__(self):
            calls["begin"] += 1
            return FakeSession()

        async def __aexit__(self, *exc):
            return False

    class FakeFactory:
        def begin(self):
            return FakeBegin()

        def __call__(self, *a, **k):
            return FakeBegin()

    monkeypatch.setattr(model_persist, "async_db_session", FakeFactory())

    result = asyncio.run(export_model(1, "paddlex", str(tmp_path)))
    assert result == {"repo_id": None, "storage_path": None}
    assert calls["begin"] == 0
    assert calls["add"] == []
