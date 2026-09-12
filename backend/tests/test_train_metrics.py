"""最优指标策略测试。"""

from app.plugin.module_train.metrics import best_metric, primary_metric_key
from app.plugin.module_train.paddlex_executor import (
    PaddleXOCRExecutor,
    select_paddlex_best,
)


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


def test_best_metric_ignores_higher_best_true_summary():
    """best:True 汇总行即使主指标更高也必须被忽略（取真实 epoch）。"""
    log = [
        {"epoch": 1, "hmean": 0.50},
        {"epoch": 2, "hmean": 0.60},
        {"hmean": 0.99, "best": True},
    ]
    best = best_metric(log, "paddlex", "ocr", mode="det")
    assert best["epoch"] == 2
    assert best["hmean"] == 0.60


def test_paddlex_parse_epoch_captures_hmean():
    """PaddleX det 逐 epoch 行应解析出 hmean（不再只认 acc/loss）。"""
    row = PaddleXOCRExecutor._parse_epoch(
        "epoch: [3/100] loss: 1.234, hmean: 0.8123, precision: 0.8, recall: 0.9"
    )
    assert row["epoch"] == 3
    assert row["loss"] == 1.234
    assert row["hmean"] == 0.8123


def test_paddlex_select_best_falls_back_to_best_true_hmean():
    """det 逐 epoch 行无 hmean 时，退化取 best:True 汇总行，保证 best_metrics 含 hmean。"""
    log = [
        {"epoch": 1, "loss": 1.2},
        {"epoch": 2, "loss": 0.9},
        {"hmean": 0.83, "best": True},
    ]
    best = select_paddlex_best(log, "det")
    assert best["hmean"] == 0.83


def test_paddlex_select_best_uses_scored_epoch_when_available():
    """有逐 epoch 主指标时直接按最大 hmean 选，不必依赖汇总行。"""
    log = [
        {"epoch": 1, "hmean": 0.70},
        {"epoch": 2, "hmean": 0.75},
        {"hmean": 0.99, "best": True},
    ]
    best = select_paddlex_best(log, "det")
    assert best["epoch"] == 2
    assert best["hmean"] == 0.75
