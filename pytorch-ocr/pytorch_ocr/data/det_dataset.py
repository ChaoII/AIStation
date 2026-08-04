"""det 训练数据集：读取 det_gt.txt，返回模型输入与 GT。自研实现。"""
import json
import random

import cv2
import numpy as np
import torch
from torch.utils.data import Dataset

from .transforms import MakeBorderMap, MakeShrinkMap

_MEAN = np.array([0.485, 0.456, 0.406], dtype=np.float32)
_STD = np.array([0.229, 0.224, 0.225], dtype=np.float32)


def _color_jitter(img, brightness=0.4, contrast=0.4, saturation=0.7, hue=0.1):
    """对齐官方 ColorJitter：HSV 空间扰动，保持文字与背景对比。"""
    import colorsys

    h, w, _ = img.shape
    img = img.astype(np.float32)

    # 亮度/对比度（HSV 的 V 通道）
    if random.random() < 0.5:
        img_hsv = cv2.cvtColor(img.astype(np.uint8), cv2.COLOR_RGB2HSV)
        gain = 1.0 + random.uniform(-brightness, brightness)
        img_hsv[:, :, 2] = np.clip(img_hsv[:, :, 2] * gain, 0, 255)
        img = cv2.cvtColor(img_hsv, cv2.COLOR_HSV2RGB).astype(np.float32)
    if random.random() < 0.5:
        gain = 1.0 + random.uniform(-contrast, contrast)
        mean_v = img.mean(axis=(0, 1), keepdims=True)
        img = (img - mean_v) * gain + mean_v
    if random.random() < 0.5:
        img_hsv = cv2.cvtColor(np.clip(img, 0, 255).astype(np.uint8), cv2.COLOR_RGB2HSV)
        sat = 1.0 + random.uniform(-saturation, saturation)
        img_hsv[:, :, 1] = np.clip(img_hsv[:, :, 1] * sat, 0, 255)
        img = cv2.cvtColor(img_hsv, cv2.COLOR_HSV2RGB).astype(np.float32)
    return np.clip(img, 0, 255).astype(np.uint8)


def _is_poly_in_rect(poly, x, y, w, h):
    return bool((poly[:, 0].min() >= x and poly[:, 0].max() <= x + w
                 and poly[:, 1].min() >= y and poly[:, 1].max() <= y + h))


def _is_poly_outside_rect(poly, x, y, w, h):
    return bool(poly[:, 0].max() < x or poly[:, 0].min() > x + w
                or poly[:, 1].max() < y or poly[:, 1].min() > y + h)


