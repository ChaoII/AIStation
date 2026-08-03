"""DBPostProcess：概率图 → 二值化 → 连通域 → unclip 膨胀 → 最小外接矩形。

自研实现，算法对齐 PaddleOCR 的 DBPostProcess：
1. 概率图按 thresh 二值化；
2. cv2.findContours 提取连通域；
3. 对每个连通域用 minAreaRect 取最小外接四边形，按 box_thresh 过滤分数；
4. 用 pyclipper 做真实多边形膨胀（unclip，distance = area * ratio / perimeter）；
5. 再取最小外接四边形，缩放到原图尺寸并裁剪到图像边界。
"""
import cv2
import numpy as np
import pyclipper
import torch


class DBPostProcess:
    def __init__(self, thresh=0.2, box_thresh=0.45, max_candidates=3000,
                 unclip_ratio=1.4, score_mode="fast"):
        self.thresh = thresh
        self.box_thresh = box_thresh
        self.max_candidates = max_candidates
        self.unclip_ratio = unclip_ratio
        self.score_mode = score_mode
        self.min_size = 3

    def __call__(self, pred, shape_list):
        """pred: (N,1,H,W) 概率图；shape_list: [[H,W],...] 原图尺寸。"""
        if isinstance(pred, torch.Tensor):
            pred = pred.detach().cpu().numpy()
        pred = pred[:, 0, :, :]
        pred = pred.astype(np.float32)
        results = []
        for p, (orih, oriw) in zip(pred, shape_list, strict=True):
            boxes = self._boxes_from_bitmap(p, (int(orih), int(oriw)))
            results.append(boxes)
        return results

    def _boxes_from_bitmap(self, pred, dest_size):
        """单张概率图 → 文本框列表（每框 4×2 坐标，原图尺度）。"""
        dest_height, dest_width = dest_size
        height, width = pred.shape
        bitmap = cv2.copyMakeBorder(pred, 1, 1, 1, 1, cv2.BORDER_CONSTANT, value=0)
        bitmap = (bitmap > self.thresh).astype(np.uint8)
        contours, _ = cv2.findContours(bitmap, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
        num_contours = min(len(contours), self.max_candidates)

        boxes = []
        scores = []
        for index in range(num_contours):
            contour = contours[index]
            points, sside = self._get_mini_boxes(contour)
            if sside < self.min_size:
                continue
            points = np.array(points)
            if self.score_mode == "fast":
                score = self._box_score_fast(pred, points.reshape(-1, 2))
            else:
                score = self._box_score_slow(pred, contour)
            if self.box_thresh > score:
                continue

            box = self._unclip(points, self.unclip_ratio)
            if len(box) == 0:
                continue
            box, sside = self._get_mini_boxes(box)
            if sside < self.min_size + 2:
                continue
            box = np.array(box, dtype=np.float32)
            box[:, 0] = np.clip(np.round(box[:, 0] / width * dest_width), 0, dest_width)
            box[:, 1] = np.clip(np.round(box[:, 1] / height * dest_height), 0, dest_height)
            boxes.append(box)
            scores.append(score)

        if not boxes:
            return []
        boxes = np.array(boxes, dtype=np.float32)
        return boxes.tolist()

    def _get_mini_boxes(self, contour):
        """最小外接矩形 → 按 左上/右上/右下/左下 排序的 4 点 + 短边。"""
        bounding_box = cv2.minAreaRect(contour)
        points = sorted(cv2.boxPoints(bounding_box),
                        key=lambda x: (int(x[1]), int(x[0])))

        index_1, index_2, index_3, index_4 = 0, 1, 2, 3
        if points[1][1] > points[0][1]:
            index_1 = 0
            index_4 = 1
        else:
            index_1 = 1
            index_4 = 0
        if points[3][1] > points[2][1]:
            index_2 = 2
            index_3 = 3
        else:
            index_2 = 3
            index_3 = 2

        box = [points[index_1], points[index_2], points[index_3], points[index_4]]
        return box, min(bounding_box[1])

    def _box_score_fast(self, bitmap, _box):
        """fast 模式：四边形内像素的平均概率（PaddleOCR 同款）。"""
        height, width = bitmap.shape[:2]
        box = _box.copy()
        xmin = np.clip(np.floor(box[:, 0].min()).astype("int32"), 0, width - 1)
        xmax = np.clip(np.ceil(box[:, 0].max()).astype("int32"), 0, width - 1)
        ymin = np.clip(np.floor(box[:, 1].min()).astype("int32"), 0, height - 1)
        ymax = np.clip(np.ceil(box[:, 1].max()).astype("int32"), 0, height - 1)

        mask = np.zeros((ymax - ymin + 1, xmax - xmin + 1), dtype=np.uint8)
        box[:, 0] = box[:, 0] - xmin
        box[:, 1] = box[:, 1] - ymin
        cv2.fillPoly(mask, box.reshape(1, -1, 2).astype("int32"), 1)
        return cv2.mean(bitmap[ymin:ymax + 1, xmin:xmax + 1], mask)[0]

    def _box_score_slow(self, bitmap, contour):
        """slow 模式：整个连通域多边形内像素的平均概率。"""
        height, width = bitmap.shape[:2]
        contour = contour.copy()
        contour = np.reshape(contour, (-1, 2))
        xmin = np.clip(np.min(contour[:, 0]), 0, width - 1)
        xmax = np.clip(np.max(contour[:, 0]), 0, width - 1)
        ymin = np.clip(np.min(contour[:, 1]), 0, height - 1)
        ymax = np.clip(np.max(contour[:, 1]), 0, height - 1)

        mask = np.zeros((ymax - ymin + 1, xmax - xmin + 1), dtype=np.uint8)
        contour[:, 0] = contour[:, 0] - xmin
        contour[:, 1] = contour[:, 1] - ymin
        cv2.fillPoly(mask, contour.reshape(1, -1, 2).astype("int32"), 1)
        return cv2.mean(bitmap[ymin:ymax + 1, xmin:xmax + 1], mask)[0]

    def _unclip(self, box, unclip_ratio):
        """对四边形做真实多边形膨胀（pyclipper offset），与 PaddleOCR 一致。

        膨胀距离 = 面积 * unclip_ratio / 周长，使面积按 unclip_ratio 扩张。
        """
        poly_area = cv2.contourArea(box)
        poly_perimeter = cv2.arcLength(box, True)
        distance = poly_area * unclip_ratio / max(poly_perimeter, 1e-6)
        offset = pyclipper.PyclipperOffset()
        offset.AddPath(box.tolist(), pyclipper.JT_ROUND, pyclipper.ET_CLOSEDPOLYGON)
        expanded = np.array(offset.Execute(distance))
        return expanded
