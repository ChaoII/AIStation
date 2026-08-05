"""det 数据增强：对齐官方 PP-OCRv6 det 训练增强管线（自研实现）。

所有增强类在数据 dict 上操作：``{"image", "polys", "ignore_tags", "texts"}``。
``image`` 为 RGB ndarray，``polys`` 为 ``list[np.ndarray (P, 2)]``，
``ignore_tags``/``texts`` 为与 polys 一一对应的 list。
顺序：CopyPaste → ColorJitter → IaaAugment → RandomPerspective → RandomCrop。
"""
import random

import albumentations as A
import cv2
import numpy as np
from albumentations.core.transforms_interface import DualTransform


def _order_points(pts):
    """按 左上/右上/右下/左下 排序四个顶点。"""
    s = pts.sum(axis=1)
    d = np.diff(pts, axis=1).ravel()
    tl = pts[np.argmin(s)]
    br = pts[np.argmax(s)]
    tr = pts[np.argmin(d)]
    bl = pts[np.argmax(d)]
    return tl, tr, br, bl


def get_rotate_crop_image(img, points):
    """将四边形文字区域透视矫正为矩形裁剪。

    ``points``: 4×2 顶点（任意顺序），返回裁剪后的矩形图像。
    """
    pts = np.asarray(points, dtype=np.float32).reshape(-1, 2)
    tl, tr, br, bl = _order_points(pts)
    w_top = np.linalg.norm(tr - tl)
    w_bottom = np.linalg.norm(br - bl)
    h_left = np.linalg.norm(tl - bl)
    h_right = np.linalg.norm(tr - br)
    dst_w = max(int(round(max(w_top, w_bottom))), 1)
    dst_h = max(int(round(max(h_left, h_right))), 1)
    dst = np.array(
        [[0, 0], [dst_w - 1, 0], [dst_w - 1, dst_h - 1], [0, dst_h - 1]],
        dtype=np.float32,
    )
    src = np.array([tl, tr, br, bl], dtype=np.float32)
    matrix = cv2.getPerspectiveTransform(src, dst)
    return cv2.warpPerspective(img, matrix, (dst_w, dst_h))


def _flatten_keypoints(polys):
    """poly 列表 → 展平 keypoints + 各 poly 长度。"""
    lengths = [len(p) for p in polys]
    keypoints = []
    for p in polys:
        keypoints.extend(np.asarray(p).reshape(-1, 2).tolist())
    return keypoints, lengths


class ColorJitter:
    """ColorJitter（brightness 0.4 / contrast 0.4 / saturation 0.7 / hue 0.1）。

    与官方 PaddleOCR 一致：HSV 空间扰动，保持文字与背景对比。
    """

    def __init__(self, brightness=0.4, contrast=0.4, saturation=0.7, hue=0.1):
        self.brightness = brightness
        self.contrast = contrast
        self.saturation = saturation
        self.hue = hue

    def _apply_brightness(self, img):
        gain = 1.0 + random.uniform(-self.brightness, self.brightness)
        return np.clip(img.astype(np.float32) * gain, 0, 255).astype(np.uint8)

    def _apply_contrast(self, img):
        gain = 1.0 + random.uniform(-self.contrast, self.contrast)
        mean = img.mean(axis=(0, 1), keepdims=True)
        return np.clip((img.astype(np.float32) - mean) * gain + mean, 0, 255).astype(np.uint8)

    def _apply_saturation(self, img):
        sat = 1.0 + random.uniform(-self.saturation, self.saturation)
        img_hsv = cv2.cvtColor(img, cv2.COLOR_RGB2HSV)
        img_hsv[:, :, 1] = np.clip(img_hsv[:, :, 1].astype(np.float32) * sat, 0, 255)
        return cv2.cvtColor(img_hsv.astype(np.uint8), cv2.COLOR_HSV2RGB)

    def _apply_hue(self, img):
        delta = random.uniform(-self.hue, self.hue)
        img_hsv = cv2.cvtColor(img, cv2.COLOR_RGB2HSV)
        img_hsv[:, :, 0] = (img_hsv[:, :, 0].astype(np.float32) + delta * 180 / np.pi) % 180
        return cv2.cvtColor(img_hsv.astype(np.uint8), cv2.COLOR_HSV2RGB)

    def __call__(self, data):
        img = data["image"]
        if random.random() < 0.5:
            img = self._apply_brightness(img)
        if random.random() < 0.5:
            img = self._apply_contrast(img)
        if random.random() < 0.5:
            img = self._apply_saturation(img)
        if random.random() < 0.5:
            img = self._apply_hue(img)
        data["image"] = img
        return data


