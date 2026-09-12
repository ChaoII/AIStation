"""YOLO Pose YAML 额外字段测试。"""
from app.plugin.module_train.exporter import pose_extra_yaml


def test_pose_extra_yaml_from_annotations():
    anns = {1: [{"type": "Keypoint", "keypoints": [{"x": 0.1, "y": 0.1, "visibility": "Visible"}] * 4}]}
    extra = pose_extra_yaml(anns)
    assert extra["kpt_shape"] == "[4, 3]"
    assert extra["flip_idx"] == "[0, 1, 2, 3]"


def test_pose_extra_yaml_empty_when_no_keypoints():
    assert pose_extra_yaml({1: [{"type": "AxisAlignedBox"}]}) == {}
