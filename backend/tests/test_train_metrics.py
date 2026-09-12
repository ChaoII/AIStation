"""最优指标策略测试。"""

from app.plugin.module_train.metrics import best_metric, primary_metric_key


def test_primary_metric_key():
    assert primary_metric_key("ultralytics", "classification") == "top1"
    assert primary_metric_key("ultralytics", "detection") == "map50"
    assert primary_metric_key("paddlex", "ocr", mode="rec") == "acc"
    assert primary_metric_key("paddlex", "ocr", mode="det") == "hmean"


def test_best_metric_picks_max_primary():
    log = [
        {"epoch": 1, "map50": 0.5},
        {"epoch": 2, "map50": 0.7},
        {"epoch": -1, "map50": 0.6},  # summary row must be ignored
    ]
    assert best_metric(log, "ultralytics", "detection")["epoch"] == 2


def test_best_metric_paddlex_rec_acc():
    log = [{"epoch": 1, "acc": 0.8}, {"epoch": 2, "acc": 0.9}]
    assert best_metric(log, "paddlex", "ocr", mode="rec")["epoch"] == 2


def test_best_metric_fallback_and_empty():
    log = [{"epoch": 1, "loss": 1.2}]
    assert best_metric(log, "ultralytics", "detection") == log[0]
    assert best_metric([], "ultralytics", "detection") is None
