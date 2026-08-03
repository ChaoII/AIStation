"""PP-OCRv6 rec 权重转换：Paddle .pdparams → PyTorch state_dict。

rec 网络：``PPLCNetV4(det=False)``（单特征 [B, C, 1, W]）+ ``MultiHead``
（CTCHead + NRTRHead 双头）。

官方 PP-OCRv6 rec 权重（PaddleX .pdparams）为语义命名，且 head 结构与自研
模型存在结构差异，转换分两条路径：

1. **位置对应法**（``convert_with_report``）：backbone 的 ``conv2d_N`` /
   ``batch_norm_N`` 命名与 det 一致，按保存序与注册序逐位配对（plan 1 产物）。
2. **语义名 + 结构变换**（``convert_rec_by_name``）：官方权重用语义名
   （``backbone.*`` / ``head.ctc_head.*`` / ``head.gtc_head.*``）。

官方 head 结构（``gtc_head``）与自研 ``nrtr_head`` 不同，需结构变换：

- ``head.before_gtc.1.fc``（Linear, [in, out]）→ ``head.nrtr_head.linear``（转置）
- ``head.gtc_head.decoder.N.self_attn.qkv``（融合 Linear [in, 3*dim]）→
  ``decoder.layers.N.self_attn.conv{1,2,3}``（1x1 Conv2d，按列拆分 + 转置）
- ``head.gtc_head.decoder.N.cross_attn.q/kv`` → ``multihead_attn.conv1`` /
  ``conv2`` + ``conv3``（kv 拆 k/v 两列）
- ``head.gtc_head.decoder.N.mlp.fc1/fc2``（Linear）→ ``conv1/conv2``（1x1 Conv2d）
- ``head.gtc_head.decoder.N.norm1/2/3`` → ``norm1/2/3``（LayerNorm 同名）
- ``head.gtc_head.tgt_word_prj``（Linear）→ ``tgt_word_prj``（转置）
- ``head.gtc_head.positional_encoding.pe`` → 自研为非持久 buffer，跳过
- CTCHead：``guide_layer.*``（Conv1d/BN1d 同名）直接对应；``fc1/fc2``
  （Linear）转置后对应
- 词表：官方 CTCHead=dict 大小（6906），GTCHead=dict+4 特殊 token（6910），
  转换时用 ``ctc_out_channels``/``nrtr_out_channels`` 分开指定
"""
import logging
import re

import numpy as np
import torch
import torch.nn as nn

from ..modeling.backbones.pplcnetv4 import PPLCNetV4
from ..modeling.heads.rec_multi_head import MultiHead
from .ppocr_v6_det_converter import (
    ConversionReport,
    _rename_semantic,
    convert_with_report,
)

logger = logging.getLogger(__name__)

__all__ = [
    "ConversionReport",
    "build_rec_model",
    "convert_ppocr_v6_rec",
    "map_semantic_rec_name",
]

# 官方 PP-OCRv6 双头词表：CTCHead=dict 大小，GTCHead=dict+4 特殊 token
_CTC_DEFAULT_OUT = 6906
_NRTR_DEFAULT_OUT = 6910

# Paddle 层编号（保存序全局计数）与自研 rec 模型注册序一致（backbone 部分）
_LAYER_KIND = {"conv2d": "conv", "batch_norm": "bn"}
_PARAM_MAP = {
    "w_0": "weight",
    "b_0": "bias",
    "w_1": "running_mean",
    "_mean": "running_mean",
    "w_2": "running_var",
    "_variance": "running_var",
}
_PADDLE_NAME_RE = re.compile(
    r"^(conv2d|batch_norm)_(\d+)\.(w_0|b_0|w_1|w_2|_mean|_variance)$"
)

# 官方 GTC decoder 层索引 → 自研 decoder.layers 索引
_DECODER_LAYER_RE = re.compile(r"^head\.gtc_head\.decoder\.(\d+)\.(.+)$")


