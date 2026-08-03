"""det 训练数据集：读取 det_gt.txt，返回模型输入与 GT。自研实现。"""
import json

import cv2
import numpy as np
import torch
from torch.utils.data import Dataset

from .transforms import MakeBorderMap, MakeShrinkMap

_MEAN = np.array([0.485, 0.456, 0.406], dtype=np.float32)
_STD = np.array([0.229, 0.224, 0.225], dtype=np.float32)


class DetDataset(Dataset):
    def __init__(
        self, gt_dir, label_path, image_shape=(640, 640), is_train=True, shrink_ratio=0.4
    ):
        self.gt_dir = gt_dir
        self.image_shape = image_shape
        self.is_train = is_train
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

    def __getitem__(self, idx):
        img_name, polys = self.items[idx]
        img = cv2.imread(f"{self.gt_dir}/{img_name}", cv2.IMREAD_COLOR)
        if img is None:
            return self[(idx + 1) % len(self.items)]
        img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        # 归一化多边形到 [0,1]
        h, w = img.shape[:2]
        norm_polys = [p / np.array([w, h]) for p in polys]
        shrink_map, shrink_mask = self.shrink_map_fn(img, norm_polys)
        thresh_map, thresh_mask = self.border_map_fn(img, norm_polys)
        # resize 到 image_shape（训练简化：直接 resize，不做随机裁剪）
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
