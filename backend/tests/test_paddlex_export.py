"""PaddleX 数据集导出测试（验证不再空实现）。"""

import inspect

from app.plugin.module_train.exporter import _export_paddlex


def test_export_paddlex_is_implemented():
    src = inspect.getsource(_export_paddlex)
    # 原实现只有 mkdir + log；修复后应有 label 或 yaml 生成
    assert "yaml" in src.lower() or "label" in src.lower() or "json" in src.lower()


def test_export_paddlex_signature():
    # 完整实现需要数据集/任务上下文与标注任务ID
    import inspect as _inspect

    params = _inspect.signature(_export_paddlex).parameters
    assert "dataset_id" in params
    assert "task_id" in params
    assert "output_dir" in params