def build_rec_model(
    model_size: str = "tiny",
    out_channels: int = 6906,
    backbone_out_channels: int = 160,
    max_text_length: int = 25,
    nrtr_dim: int = 384,
    ctc_out_channels: int | None = None,
    nrtr_out_channels: int | None = None,
) -> nn.Module:
    """构建自研 PP-OCRv6 rec 模型（PPLCNetV4(rec) + MultiHead）。

    参数路径前缀固定为 ``backbone.*`` / ``head.*``，与转换结果保持一致。
    ``out_channels`` 默认 6906（官方 ppocrv6_tiny_dict.txt 词表 + blank）。

    官方 PP-OCRv6 双头词表大小不同（CTCHead=dict 大小，NRTRHead=dict+4 特殊
    token）。转换官方权重时用 ``ctc_out_channels`` / ``nrtr_out_channels``
    单独指定（默认 None → 共用 ``out_channels``）。
    """
    backbone = PPLCNetV4(model_size=model_size, det=False)
    head = MultiHead(
        in_channels=backbone_out_channels,
        out_channels=out_channels,
        max_text_length=max_text_length,
        nrtr_dim=nrtr_dim,
        ctc_out_channels=ctc_out_channels,
        nrtr_out_channels=nrtr_out_channels,
    )
    model = nn.Module()
    model.backbone = backbone
    model.head = head
    model.eval()
    return model


# ---------------------------------------------------------------------------
# 语义名映射（官方 PaddleX .pdparams）
# ---------------------------------------------------------------------------


def _ctc_head_mapping(paddle_name: str) -> list[tuple[str, str]]:
    """CTCHead 语义名 → (torch 路径, 变换类型)。

    变换类型：
    - ``direct``：直接拷贝（Conv1d/BN1d 参数布局两框架一致）
    - ``t``：转置（Paddle Linear [in, out] → PyTorch [out, in]）
    """
    rest = paddle_name[len("head.ctc_head."):]
    # guide_layer: 索引命名一致（Conv1d conv1/conv2、BN1d）
    m = re.match(r"^guide_layer\.(\d+)\.(weight|bias|_mean|_variance)$", rest)
    if m:
        idx, kind = m.group(1), m.group(2)
        torch_kind = _PARAM_MAP.get(kind, kind)
        return [(f"head.ctc_head.guide_layer.{idx}.{torch_kind}", "direct")]
    # fc1/fc2: Paddle Linear [in, out] → PyTorch Linear [out, in]
    m = re.match(r"^(fc1|fc2)\.(weight|bias)$", rest)
    if m:
        name, kind = m.group(1), m.group(2)
        transform = "t" if kind == "weight" else "direct"
        return [(f"head.ctc_head.{name}.{kind}", transform)]
    return []


