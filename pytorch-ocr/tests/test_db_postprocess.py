"""DBPostProcess 后处理测试。"""
import numpy as np
import torch

from pytorch_ocr.postprocess.db_postprocess import DBPostProcess


def test_db_postprocess_returns_boxes():
    pp = DBPostProcess(thresh=0.2, box_thresh=0.45, max_candidates=3000,
                       unclip_ratio=1.4)
    # 模拟检测到一块白色区域（概率图中心高亮）
    pred = torch.zeros(1, 1, 64, 64)
    pred[0, 0, 20:44, 20:44] = 0.9
    shape_list = [[64, 64]]  # (H, W)
    boxes = pp(pred, shape_list)
    assert isinstance(boxes, list)
    assert len(boxes) == 1
    if len(boxes[0]) > 0:
        box = boxes[0][0]
        assert len(box) == 4  # 4 个角点
        assert all(len(pt) == 2 for pt in box)


def test_db_postprocess_scales_to_original_size():
    """概率图为 64x64，原图为 128x64：坐标应缩放到原图尺度。"""
    pp = DBPostProcess(thresh=0.2, box_thresh=0.45, max_candidates=3000,
                       unclip_ratio=1.4)
    pred = torch.zeros(1, 1, 64, 64)
    pred[0, 0, 20:44, 20:44] = 0.9
    shape_list = [[128, 64]]  # 原图 H=128, W=64
    boxes = pp(pred, shape_list)
    assert isinstance(boxes, list)
    assert len(boxes) == 1
    if len(boxes[0]) > 0:
        for box in boxes[0]:
            assert len(box) == 4
            for pt in box:
                assert len(pt) == 2
                assert 0 <= pt[0] <= 64
                assert 0 <= pt[1] <= 128


def test_db_postprocess_empty_when_no_high_prob():
    """无高概率区域时应返回空列表。"""
    pp = DBPostProcess(thresh=0.2, box_thresh=0.45, max_candidates=3000,
                       unclip_ratio=1.4)
    pred = torch.zeros(2, 1, 64, 64)
    shape_list = [[64, 64], [64, 64]]
    boxes = pp(pred, shape_list)
    assert isinstance(boxes, list)
    assert len(boxes) == 2
    assert all(len(img_boxes) == 0 for img_boxes in boxes)


def test_db_postprocess_multiple_images():
    """多图输入，每图独立返回四边形列表。"""
    pp = DBPostProcess(thresh=0.2, box_thresh=0.45, max_candidates=3000,
                       unclip_ratio=1.4)
    pred = torch.zeros(2, 1, 64, 64)
    pred[0, 0, 10:30, 10:30] = 0.9  # 仅第一张有检测目标
    shape_list = [[64, 64], [64, 64]]
    boxes = pp(pred, shape_list)
    assert len(boxes) == 2
    assert len(boxes[0]) > 0
    assert len(boxes[1]) == 0


def test_db_postprocess_accepts_numpy_input():
    """兼容 numpy 输入（head 输出经 model_dump(mode='json') 后的形态）。"""
    pp = DBPostProcess(thresh=0.2, box_thresh=0.45, max_candidates=3000,
                       unclip_ratio=1.4)
    pred = np.zeros((1, 1, 64, 64), dtype=np.float32)
    pred[0, 0, 20:44, 20:44] = 0.9
    boxes = pp(pred, [[64, 64]])
    assert isinstance(boxes, list)
    assert len(boxes) == 1
