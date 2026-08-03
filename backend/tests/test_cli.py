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


def test_normalize_device():
    from pytorch_ocr.cli import _normalize_device
    assert _normalize_device("0") == "cuda:0"
    assert _normalize_device("cuda:0") == "cuda:0"
    assert _normalize_device("cpu") == "cpu"
    assert _normalize_device("") == "cuda:0"
