"""LightSVTR neck（PP-OCRv6 small/medium rec CTCHead neck）测试。"""
import re

import numpy as np
import torch

from pytorch_ocr.modeling.heads.rec_multi_head import MultiHead
from pytorch_ocr.modeling.necks.rec_lightsvtr import LightSVTR
from pytorch_ocr.trainer.rec_trainer import RecTrainer


def test_lightsvtr_forward_shapes():
    """LightSVTR(in_channels=384, dims=120, depth=2, mlp_ratio=2.0, local_kernel=7)。

    输入 [B, W, C] → 输出 [B, W, dims]。
    """
    neck = LightSVTR(in_channels=384, dims=120, depth=2, mlp_ratio=2.0, local_kernel=7)
    x = torch.randn(2, 25, 384)
    out = neck(x)
    assert out.shape == (2, 25, 120)


def test_multihead_lightsvtr_config():
    """MultiHead lightsvtr neck：backbone-feat (2,384,1,20) → {ctc, nrtr}。"""
    head = MultiHead(
        in_channels=384,
        out_channels=6906,
        head_list=[
            {"CTCHead": {"Neck": {"name": "lightsvtr", "dims": 120, "depth": 2,
                                  "mlp_ratio": 2.0, "local_kernel": 7}}},
            {"NRTRHead": {"nrtr_dim": 384, "max_text_length": 25}},
        ],
    )
    assert head.ctc_neck is not None
    assert head.ctc_neck.out_channels == 120
    head.eval()
    x = torch.randn(2, 384, 1, 20)
    with torch.no_grad():
        preds = head(x)
    assert set(preds) == {"ctc", "nrtr"}
    assert preds["ctc"].shape == (2, 20, 6906)
    assert preds["nrtr"].shape == (2, 25, 6906)


def test_multihead_medium_nrtr_dim_512():
    """medium：lightsvtr dims=192 + NRTR nrtr_dim=512（nrtr 输出通道 512）。"""
    head = MultiHead(
        in_channels=768,
        out_channels=6906,
        head_list=[
            {"CTCHead": {"Neck": {"name": "lightsvtr", "dims": 192, "depth": 2,
                                  "mlp_ratio": 4.0, "local_kernel": 7}}},
            {"NRTRHead": {"nrtr_dim": 512, "max_text_length": 25}},
        ],
    )
    assert head.ctc_neck.out_channels == 192
    assert head.ctc_head.out_features == 6906
    assert head.nrtr_head.linear.out_features == 512
    assert head.nrtr_head.transformer.d_model == 512


def test_rec_trainer_small_constructs():
    """RecTrainer model_size=small + lightsvtr head_list 在 CPU 上构造成功。"""
    config = {
        "model_size": "small",
        "num_classes": 6906,
        "image_shape": (48, 320),
        "max_text_length": 25,
        "head_list": [
            {"CTCHead": {"Neck": {"name": "lightsvtr", "dims": 120, "depth": 2,
                                  "mlp_ratio": 2.0, "local_kernel": 7}}},
            {"NRTRHead": {"nrtr_dim": 384, "max_text_length": 25}},
        ],
    }
    trainer = RecTrainer(config, device="cpu")
    assert trainer.backbone.out_channels == 384
    assert trainer.head.ctc_neck is not None
    assert trainer.head.ctc_neck.out_channels == 120
    assert trainer.head.ctc_head.out_features == 6906
    assert trainer.head.nrtr_head.linear.out_features == 384