def _gtc_decoder_mapping(paddle_name: str, layer_idx: str, sub: str) -> list[tuple[str, str]]:
    """GTC decoder 子层 → 自研 decoder.layers 子层（1x1 Conv2d / LayerNorm）。"""
    base = f"head.nrtr_head.transformer.decoder.layers.{layer_idx}."
    # self_attn: 融合 qkv Linear → conv1/conv2/conv3
    m = re.match(r"^self_attn\.qkv\.(weight|bias)$", sub)
    if m:
        kind = m.group(1)
        if kind == "weight":
            return [
                (f"{base}self_attn.conv1.weight", "split_qkv_w_0"),
                (f"{base}self_attn.conv2.weight", "split_qkv_w_1"),
                (f"{base}self_attn.conv3.weight", "split_qkv_w_2"),
            ]
        return [
            (f"{base}self_attn.conv1.bias", "split_qkv_b_0"),
            (f"{base}self_attn.conv2.bias", "split_qkv_b_1"),
            (f"{base}self_attn.conv3.bias", "split_qkv_b_2"),
        ]
    m = re.match(r"^self_attn\.out_proj\.(weight|bias)$", sub)
    if m:
        kind = m.group(1)
        return [(f"{base}self_attn.out_proj.{kind}", "t" if kind == "weight" else "direct")]
    # cross_attn: q → conv1，kv → conv2（k）+ conv3（v）
    m = re.match(r"^cross_attn\.q\.(weight|bias)$", sub)
    if m:
        kind = m.group(1)
        return [(f"{base}multihead_attn.conv1.{kind}", "t" if kind == "weight" else "direct")]
    m = re.match(r"^cross_attn\.kv\.(weight|bias)$", sub)
    if m:
        kind = m.group(1)
        if kind == "weight":
            return [
                (f"{base}multihead_attn.conv2.weight", "split_kv_w_0"),
                (f"{base}multihead_attn.conv3.weight", "split_kv_w_1"),
            ]
        return [
            (f"{base}multihead_attn.conv2.bias", "split_kv_b_0"),
            (f"{base}multihead_attn.conv3.bias", "split_kv_b_1"),
        ]
    m = re.match(r"^cross_attn\.out_proj\.(weight|bias)$", sub)
    if m:
        kind = m.group(1)
        return [(f"{base}multihead_attn.out_proj.{kind}", "t" if kind == "weight" else "direct")]
    # mlp: fc1/fc2 Linear → conv1/conv2（1x1 Conv2d）
    m = re.match(r"^mlp\.fc1\.(weight|bias)$", sub)
    if m:
        kind = m.group(1)
        return [(f"{base}conv1.{kind}", "t" if kind == "weight" else "direct")]
    m = re.match(r"^mlp\.fc2\.(weight|bias)$", sub)
    if m:
        kind = m.group(1)
        return [(f"{base}conv2.{kind}", "t" if kind == "weight" else "direct")]
    # norm1/2/3: LayerNorm 同名
    m = re.match(r"^norm([123])\.(weight|bias)$", sub)
    if m:
        idx, kind = m.group(1), m.group(2)
        return [(f"{base}norm{idx}.{kind}", "direct")]
    return []


def map_semantic_rec_name(paddle_name: str) -> list[tuple[str, str]] | None:
    """官方 PaddleX rec 语义参数名 → [(torch 路径, 变换类型), ...] 列表。

    返回 None 表示该 Paddle 参数无 torch 对应项（跳过）。backbone 语义名与
    自研一致（仅 BN 统计量后缀 ``_mean``/``_variance`` 不同），直接 rename。
    """
    if paddle_name.startswith("backbone."):
        return [(_rename_semantic(paddle_name), "direct")]
    if paddle_name.startswith("head.ctc_head."):
        return _ctc_head_mapping(paddle_name)
    if paddle_name == "head.before_gtc.1.fc.weight":
        return [("head.nrtr_head.linear.weight", "t")]
    if paddle_name == "head.gtc_head.embedding.embedding.weight":
        return [("head.nrtr_head.transformer.embedding.embedding.weight", "direct")]
    if paddle_name == "head.gtc_head.tgt_word_prj.weight":
        return [("head.nrtr_head.transformer.tgt_word_prj.weight", "t")]
    m = _DECODER_LAYER_RE.match(paddle_name)
    if m:
        return _gtc_decoder_mapping(paddle_name, m.group(1), m.group(2))
    # positional_encoding.pe / 其他无对应项
    return None


