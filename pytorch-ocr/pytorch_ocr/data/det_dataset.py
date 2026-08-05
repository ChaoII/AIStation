"""det 训练数据集：读取 det_gt.txt，返回模型输入与 GT。自研实现。"""
import json
import os
import random

import cv2
import numpy as np
import torch
from torch.utils.data import Dataset

from .augment import ColorJitter, CopyPaste, IaaAugment, RandomPerspective
from .transforms import MakeBorderMap, MakeShrinkMap

_MEAN = np.array([0.485, 0.456, 0.406], dtype=np.float32)
_STD = np.array([0.229, 0.224, 0.225], dtype=np.float32)


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
        use_iaa=True, use_color_jitter=True, use_perspective=False,
        copy_paste=False, ext_data_dir=None, augmenter_args=None,
    ):
        self.gt_dir = gt_dir
        self.image_shape = image_shape
        self.is_train = is_train
        self.use_aug = use_aug and is_train
        self.max_tries = max_tries
        self.shrink_map_fn = MakeShrinkMap(shrink_ratio)
        self.border_map_fn = MakeBorderMap(shrink_ratio)
        # 增强配置：对齐官方 PP-OCRv6 det 训练增强顺序
        self.use_iaa = use_iaa
        self.use_color_jitter = use_color_jitter
        self.use_perspective = use_perspective
        self.color_jitter = ColorJitter()
        self.iaa = IaaAugment(augmenter_args=augmenter_args)
        self.perspective = RandomPerspective()
        self.copy_paste_op = CopyPaste()
        self.ext_data_dir = ext_data_dir
        # copy_paste 需要外部数据集，缺失时优雅跳过
        self.copy_paste = bool(copy_paste and ext_data_dir)
        self.ext_items = self._load_ext(ext_data_dir) if self.copy_paste else []
        self._load_labels(label_path)

    def _load_ext(self, ext_data_dir):
        """懒加载外部数据集标注（与 det_gt.txt 同格式），供 CopyPaste 使用。"""
        label_path = os.path.join(ext_data_dir, "det_gt.txt")
        if not os.path.isfile(label_path):
            return []
        items = []
        with open(label_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                parts = line.split(None, 1)
                if len(parts) < 2:
                    continue
                polys, texts, tags = self._parse_label(parts[1])
                if not polys:
                    continue
                items.append((parts[0], polys, texts, tags))
        return items

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
                polys, texts, tags = self._parse_label(parts[1])
                if not polys:
                    continue
                self.items.append((img_name, polys, texts, tags))

    def _parse_label(self, s):
        """解析标注为 (polys, texts, ignore_tags)。

        兼容两种格式：
        - 纯四边形：``[[x1,y1],[x2,y2],[x3,y3],[x4,y4]]`` 或 ``[[[...],...],...]``
        - PaddleOCR 字典格式：``[{"transcription": ..., "points": [...], "ignore": 0}]``
        """
        try:
            data = json.loads(s)
        except json.JSONDecodeError:
            return [], [], []
        if not data:
            return [], [], []
        if isinstance(data[0], dict):
            polys, texts, tags = [], [], []
            for item in data:
                pts = np.array([[p[0], p[1]] for p in item["points"]], dtype=np.float32)
                polys.append(pts)
                texts.append(item.get("transcription", ""))
                tags.append(bool(item.get("ignore", 0)))
            return polys, texts, tags
        if isinstance(data[0][0], (int, float)):
            # 单四边形：[[x1,y1],[x2,y2],[x3,y3],[x4,y4]]
            data = [data]
        polys, texts, tags = [], [], []
        for quad in data:
            pts = np.array([[p[0], p[1]] for p in quad], dtype=np.float32)
            polys.append(pts)
            texts.append("")
            tags.append(False)
        return polys, texts, tags

    def __len__(self):
        return len(self.items)

    def _random_crop(self, data):
        """官方 RandomCrop：在原分辨率图上随机裁 640×640 区域，poly 平移。

        不强制等比缩放——文字保持原始大小（对齐官方训练分布）。裁剪区含至少
        一个有效文字框；图小于 640 时 pad。同步过滤 polys/texts/ignore_tags。
        """
        img = data["image"]
        polys = data["polys"]
        size_h, size_w = self.image_shape
        h, w = img.shape[:2]
        crop_x = crop_y = 0
        crop_w, crop_h = min(w, size_w), min(h, size_h)
        found = (w <= size_w and h <= size_h)
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
        img = img[crop_y:crop_y + crop_h, crop_x:crop_x + crop_w]
        polys = [p - np.array([crop_x, crop_y]) for p in polys]
        # padding 到 size_h×size_w
        pad_img = np.zeros((size_h, size_w, 3), dtype=np.uint8)
        pad_img[:crop_h, :crop_w] = img
        new_polys, new_tags, new_texts = [], [], []
        for p, tag, text in zip(polys, data["ignore_tags"], data["texts"], strict=False):
            if not _is_poly_outside_rect(p, 0, 0, size_w, size_h):
                new_polys.append(p)
                new_tags.append(tag)
                new_texts.append(text)
        data["image"] = pad_img
        data["polys"] = new_polys
        data["ignore_tags"] = new_tags
        data["texts"] = new_texts
        return data

    def __getitem__(self, idx):
        img_name, polys, texts, ignore_tags = self.items[idx]
        img = cv2.imread(f"{self.gt_dir}/{img_name}", cv2.IMREAD_COLOR)
        if img is None:
            return self[(idx + 1) % len(self.items)]
        img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        if self.use_aug:
            data = {
                "image": img,
                "polys": polys,
                "ignore_tags": ignore_tags,
                "texts": texts,
            }
            # 官方顺序：CopyPaste → ColorJitter → IaaAugment → RandomPerspective → RandomCrop
            if self.copy_paste and self.ext_items:
                ext_name, ext_polys, ext_texts, ext_tags = random.choice(self.ext_items)
                ext_img = cv2.imread(os.path.join(self.ext_data_dir, "images", ext_name),
                                     cv2.IMREAD_COLOR)
                if ext_img is not None:
                    ext_img = cv2.cvtColor(ext_img, cv2.COLOR_BGR2RGB)
                    ext_data = {
                        "image": ext_img,
                        "polys": ext_polys,
                        "texts": ext_texts,
                        "ignore_tags": ext_tags,
                    }
                    data = self.copy_paste_op(data, ext_data=ext_data)
            if self.use_color_jitter:
                data = self.color_jitter(data)
            if self.use_iaa:
                data = self.iaa(data)
            if self.use_perspective:
                data = self.perspective(data)
            data = self._random_crop(data)
            img = data["image"]
            polys = data["polys"]
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