class ImgaugLikeResize(DualTransform):
    """imgaug 风格 Resize：以随机比例缩放图像与 keypoints。"""

    def __init__(self, scale_range=(0.5, 3.0), interpolation=cv2.INTER_LINEAR, p=1.0):
        super().__init__(p=p)
        self.scale_range = scale_range
        self.interpolation = interpolation

    def get_params(self):
        return {"scale": float(np.random.uniform(self.scale_range[0], self.scale_range[1]))}

    def apply(self, img, scale=1.0, **params):
        return cv2.resize(img, None, fx=scale, fy=scale, interpolation=self.interpolation)

    def apply_to_keypoints(self, keypoints, scale=1.0, **params):
        kps = np.asarray(keypoints, dtype=np.float32).copy()
        kps[:, 0] *= scale
        kps[:, 1] *= scale
        return kps


class AugmenterBuilder:
    """官方 IaaAugment 的 albumentations 版构建器。"""

    def __init__(self):
        self.imgaug_to_albu = {
            "Fliplr": "HorizontalFlip",
            "Flipud": "VerticalFlip",
            "Affine": "Affine",
        }

    def build(self, args, root=True):
        if args is None or len(args) == 0:
            return None
        if isinstance(args, list):
            if root:
                sequence = [self.build(value, root=False) for value in args]
                return A.Compose(
                    sequence,
                    keypoint_params=A.KeypointParams(format="xy", remove_invisible=False),
                )
            augmenter_type = args[0]
            augmenter_args = args[1] if len(args) > 1 else {}
            return self._build_single(augmenter_type, augmenter_args)
        if isinstance(args, dict):
            return self._build_single(args["type"], args.get("args", {}))
        return None

    def _build_single(self, augmenter_type, augmenter_args):
        augmenter_args = self.map_arguments(augmenter_type, augmenter_args)
        augmenter_type_mapped = self.imgaug_to_albu.get(augmenter_type, augmenter_type)
        if augmenter_type_mapped == "Resize":
            return ImgaugLikeResize(**augmenter_args)
        cls = getattr(A, augmenter_type_mapped)
        return cls(**{k: self.to_tuple_if_list(v) for k, v in augmenter_args.items()})

    def map_arguments(self, augmenter_type, augmenter_args):
        augmenter_args = dict(augmenter_args)
        if augmenter_type == "Resize":
            size = augmenter_args.get("size", [0.5, 3.0])
            return {
                "scale_range": (float(size[0]), float(size[1])),
                "interpolation": augmenter_args.get("interpolation", cv2.INTER_LINEAR),
                "p": augmenter_args.get("p", 1.0),
            }
        if augmenter_type == "Affine":
            args = dict(augmenter_args)
            rotate = args.get("rotate", 0)
            if isinstance(rotate, list):
                args["rotate"] = (float(rotate[0]), float(rotate[1]))
            args.setdefault("p", 0.5)
            return args
        return augmenter_args

    def to_tuple_if_list(self, obj):
        return tuple(obj) if isinstance(obj, list) else obj


class IaaAugment:
    """IaaAugment（Fliplr / Affine / Resize）：keypoints 方式变换 polys。"""

    def __init__(self, augmenter_args=None):
        default = [
            {"type": "Fliplr", "args": {"p": 0.5}},
            {"type": "Affine", "args": {"rotate": [-10, 10]}},
            {"type": "Resize", "args": {"size": [0.5, 3]}},
        ]
        self.augmenter_args = augmenter_args if augmenter_args else default
        self.augmenter = AugmenterBuilder().build(self.augmenter_args)

    def __call__(self, data):
        image = data["image"]
        polys = data["polys"]
        if self.augmenter is None:
            return data
        keypoints, lengths = _flatten_keypoints(polys)
        result = self.augmenter(image=image, keypoints=keypoints)
        image = result["image"]
        new_keypoints = result["keypoints"]
        h, w = image.shape[:2]
        new_polys = []
        new_tags = []
        new_texts = []
        idx = 0
        for length, tag, text in zip(lengths, data["ignore_tags"], data["texts"], strict=False):
            pts = np.array(new_keypoints[idx:idx + length], dtype=np.float32).reshape(length, 2)
            idx += length
            x0, y0, x1, y1 = pts[:, 0].min(), pts[:, 1].min(), pts[:, 0].max(), pts[:, 1].max()
            if x1 - x0 < 1 or y1 - y0 < 1:
                continue
            if x1 < 0 or y1 < 0 or x0 > w or y0 > h:
                continue
            new_polys.append(pts)
            new_tags.append(tag)
            new_texts.append(text)
        data["image"] = image
        data["polys"] = new_polys
        data["ignore_tags"] = new_tags
        data["texts"] = new_texts
        return data


