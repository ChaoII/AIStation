"""测试多标签分类数据集导出（YOLO CLS multi-label 格式）。"""
import inspect

from app.plugin.module_train.exporter import _export_core, _export_yolo_cls


def test_export_yolo_cls_accepts_multi_label_param():
    """_export_yolo_cls 应支持 multi_label 参数（规范参数检查）。"""
    sig = inspect.signature(_export_yolo_cls)
    assert "multi_label" in sig.parameters


def test_export_core_passes_classification_mode():
    """_export_core 应读取 annotation_task.classification_mode 并传给 _export_yolo_cls。"""
    src = inspect.getsource(_export_core)
    assert "classification_mode" in src
