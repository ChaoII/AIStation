"""指标回流测试：训练最优指标写回模型版本。

- export_model 创建的版本行必须携带训练最优指标（best_metrics）
- _compute_best 保证 best_metrics 非 None（map50 最优；无 map50 时兜底）
"""

import inspect

from app.plugin.module_train.exporter import export_model
from app.plugin.module_train.scheduler import TrainExecutor, _compute_best


def test_export_model_passes_best_metrics():
    """export_model 创建 TrainModel 时写入 metrics（优先用传入的 best_metrics，兜底 task.best_metrics）。"""
    src = inspect.getsource(export_model)
    assert "best_metrics" in src
    assert "task.best_metrics" in src


def test_execute_computes_best_before_export_and_passes_it():
    """_execute 须先计算 best_metrics，再传给 export_model。

    否则 export_model 读到的 task.best_metrics 仍是 DB 旧值（None）。
    """
    src = inspect.getsource(TrainExecutor._execute)
    assert src.index("best_metrics = _compute_best") < src.index("export_model(")
    assert "best_metrics=best_metrics" in src


def test_compute_best_picks_highest_map50():
    log = [
        {"epoch": 1, "precision": 0.5, "recall": 0.4, "map50": 0.3, "map5095": 0.1},
        {"epoch": 2, "precision": 0.7, "recall": 0.6, "map50": 0.6, "map5095": 0.3},
        {"epoch": 3, "precision": 0.6, "recall": 0.5, "map50": 0.4, "map5095": 0.2},
    ]
    best = _compute_best(log)
    assert best["map50"] == 0.6
    assert best["epoch"] == 2


def test_compute_best_returns_none_for_empty_log():
    assert _compute_best([]) is None
    assert _compute_best(None) is None


def test_compute_best_ignores_none_entries():
    log = [None, {"epoch": 1, "precision": 0.5, "recall": 0.4, "map50": 0.3, "map5095": 0.1}]
    assert _compute_best(log)["map50"] == 0.3


def test_compute_best_falls_back_to_last_when_all_rows_empty():
    """全行均无任何指标字段时（含空行），退回最后一轮且不返回 None。"""
    log = [{}, {"epoch": 5}]
    assert _compute_best(log) == {"epoch": 5}


def test_compute_best_ranks_by_metric_fields_when_no_map50():
    """无任何 map50 时，取含最多数值字段的一轮，而非盲目取最后一轮。"""
    log = [
        {"epoch": 1, "precision": 0.7, "recall": 0.6, "map5095": 0.3},
        {"epoch": 2},
    ]
    assert _compute_best(log) == log[0]