def test_convert_lightsvtr_semantic_roundtrip():
    """官方 lightsvtr 语义名（head.ctc_encoder.encoder.*）可完整映射并 round-trip。

    用自研 lightsvtr 模型反转生成官方 PaddleX 命名的合成权重，
    convert_ppocr_v6_rec(neck="lightsvtr") 后 strict 加载零缺失、数值不变。
    """
    from pytorch_ocr.converter.ppocr_v6_rec_converter import (
        build_rec_model,
        convert_ppocr_v6_rec,
    )

    model = build_rec_model("small", neck="lightsvtr")
    torch_sd = {k: v.detach().numpy() for k, v in model.state_dict().items()}

    decoder_layer_re = re.compile(
        r"^head\.nrtr_head\.transformer\.decoder\.layers\.(\d+)\.(.+)$"
    )

    def torch_to_paddle(t_path, value):
        if t_path.startswith("head.ctc_neck."):
            rest = t_path[len("head.ctc_neck."):]
            p_rest = (
                rest.replace(".running_mean", "._mean")
                .replace(".running_var", "._variance")
            )
            p_name = f"head.ctc_encoder.encoder.{p_rest}"
            if re.search(r"mixer\.(qkv|proj)\.weight$|mlp\.fc[12]\.weight$", rest):
                return p_name, value.T
            return p_name, value
        if t_path == "head.ctc_head.weight":
            return "head.ctc_head.fc.weight", value.T
        if t_path == "head.ctc_head.bias":
            return "head.ctc_head.fc.bias", value
        if t_path == "head.nrtr_head.linear.weight":
            return "head.before_gtc.1.fc.weight", value.T
        if t_path == "head.nrtr_head.transformer.embedding.embedding.weight":
            return "head.gtc_head.embedding.embedding.weight", value
        if t_path == "head.nrtr_head.transformer.tgt_word_prj.weight":
            return "head.gtc_head.tgt_word_prj.weight", value.T
        m = decoder_layer_re.match(t_path)
        if m:
            lidx, sub = m.group(1), m.group(2)
            base = f"head.gtc_head.decoder.{lidx}."
            m2 = re.match(r"self_attn\.conv([123])\.(weight|bias)$", sub)
            if m2:
                cidx = int(m2.group(1)) - 1
                kind = m2.group(2)
                if kind == "weight":
                    value = value[:, :, 0, 0].T
                return (f"{base}self_attn.qkv.{kind}", value, cidx, 3)
            m2 = re.match(r"self_attn\.out_proj\.(weight|bias)$", sub)
            if m2:
                kind = m2.group(1)
                if kind == "weight":
                    return f"{base}self_attn.out_proj.weight", value.T
                return f"{base}self_attn.out_proj.bias", value
            m2 = re.match(r"multihead_attn\.conv([123])\.(weight|bias)$", sub)
            if m2:
                cidx = int(m2.group(1)) - 1
                kind = m2.group(2)
                if cidx == 0:
                    if kind == "weight":
                        return f"{base}cross_attn.q.weight", value[:, :, 0, 0].T
                    return f"{base}cross_attn.q.bias", value
                if kind == "weight":
                    value = value[:, :, 0, 0].T
                return (f"{base}cross_attn.kv.{kind}", value, cidx - 1, 2)
            m2 = re.match(r"multihead_attn\.out_proj\.(weight|bias)$", sub)
            if m2:
                kind = m2.group(1)
                if kind == "weight":
                    return f"{base}cross_attn.out_proj.weight", value.T
                return f"{base}cross_attn.out_proj.bias", value
            m2 = re.match(r"conv([12])\.(weight|bias)$", sub)
            if m2:
                fcidx = int(m2.group(1))
                kind = m2.group(2)
                if kind == "weight":
                    return f"{base}mlp.fc{fcidx}.weight", value[:, :, 0, 0].T
                return f"{base}mlp.fc{fcidx}.bias", value
            m2 = re.match(r"norm([123])\.(weight|bias)$", sub)
            if m2:
                return f"{base}norm{m2.group(1)}.{m2.group(2)}", value
        if t_path.startswith("backbone."):
            p_name = (
                t_path.replace(".running_mean", "._mean")
                .replace(".running_var", "._variance")
            )
            return p_name, value
        raise AssertionError(f"unmapped param: {t_path}")

    paddle = {}
    split_targets = {}
    for t_path, value in torch_sd.items():
        if t_path.endswith("num_batches_tracked"):
            continue
        res = torch_to_paddle(t_path, value)
        if isinstance(res, tuple) and len(res) == 4:
            p_name, value, cidx, n = res
            split_targets.setdefault(p_name, []).append((cidx, value))
        else:
            p_name, value = res
            paddle[p_name] = value
    for p_name, parts in split_targets.items():
        first = parts[0][1]
        if first.ndim == 1:
            merged = np.concatenate([p[1] for p in sorted(parts)], axis=0)
        else:
            merged = np.concatenate([p[1] for p in sorted(parts)], axis=1)
        paddle[p_name] = merged

    state = convert_ppocr_v6_rec(paddle, "small", neck="lightsvtr")
    result = model.load_state_dict(state, strict=True)
    assert result.missing_keys == []
    assert result.unexpected_keys == []
    for path, tensor in torch_sd.items():
        if path.endswith("num_batches_tracked"):
            continue
        assert path in state, f"missing {path}"
        assert np.allclose(state[path].numpy(), tensor), f"value changed: {path}"
