"""CLI 参数解析测试。"""

from pytorch_ocr.cli import build_parser


def test_build_parser_has_subcommands():
    parser = build_parser()
    sub = parser._subparsers
    assert sub is not None
    # 校验子命令名（argparse 版本间 `choices` 是稳定的公开属性）
    actions = list(sub._group_actions[0].choices.keys())
    assert "train-det" in actions
    assert "eval-det" in actions


def test_build_parser_has_rec_subcommands():
    parser = build_parser()
    sub = parser._subparsers
    actions = list(sub._group_actions[0].choices.keys())
    assert "train-rec" in actions
    assert "eval-rec" in actions


def test_build_parser_has_predict():
    parser = build_parser()
    sub = parser._subparsers
    actions = list(sub._group_actions[0].choices.keys())
    assert "predict" in actions


def test_predict_parser_has_required_args():
    from pytorch_ocr.cli import build_parser
    parser = build_parser()
    args = parser.parse_args([
        "predict",
        "--image", "/input/img.jpg",
        "--det-model", "/model/det.pt",
        "--rec-model", "/model/rec.pt",
    ])
    assert args.command == "predict"
    assert args.image == "/input/img.jpg"
    assert args.det_model == "/model/det.pt"
    assert args.rec_model == "/model/rec.pt"
    assert args.output == "/output/result.json"
    assert args.device == "0"


def test_normalize_device():
    from pytorch_ocr.cli import _normalize_device
    assert _normalize_device("0") == "cuda:0"
    assert _normalize_device("cuda:0") == "cuda:0"
    assert _normalize_device("cpu") == "cpu"
    assert _normalize_device("") == "cuda:0"


def test_build_config_rec_derives_backbone_out_channels():
    """rec 配置的 backbone_out_channels 按 model_size 推导（不再硬编码 160）。"""
    from argparse import Namespace

    from pytorch_ocr.cli import _build_config
    from pytorch_ocr.modeling.backbones.pplcnetv4 import rec_backbone_out_channels

    for size in ("tiny", "small", "medium"):
        cfg = _build_config(Namespace(model_size=size, config=""), rec=True)
        assert cfg["backbone_out_channels"] == rec_backbone_out_channels(size)
