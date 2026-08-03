"""det 训练器结构与端到端训练冒烟测试。"""
import inspect
import os
import tempfile

import numpy as np
from PIL import Image

from pytorch_ocr.trainer.det_trainer import DetTrainer


def test_det_trainer_init_signature():
    sig = inspect.signature(DetTrainer.__init__)
    params = list(sig.parameters.keys())
    assert "config" in params
    assert "device" in params


def test_det_trainer_has_train_and_eval():
    assert hasattr(DetTrainer, "train")
    assert hasattr(DetTrainer, "eval")


def _write_synthetic_data(data_dir, num_images=3, size=64):
    """构造最小可训练数据集：data_dir/images/*.jpg + data_dir/det_gt.txt。"""
    images_dir = os.path.join(data_dir, "images")
    os.makedirs(images_dir, exist_ok=True)
    lines = []
    for i in range(num_images):
        img = np.zeros((size, size, 3), dtype=np.uint8)
        img[10:40, 10:50] = 200
        Image.fromarray(img).save(os.path.join(images_dir, f"img_{i}.jpg"))
        poly = "[[12.8,12.8],[51.2,12.8],[51.2,25.6],[12.8,25.6]]"
        lines.append(f"img_{i}.jpg\t{poly}\n")
    with open(os.path.join(data_dir, "det_gt.txt"), "w", encoding="utf-8") as f:
        f.writelines(lines)


def test_det_trainer_smoke_train_produces_best_pt():
    """端到端冒烟：CPU 上 1 个 epoch 训练后 output_dir 生成 best.pt。"""
    with tempfile.TemporaryDirectory() as tmp:
        data_dir = os.path.join(tmp, "data")
        output_dir = os.path.join(tmp, "output")
        _write_synthetic_data(data_dir)
        config = {
            "model_size": "tiny",
            "out_channels": 16,
            "image_shape": (64, 64),
        }
        trainer = DetTrainer(config, device="cpu")
        best_path = trainer.train(
            data_dir,
            num_epochs=1,
            batch_size=2,
            output_dir=output_dir,
            workers=0,
            lr=0.001,
        )
        assert best_path == os.path.join(output_dir, "best.pt")
        assert os.path.isfile(best_path)
