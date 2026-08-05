"""det 训练增强（pytorch_ocr/data/augment.py）测试。"""
import os
import random
import tempfile

import numpy as np
from PIL import Image

from pytorch_ocr.data.augment import (
    ColorJitter,
    CopyPaste,
    IaaAugment,
    RandomPerspective,
    get_rotate_crop_image,
)
from pytorch_ocr.data.det_dataset import DetDataset


def _synthetic_data(img_shape=(100, 200, 3), n=3):
    img = np.random.randint(0, 255, img_shape, dtype=np.uint8)
    h, w = img.shape[:2]
    polys = []
    for i in range(n):
        x0 = 30 + i * 50
        y0 = 20 + (i % 2) * 20
        polys.append(
            np.array(
                [[x0, y0], [x0 + 30, y0], [x0 + 30, y0 + 30], [x0, y0 + 30]],
                dtype=np.float32,
            )
        )
    return img, polys


def _data(img, polys):
    return {
        "image": img,
        "polys": polys,
        "ignore_tags": [False] * len(polys),
        "texts": [f"t{i}" for i in range(len(polys))],
    }


def test_iaa_augment_preserves_poly_count():
    random.seed(0)
    np.random.seed(0)
    img, polys = _synthetic_data(img_shape=(100, 200, 3), n=3)
    out = IaaAugment()(_data(img, polys))
    assert len(out["polys"]) == 3
    for p in out["polys"]:
        assert p.shape == (4, 2)
    assert out["image"].dtype == np.uint8


def test_color_jitter_shapes():
    img, polys = _synthetic_data(img_shape=(100, 200, 3), n=3)
    out = ColorJitter()(_data(img, polys))
    assert out["image"].shape == img.shape
    assert out["image"].dtype == np.uint8


def test_perspective_preserves_poly_count():
    random.seed(1)
    np.random.seed(1)
    img, polys = _synthetic_data(img_shape=(100, 200, 3), n=3)
    out = RandomPerspective(prob=1.0)(_data(img, polys))
    assert len(out["polys"]) == 3
    for p in out["polys"]:
        assert p.shape == (4, 2)


def test_get_rotate_crop_image_returns_rect():
    img = np.random.randint(0, 255, (80, 80, 3), dtype=np.uint8)
    poly = np.array([[10, 20], [50, 22], [48, 40], [12, 38]], dtype=np.float32)
    crop = get_rotate_crop_image(img, poly)
    assert crop.ndim == 3
    assert crop.shape[-1] == 3
    assert crop.shape[0] > 0 and crop.shape[1] > 0


def test_random_crop_still_works():
    with tempfile.TemporaryDirectory() as tmp:
        gt_dir = os.path.join(tmp, "images")
        os.makedirs(gt_dir, exist_ok=True)
        img = np.random.randint(0, 255, (192, 256, 3), dtype=np.uint8)
        Image.fromarray(img).save(os.path.join(gt_dir, "img_0.jpg"))
        label = os.path.join(tmp, "det_gt.txt")
        with open(label, "w", encoding="utf-8") as f:
            f.write("img_0.jpg [[20.0,20.0],[80.0,20.0],[80.0,40.0],[20.0,40.0]]\n")
        ds = DetDataset(gt_dir=gt_dir, label_path=label,
                        image_shape=(128, 128), use_aug=True)
        img_t, shrink_map, shrink_mask, thresh_map, thresh_mask = ds[0]
        assert tuple(img_t.shape) == (3, 128, 128)
        assert tuple(shrink_map.shape) == (1, 128, 128)
        assert tuple(thresh_map.shape) == (1, 128, 128)


def test_det_trainer_aug_config_constructs():
    from pytorch_ocr.trainer.det_trainer import DetTrainer

    with tempfile.TemporaryDirectory() as tmp:
        data_dir = os.path.join(tmp, "data")
        images_dir = os.path.join(data_dir, "images")
        os.makedirs(images_dir, exist_ok=True)
        for i in range(3):
            img = np.zeros((64, 64, 3), dtype=np.uint8)
            img[10:40, 10:50] = 200
            Image.fromarray(img).save(os.path.join(images_dir, f"img_{i}.jpg"))
        poly = "[[12.8,12.8],[51.2,12.8],[51.2,25.6],[12.8,25.6]]"
        with open(os.path.join(data_dir, "det_gt.txt"), "w", encoding="utf-8") as f:
            f.writelines([f"img_{i}.jpg\t{poly}\n" for i in range(3)])

        config = {
            "model_size": "tiny",
            "out_channels": 16,
            "image_shape": (64, 64),
            "use_iaa": True,
            "use_color_jitter": True,
            "use_perspective": True,
            "copy_paste": False,
        }
        trainer = DetTrainer(config, device="cpu")
        best_path = trainer.train(
            data_dir,
            num_epochs=1,
            batch_size=2,
            output_dir=os.path.join(tmp, "output"),
            workers=0,
            lr=0.001,
        )
        assert os.path.isfile(best_path)


def test_copy_paste_appends_polys():
    src_img = np.random.randint(0, 255, (200, 200, 3), dtype=np.uint8)
    src_polys = [
        np.array([[20, 20], [60, 20], [60, 40], [20, 40]], dtype=np.float32)
    ]
    ext_img = np.random.randint(0, 255, (120, 120, 3), dtype=np.uint8)
    ext_polys = []
    for i in range(10):
        x = (i % 3) * 30 + 5
        y = (i // 3) * 30 + 5
        ext_polys.append(
            np.array(
                [[x, y], [x + 25, y], [x + 25, y + 15], [x, y + 15]],
                dtype=np.float32,
            )
        )
    ext_texts = [f"ext{i}" for i in range(10)]
    ext_data = {
        "image": ext_img,
        "polys": ext_polys,
        "texts": ext_texts,
        "ignore_tags": [False] * 10,
    }
    data = _data(src_img, src_polys)
    src_texts = data["texts"]
    out = CopyPaste(objects_paste_ratio=0.2)(data, ext_data=ext_data)
    assert len(out["polys"]) > len(src_polys)
    assert len(out["texts"]) > len(src_texts)
