"""转换校验：加载转换后的 .pt 权重，跑自研模型前向，输出与 Paddle 参考对比。

完整数值级校验需在 Paddle 环境（paddlex:latest 容器）同时跑两个模型做逐层
对比——这是 plan 3 的端到端人工验收项。本脚本交付：加载转换权重 + 前向冒烟 +
形状/数值统计输出，供容器内与 Paddle 输出做对比。

用法（容器内或 backend 根目录）:
  python verify_conversion.py --pytorch /path/converted.pt [--input sample.npy]
  python verify_conversion.py --rec --pytorch /path/converted.pt [--input sample.npy]
"""
import argparse
import os
import sys

import numpy as np
import torch

# 支持从任意目录直接运行：将 backend 根目录加入 sys.path
_BACKEND_ROOT = os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")
)
if _BACKEND_ROOT not in sys.path:
    sys.path.insert(0, _BACKEND_ROOT)

from pytorch_ocr.converter.ppocr_v6_det_converter import build_det_model  # noqa: E402


def _load_input(args) -> torch.Tensor:
    """构造测试输入：优先读 .npy，否则用随机张量（det/rec 各自默认尺寸）。"""
    if args.input:
        x = torch.from_numpy(np.load(args.input)).unsqueeze(0).float()
    elif args.rec:
        x = torch.randn(1, 3, 48, 320)
    else:
        x = torch.randn(1, 3, 640, 640)
    return x / 255.0 if x.max() > 1.0 else x


def _verify_det(args) -> None:
    model = build_det_model(model_size=args.model_size)
    state = torch.load(args.pytorch, map_location="cpu")
    result = model.load_state_dict(state, strict=False)
    if result.missing_keys:
        print(f"[warn] missing keys: {result.missing_keys}")
    if result.unexpected_keys:
        print(f"[warn] unexpected keys: {result.unexpected_keys}")

    x = _load_input(args)
    with torch.no_grad():
        feats = model.backbone(x)
        fuse = model.neck(feats)
        out = model.head(fuse)
    maps = out["maps"] if isinstance(out, dict) else out
    print(f"input: {tuple(x.shape)}")
    print(f"fuse: {tuple(fuse.shape)}")
    print(f"det output: {tuple(maps.shape)}")
    print(
        f"output stats: sum={maps.sum().item():.6f} mean={maps.mean().item():.6f} "
        f"max={maps.max().item():.6f} min={maps.min().item():.6f}"
    )


def _verify_rec(args) -> None:
    from pytorch_ocr.converter.ppocr_v6_rec_converter import build_rec_model

    model = build_rec_model(model_size=args.model_size)
    state = torch.load(args.pytorch, map_location="cpu")
    result = model.load_state_dict(state, strict=False)
    if result.missing_keys:
        print(f"[warn] missing keys: {result.missing_keys}")
    if result.unexpected_keys:
        print(f"[warn] unexpected keys: {result.unexpected_keys}")

    x = _load_input(args)
    with torch.no_grad():
        feat = model.backbone(x)
        out = model.head(feat)
    print(f"input: {tuple(x.shape)}")
    print(f"rec backbone: {tuple(feat.shape)}")
    for name, logits in out.items():
        print(f"rec {name} output: {tuple(logits.shape)}")
        print(
            f"{name} stats: sum={logits.sum().item():.6f} "
            f"mean={logits.mean().item():.6f} "
            f"max={logits.max().item():.6f} min={logits.min().item():.6f}"
        )


def main() -> None:
    ap = argparse.ArgumentParser(description="PP-OCRv6 det/rec 权重转换校验")
    ap.add_argument(
        "--pytorch", required=True, help="转换后的 PyTorch 权重文件 (.pt/.pth)"
    )
    ap.add_argument("--rec", action="store_true", help="验证 rec 权重")
    ap.add_argument("--model_size", default="tiny", choices=["tiny", "small", "medium"])
    ap.add_argument("--input", default=None, help="测试输入 .npy (C,H,W)")
    args = ap.parse_args()

    if args.rec:
        _verify_rec(args)
    else:
        _verify_det(args)
    print("conversion verification: run Paddle-side comparison in container")


if __name__ == "__main__":
    main()
