"""验证 PaddleX 训练入口已移除。"""
import inspect

from app.plugin.module_train.model import TrainFramework
from app.plugin.module_train.scheduler import _build_cmd


def test_build_cmd_has_no_paddlex_branch():
    """_build_cmd 不再构造 paddlex 命令。"""
    src = inspect.getsource(_build_cmd)
    assert "paddlex" not in src.lower()


def test_paddlex_framework_removed():
    """枚举值已删除（PaddleX 框架完全下线）。"""
    assert not hasattr(TrainFramework, "PADDLEX")
