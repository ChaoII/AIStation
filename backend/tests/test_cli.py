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
