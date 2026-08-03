"""det 数据加载器与增强测试。"""
import numpy as np

from pytorch_ocr.data.det_dataset import DetDataset
from pytorch_ocr.data.transforms import MakeBorderMap, MakeShrinkMap


def test_make_shrink_map_shapes():
    transform = MakeShrinkMap(shrink_ratio=0.4, min_text_size=8)
    img = np.random.randint(0, 255, (64, 64, 3), dtype=np.uint8)
    # 一个矩形文本区域（归一化坐标）
    polys = [np.array([[0.2, 0.2], [0.8, 0.2], [0.8, 0.4], [0.2, 0.4]])]
    shrink_map, mask = transform(img, polys)
    assert shrink_map.shape == (64, 64)
    assert mask.shape == (64, 64)
    assert mask.sum() > 0  # 有标注区域


def test_make_border_map_shapes():
    transform = MakeBorderMap(shrink_ratio=0.4, thresh_min=0.3, thresh_max=0.7)
    img = np.random.randint(0, 255, (64, 64, 3), dtype=np.uint8)
    polys = [np.array([[0.2, 0.2], [0.8, 0.2], [0.8, 0.4], [0.2, 0.4]])]
    thresh_map, thresh_mask = transform(img, polys)
    assert thresh_map.shape == (64, 64)
    assert thresh_mask.shape == (64, 64)
    assert 0 <= thresh_map.min() <= thresh_map.max() <= 1


def test_det_dataset_len_and_item():
    import os
    import tempfile
    # 创建临时 det_gt.txt
    with tempfile.TemporaryDirectory() as tmp:
        img = np.random.randint(0, 255, (64, 64, 3), dtype=np.uint8).astype(np.uint8)
        from PIL import Image
        Image.fromarray(img).save(os.path.join(tmp, "img_0.jpg"))
        gt = os.path.join(tmp, "det_gt.txt")
        with open(gt, "w") as f:
            f.write("img_0.jpg [[12.8,12.8],[51.2,12.8],[51.2,25.6],[12.8,25.6]]\n")
        ds = DetDataset(gt_dir=tmp, label_path=gt, image_shape=(64, 64))
        assert len(ds) == 1
        item = ds[0]
        assert isinstance(item, tuple) and len(item) >= 4