def _transform_array(arr: np.ndarray, transform: str, target_shape: tuple) -> np.ndarray:
    """按变换类型处理 Paddle 数组，输出与 target_shape 一致的数组。

    - ``direct``: 原样（float32）
    - ``t``: 转置（Linear [in,out] → [out,in]），再 reshape 到目标（如 1x1 Conv2d）
    - ``split_qkv_w_{i}``: 融合 QKV Linear weight [in, 3*dim] 取第 i 段 [in, dim]
      转置后 reshape 为 1x1 Conv2d weight [dim, in, 1, 1]
    - ``split_qkv_b_{i}``: 融合 QKV bias [3*dim] 取第 i 段 [dim]
    - ``split_kv_w_{i}``: 融合 KV weight [in, 2*dim] 取第 i 段，转置 + reshape
    - ``split_kv_b_{i}``: 融合 KV bias [2*dim] 取第 i 段
    """
    arr = np.asarray(arr, dtype=np.float32)
    m = re.match(r"^split_(qkv|kv)_(w|b)_(\d+)$", transform)
    if m:
        kind, wb, idx = m.group(1), m.group(2), int(m.group(3))
        n = 3 if kind == "qkv" else 2
        if wb == "w":
            dim = arr.shape[1] // n
            out = arr[:, idx * dim:(idx + 1) * dim].T  # [dim, in]
            return out.reshape(target_shape)
        dim = arr.shape[0] // n
        return arr[idx * dim:(idx + 1) * dim].reshape(target_shape)
    if transform == "t":
        return arr.T.reshape(target_shape)
    return arr.reshape(target_shape) if arr.shape != target_shape else arr


def convert_rec_by_name(paddle_state: dict, model: nn.Module) -> tuple[dict, ConversionReport]:
    """语义名 + 结构变换转换：官方 PaddleX .pdparams → PyTorch state_dict。

    ``paddle_state``: {paddle_param_name: np.ndarray}
    ``model``: 自研 rec 模型（用于取参数路径与形状）。
    返回 ``(torch_state_dict, ConversionReport)``。
    """
    torch_sd = model.state_dict()
    torch_shapes = {
        k: tuple(v.shape)
        for k, v in torch_sd.items()
        if not k.endswith("num_batches_tracked")
    }
    state: dict = {}
    report = ConversionReport()
    used_paddle = set()

    for p_name, arr in paddle_state.items():
        if not isinstance(arr, (np.ndarray,)) or arr.ndim == 0:
            continue
        targets = map_semantic_rec_name(p_name)
        if not targets:
            continue
        for t_path, transform in targets:
            if t_path not in torch_shapes:
                continue
            t_shape = torch_shapes[t_path]
            kind = t_path.rsplit(".", 1)[-1]
            p_kind = _PARAM_MAP.get(p_name.rsplit(".", 1)[-1], p_name.rsplit(".", 1)[-1])
            if kind not in ("weight", "bias", "running_mean", "running_var"):
                continue
            # 语义名 BN 统计量后缀已由 _rename_semantic 转换，这里 kind 直接一致
            if p_kind not in ("weight", "bias", "running_mean", "running_var"):
                continue
            if kind != p_kind:
                report.warnings.append(
                    f"kind mismatch: paddle {p_name} ({p_kind}) vs torch {t_path} ({kind})"
                )
                report.skipped += 1
                continue
            out = _transform_array(arr, transform, t_shape)
            out = torch.from_numpy(np.ascontiguousarray(out))
            # 拆分/转置后 shape 与目标匹配校验
            if tuple(out.shape) != t_shape:
                report.warnings.append(
                    f"shape mismatch: paddle {p_name} {tuple(np.asarray(arr).shape)} "
                    f"-> torch {t_path} {t_shape} (got {tuple(out.shape)})"
                )
                report.skipped += 1
                continue
            state[t_path] = out.clone()
            report.path_to_paddle[t_path] = p_name
            report.matched += 1
            used_paddle.add(p_name)

    for p_name in paddle_state:
        if p_name not in used_paddle and not p_name.startswith("head.aux_"):
            report.warnings.append(f"unused paddle param: {p_name}")

    for path in torch_sd:
        if path.endswith("num_batches_tracked"):
            state[path] = torch.tensor(0, dtype=torch.long)

    return state, report


# ---------------------------------------------------------------------------
# 位置对应法（backbone conv2d_N/batch_norm_N 命名回退）
# ---------------------------------------------------------------------------


