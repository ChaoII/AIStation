"""PP-OCRv6 det 权重转换：Paddle .pdparams → PyTorch state_dict。

Paddle 参数名形如 ``conv2d_56.w_0`` / ``batch_norm_47.b_0`` /
``conv2d_transpose_0.w_0``，层索引按声明顺序逐类全局编号（conv2d / batch_norm /
conv2d_transpose 各自独立计数）。自研 PPLCNetV4/RepLKFPN/DBHead 使用语义命名
（如 ``stem.stem1.conv.weight``），因此无法像 frotms 参考实现那样按同名映射。

本转换器采用 **位置对应法**：

1. 遍历 Paddle state_dict（.pdparams 中按层创建顺序保存），解析出可映射参数；
2. 按注册顺序遍历自研模型的可加载参数（跳过 ``num_batches_tracked``）；
3. 逐位配对，对每一对做「参数种类 + 形状」双重校验；
4. 生成 PyTorch state_dict（BN 的 running_mean/var 由 Paddle 的 ``w_1``/``w_2``
   或 ``_mean``/``_variance`` 提供，``num_batches_tracked`` 置 0）。

DBHead 尾部的层编号可从参考实现（frotms det_db_head.py 的
``binarize_name_list``/``thresh_name_list``）确定，见 ``map_param_name``，用于
容器内校验转换结果是否落位正确。
"""
import logging
import re
from dataclasses import dataclass, field

import numpy as np
import torch
import torch.nn as nn

from ..modeling.backbones.pplcnetv4 import PPLCNetV4
from ..modeling.heads.det_db_head import DBHead
from ..modeling.necks.rep_lk_fpn import RepLKFPN

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Paddle 参数名解析
# ---------------------------------------------------------------------------

# 层类型（Paddle 命名前缀）→ 内部层类型
_LAYER_KIND = {
    "conv2d": "conv",
    "batch_norm": "bn",
    "conv2d_transpose": "conv_transpose",
}

# 参数后缀 → (排序权重, 目标参数名)。排序权重保证单层内
# weight < bias < running_mean < running_var，与 PyTorch BN 注册顺序一致。
_PARAM_MAP = {
    "w_0": (0, "weight"),
    "b_0": (1, "bias"),
    "w_1": (2, "running_mean"),
    "_mean": (2, "running_mean"),
    "w_2": (3, "running_var"),
    "_variance": (3, "running_var"),
}

_PADDLE_NAME_RE = re.compile(
    r"^(conv2d|batch_norm|conv2d_transpose)_(\d+)\.(w_0|b_0|w_1|w_2|_mean|_variance)$"
)


def parse_paddle_name(paddle_name: str) -> tuple[str, int, int, str] | None:
    """解析 Paddle 参数名，返回 ``(layer_type, layer_index, kind_rank, kind)``。

    无法识别的名字（含 ``aux_*`` / optimizer 等）返回 ``None``。
    """
    m = _PADDLE_NAME_RE.match(paddle_name)
    if m is None:
        return None
    rank, kind = _PARAM_MAP[m.group(3)]
    return (_LAYER_KIND[m.group(1)], int(m.group(2)), rank, kind)


# ---------------------------------------------------------------------------
# DBHead 已知层索引（frotms 参考 det_db_head.py 的 binarize/thresh name_list）
# ---------------------------------------------------------------------------

_DB_HEAD_PATH = {
    ("conv", 56): "head.binarize.0",
    ("bn", 47): "head.binarize.1",
    ("conv_transpose", 0): "head.binarize.3",
    ("bn", 48): "head.binarize.4",
    ("conv_transpose", 1): "head.binarize.6",
    ("conv", 57): "head.thresh.0",
    ("bn", 49): "head.thresh.1",
    ("conv_transpose", 2): "head.thresh.3",
    ("bn", 50): "head.thresh.4",
    ("conv_transpose", 3): "head.thresh.6",
}


def map_param_name(paddle_name: str) -> str | None:
    """将单个 Paddle 参数名映射为语义 PyTorch 路径。

    仅覆盖 DBHead 层索引（取自 frotms 参考 det_db_head.py 的
    ``binarize_name_list``/``thresh_name_list``），用于核对 DBHead 结构。

    .. note::
        DBHead 的相对结构（binarize: conv/bn/transposed/bn/transposed，
        thresh 同）确定可靠，但 ``conv2d_56`` / ``batch_norm_47`` 等**绝对
        层号**依赖其前的 backbone+neck 层数，随模型大小/版本变化，未经本仓库
        网络验证（如自研 tiny 模型位置对应结果为 ``conv2d_104``）。实际转换
        以 ``convert_ppocr_v6_det`` 的位置对应法为准。
    """
    parsed = parse_paddle_name(paddle_name)
    if parsed is None:
        return None
    layer_type, layer_index, _rank, kind = parsed
    base = _DB_HEAD_PATH.get((layer_type, layer_index))
    if base is None:
        return None
    return f"{base}.{kind}"


# ---------------------------------------------------------------------------
# 有序参数收集
# ---------------------------------------------------------------------------


