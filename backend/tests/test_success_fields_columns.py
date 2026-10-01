"""``success_fields`` 的键必须是目标模型**真实存在**的列。

为什么需要这条守卫
------------------
``settle_by_status`` 把 ``success_fields`` 原样交给 ``TaskExecutor._mark_status``，
后者最终走 SQLAlchemy 的 ``setattr``。键名不存在时**不报错在提交时，而是在
``_mark_status`` 内部抛** ``Unconsumed column names: ...``。

而收尾抛异常的后果特别糟：此时容器已经停了、结果图已经传上去了，
**任务却被判成失败**。用户看到的是「预测失败」，日志里是一条与真实原因
毫无关系的列名错误。

实跑就踩过一次：给 ``TrainPredict`` 传了 ``metrics`` / ``metrics_log`` /
``last_metrics``——那是训练与评估才有的列，预测表没有。
"""
import inspect

import pytest

from app.plugin.module_train import job_runner
from app.plugin.module_train.model import TrainEval, TrainPredict, TrainTask


def _columns(model):
    return {c.name for c in model.__table__.columns}


#: 三条链路的「成功时要落什么字段」。
#: 与 eval_scheduler / predict_executor 里的 success_fields 一一对应。
SUCCESS_FIELDS = {
    "train": (TrainTask, {
        "metrics_log": "metrics_log",
        "best_metrics": "best_metrics",
        "last_metrics": "last_metrics",
        "model_repo_id": "model_repo_id",
        "error_log": "error_log",
    }),
    "eval": (TrainEval, {
        "metrics": "metrics",
        "metrics_log": "metrics_log",
        "best_metrics": "best_metrics",
        "last_metrics": "last_metrics",
    }),
    "predict": (TrainPredict, {
        "result_images": "result_images",
        "result_zip_path": "result_zip_path",
    }),
}


@pytest.mark.parametrize("kind", sorted(SUCCESS_FIELDS))
def test_success_field_keys_are_real_columns(kind):
    model, fields = SUCCESS_FIELDS[kind]
    cols = _columns(model)
    missing = sorted(set(fields) - cols)
    assert not missing, (
        f"{model.__name__} 没有这些列：{missing}"
        f"——写进 success_fields 会在收尾阶段抛 "
        f"Unconsumed column names，导致成功任务被判失败")


def test_predict_has_no_metrics_columns():
    """断言这个事实本身，避免有人「顺手」给预测加一个 metrics 字段。

    预测没有 ground truth，指标只有计数与耗时；真要落库应该新建一列，
    而不是复用训练/评估那套精度指标语义。
    """
    cols = _columns(TrainPredict)
    for gone in ("metrics", "metrics_log", "best_metrics", "last_metrics"):
        assert gone not in cols, (
            f"TrainPredict 竟有 {gone} 列——预测的指标语义与训练/评估不同，"
            f"真要落库应新建列而不是复用")


def test_predict_executor_does_not_pass_metrics_columns():
    """源码级守卫：``_execute`` 里不得出现给预测传 metrics 类字段。"""
    import pathlib

    from app.plugin.module_train import predict_executor

    src = pathlib.Path(predict_executor.__file__).read_text(encoding="utf-8")
    # 取 settle_by_status 调用片段（源码级断言比运行级更早暴露意图偏离）
    idx = src.index("settle_by_status(")
    seg = src[idx:idx + 600]
    for banned in ('"metrics":', "'metrics':", '"metrics_log":', '"last_metrics":'):
        assert banned not in seg, (
            f"predict 的 success_fields 里不该有 {banned}——"
            f"TrainPredict 没有这些列，会让成功任务被判失败")


def test_mark_failed_signature_accepts_keyword_fields():
    """``mark_failed`` 走的是「异常信息」路径，不受列名影响——
    但也意味着它**不会**帮你发现 success_fields 写错列。所以才有上面几条。"""
    sig = inspect.signature(job_runner.mark_failed)
    assert "kind" in sig.parameters
    assert "exc" in sig.parameters