class DetDataset(Dataset):
    def __init__(
        self, gt_dir, label_path, image_shape=(640, 640), is_train=True, shrink_ratio=0.4,
        use_aug=True, max_tries=20,
    ):
        self.gt_dir = gt_dir
        self.image_shape = image_shape
        self.is_train = is_train
        self.use_aug = use_aug and is_train
        self.max_tries = max_tries
        self.shrink_map_fn = MakeShrinkMap(shrink_ratio)
        self.border_map_fn = MakeBorderMap(shrink_ratio)
        self._load_labels(label_path)

    def _load_labels(self, label_path):
        self.items = []
        with open(label_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                # 兼容 tab（计划格式）与空格分隔
                parts = line.split(None, 1)
                if len(parts) < 2:
                    continue
                img_name = parts[0]
                # 解析四边形：[[[x1,y1],...], ...] 或单四边形 [[x1,y1],...]
                polys = self._parse_polys(parts[1])
                if not polys:
                    continue
                self.items.append((img_name, polys))

    def _parse_polys(self, s):
        try:
            data = json.loads(s)
        except json.JSONDecodeError:
            return []
        if data and isinstance(data[0][0], (int, float)):
            # 单四边形：[[x1,y1],[x2,y2],[x3,y3],[x4,y4]]
            data = [data]
        polys = []
        for quad in data:
            pts = np.array([[p[0], p[1]] for p in quad], dtype=np.float32)
            polys.append(pts)
        return polys

    def __len__(self):
        return len(self.items)

    def _random_crop(self, img, polys):
        """官方 RandomCrop 简化版：等比缩放（最长边 ≤640）+ 随机裁剪 640×640 + padding。

        在缩放后的图上随机裁 640×640，尽量包含至少一个文字框；裁剪不足时 padding。
        返回 (img, polys) 均已在 640×640 输入坐标系。
        """
        size_h, size_w = self.image_shape
        h, w = img.shape[:2]
        # 等比缩放：最长边到 size，保持比例
        max_side = max(h, w)
        scale = size_w / max_side if max_side > size_w else 1.0
        if scale < 1.0:
            new_h, new_w = max(1, int(h * scale)), max(1, int(w * scale))
            img = cv2.resize(img, (new_w, new_h))
            polys = [p * scale for p in polys]
            h, w = new_h, new_w

        # 尝试随机裁剪，包含至少一个有效文字框
        crop_x = crop_y = 0
        crop_w, crop_h = min(w, size_w), min(h, size_h)
        found = False
        if w <= size_w and h <= size_h:
            found = True  # 图比 target 小，无需裁剪
        for _ in range(self.max_tries):
            if w > size_w:
                crop_x = random.randint(0, w - size_w)
                crop_w = size_w
            if h > size_h:
                crop_y = random.randint(0, h - size_h)
                crop_h = size_h
            for poly in polys:
                if _is_poly_in_rect(poly, crop_x, crop_y, crop_w, crop_h):
                    found = True
                    break
            if found:
                break
        # 裁剪
        img = img[crop_y:crop_y + crop_h, crop_x:crop_x + crop_w]
        polys = [p - np.array([crop_x, crop_y]) for p in polys]
        # padding 到 640×640（等比）
        pad_img = np.zeros((size_h, size_w, 3), dtype=np.uint8)
        pad_img[:crop_h, :crop_w] = img
        polys = [p for p in polys
                 if not _is_poly_outside_rect(p, 0, 0, size_w, size_h)]
        return pad_img, polys

    def __getitem__(self, idx):
        img_name, polys = self.items[idx]
        img = cv2.imread(f"{self.gt_dir}/{img_name}", cv2.IMREAD_COLOR)
        if img is None:
            return self[(idx + 1) % len(self.items)]
        img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        if self.use_aug:
            img = _color_jitter(img)
            img, polys = self._random_crop(img, polys)
        h, w = img.shape[:2]
        # 归一化多边形到 [0,1]
        norm_polys = [p / np.array([w, h]) for p in polys if len(p) >= 3]
        shrink_map, shrink_mask = self.shrink_map_fn(img, norm_polys)
        thresh_map, thresh_mask = self.border_map_fn(img, norm_polys)
        # 无增强时直接 resize 到 image_shape；有增强时已经 640×640
        if tuple(img.shape[:2]) != tuple(self.image_shape):
            img = cv2.resize(img, self.image_shape)
            shrink_map = cv2.resize(shrink_map, self.image_shape)
            thresh_map = cv2.resize(thresh_map, self.image_shape)
            shrink_mask = cv2.resize(shrink_mask, self.image_shape).astype(np.uint8)
            thresh_mask = cv2.resize(thresh_mask, self.image_shape).astype(np.uint8)
        # normalize + CHW
        img = (img.astype(np.float32) / 255.0 - _MEAN) / _STD
        img = torch.from_numpy(img).permute(2, 0, 1).float()
        shrink_map = torch.from_numpy(shrink_map).unsqueeze(0).float()
        shrink_mask = torch.from_numpy(shrink_mask).unsqueeze(0).float()
        thresh_map = torch.from_numpy(thresh_map).unsqueeze(0).float()
        thresh_mask = torch.from_numpy(thresh_mask).unsqueeze(0).float()
        return img, shrink_map, shrink_mask, thresh_map, thresh_mask
