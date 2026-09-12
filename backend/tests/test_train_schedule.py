"""定时训练数据构造与 schedule 序列化测试。"""
import json
from types import SimpleNamespace

from app.plugin.module_train.model import TrainFramework
from app.plugin.module_train.schedule_model import TrainScheduleModel
from app.plugin.module_train.schedule_service import _schedule_to_dict
from app.plugin.module_train.scheduler import build_scheduled_task_data


def test_build_scheduled_task_data_has_required_attrs():
    s = SimpleNamespace(
        name="x", dataset_id=1, annotation_task_id=2,
        framework=TrainFramework.ULTRALYTICS, hyperparams={},
    )
    data = build_scheduled_task_data(s)
    for attr in ("name", "dataset_id", "annotation_task_id", "framework", "hyperparams", "base_model_id"):
        assert hasattr(data, attr), attr


def test_schedule_to_dict_is_json_serializable():
    s = TrainScheduleModel(name="n", dataset_id=1, framework="ultralytics",
                           hyperparams={}, cron_expr="0 2 * * 0")
    d = _schedule_to_dict(s)
    json.dumps(d)  # 不得抛异常
    assert "_sa_instance_state" not in d
    assert d["name"] == "n"
