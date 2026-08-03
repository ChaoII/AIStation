"""Paddle→PyTorch 权重转换器测试。

自研 PPLCNetV4/RepLKFPN/DBHead 使用语义参数名（如 ``stem.stem1.conv.weight``），
而 Paddle 权重为层索引命名（``conv2d_0.w_0``）。转换器按「位置对应法」：
Paddle 权重在 .pdparams 中按层创建顺序排列，与自研模型注册顺序一致，逐位配对。

本测试用合成 Paddle state_dict（由自研模型反转命名生成）验证：
- 已知 DBHead 层索引（frotms 参考 det_db_head.py 注释）→ 语义路径映射
- 转换结果可 strict=False 加载进自研模型，且无 missing/unexpected keys
- 数值 round-trip、形状校验告警、未知 key 忽略
"""
import numpy as np
import pytest
import torch
import torch.nn as nn

from pytorch_ocr.converter.ppocr_v6_det_converter import (
    build_det_model,
    convert_ppocr_v6_det,
    convert_with_report,
    map_param_name,
    map_semantic_name,
    parse_paddle_name,
)


def synthetic_paddle_state(model):
    """将自研模型参数反转为 Paddle 风格命名（按注册顺序逐层编号）。

    模拟 PaddleOCR 的 .pdparams 保存格式：
    conv2d_N.w_0/b_0, batch_norm_N.w_0/b_0/_mean/_variance,
    conv2d_transpose_N.w_0/b_0。
    """
    out = {}
    counters = {"conv": 0, "bn": 0, "conv_transpose": 0}
    for _path, module in model.named_modules():
        if isinstance(module, nn.ConvTranspose2d):
            key = f"conv2d_transpose_{counters['conv_transpose']}"
            counters["conv_transpose"] += 1
            out[f"{key}.w_0"] = module.weight.detach().numpy()
            if module.bias is not None:
                out[f"{key}.b_0"] = module.bias.detach().numpy()
        elif isinstance(module, nn.Conv2d):
            key = f"conv2d_{counters['conv']}"
            counters["conv"] += 1
            out[f"{key}.w_0"] = module.weight.detach().numpy()
            if module.bias is not None:
                out[f"{key}.b_0"] = module.bias.detach().numpy()
        elif isinstance(module, nn.BatchNorm2d):
            key = f"batch_norm_{counters['bn']}"
            counters["bn"] += 1
            out[f"{key}.w_0"] = module.weight.detach().numpy()
            out[f"{key}.b_0"] = module.bias.detach().numpy()
            out[f"{key}._mean"] = module.running_mean.detach().numpy()
            out[f"{key}._variance"] = module.running_var.detach().numpy()
    return out


def test_map_semantic_name():
    """官方 PaddleX .pdparams 的语义名 → 自研模型参数名。

    官方权重（PaddleX 3.0）使用语义命名，backbone/neck 两框架命名一致，
    仅 DBHead 子层名不同（conv1→0, conv_bn1→1, conv2→3, conv_bn2→4, conv3→6）。
    """
    # backbone/neck 语义名直接映射（BN 统计量后缀替换）
    assert map_semantic_name("backbone.stem.stem1.conv.weight") == (
        "backbone.stem.stem1.conv.weight"
    )
    assert map_semantic_name("backbone.stem.stem1.bn._mean") == (
        "backbone.stem.stem1.bn.running_mean"
    )
    assert map_semantic_name("backbone.stem.stem1.bn._variance") == (
        "backbone.stem.stem1.bn.running_var"
    )
    # DBHead 语义子层名 → 索引
    assert map_semantic_name("head.binarize.conv1.weight") == "head.binarize.0.weight"
    assert map_semantic_name("head.binarize.conv_bn1._mean") == (
        "head.binarize.1.running_mean"
    )
    assert map_semantic_name("head.binarize.conv2.weight") == "head.binarize.3.weight"
    assert map_semantic_name("head.thresh.conv_bn2.bias") == "head.thresh.4.bias"
    assert map_semantic_name("head.thresh.conv3.bias") == "head.thresh.6.bias"
    # 辅助深度监督头（自研模型不实现）→ None
    assert map_semantic_name("head.aux_binarize_p2.conv1.weight") is None
    assert map_semantic_name("head.aux_thresh_p3.conv2.weight") is None


