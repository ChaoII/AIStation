"""framework_value 归一化测试。"""
from app.plugin.module_train.framework_utils import framework_value
from app.plugin.module_train.model import TrainFramework


def test_framework_value_from_enum():
    assert framework_value(TrainFramework.PADDLEX) == "paddlex"
    assert framework_value(TrainFramework.ULTRALYTICS) == "ultralytics"


def test_framework_value_from_plain_string():
    assert framework_value("paddlex") == "paddlex"
    assert framework_value("ULTRALYTICS") == "ultralytics"


def test_framework_value_from_repr_like_string():
    assert framework_value("TrainFramework.PADDLEX") == "paddlex"


def test_framework_value_none_is_empty():
    assert framework_value(None) == ""
