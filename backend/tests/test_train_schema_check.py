"""训练模块补列清单与 ORM 对齐测试。"""
from app.plugin.module_train import schema_check
from app.plugin.module_train.model import TrainEval, TrainModel, TrainTask


def test_backfill_covers_orm_columns():
    # 清单声明的列必须是 ORM 真实字段，且覆盖所有预期缺失列
    for _table, columns in schema_check.MISSING_TRAIN_COLUMNS.items():
        assert isinstance(columns, list) and columns
        for name, _type in columns:
            assert name


def test_expected_columns_listed():
    task_cols = dict(schema_check.MISSING_TRAIN_COLUMNS["train_tasks"])
    assert "annotation_task_id" in task_cols
    assert "cleanup_delay_minutes" in task_cols

    model_cols = dict(schema_check.MISSING_TRAIN_COLUMNS["train_models"])
    assert "repo_id" in model_cols
    assert "export_format" in model_cols

    eval_cols = dict(schema_check.MISSING_TRAIN_COLUMNS["train_evals"])
    assert "progress" in eval_cols
    assert "error_log" in eval_cols


def test_models_have_declared_columns():
    for table, columns in schema_check.MISSING_TRAIN_COLUMNS.items():
        cls = {
            "train_tasks": TrainTask,
            "train_models": TrainModel,
            "train_evals": TrainEval,
        }[table]
        for name, _type in columns:
            assert hasattr(cls, name), f"{cls.__name__} 缺少字段 {name}"