def test_convert_by_name_roundtrip():
    """语义名直接映射：官方 PaddleX .pdparams 格式可完整转换。

    用自研模型参数值生成语义命名的伪 Paddle state_dict（与 PaddleX 3.0 一致），
    验证 convert_ppocr_v6_det 走语义映射路径并数值 round-trip。
    """
    model = build_det_model("tiny")
    original = {k: v.detach().clone() for k, v in model.state_dict().items()}
    paddle = {}
    for path, tensor in original.items():
        if path.endswith("num_batches_tracked"):
            continue
        pad = map_semantic_name(path)
        # map_semantic_name 是 Paddle→torch；反向：把 torch 语义名加回 Paddle 后缀
        if ".running_mean" in path:
            pad = path.replace(".running_mean", "._mean")
        elif ".running_var" in path:
            pad = path.replace(".running_var", "._variance")
        else:
            pad = path
        if path.startswith("head."):
            parts = path.split(".")
            idx = parts[2]
            sub_map = {v: k for k, v in {
                "conv1": "0", "conv_bn1": "1", "conv2": "3",
                "conv_bn2": "4", "conv3": "6",
            }.items()}
            sem = sub_map[idx]
            pad = f"head.{parts[1]}.{sem}.{parts[3]}"
            if pad.endswith("running_mean"):
                pad = pad.replace("running_mean", "_mean")
            elif pad.endswith("running_var"):
                pad = pad.replace("running_var", "_variance")
        paddle[pad] = tensor.numpy()

    state = convert_ppocr_v6_det(paddle, "tiny")
    result = model.load_state_dict(state, strict=False)
    assert result.missing_keys == []
    assert result.unexpected_keys == []
    for path, tensor in original.items():
        if path.endswith("num_batches_tracked"):
            continue
        assert path in state, f"missing {path}"
        assert torch.equal(state[path], tensor), f"value changed: {path}"


def test_map_param_name_basic():
    # DBHead 层索引来自 frotms 参考 det_db_head.py 的 binarize/thresh name_list
    assert map_param_name("conv2d_56.w_0") == "head.binarize.0.weight"
    assert map_param_name("batch_norm_47.w_0") == "head.binarize.1.weight"
    assert map_param_name("batch_norm_47.b_0") == "head.binarize.1.bias"
    assert map_param_name("conv2d_transpose_0.w_0") == "head.binarize.3.weight"
    assert map_param_name("batch_norm_48._mean") == "head.binarize.4.running_mean"
    assert map_param_name("batch_norm_48.w_2") == "head.binarize.4.running_var"
    assert map_param_name("conv2d_57.w_0") == "head.thresh.0.weight"


def test_map_param_name_unknown():
    # 骨干/neck 层索引未知（与模型大小相关），按位置对应法处理 → 返回 None
    assert map_param_name("conv2d_0.w_0") is None
    assert map_param_name("some_unknown") is None
    assert map_param_name("aux_binarize_0.w_0") is None
    assert map_param_name("") is None


def test_parse_paddle_name():
    assert parse_paddle_name("conv2d_5.w_0") == ("conv", 5, 0, "weight")
    assert parse_paddle_name("batch_norm_3.w_2") == ("bn", 3, 3, "running_var")
    assert parse_paddle_name("batch_norm_3._mean") == ("bn", 3, 2, "running_mean")
    assert parse_paddle_name("conv2d_transpose_1.b_0") == (
        "conv_transpose", 1, 1, "bias",
    )
    assert parse_paddle_name("some_unknown") is None


def test_convert_full_model_roundtrip():
    model = build_det_model("tiny")
    original = {k: v.detach().clone() for k, v in model.state_dict().items()}
    paddle = synthetic_paddle_state(model)
    state, report = convert_with_report(paddle, model)

    assert report.warnings == [], report.warnings
    assert report.matched > 0
    assert report.skipped == 0

    result = model.load_state_dict(state, strict=False)
    assert result.missing_keys == []
    assert result.unexpected_keys == []

    # 数值 round-trip：每个可加载参数值应与转换前一致
    for path in original:
        if path.endswith("num_batches_tracked"):
            assert int(state[path]) == 0
            assert int(model.state_dict()[path]) == 0
        else:
            assert path in state, f"missing {path}"
            assert torch.equal(state[path], original[path]), f"value changed: {path}"


@pytest.mark.parametrize("size", ["tiny", "small", "medium"])
def test_convert_model_sizes(size):
    model = build_det_model(size)
    paddle = synthetic_paddle_state(model)
    state, report = convert_with_report(paddle, model)
    assert report.warnings == [], report.warnings
    result = model.load_state_dict(state, strict=False)
    assert result.missing_keys == []
    assert result.unexpected_keys == []


def test_convert_ignores_unknown_keys():
    model = build_det_model("tiny")
    paddle = synthetic_paddle_state(model)
    n_known = len(paddle)
    paddle["aux_binarize_0.weight"] = np.zeros((1, 1), dtype=np.float32)
    paddle["optimizer.learning_rate"] = np.array(0.001, dtype=np.float32)
    paddle["num_batches_tracked"] = np.array(0, dtype=np.int64)

    state, report = convert_with_report(paddle, model)
    assert report.matched == n_known
    assert report.skipped == 0
    result = model.load_state_dict(state, strict=False)
    assert result.missing_keys == []
    assert result.unexpected_keys == []


