"""最优指标策略测试。

策略已随 Ultralytics / PaddleX 退场而改写：主指标不再按框架查表
（``_PRIMARY[("ultralytics","classification")] = "top1"`` 那种），而是按
**候选键依次探测**——TorchKiln 的 ``main_indicator`` 由各任务配置自行声明
（``mAP50-95`` / ``hmean`` / ``acc`` …），键名不固定，表格反而会漏。
"""

from app.plugin.module_train.metrics import best_metric, primary_metric_key


def test_primary_metric_key_is_stable_default():
    """返回值只是首选键；签名保留 framework/task_type 以免调用点为退场改一轮。"""
    assert primary_metric_key("torchkiln", "detection") == "mAP50-95"
    # 传什么都不该崩——它现在不按框架分流
    assert primary_metric_key("ultralytics", "classification") == "mAP50-95"
    assert primary_metric_key("", "") == "mAP50-95"


def test_best_metric_picks_max_map50():
    log = [
        {"epoch": 1, "map50": 0.5},
        {"epoch": 2, "map50": 0.7},
        {"epoch": -1, "map50": 0.6},  # summary row must be ignored
    ]
    assert best_metric(log, "torchkiln", "detection")["epoch"] == 2


def test_best_metric_prefers_map5095_over_map50():
    """有 mAP50-95 时按它选——它才是检测任务的主指标，map50 只是次优近似。"""
    log = [
        {"epoch": 1, "mAP50": 0.95, "mAP50-95": 0.40},
        {"epoch": 2, "mAP50": 0.60, "mAP50-95": 0.55},
    ]
    best = best_metric(log, "torchkiln", "segment")
    assert best["epoch"] == 2, "mAP50 最高的那轮不是最优轮，必须以 mAP50-95 为准"


def test_best_metric_uses_hmean_for_ocr():
    """OCR 任务的主指标是 hmean，键不在候选表里的旧写法下会静默退到最后一轮。"""
    log = [{"epoch": 1, "hmean": 0.80}, {"epoch": 2, "hmean": 0.83}]
    assert best_metric(log, "torchkiln", "ocr")["epoch"] == 2


def test_best_metric_uses_acc_for_rec():
    log = [{"epoch": 1, "acc": 0.8}, {"epoch": 2, "acc": 0.9}]
    assert best_metric(log, "torchkiln", "ocr", mode="rec")["epoch"] == 2


def test_best_metric_fallback_and_empty():
    log = [{"epoch": 1, "loss": 1.2}]
    assert best_metric(log, "torchkiln", "detection") == log[0]
    assert best_metric([], "torchkiln", "detection") is None


def test_best_metric_ignores_higher_best_true_summary():
    """best:True 汇总行即使主指标更高也必须被忽略（取真实 epoch）。"""
    log = [
        {"epoch": 1, "hmean": 0.50},
        {"epoch": 2, "hmean": 0.60},
        {"hmean": 0.99, "best": True},
    ]
    best = best_metric(log, "torchkiln", "ocr")
    assert best["epoch"] == 2
    assert best["hmean"] == 0.60


def test_best_metric_ignores_non_dict_rows():
    log = [None, "not-a-dict", {"epoch": 1, "mAP50": 0.4}, 123]
    assert best_metric(log, "torchkiln", "detection")["epoch"] == 1


def test_best_metric_zero_value_is_not_treated_as_missing():
    """0 是合法指标值（第一轮常为 0），不能被 ``if m.get(key)`` 当成缺失而跳过。"""
    log = [{"epoch": 1, "mAP50-95": 0.0}, {"epoch": 2, "mAP50-95": 0.3}]
    assert best_metric(log, "torchkiln", "detection")["epoch"] == 2