def ordered_paddle_entries(paddle_state: dict) -> list[tuple]:
    """按 .pdparams 保存顺序收集可映射的 Paddle 参数。

    返回 ``(key, layer_type, layer_index, kind_rank, kind, shape)`` 元组列表。
    Paddle 的 state_dict 按层创建顺序保存，因此保持原字典顺序即可与自研
    模型的注册顺序逐位对应。
    """
    entries = []
    for key, arr in paddle_state.items():
        parsed = parse_paddle_name(key)
        if parsed is None:
            continue
        layer_type, layer_index, rank, kind = parsed
        entries.append(
            (key, layer_type, layer_index, rank, kind, tuple(np.asarray(arr).shape))
        )
    return entries


def ordered_torch_entries(model: nn.Module) -> list[tuple]:
    """按注册顺序收集自研模型的可加载参数。

    返回 ``(path, kind, shape)`` 元组列表，跳过 ``num_batches_tracked``
    （Paddle 无对应物，转换后统一置 0）。
    """
    entries = []
    for path, tensor in model.state_dict().items():
        if path.endswith("num_batches_tracked"):
            continue
        entries.append((path, path.rsplit(".", 1)[-1], tuple(tensor.shape)))
    return entries


# ---------------------------------------------------------------------------
# 转换
# ---------------------------------------------------------------------------


@dataclass
class ConversionReport:
    """转换结果摘要。"""

    matched: int = 0
    skipped: int = 0
    warnings: list[str] = field(default_factory=list)
    path_to_paddle: dict = field(default_factory=dict)


def convert_with_report(paddle_state: dict, model: nn.Module) -> tuple[dict, ConversionReport]:
    """位置对应法转换：Paddle state_dict → PyTorch state_dict。

    ``paddle_state``: {paddle_param_name: np.ndarray}
    ``model``: 自研 det 模型（backbone + neck + head，用于取参数路径与形状）。
    返回 ``(torch_state_dict, ConversionReport)``。
    """
    torch_entries = ordered_torch_entries(model)
    paddle_entries = ordered_paddle_entries(paddle_state)

    state: dict = {}
    report = ConversionReport()
    n = max(len(torch_entries), len(paddle_entries))
    for i in range(n):
        t = torch_entries[i] if i < len(torch_entries) else None
        p = paddle_entries[i] if i < len(paddle_entries) else None
        if t is None:
            report.warnings.append(f"unused paddle param: {p[0]}")
            continue
        if p is None:
            report.warnings.append(f"no paddle counterpart for torch param: {t[0]}")
            report.skipped += 1
            continue
        t_path, t_kind, t_shape = t
        p_key, _p_type, _p_index, _p_rank, p_kind, p_shape = p
        if p_kind != t_kind:
            report.warnings.append(
                f"kind mismatch at position {i}: paddle {p_key} ({p_kind}) "
                f"vs torch {t_path} ({t_kind})"
            )
            report.skipped += 1
            continue
        if p_shape != t_shape:
            report.warnings.append(
                f"shape mismatch: paddle {p_key} {p_shape} vs torch {t_path} {t_shape}"
            )
            report.skipped += 1
            continue
        arr = np.asarray(paddle_state[p_key], dtype=np.float32)
        # clone：避免 from_numpy 与原数组共享内存，防止调用方后续修改影响结果
        state[t_path] = torch.from_numpy(arr).clone()
        report.path_to_paddle[t_path] = p_key
        report.matched += 1

    # Paddle 无 num_batches_tracked，统一初始化为 0
    for path in model.state_dict():
        if path.endswith("num_batches_tracked"):
            state[path] = torch.tensor(0, dtype=torch.long)

    return state, report


def build_det_model(
    model_size: str = "tiny", fpn_out_channels: int = 64, k: int = 50
) -> nn.Module:
    """构建自研 PP-OCRv6 det 模型（PPLCNetV4 + RepLKFPN + DBHead）。

    参数路径前缀固定为 ``backbone.*`` / ``neck.*`` / ``head.*``，
    与转换结果保持一致。
    """
    backbone = PPLCNetV4(model_size=model_size, det=True)
    fpn = RepLKFPN(
        in_channels=backbone.out_channels,
        out_channels=fpn_out_channels,
    )
    head = DBHead(in_channels=fpn_out_channels, k=k)
    model = nn.Module()
    model.backbone = backbone
    model.neck = fpn
    model.head = head
    model.eval()
    return model


def convert_ppocr_v6_det(
    paddle_state: dict, model_size: str = "tiny", fpn_out_channels: int = 64, k: int = 50
) -> dict:
    """转换 Paddle state dict 为 PyTorch state dict。

    ``paddle_state``: {paddle_param_name: np.ndarray}（Paddle .pdparams 内容）
    返回 ``{pytorch_param_name: torch.Tensor}``，可 ``strict=False`` 加载进
    ``build_det_model(model_size)`` 构造的模型。
    """
    model = build_det_model(model_size, fpn_out_channels=fpn_out_channels, k=k)
    state, report = convert_with_report(paddle_state, model)
    for warning in report.warnings:
        logger.warning("weight converter: %s", warning)
    if report.matched == 0:
        raise ValueError("no parameters mapped — check Paddle param name format")
    return state
