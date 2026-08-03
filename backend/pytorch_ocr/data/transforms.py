"""det 数据增强：MakeShrinkMap / MakeBorderMap（对齐 PaddleOCR，自研实现）。"""
import cv2
import numpy as np
import pyclipper


def _shrink_poly(poly, ratio):
    """按比例收缩多边形（pyclipper 负偏移）。"""
    area = cv2.contourArea(poly)
    perimeter = cv2.arcLength(poly, True)
    distance = area * (1 - ratio) / perimeter if perimeter > 0 else 0
    pco = pyclipper.PyclipperOffset()
    pco.AddPath(poly, pyclipper.JT_ROUND, pyclipper.ET_CLOSEDPOLYGON)
    offset = pco.Execute(-distance)
    if not offset:
        return None
    return np.array(offset[0], dtype=np.float32)


def _expand_poly(poly, ratio):
    """按比例扩张多边形（pyclipper 正偏移）。"""
    area = cv2.contourArea(poly)
    perimeter = cv2.arcLength(poly, True)
    distance = area * (1 - ratio * ratio) / perimeter if perimeter > 0 else 0
    pco = pyclipper.PyclipperOffset()
    pco.AddPath(poly, pyclipper.JT_ROUND, pyclipper.ET_CLOSEDPOLYGON)
    offset = pco.Execute(distance)
    if not offset:
        return None
    return np.array(offset[0], dtype=np.float32)


class MakeShrinkMap:
    """生成 shrink_map（文字区域收缩后的二值图）与 shrink_mask。"""

    def __init__(self, shrink_ratio=0.4, min_text_size=8):
        self.shrink_ratio = shrink_ratio
        self.min_text_size = min_text_size

    def __call__(self, img, polys):
        h, w = img.shape[:2]
        shrink_map = np.zeros((h, w), dtype=np.float32)
        mask = np.zeros((h, w), dtype=np.uint8)
        for poly in polys:
            pts = (poly * np.array([w, h])).astype(np.int32)
            height = pts[:, 1].max() - pts[:, 1].min()
            width = pts[:, 0].max() - pts[:, 0].min()
            if min(height, width) < self.min_text_size:
                continue
            shrunk = _shrink_poly(pts, self.shrink_ratio)
            if shrunk is None or cv2.contourArea(shrunk) < 1:
                continue
            cv2.fillPoly(shrink_map, [shrunk.astype(np.int32)], 1.0)
            cv2.fillPoly(mask, [pts], 1)
        return shrink_map, mask


class MakeBorderMap:
    """生成 threshold_map（文字边界渐变）与 threshold_mask。

    对齐 PaddleOCR 的 make_border_map：用 pyclipper 向外扩张多边形，对扩张带内
    每个像素计算到原始多边形各边的最短距离，距离 0（原始边界）→1（扩张外边界
    或更深内部），再线性缩放到 [thresh_min, thresh_max]。
    """

    def __init__(self, shrink_ratio=0.4, thresh_min=0.3, thresh_max=0.7):
        self.shrink_ratio = shrink_ratio
        self.thresh_min = thresh_min
        self.thresh_max = thresh_max

    def __call__(self, img, polys):
        h, w = img.shape[:2]
        canvas = np.zeros((h, w), dtype=np.float32)
        mask = np.zeros((h, w), dtype=np.float32)
        for poly in polys:
            polygon = (poly * np.array([w, h])).astype(np.float32)
            self._draw_border_map(polygon, canvas, mask)
        canvas = canvas * (self.thresh_max - self.thresh_min) + self.thresh_min
        return canvas, mask

    def _draw_border_map(self, polygon, canvas, mask):
        if np.isnan(polygon).any():
            return
        area = cv2.contourArea(polygon)
        if area <= 0:
            return
        perimeter = cv2.arcLength(polygon, True)
        if perimeter <= 0:
            return
        distance = area * (1 - np.power(self.shrink_ratio, 2)) / perimeter
        pco = pyclipper.PyclipperOffset()
        pco.AddPath(polygon, pyclipper.JT_ROUND, pyclipper.ET_CLOSEDPOLYGON)
        padded_polygon = pco.Execute(distance)
        if not padded_polygon:
            return
        padded_polygon = np.round(np.array(padded_polygon[0])).astype(np.int32)

        xmin = padded_polygon[:, 0].min()
        xmax = padded_polygon[:, 0].max()
        ymin = padded_polygon[:, 1].min()
        ymax = padded_polygon[:, 1].max()
        if xmax < 0 or xmin >= canvas.shape[1] or ymax < 0 or ymin >= canvas.shape[0]:
            return

        cv2.fillPoly(mask, [padded_polygon], 1.0)

        width = int(xmax - xmin + 1)
        height = int(ymax - ymin + 1)

        poly_shift = polygon.astype(np.float32).copy()
        poly_shift[:, 0] -= xmin
        poly_shift[:, 1] -= ymin

        xs = np.broadcast_to(
            np.linspace(0, width - 1, num=width).reshape(1, width), (height, width)
        )
        ys = np.broadcast_to(
            np.linspace(0, height - 1, num=height).reshape(height, 1), (height, width)
        )

        distance_map = np.zeros((polygon.shape[0], height, width), dtype=np.float32)
        for i in range(polygon.shape[0]):
            j = (i + 1) % polygon.shape[0]
            with np.errstate(divide="ignore", invalid="ignore"):
                absolute_distance = self._distance(xs, ys, poly_shift[i], poly_shift[j])
            distance_map[i] = np.clip(absolute_distance / distance, 0, 1)
        distance_map = distance_map.min(axis=0)

        xmin_valid = min(max(0, xmin), canvas.shape[1] - 1)
        xmax_valid = min(max(0, xmax), canvas.shape[1] - 1)
        ymin_valid = min(max(0, ymin), canvas.shape[0] - 1)
        ymax_valid = min(max(0, ymax), canvas.shape[0] - 1)
        canvas[ymin_valid : ymax_valid + 1, xmin_valid : xmax_valid + 1] = np.fmax(
            1
            - distance_map[
                ymin_valid - ymin : ymax_valid - ymax + height,
                xmin_valid - xmin : xmax_valid - xmax + width,
            ],
            canvas[ymin_valid : ymax_valid + 1, xmin_valid : xmax_valid + 1],
        )

    @staticmethod
    def _distance(xs, ys, point_1, point_2):
        """计算点到线段的最短距离（向量化）。"""
        square_distance_1 = np.square(xs - point_1[0]) + np.square(ys - point_1[1])
        square_distance_2 = np.square(xs - point_2[0]) + np.square(ys - point_2[1])
        square_distance = np.square(point_1[0] - point_2[0]) + np.square(
            point_1[1] - point_2[1]
        )
        cosin = (square_distance - square_distance_1 - square_distance_2) / (
            2 * np.sqrt(square_distance_1 * square_distance_2)
        )
        square_sin = 1 - np.square(cosin)
        square_sin = np.nan_to_num(square_sin)
        result = np.sqrt(
            square_distance_1 * square_distance_2 * square_sin / square_distance
        )
        result[cosin < 0] = np.sqrt(np.fmin(square_distance_1, square_distance_2))[
            cosin < 0
        ]
        return result