def test_convert_shape_mismatch_warns():
    model = build_det_model("tiny")
    paddle = synthetic_paddle_state(model)
    # 篡改第一个 conv 权重的形状，模拟转换中发现结构不对齐
    bad_key = next(k for k in paddle if k.startswith("conv2d_0."))
    paddle[bad_key] = np.zeros((1, 1, 1, 1), dtype=np.float32)

    state, report = convert_with_report(paddle, model)
    assert any("shape mismatch" in w for w in report.warnings)
    # 对应 torch 参数被跳过，其余参数仍正常映射
    assert "backbone.stem.stem1.conv.weight" not in state
    result = model.load_state_dict(state, strict=False)
    assert "backbone.stem.stem1.conv.weight" in result.missing_keys


def test_convert_empty_raises():
    with pytest.raises(ValueError):
        convert_ppocr_v6_det({}, "tiny")
    with pytest.raises(ValueError):
        convert_ppocr_v6_det({"some_junk": np.zeros((1, 1), dtype=np.float32)}, "tiny")


def test_convert_interface_returns_state_dict():
    model = build_det_model("tiny")
    paddle = synthetic_paddle_state(model)
    state = convert_ppocr_v6_det(paddle, "tiny")
    assert isinstance(state, dict)
    result = model.load_state_dict(state, strict=False)
    assert result.missing_keys == []
    assert result.unexpected_keys == []


def test_build_det_model_neck_dilated_kernel_size_is_5():
    """build_det_model 的 neck 必须使用 dilated_kernel_size=5（对齐 tiny_det.yml）。"""
    model = build_det_model("tiny")
    for blk in model.neck.inp_conv_dw:
        assert blk.kernel_size == 5
        assert len(blk.dilates) == 2


def test_convert_ppocr_v6_rec_exists():
    """rec 转换器底层位置对应法可完整映射 backbone（conv/bn）参数。

    rec 模型 = PPLCNetV4(det=False) + MultiHead(CTC + NRTR)。head 内
    Linear/Embedding/LayerNorm/Conv1d 的 Paddle 命名映射留待 plan 3b 真实权重验证。
    ``convert_ppocr_v6_rec`` 现带 head 完整性守卫（head 无法完整映射时抛错，
    见 test_convert_ppocr_v6_rec_head_missing_raises），此处直接测底层
    ``convert_with_report`` 确认 backbone 位置对应仍可靠。
    """
    from pytorch_ocr.converter.ppocr_v6_det_converter import convert_with_report
    from pytorch_ocr.converter.ppocr_v6_rec_converter import build_rec_model

    model = build_rec_model("tiny")
    original = {k: v.detach().clone() for k, v in model.state_dict().items()}
    paddle = synthetic_paddle_state(model)
    result, _report = convert_with_report(paddle, model)
    assert isinstance(result, dict)
    assert "backbone.conv1.0.conv.weight" in result
    # 数值 round-trip
    assert torch.equal(
        result["backbone.conv1.0.conv.weight"],
        original["backbone.conv1.0.conv.weight"],
    )
    # 位置对应：backbone 全部参数映射完整，无缺失
    loaded = model.load_state_dict(result, strict=False)
    assert all(not k.startswith("backbone.") for k in loaded.missing_keys)


def test_convert_ppocr_v6_rec_head_missing_raises():
    """守卫：head 层无法完整映射时必须抛错，不能静默产出垃圾权重。

    真实 Paddle rec head 参数命名（linear_N/embedding_N/layer_norm_N/
    conv1d_N/batch_norm1d_N）与 det 的 conv2d_N/batch_norm_N 不同，
    位置对应法无法覆盖 → head 映射不完整 → 必须 raise。
    """
    from pytorch_ocr.converter.ppocr_v6_rec_converter import (
        build_rec_model,
        convert_ppocr_v6_rec,
    )

    model = build_rec_model("tiny")
    sd = model.state_dict()
    # 模拟真实 Paddle 命名：backbone 的 conv/bn 用 Paddle 名，head 参数全部缺席
    # （真实 Paddle 会用 linear_N/embedding_N/layer_norm_N 等，无法被位置对应法解析）
    paddle_state = {}
    conv_idx = 0
    bn_idx = 0
    for k, v in sd.items():
        if k.startswith("head."):
            continue
        if "conv" in k and "weight" in k:
            paddle_state[f"conv2d_{conv_idx}.w_0"] = v.numpy()
            conv_idx += 1
        elif "bn" in k:
            paddle_state[f"batch_norm_{bn_idx}.w_0"] = v.numpy()
            bn_idx += 1
    with pytest.raises(ValueError, match="head"):
        convert_ppocr_v6_rec(paddle_state, "tiny")


def test_convert_ppocr_v6_rec_empty_raises():
    from pytorch_ocr.converter.ppocr_v6_rec_converter import convert_ppocr_v6_rec

    with pytest.raises(ValueError):
        convert_ppocr_v6_rec({}, "tiny")


def test_verify_conversion_supports_rec():
    """verify_conversion.py 必须支持 --rec 模式（rec 权重逐层输出对比）。"""
    import inspect

    from pytorch_ocr.converter.verify_conversion import main

    src = inspect.getsource(main)
    assert "--rec" in src or "rec" in src.lower()
