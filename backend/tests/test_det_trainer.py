"""det 训练器结构与端到端训练冒烟测试。"""
import inspect
import os
import tempfile

import numpy as np
import pytest
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


def test_det_trainer_empty_dataset_raises():
    """空 det_gt.txt（无有效标注）时 train() 应抛出 ValueError。"""
    with tempfile.TemporaryDirectory() as tmp:
        data_dir = os.path.join(tmp, "data")
        os.makedirs(os.path.join(data_dir, "images"), exist_ok=True)
        with open(os.path.join(data_dir, "det_gt.txt"), "w", encoding="utf-8") as f:
            f.write("")
        config = {
            "model_size": "tiny",
            "out_channels": 16,
            "image_shape": (64, 64),
        }
        trainer = DetTrainer(config, device="cpu")
        with pytest.raises(ValueError, match="数据集为空"):
            trainer.train(
                data_dir,
                num_epochs=1,
                output_dir=os.path.join(tmp, "output"),
                workers=0,
            )


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


# ---------------------------------------------------------------------------
# eval（Hmean）
# ---------------------------------------------------------------------------


def test_polygon_iou_overlap():
    from pytorch_ocr.trainer.det_trainer import polygon_iou
    a = [[0, 0], [10, 0], [10, 10], [0, 10]]
    b = [[5, 0], [15, 0], [15, 10], [5, 10]]  # 重叠 5x10=50
    iou = polygon_iou(a, b)
    assert 0.3 < iou < 0.4  # 50 / (100+100-50)


def test_polygon_iou_no_overlap():
    from pytorch_ocr.trainer.det_trainer import polygon_iou
    a = [[0, 0], [10, 0], [10, 10], [0, 10]]
    b = [[20, 20], [30, 20], [30, 30], [20, 30]]
    assert polygon_iou(a, b) == 0.0


def test_compute_det_metrics_perfect():
    from pytorch_ocr.trainer.det_trainer import compute_det_metrics
    gt = [[[[0, 0], [10, 0], [10, 10], [0, 10]]]]
    pred = [[[[0, 0], [10, 0], [10, 10], [0, 10]]]]
    m = compute_det_metrics(pred, gt)
    assert m["tp"] == 1 and m["fp"] == 0 and m["fn"] == 0
    assert m["precision"] == 1.0
    assert m["recall"] == 1.0
    assert m["hmean"] == 1.0


def test_compute_det_metrics_miss_and_false_positive():
    from pytorch_ocr.trainer.det_trainer import compute_det_metrics
    gt = [[[[0, 0], [10, 0], [10, 10], [0, 10]]]]
    # 一个远离 GT 的误检（FP）+ 一个漏检（FN）
    pred = [[[[50, 50], [60, 50], [60, 60], [50, 60]]]]
    m = compute_det_metrics(pred, gt)
    assert m["tp"] == 0 and m["fp"] == 1 and m["fn"] == 1
    assert m["precision"] == 0.0
    assert m["recall"] == 0.0
    assert m["hmean"] == 0.0


def test_det_trainer_eval_deterministic_hmean():
    """eval 端到端：伪造概率图全亮 → 检出整幅图 → 与全幅 GT 匹配 → Hmean=1.0。"""
    import torch
    from PIL import Image

    from pytorch_ocr.trainer.det_trainer import DetTrainer

    with tempfile.TemporaryDirectory() as tmp:
        data_dir = os.path.join(tmp, "data")
        images_dir = os.path.join(data_dir, "images")
        os.makedirs(images_dir, exist_ok=True)
        for i in range(2):
            img = np.zeros((64, 64, 3), dtype=np.uint8)
            img[10:40, 10:50] = 200
            Image.fromarray(img).save(os.path.join(images_dir, f"img_{i}.jpg"))
        poly = "[[0,0],[64,0],[64,64],[0,64]]"
        with open(os.path.join(data_dir, "det_gt.txt"), "w", encoding="utf-8") as f:
            f.writelines([f"img_{i}.jpg\t{poly}\n" for i in range(2)])

        config = {
            "model_size": "tiny",
            "out_channels": 16,
            "image_shape": (64, 64),
        }
        trainer = DetTrainer(config, device="cpu")

        class FakeBackbone(torch.nn.Module):
            def forward(self, x):
                return x

        class FakeFPN(torch.nn.Module):
            def forward(self, feats):
                return {"fuse": feats}

        class FakeHead(torch.nn.Module):
            def forward(self, fused):
                m = np.ones((1, 1, 64, 64), dtype=np.float32)
                return {"maps": torch.from_numpy(m)}

        trainer.backbone = FakeBackbone()
        trainer.fpn = FakeFPN()
        trainer.head = FakeHead()

        result = trainer.eval(data_dir=data_dir)
        assert result["hmean"] == 1.0
        assert result["precision"] == 1.0
        assert result["recall"] == 1.0
        assert result["tp"] == 2
        assert result["fp"] == 0
        assert result["fn"] == 0
        assert result["num_images"] == 2
