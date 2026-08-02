"""版本号与模型引用语义测试。

- `_parse_version`：纯数字版本号解析（Task 3 已实现，此处回归锁定）。
- `_backtrack_export_path`：storage_path 为导出产物(/export/)时回溯原始训练产物的纯函数。
"""


def test_parse_version_removes_all_non_digits():
    from app.plugin.module_train.service import TrainService
    assert TrainService._parse_version("vv1") == 1
    assert TrainService._parse_version("v1") == 1
    assert TrainService._parse_version("v12") == 12
    assert TrainService._parse_version("") == 1
    assert TrainService._parse_version(None) == 1


def test_backtrack_export_path_backtracks_export_product():
    """导出产物路径 + 存在训练任务 -> 回溯到原始 best.pt。"""
    from app.plugin.module_train.service import _backtrack_export_path
    assert _backtrack_export_path("train/models/model_5/export/best.onnx", 7) == "train/models/task_7/best.pt"


def test_backtrack_export_path_keeps_path_without_export():
    """非导出产物路径保持原样。"""
    from app.plugin.module_train.service import _backtrack_export_path
    assert _backtrack_export_path("train/models/task_3/best.pt", 9) == "train/models/task_3/best.pt"


def test_backtrack_export_path_keeps_path_when_no_task():
    """导出产物路径但无对应训练任务 -> 保持原路径（避免误回溯）。"""
    from app.plugin.module_train.service import _backtrack_export_path
    assert _backtrack_export_path("train/models/model_5/export/best.onnx", None) == "train/models/model_5/export/best.onnx"
