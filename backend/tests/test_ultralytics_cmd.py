"""测试 ultralytics 训练命令白名单映射。"""

from app.plugin.module_train.scheduler import _ULTRALYTICS_HP, _build_ultralytics_cmd


def test_all_frontend_keys_mapped():
    """前端会发送的所有 key 都应出现在白名单（除 train_ratio）。"""
    hp = {"model": "yolo11n.pt", "epochs": 100, "batch": 16, "lr0": 0.01,
          "optimizer": "AdamW", "imgsz": 640, "workers": 4, "device": "0",
          "train_ratio": 0.8}
    assert set(hp.keys()) - {"train_ratio"} <= set(_ULTRALYTICS_HP.keys())


def test_build_cmd_includes_all_present_params():
    hp = {"model": "yolo11n.pt", "epochs": 50, "batch": 32, "lr0": 0.02,
          "optimizer": "SGD", "imgsz": 512, "workers": 8, "device": "1",
          "hsv_h": 0.1, "mosaic": 0.5}
    cmd = _build_ultralytics_cmd(hp, "/data", "/output", "detection")
    s = " ".join(cmd)
    assert "model=/models/yolo11n.pt" in s
    assert "epochs=50" in s
    assert "batch=32" in s
    assert "lr0=0.02" in s
    assert "optimizer=SGD" in s
    assert "imgsz=512" in s
    assert "workers=8" in s
    assert "device=1" in s
    assert "hsv_h=0.1" in s
    assert "mosaic=0.5" in s
    assert "data=/data/dataset.yaml" in s
    assert "project=/output" in s


def test_build_cmd_omits_absent_params():
    hp = {"model": "yolo11n.pt", "epochs": 100}
    cmd = _build_ultralytics_cmd(hp, "/data", "/output", "detection")
    s = " ".join(cmd)
    assert "epochs=100" in s
    assert "batch=" not in s
    assert "imgsz=" not in s
    assert "optimizer=" not in s


def test_build_cmd_obb_suffix():
    hp = {"model": "yolo11n.pt"}
    cmd = _build_ultralytics_cmd(hp, "/data", "/output", "rotated_detection")
    assert "model=/models/yolo11n-obb.pt" in " ".join(cmd)


def test_build_cmd_invalid_param_skipped():
    """校验失败的参数应被跳过（不中断训练）。"""
    hp = {"model": "yolo11n.pt", "epochs": 99999}  # >1000, invalid
    cmd = _build_ultralytics_cmd(hp, "/data", "/output", "detection")
    s = " ".join(cmd)
    assert "epochs=" not in s
    assert "model=/models/yolo11n.pt" in s


def test_build_cmd_classification_multi_label():
    hp = {"model": "yolo11n-cls.pt", "multi_label": True}
    cmd = _build_ultralytics_cmd(hp, "/data", "/output", "cls")
    assert "multi_label=True" in " ".join(cmd)
