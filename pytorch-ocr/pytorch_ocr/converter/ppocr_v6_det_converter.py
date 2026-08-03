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
# 语义名映射（官方 PaddleX .pdparams 使用语义命名，如
# ``backbone.stem.stem1.conv.weight`` / ``head.binarize.conv1.weight``；
# 自研模型 backbone/neck 与 Paddle 语义名一致，仅 DBHead 用索引命名）
# ---------------------------------------------------------------------------

# Paddle BN 统计量名 → PyTorch BN 统计量名
_SEMANTIC_SUFFIX_MAP = {
    "weight": "weight",
    "bias": "bias",
    "_mean": "running_mean",
    "_variance": "running_var",
}

# DBHead：Paddle 语义子层名 → 自研 nn.Sequential 索引（conv1→0, conv_bn1→1,
# conv2→3, conv_bn2→4, conv3→6；间隔为 relu 激活，无参数）
_HEAD_SUB_MAP = {
    "conv1": "0",
    "conv_bn1": "1",
    "conv2": "3",
    "conv_bn2": "4",
    "conv3": "6",
}


def _rename_semantic(paddle_name: str) -> str:
    """语义名重命名：``_mean``/``_variance`` → ``running_mean``/``running_var``。

    仅处理尾部统计量后缀，backbone/neck 其余部分两框架命名完全一致。
    """
    for pad_suffix, torch_suffix in _SEMANTIC_SUFFIX_MAP.items():
        if paddle_name.endswith("." + pad_suffix):
            return paddle_name[: -len(pad_suffix)] + torch_suffix
    return paddle_name


def map_semantic_name(paddle_name: str) -> str | None:
    """将语义 Paddle 参数名映射为自研模型 PyTorch 参数名。

    - ``head.<sub>.<conv1|conv_bn1|...>.<suffix>`` → ``head.<sub>.<idx>.<suffix>``
    - 其余语义名直接映射（backbone/neck 命名一致，仅替换 BN 统计量后缀）。
    - ``head.aux_*``（辅助深度监督头，自研模型不实现）返回 None。
    返回 None 表示无对应 torch 参数。
    """
    if paddle_name.startswith("head.aux_"):
        return None
    parts = paddle_name.split(".")
    if len(parts) >= 4 and parts[0] == "head" and parts[2] in _HEAD_SUB_MAP:
        head_sub = parts[1]  # binarize / thresh
        idx = _HEAD_SUB_MAP[parts[2]]
        torch_suffix = _SEMANTIC_SUFFIX_MAP.get(parts[3], parts[3])
        return f"head.{head_sub}.{idx}.{torch_suffix}"
    return _rename_semantic(paddle_name)


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


def convert_by_name(paddle_state: dict, model: nn.Module) -> tuple[dict, ConversionReport]:
    """语义名直接映射转换：官方 PaddleX .pdparams → PyTorch state_dict。

    官方权重（PaddleX 3.0）使用语义命名（``backbone.stem.stem1.conv.weight``、
    ``head.binarize.conv1.weight``），与自研模型 backbone/neck 命名一致，
    仅 DBHead 子层名不同（见 ``map_semantic_name``）。逐名做「kind + shape」
    双重校验，剩余无对应项进入 warning。

    ``paddle_state``: {paddle_param_name: np.ndarray}
    ``model``: 自研 det 模型。
    返回 ``(torch_state_dict, ConversionReport)``。
    """
    torch_sd = model.state_dict()
    state: dict = {}
    report = ConversionReport()
    used_paddle = set()

    for t_path, tensor in torch_sd.items():
        if t_path.endswith("num_batches_tracked"):
            continue
        kind = t_path.rsplit(".", 1)[-1]
        shape = tuple(tensor.shape)
        # 先直接匹配（backbone/neck 语义名一致），再走语义映射
        p_key = None
        if t_path in paddle_state:
            p_key = t_path
        else:
            for p_name in paddle_state:
                mapped = map_semantic_name(p_name)
                if mapped == t_path:
                    p_key = p_name
                    break
        if p_key is None:
            report.warnings.append(f"no paddle counterpart for torch param: {t_path}")
            report.skipped += 1
            continue
        p_shape = tuple(np.asarray(paddle_state[p_key]).shape)
        p_kind = p_key.rsplit(".", 1)[-1]
        if p_kind in ("_mean", "_variance"):
            p_kind = "running_mean" if p_kind == "_mean" else "running_var"
        if p_kind != kind:
            report.warnings.append(
                f"kind mismatch: paddle {p_key} ({p_kind}) vs torch {t_path} ({kind})"
            )
            report.skipped += 1
            continue
        if p_shape != shape:
            report.warnings.append(
                f"shape mismatch: paddle {p_key} {p_shape} vs torch {t_path} {shape}"
            )
            report.skipped += 1
            continue
        arr = np.asarray(paddle_state[p_key], dtype=np.float32)
        state[t_path] = torch.from_numpy(arr).clone()
        report.path_to_paddle[t_path] = p_key
        report.matched += 1
        used_paddle.add(p_key)

    for p_name in paddle_state:
        if p_name not in used_paddle and not p_name.startswith("head.aux_"):
            report.warnings.append(f"unused paddle param: {p_name}")

    # Paddle 无 num_batches_tracked，统一初始化为 0
    for path in torch_sd:
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
        shortcut=True,
        dilated_kernel_size=5,  # 对齐 det 配置 tiny_det.yml
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

    优先使用语义名直接映射（官方 PaddleX .pdparams）；若匹配数为 0（说明输入
    是旧式 ``conv2d_N.w_0`` 命名），回退到位置对应法。
    """
    model = build_det_model(model_size, fpn_out_channels=fpn_out_channels, k=k)
    state, report = convert_by_name(paddle_state, model)
    if report.matched == 0:
        state, report = convert_with_report(paddle_state, model)
    for warning in report.warnings:
        logger.warning("weight converter: %s", warning)
    if report.matched == 0:
        raise ValueError("no parameters mapped — check Paddle param name format")
    return state
