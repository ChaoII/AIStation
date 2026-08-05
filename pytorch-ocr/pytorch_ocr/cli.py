"""pytorch_ocr CLI：容器内训练/评估入口。自研实现。"""
import argparse
import json


def build_parser():
    parser = argparse.ArgumentParser(prog="pytorch_ocr",
                                     description="AIStation OCR CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    train_det = sub.add_parser("train-det", help="训练 det 检测模型")
    train_det.add_argument("--data", required=True, help="数据集目录(含 images/ + det_gt.txt)")
    train_det.add_argument("--output", default="/output", help="输出目录")
    train_det.add_argument("--device", default="0", help="GPU 设备 (0 / cpu)")
    train_det.add_argument("--epochs", type=int, default=100)
    train_det.add_argument("--batch", type=int, default=8)
    train_det.add_argument("--lr", type=float, default=0.001)
    train_det.add_argument("--workers", type=int, default=0,
                           help="DataLoader worker 数(默认 0，Windows/Docker 下避免 spawn 风险)")
    train_det.add_argument("--config", default="", help="JSON 配置文件路径(可选)")
    train_det.add_argument("--model-size", default="tiny",
                           choices=["tiny", "small", "medium"])
    train_det.add_argument("--neck", default="rep_lk_fpn",
                           choices=["rep_lk_fpn", "rep_lk_pan"],
                           help="det neck：rep_lk_fpn（tiny/small）或 rep_lk_pan（medium）")
    train_det.add_argument("--pretrained", default="",
                           help="预训练权重路径(官方转换的 .pt)，用于微调；容器内需挂载权重")
    train_det.add_argument("--freeze-backbone", action="store_true",
                           help="微调时冻结 backbone+fpn，只训练 head（防 BN 梯度爆炸/灾难性遗忘）")

    eval_det = sub.add_parser("eval-det", help="评估 det 模型")
    eval_det.add_argument("--data", required=True)
    eval_det.add_argument("--model", required=True, help="best.pt 路径")
    eval_det.add_argument("--output", default="/output")
    eval_det.add_argument("--device", default="0")
    eval_det.add_argument("--config", default="")

    train_rec = sub.add_parser("train-rec", help="训练 rec 识别模型")
    train_rec.add_argument("--data", required=True, help="数据集目录(含 images/ + train_list.txt)")
    train_rec.add_argument("--output", default="/output", help="输出目录")
    train_rec.add_argument("--device", default="0", help="GPU 设备 (0 / cpu)")
    train_rec.add_argument("--epochs", type=int, default=100)
    train_rec.add_argument("--batch", type=int, default=128)
    train_rec.add_argument("--lr", type=float, default=0.001)
    train_rec.add_argument("--workers", type=int, default=0,
                           help="DataLoader worker 数(默认 0，Windows/Docker 下避免 spawn 风险)")
    train_rec.add_argument("--config", default="", help="JSON 配置文件路径(可选)")
    train_rec.add_argument("--model-size", default="tiny",
                           choices=["tiny", "small", "medium"])
    train_rec.add_argument("--pretrained", default="",
                           help="预训练权重路径(官方转换的 .pt)，用于微调；容器内需挂载权重")
    train_rec.add_argument("--dict", default="",
                           help="字符集文件(每行一字符)，默认内置 ppocrv6_tiny_dict(6904)")
    train_rec.add_argument("--rec-head", default="auto",
                           help="CTCHead neck: auto(tiny=reshape/small+medium=lightsvtr) / reshape / lightsvtr")

    eval_rec = sub.add_parser("eval-rec", help="评估 rec 模型")
    eval_rec.add_argument("--data", required=True)
    eval_rec.add_argument("--model", required=True, help="best.pt 路径")
    eval_rec.add_argument("--output", default="/output")
    eval_rec.add_argument("--device", default="0")
    eval_rec.add_argument("--config", default="")
    eval_rec.add_argument("--dict", default="", help="字符集文件(每行一字符)")
    eval_rec.add_argument("--model-size", default="tiny",
                          choices=["tiny", "small", "medium"])

    predict = sub.add_parser("predict", help="OCR 推理")
    predict.add_argument("--image", required=True, help="输入图片路径")
    predict.add_argument("--det-model", required=True, help="det best.pt")
    predict.add_argument("--rec-model", required=True, help="rec best.pt")
    predict.add_argument("--output", default="/output/result.json")
    predict.add_argument("--device", default="0")
    predict.add_argument("--config", default="")
    return parser


def _normalize_device(raw: str) -> str:
    """'0'->'cuda:0', 'cuda:0'->'cuda:0', 'cpu'->'cpu'."""
    raw = (raw or "0").strip()
    if raw == "cpu":
        return "cpu"
    if ":" in raw:
        return raw
    return f"cuda:{raw}"


def _build_config(args, *, rec: bool = False) -> dict:
    if rec:
        from .modeling.backbones.pplcnetv4 import rec_backbone_out_channels
        cfg = {
            "model_size": getattr(args, "model_size", "tiny"),
            "num_classes": 6906,
            "max_text_length": 25,
            "nrtr_dim": 384,
            "backbone_out_channels": rec_backbone_out_channels(
                getattr(args, "model_size", "tiny")
            ),
            "image_shape": (48, 320),
        }
    else:
        cfg = {
            "model_size": getattr(args, "model_size", "tiny"),
            "neck": getattr(args, "neck", "rep_lk_fpn"),
            "out_channels": 64,
            "dilated_kernel_size": 5,
            "k": 50,
            "alpha": 5,
            "beta": 10,
            "image_shape": (640, 640),
        }
    if getattr(args, "config", ""):
        with open(args.config, encoding="utf-8") as f:
            cfg.update(json.load(f))
    return cfg


def cmd_train_det(args):
    from .trainer.det_trainer import DetTrainer
    device = _normalize_device(args.device)
    cfg = _build_config(args)
    cfg["model_size"] = args.model_size
    cfg["neck"] = args.neck
    cfg["image_shape"] = tuple(cfg.get("image_shape", (640, 640)))
    if args.pretrained:
        cfg["pretrained"] = args.pretrained
    if getattr(args, "freeze_backbone", False):
        cfg["freeze_backbone"] = True
    trainer = DetTrainer(cfg, device=device)
    best_path = trainer.train(
        data_dir=args.data, num_epochs=args.epochs, batch_size=args.batch,
        output_dir=args.output, workers=args.workers, lr=args.lr,
    )
    print(f"[cli] best model saved: {best_path}", flush=True)


def cmd_eval_det(args):
    from .trainer.det_trainer import DetTrainer
    device = _normalize_device(args.device)
    cfg = _build_config(args)
    trainer = DetTrainer(cfg, device=device)
    # 加载模型（兼容官方转换权重的 neck.* -> fpn.* 前缀）
    import torch
    state = torch.load(args.model, map_location="cpu")
    remap = {}
    for k, v in state.items():
        if k.startswith("neck."):
            remap["fpn." + k[len("neck."):]] = v
        else:
            remap[k] = v
    trainer.net.load_state_dict(remap, strict=False)
    result = trainer.eval(data_dir=args.data, output_dir=args.output)
    print(f"[cli] eval result: {json.dumps(result)}", flush=True)


def cmd_train_rec(args):
    from .trainer.rec_trainer import RecTrainer
    device = _normalize_device(args.device)
    cfg = _build_config(args, rec=True)
    cfg["model_size"] = args.model_size
    cfg["image_shape"] = tuple(cfg.get("image_shape", (48, 320)))
    if args.pretrained:
        cfg["pretrained"] = args.pretrained
    if getattr(args, "dict", ""):
        cfg["dict_path"] = args.dict
    rh = getattr(args, "rec_head", "auto")
    if rh != "auto":
        from .modeling.heads.rec_multi_head import build_default_head_list
        # 显式指定 reshape / lightsvtr：按 model_size 构造 head_list
        cfg["head_list"] = build_default_head_list(
            cfg["model_size"], nrtr_dim=cfg.get("nrtr_dim", 384),
            max_text_length=cfg.get("max_text_length", 25))
        if rh == "lightsvtr":
            from .modeling.heads.rec_multi_head import _LIGHTSVTR_PRESET, _NRTR_DIM_PRESET
            cfg["head_list"] = [
                {"CTCHead": {"Neck": {"name": "lightsvtr", **_LIGHTSVTR_PRESET[cfg["model_size"]]}}},
                {"NRTRHead": {"nrtr_dim": _NRTR_DIM_PRESET.get(cfg["model_size"], 384),
                              "max_text_length": cfg.get("max_text_length", 25)}},
            ]
    trainer = RecTrainer(cfg, device=device)
    best_path = trainer.train(
        data_dir=args.data, num_epochs=args.epochs, batch_size=args.batch,
        output_dir=args.output, workers=args.workers, lr=args.lr,
    )
    print(f"[cli] best model saved: {best_path}", flush=True)


def cmd_eval_rec(args):
    from .trainer.rec_trainer import RecTrainer
    device = _normalize_device(args.device)
    cfg = _build_config(args, rec=True)
    if getattr(args, "dict", ""):
        cfg["dict_path"] = args.dict
    cfg["model_size"] = getattr(args, "model_size", "tiny")
    trainer = RecTrainer(cfg, device=device)
    import torch
    trainer.net.load_state_dict(torch.load(args.model, map_location="cpu"))
    result = trainer.eval(data_dir=args.data, output_dir=args.output)
    print(f"[cli] eval result: {json.dumps(result)}", flush=True)


def cmd_predict(args):
    import cv2
    import torch

    from .inference.ocr_pipeline import OCRPipeline

    # OCR 推理需要 det + rec 两套配置键
    cfg = _build_config(args, rec=True)
    cfg.update(_build_config(args))
    det_state = torch.load(args.det_model, map_location="cpu")
    rec_state = torch.load(args.rec_model, map_location="cpu")
    pipe = OCRPipeline(det_state=det_state, rec_state=rec_state, config=cfg)
    img = cv2.imread(args.image)
    if img is None:
        raise ValueError(f"无法读取图片: {args.image}")
    result = pipe(img)
    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False)
    print(f"[cli] OCR result: {len(result)} detections -> {args.output}", flush=True)


def main():
    parser = build_parser()
    args = parser.parse_args()
    if args.command == "train-det":
        cmd_train_det(args)
    elif args.command == "eval-det":
        cmd_eval_det(args)
    elif args.command == "train-rec":
        cmd_train_rec(args)
    elif args.command == "eval-rec":
        cmd_eval_rec(args)
    elif args.command == "predict":
        cmd_predict(args)


if __name__ == "__main__":
    main()