def _parse_paddle_name(paddle_name: str) -> tuple[str, int, str] | None:
    m = _PADDLE_NAME_RE.match(paddle_name)
    if m is None:
        return None
    return (_LAYER_KIND[m.group(1)], int(m.group(2)), _PARAM_MAP[m.group(3)])


def _ordered_paddle_entries(paddle_state: dict) -> list[tuple]:
    entries = []
    for key, arr in paddle_state.items():
        parsed = _parse_paddle_name(key)
        if parsed is None:
            continue
        layer_type, _index, kind = parsed
        entries.append((key, layer_type, kind, tuple(np.asarray(arr).shape)))
    return entries


def _ordered_torch_entries(model: nn.Module) -> list[tuple]:
    entries = []
    for path, tensor in model.state_dict().items():
        if path.endswith("num_batches_tracked"):
            continue
        entries.append((path, path.rsplit(".", 1)[-1], tuple(tensor.shape)))
    return entries


# ---------------------------------------------------------------------------
# 入口
# ---------------------------------------------------------------------------


def _guess_out_channels(paddle_state: dict) -> tuple[int | None, int | None]:
    """从官方权重的 fc2 / embedding 形状猜测 ctc / nrtr 词表大小。"""
    ctc_out: int | None = None
    nrtr_out: int | None = None
    for key, arr in paddle_state.items():
        if not isinstance(arr, (np.ndarray,)):
            continue
        if key == "head.ctc_head.fc2.weight" and arr.ndim == 2:
            # Paddle Linear [in, out] → out = shape[1]
            ctc_out = int(arr.shape[1])
        elif key == "head.gtc_head.embedding.embedding.weight" and arr.ndim == 2:
            nrtr_out = int(arr.shape[0])
    return ctc_out, nrtr_out


def convert_ppocr_v6_rec(
    paddle_state: dict,
    model_size: str = "tiny",
    out_channels: int = 6906,
    backbone_out_channels: int = 160,
    max_text_length: int = 25,
    nrtr_dim: int = 384,
) -> dict:
    """转换 Paddle state dict 为 PyTorch state dict。

    ``paddle_state``: {paddle_param_name: np.ndarray}（Paddle .pdparams 内容）
    返回 ``{pytorch_param_name: torch.Tensor}``，可 ``strict=False`` 加载进
    ``build_rec_model(model_size)`` 构造的模型。

    优先语义名 + 结构变换（官方 PaddleX .pdparams）；若匹配数为 0（说明输入
    是旧式 ``conv2d_N.w_0`` 命名），回退到位置对应法（backbone 部分）。
    """
    ctc_out, nrtr_out = _guess_out_channels(paddle_state)
    ctc_out = ctc_out or out_channels
    nrtr_out = nrtr_out or out_channels
    model = build_rec_model(
        model_size,
        out_channels=out_channels,
        backbone_out_channels=backbone_out_channels,
        max_text_length=max_text_length,
        nrtr_dim=nrtr_dim,
        ctc_out_channels=ctc_out,
        nrtr_out_channels=nrtr_out,
    )
    state, report = convert_rec_by_name(paddle_state, model)
    if report.matched == 0:
        state, report = convert_with_report(paddle_state, model)
    for warning in report.warnings:
        logger.warning("weight converter (rec): %s", warning)
    if report.matched == 0:
        raise ValueError("no parameters mapped — check Paddle param name format")
    # 守卫：head 层必须完整映射，否则报错（位置对应法无法表达 head 内 linear/embedding/layer_norm 交错）
    head_params = [k for k in model.state_dict() if k.startswith("head.")]
    missing_head = [k for k in head_params if k not in state]
    if missing_head:
        raise ValueError(
            f"rec head 权重未完整映射: {len(missing_head)}/{len(head_params)} missing "
            f"(e.g. {missing_head[:5]}). 位置对应法仅覆盖 conv/bn，head 需 name-based 映射 "
            f"(plan 3b)。"
        )
    return state