class RandomPerspective:
    """RandomPerspective（prob 0.3 / shear 20 / perspective 0.001 / fit_output）。

    cv2 实现：随机扰动四个角点计算单应矩阵，warp 图像并同步变换 polys。
    """

    def __init__(self, prob=0.3, shear=20, perspective=0.001, fit_output=True, fill=0):
        self.prob = prob
        self.shear = shear
        self.perspective = perspective
        self.fit_output = fit_output
        self.fill = fill

    def _random_matrix(self, h, w):
        corners = np.array([[0, 0], [w, 0], [w, h], [0, h]], dtype=np.float32)
        shear_rad = np.deg2rad(self.shear)
        shear_offset = random.uniform(-shear_rad, shear_rad) * h
        disp = np.random.uniform(-1, 1, (4, 2)) * self.perspective * np.array([w, h])
        dst = corners.copy()
        dst[0, 0] += shear_offset / 2
        dst[1, 0] += shear_offset / 2
        dst[2, 0] -= shear_offset / 2
        dst[3, 0] -= shear_offset / 2
        dst += disp
        return cv2.getPerspectiveTransform(corners, dst)

    def __call__(self, data):
        if random.random() >= self.prob:
            return data
        img = data["image"]
        polys = data["polys"]
        h, w = img.shape[:2]
        matrix = self._random_matrix(h, w)
        if self.fit_output:
            corners = np.array([[0, 0], [w, 0], [w, h], [0, h]], dtype=np.float32)
            pts = cv2.perspectiveTransform(corners.reshape(1, 4, 2), matrix).reshape(4, 2)
            x0, y0 = float(pts[:, 0].min()), float(pts[:, 1].min())
            x1, y1 = float(pts[:, 0].max()), float(pts[:, 1].max())
            new_w = max(int(round(x1 - x0)), 1)
            new_h = max(int(round(y1 - y0)), 1)
            translate = np.array([[1, 0, -x0], [0, 1, -y0], [0, 0, 1]], dtype=np.float32)
            matrix = translate @ matrix
        else:
            new_w, new_h = w, h
        warped = cv2.warpPerspective(
            img, matrix, (new_w, new_h), flags=cv2.INTER_LINEAR,
            borderMode=cv2.BORDER_CONSTANT, borderValue=self.fill,
        )
        new_polys = []
        for poly in polys:
            kps = np.asarray(poly, dtype=np.float32).reshape(1, -1, 2)
            out = cv2.perspectiveTransform(kps, matrix).reshape(-1, 2)
            new_polys.append(out)
        data["image"] = warped
        data["polys"] = new_polys
        return data


class CopyPaste:
    """CopyPaste：从外部图像粘贴文字区域，补充训练样本多样性。

    接受 ``ext_image``/``ext_polys``/``ext_texts`` 或一个 dict
    ``{"image", "polys", "texts", "ignore_tags"}``。粘贴至多
    ``objects_paste_ratio * len(ext_polys)`` 个非 ignore 区域。
    """

    def __init__(self, objects_paste_ratio=0.2, max_tries=50):
        self.objects_paste_ratio = objects_paste_ratio
        self.max_tries = max_tries

    def _find_place(self, img, polys, cw, ch):
        h, w = img.shape[:2]
        if cw > w or ch > h:
            return None
        boxes = []
        for p in polys:
            pts = np.asarray(p).reshape(-1, 2)
            boxes.append((pts[:, 0].min(), pts[:, 1].min(), pts[:, 0].max(), pts[:, 1].max()))

        def overlap(x, y):
            for bx0, by0, bx1, by1 in boxes:
                if not (x + cw <= bx0 or x >= bx1 or y + ch <= by0 or y >= by1):
                    return True
            return False

        for _ in range(self.max_tries):
            x = random.randint(0, max(w - cw, 0))
            y = random.randint(0, max(h - ch, 0))
            if not overlap(x, y):
                return (x, y)
        step = max(cw, ch, 8)
        for y in range(0, h - ch + 1, step):
            for x in range(0, w - cw + 1, step):
                if not overlap(x, y):
                    return (x, y)
        return None

    def __call__(self, data, ext_image=None, ext_polys=None, ext_texts=None, ext_data=None):
        if ext_data is not None:
            ext_image = ext_data["image"]
            ext_polys = ext_data["polys"]
            ext_texts = ext_data.get("texts")
        if ext_image is None or ext_polys is None or len(ext_polys) == 0:
            return data
        if ext_texts is None:
            ext_texts = [""] * len(ext_polys)
        ext_tags = (ext_data or {}).get("ignore_tags", [False] * len(ext_polys))

        src_img = data["image"]
        src_polys = list(data["polys"])
        src_texts = list(data["texts"])
        src_tags = list(data["ignore_tags"])

        candidates = [
            (p, t) for p, t, g in zip(ext_polys, ext_texts, ext_tags, strict=False) if not g
        ]
        if not candidates:
            return data
        n_paste = max(1, int(self.objects_paste_ratio * len(candidates)))
        random.shuffle(candidates)
        for poly, text in candidates[:n_paste]:
            crop = get_rotate_crop_image(ext_image, poly)
            ch, cw = crop.shape[:2]
            place = self._find_place(src_img, src_polys, cw, ch)
            if place is None:
                continue
            x, y = place
            src_img[y:y + ch, x:x + cw] = crop
            box = np.array(
                [[x, y], [x + cw, y], [x + cw, y + ch], [x, y + ch]], dtype=np.float32
            )
            src_polys.append(box)
            src_texts.append(text)
            src_tags.append(False)

        data["image"] = src_img
        data["polys"] = src_polys
        data["texts"] = src_texts
        data["ignore_tags"] = src_tags
        return data
