"""预测命令与 GPU 处理测试。"""
from app.plugin.module_train.predict_executor import build_predict_cmd, predict_gpu_id


def test_predict_gpu_id():
    assert predict_gpu_id("cpu") is None
    assert predict_gpu_id("") is None
    assert predict_gpu_id(None) is None
    assert predict_gpu_id("0") == "0"


def test_paddlex_predict_single_dash_o():
    cmd = build_predict_cmd("paddlex", "best_accuracy.pdparams",
                            {"mode": "det", "model_size": "small", "device": "cpu"})
    assert cmd[0] == "bash" and cmd[1] == "-c"
    inner = cmd[2]
    assert inner.count(" -o ") == 1            # 只有一个 -o
    assert "Global.infer_img=/data" in inner
    assert "Global.pretrained_model=/model/best_accuracy.pdparams" in inner
    assert "Global.save_res_path=/output/results.txt" in inner
    assert "Global.output_dir=/output" in inner
    assert "PP-OCRv6_small_det.yml" in inner
    assert "use_gpu=false" in inner            # device=cpu 时不启用 GPU

    cmd_gpu = build_predict_cmd("paddlex", "best_accuracy.pdparams",
                                {"mode": "det", "model_size": "small", "device": "0"})
    assert "use_gpu=true" in cmd_gpu[2]        # 指定 GPU id 时启用 GPU


def test_ultralytics_predict_has_device():
    cmd = build_predict_cmd("ultralytics", "best.pt", {"device": "cpu", "imgsz": 640})
    assert "device=cpu" in cmd
