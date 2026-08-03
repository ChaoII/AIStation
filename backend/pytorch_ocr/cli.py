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
    train_det.add_argument("--device", default="0", help="GPU 设备(cuda:0 / cpu)")
    train_det.add_argument("--epochs", type=int, default=100)
    train_det.add_argument("--batch", type=int, default=8)
    train_det.add_argument("--lr", type=float, default=0.001)
    train_det.add_argument("--workers", type=int, default=0,
                           help="DataLoader worker 数(默认 0，Windows/Docker 下避免 spawn 风险)")
    train_det.add_argument("--config", default="", help="JSON 配置文件路径(可选)")
    train_det.add_argument("--model-size", default="tiny",
                           choices=["tiny", "small", "medium"])

    eval_det = sub.add_parser("eval-det", help="评估 det 模型")
    eval_det.add_argument("--data", required=True)
    eval_det.add_argument("--model", required=True, help="best.pt 路径")
    eval_det.add_argument("--output", default="/output")
    eval_det.add_argument("--device", default="0")
    eval_det.add_argument("--config", default="")
    return parser


def _build_config(args) -> dict:
    cfg = {
        "model_size": getattr(args, "model_size", "tiny"),
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
    device = "cpu" if args.device == "cpu" else f"cuda:{args.device}"
    cfg = _build_config(args)
    cfg["model_size"] = args.model_size
    cfg["image_shape"] = tuple(cfg.get("image_shape", (640, 640)))
    trainer = DetTrainer(cfg, device=device)
    best_path = trainer.train(
        data_dir=args.data, num_epochs=args.epochs, batch_size=args.batch,
        output_dir=args.output, workers=args.workers, lr=args.lr,
    )
    print(f"[cli] best model saved: {best_path}", flush=True)


def cmd_eval_det(args):
    from .trainer.det_trainer import DetTrainer
    device = "cpu" if args.device == "cpu" else f"cuda:{args.device}"
    cfg = _build_config(args)
    trainer = DetTrainer(cfg, device=device)
    # 加载模型
    import torch
    trainer.net.load_state_dict(torch.load(args.model, map_location="cpu"))
    result = trainer.eval(data_dir=args.data, output_dir=args.output)
    print(f"[cli] eval result: {json.dumps(result)}", flush=True)


def main():
    parser = build_parser()
    args = parser.parse_args()
    if args.command == "train-det":
        cmd_train_det(args)
    elif args.command == "eval-det":
        cmd_eval_det(args)


if __name__ == "__main__":
    main()
