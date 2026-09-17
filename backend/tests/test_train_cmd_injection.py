"""训练基础模型文件名注入防护测试（审计 #14）。

``base_model_name`` 来自 ``storage_path`` 的 basename，会经 ``bash -c`` 拼入
PaddleX 训练命令；含 shell 元字符时可命令注入。要求白名单校验后拒绝。
"""
import pytest

from app.plugin.module_train import scheduler as sch

_MALICIOUS = [
    "evil;rm -rf /",
    "x$(whoami).pdparams",
    "a`id`.pt",
    "name with space.pt",
    "a|cat /etc/passwd",
    "a&b.pt",
    "a\nb.pt",
    "a>out.pt",
    "-oops.pt",
    "..",
    ".",
]


@pytest.mark.parametrize("name", _MALICIOUS)
def test_paddlex_cmd_rejects_malicious_base_model_name(name):
    with pytest.raises(ValueError):
        sch._build_paddlex_ocr_cmd(
            {"mode": "det", "model_size": "small", "pretrained": False},
            "/data",
            "/output",
            mode="det",
            base_model_name=name,
        )


@pytest.mark.parametrize("name", _MALICIOUS)
def test_ultralytics_cmd_rejects_malicious_base_model_name(name):
    with pytest.raises(ValueError):
        sch._build_ultralytics_cmd(
            {"model": "yolo11n.pt", "epochs": 10},
            "/data",
            "/output",
            "detection",
            base_model_name=name,
        )


def test_safe_base_model_names_still_work():
    cmd = sch._build_paddlex_ocr_cmd(
        {"mode": "det", "model_size": "small", "pretrained": False},
        "/data",
        "/output",
        mode="det",
        base_model_name="best_accuracy.pdparams",
    )
    assert "Global.pretrained_model=/pretrained/best_accuracy.pdparams" in " ".join(cmd)

    yolo = sch._build_ultralytics_cmd(
        {"model": "yolo11n.pt"}, "/data", "/output", "detection",
        base_model_name="best-v2.pt",
    )
    assert "model=/base/best-v2.pt" in " ".join(yolo)


def test_safe_name_helper():
    assert sch.safe_base_model_name("best.pt") == "best.pt"
    assert sch.safe_base_model_name("模型.pdparams") == "模型.pdparams"
    with pytest.raises(ValueError):
        sch.safe_base_model_name("../x")
