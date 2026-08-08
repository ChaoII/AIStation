"""验证 PaddleX PP-OCRv6 训练入口已恢复并支持 det/rec tiny/small/medium。"""
import asyncio
import inspect

from app.plugin.module_train.model import TrainFramework
from app.plugin.module_train.scheduler import (
    _build_cmd,
    _build_paddlex_ocr_cmd,
    _PADDLEX_WEIGHTS,
)


def test_paddlex_framework_present():
    """枚举值已恢复（PaddleX 框架重新上线）。"""
    assert TrainFramework.PADDLEX == "paddlex"


def test_paddlex_weights_cover_all_sizes():
    """det/rec 均覆盖 tiny/small/medium 三个规格。"""
    assert set(_PADDLEX_WEIGHTS["det"].keys()) == {"tiny", "small", "medium"}
    assert set(_PADDLEX_WEIGHTS["rec"].keys()) == {"tiny", "small", "medium"}


def test_build_paddlex_det_cmd():
    """det 训练命令：config 路径 + 数据目录 + 预训练参数。"""
    hp = {"mode": "det", "model_size": "small", "epochs": 100, "batch": 8,
          "lr": 0.0005, "device": "0", "pretrained": True}
    cmd = _build_paddlex_ocr_cmd(hp, "/data", "/output", mode="det")
    joined = " ".join(cmd)
    assert "PP-OCRv6_small_det.yml" in joined
    assert "configs/det/PP-OCRv6/" in joined
    assert "/data/det/dataset" in joined
    assert "Global.pretrained_model=/pretrained/det.pdparams" in joined
    assert "Global.epoch_num=100" in joined


def test_build_paddlex_rec_cmd():
    """rec 训练命令：config 路径 + 数据目录 + 官方词表（不覆盖 character_dict_path）。"""
    hp = {"mode": "rec", "model_size": "medium", "epochs": 50, "batch": 64,
          "lr": 0.0005, "device": "0", "pretrained": False}
    cmd = _build_paddlex_ocr_cmd(hp, "/data", "/output", mode="rec")
    joined = " ".join(cmd)
    assert "PP-OCRv6_medium_rec.yml" in joined
    assert "configs/rec/PP-OCRv6/" in joined
    assert "/data/rec/dataset" in joined
    assert "Global.pretrained_model=" not in joined


class _FakeTask:
    framework = TrainFramework.PADDLEX
    hyperparams = {"mode": "det", "model_size": "tiny", "epochs": 100,
                   "batch": 8, "lr": 0.0005, "device": "0"}
    annotation_task_id = None


def test_build_cmd_paddlex_branch():
    """_build_cmd 对 PADDLEX 框架走 det 分支。"""
    cmd = asyncio.run(_build_cmd(_FakeTask(), "/data", "/output"))
    joined = " ".join(cmd)
    assert "tools/train.py" in joined
    assert "PP-OCRv6_tiny_det.yml" in joined
    assert "paddlex" in joined.lower() or "PaddleOCR" in joined


def test_ultralytics_lr_not_dropped():
    """前端发 lr（旧）或 lr0（新）都应进训练命令（B2 回归）。"""
    from app.plugin.module_train.scheduler import _build_ultralytics_cmd
    cmd_new = _build_ultralytics_cmd({"lr0": 0.001}, "/data", "/out")
    assert "lr0=0.001" in " ".join(cmd_new)
    cmd_old = _build_ultralytics_cmd({"lr": 0.001}, "/data", "/out")
    assert "lr0=0.001" in " ".join(cmd_old)
    cmd_missing = _build_ultralytics_cmd({}, "/data", "/out")
    assert "lr0" not in " ".join(cmd_missing)
