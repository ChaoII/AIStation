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
from PIL import Image


def _order_points(pts):
    """质心极角排序（顺时针）。"""
    center = pts.mean(axis=0)
    angles = np.arctan2(pts[:, 1] - center[1], pts[:, 0] - center[0])
    return pts[np.argsort(angles)]


def _rotate_bbox(img, text_polys, angle, scale=1):
    """官方 rotate_bbox：旋转图像与四边形（copy_paste.py）。"""
    w = img.shape[1]
    h = img.shape[0]
    rangle = np.deg2rad(angle)
    nw = abs(np.sin(rangle) * h) + abs(np.cos(rangle) * w)
    nh = abs(np.cos(rangle) * h) + abs(np.sin(rangle) * w)
    rot_mat = cv2.getRotationMatrix2D((nw * 0.5, nh * 0.5), angle, scale)
    rot_move = np.dot(rot_mat, np.array([(nw - w) * 0.5, (nh - h) * 0.5, 0]))
    rot_mat[0, 2] += rot_move[0]
    rot_mat[1, 2] += rot_move[1]
    rot_text_polys = []
    for bbox in text_polys:
        pts = []
        for i in range(len(bbox)):
            p = np.dot(rot_mat, np.array([bbox[i, 0], bbox[i, 1], 1]))
            pts.append(p)
        rot_text_polys.append(pts)
    return np.array(rot_text_polys, dtype=np.float32)
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
        # 对齐官方 PP-OCRv6 det config：Fliplr p0.5, Affine rotate[-45,45] fit_output,
        # Resize size[0.1,2]
        default = [
            {"type": "Fliplr", "args": {"p": 0.5}},
            {"type": "Affine", "args": {"p": 0.5, "rotate": [-45, 45], "fit_output": True}},
            {"type": "Resize", "args": {"size": [0.1, 2]}},
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
        # 官方对齐：随机旋转 0-360° + RGBA alpha 混合
        src_rgba = np.array(Image.fromarray(src_img).convert("RGBA"))
        for poly, text in candidates[:n_paste]:
            crop = get_rotate_crop_image(ext_image, poly)
            box_img_pil = Image.fromarray(crop).convert("RGBA")
            angle = np.random.randint(0, 360)
            box = np.array([[[0, 0], [crop.shape[1], 0],
                             [crop.shape[1], crop.shape[0]], [0, crop.shape[0]]]])
            rot_box = _rotate_bbox(crop, box, angle)[0]
            box_img_pil = box_img_pil.rotate(angle, expand=1)
            cw, ch = box_img_pil.width, box_img_pil.height
            if src_rgba.shape[1] - cw < 0 or src_rgba.shape[0] - ch < 0:
                continue
            place = self._find_place(src_rgba, src_polys, cw, ch)
            if place is None:
                continue
            x, y = place
            box_img_arr = np.array(box_img_pil)
            alpha = box_img_arr[:, :, 3:4].astype(np.float32) / 255.0
            region = src_rgba[y:y + ch, x:x + cw].astype(np.float32)
            blended = box_img_arr[:, :, :3].astype(np.float32) * alpha + region[:, :, :3] * (1 - alpha)
            src_rgba[y:y + ch, x:x + cw, :3] = blended.astype(np.uint8)
            src_rgba[y:y + ch, x:x + cw, 3] = 255
            box = rot_box + np.array([x, y])
            src_polys.append(box.astype(np.float32))
            src_texts.append(text)
            src_tags.append(False)

        src_img = np.array(Image.fromarray(src_rgba).convert("RGB"))
        data["image"] = src_img
        data["polys"] = src_polys
        data["texts"] = src_texts
        data["ignore_tags"] = src_tags
        return data


# ---------------------------------------------------------------------------
# 官方 PP-OCRv6 RandomCrop（configs/det/PP-OCRv6/*.yml 使用）
# ---------------------------------------------------------------------------
def _is_poly_in_rect(poly, x, y, w, h):
    poly = np.array(poly)
    if poly[:, 0].min() < x or poly[:, 0].max() > x + w:
        return False
    if poly[:, 1].min() < y or poly[:, 1].max() > y + h:
        return False
    return True


def _is_poly_outside_rect(poly, x, y, w, h):
    poly = np.array(poly)
    if poly[:, 0].max() < x or poly[:, 0].min() > x + w:
        return True
    if poly[:, 1].max() < y or poly[:, 1].min() > y + h:
        return True
    return False


def _get_min_rotated_rect_side(poly):
    poly = np.array(poly).astype(np.float32)
    if len(poly) < 3:
        return 0
    rect = cv2.minAreaRect(poly)
    width, height = rect[1]
    return min(width, height)


def _get_min_quad_side(quad):
    if len(quad) != 4:
        return 0
    quad = np.array(quad)
    sides = []
    for i in range(4):
        side = np.linalg.norm(quad[i] - quad[(i + 1) % 4])
        sides.append(side)
    return min(sides) if sides else 0


def _clip_poly_to_rect(poly, x, y, w, h):
    from shapely.geometry import Polygon, box as shapely_box

    try:
        poly_shape = Polygon(poly)
        crop_rect = shapely_box(x, y, x + w, y + h)
        clipped = poly_shape.intersection(crop_rect)
        if clipped.is_empty:
            return None
        if clipped.geom_type == "Polygon":
            coords = list(clipped.exterior.coords[:-1])
        elif clipped.geom_type == "MultiPolygon":
            largest = max(clipped.geoms, key=lambda p: p.area)
            coords = list(largest.exterior.coords[:-1])
        elif clipped.geom_type == "GeometryCollection":
            polygons = [g for g in clipped.geoms if g.geom_type == "Polygon"]
            if not polygons:
                return None
            largest = max(polygons, key=lambda p: p.area)
            coords = list(largest.exterior.coords[:-1])
        else:
            return None
        if len(coords) <= 3:
            return None
        coords = np.array(coords)
        if len(coords) == 4:
            return coords
        if len(coords) > 4:
            poly_cv = coords.reshape(-1, 1, 2).astype(np.float32)
            peri = cv2.arcLength(poly_cv, True)
            if peri < 1e-6:
                return None
            lo, hi = 0.0, 0.5
            best = None
            for _ in range(50):
                mid = (lo + hi) / 2
                approx = cv2.approxPolyDP(poly_cv, mid * peri, True)
                if len(approx) <= 4:
                    best = approx
                    hi = mid
                else:
                    lo = mid
            if best is not None and len(best) >= 3:
                return best.reshape(-1, 2)
            return None
        return coords
    except Exception:
        return None


class RandomCropV6:
    """官方 PP-OCRv6 det RandomCrop（random_crop_data.py RandomCrop）。

    crop 区域大小随机（min_ratio 到 size*3），须包含至少一个完整/可裁剪文字框，
    poly 按 char_height 校验；只缩小不放大（crop 区<=size 时 scale=1.0 + 随机 pad）。
    """

    def __init__(self, size=(640, 640), max_tries=50, min_crop_side_ratio=0.1,
                 keep_ratio=True):
        self.size = size
        self.max_tries = max_tries
        self.min_crop_side_ratio = min_crop_side_ratio
        self.keep_ratio = keep_ratio

    def __call__(self, data):
        img = data["image"]
        text_polys = data["polys"]
        ignore_tags = data["ignore_tags"]
        texts = data["texts"]
        care_indices = [i for i, tag in enumerate(ignore_tags) if not tag]
        all_care_polys = [text_polys[i] for i in care_indices]
        h, w = img.shape[:2]
        size_h, size_w = self.size

        if len(all_care_polys) == 0:
            crop_x, crop_y, crop_w, crop_h = 0, 0, w, h
            valid_care_data = []
        else:
            char_heights = np.array(
                [_get_min_rotated_rect_side(p) for p in all_care_polys])
            valid_care_data = []
            for _ in range(self.max_tries):
                crop_w_min = min(int(w * self.min_crop_side_ratio), size_w)
                crop_w_max = int(size_w * 3)
                crop_w = (w if crop_w_min >= crop_w_max
                          else min(random.randint(crop_w_min, crop_w_max), w))
                crop_h_min = min(int(h * self.min_crop_side_ratio), size_h)
                crop_h_max = int(size_h * 3)
                crop_h = (h if crop_h_min >= crop_h_max
                          else min(random.randint(crop_h_min, crop_h_max), h))
                crop_x = 0 if crop_w >= w else random.randint(0, w - crop_w)
                crop_y = 0 if crop_h >= h else random.randint(0, h - crop_h)
                valid_care_data = []
                for care_idx, (poly, char_height) in enumerate(
                        zip(all_care_polys, char_heights)):
                    if _is_poly_outside_rect(poly, crop_x, crop_y, crop_w, crop_h):
                        continue
                    if _is_poly_in_rect(poly, crop_x, crop_y, crop_w, crop_h):
                        valid_care_data.append((care_idx, None))
                        continue
                    clipped_poly = _clip_poly_to_rect(
                        poly, crop_x, crop_y, crop_w, crop_h)
                    if clipped_poly is None:
                        continue
                    clipped_area = cv2.contourArea(clipped_poly.astype(np.float32))
                    if clipped_area < 80:
                        continue
                    clipped_char_height = _get_min_rotated_rect_side(clipped_poly)
                    if clipped_char_height < char_height * 0.35:
                        continue
                    if len(clipped_poly) == 4:
                        min_side = _get_min_quad_side(clipped_poly)
                        if min_side < char_height * 0.35:
                            continue
                    valid_care_data.append((care_idx, clipped_poly))
                if len(valid_care_data) >= 1:
                    break
            else:
                crop_x, crop_y, crop_w, crop_h = 0, 0, w, h
                valid_care_data = [(i, None) for i in range(len(all_care_polys))]

        need_resize = crop_w > size_w or crop_h > size_h
        if need_resize:
            scale_w = size_w / crop_w
            scale_h = size_h / crop_h
            scale = min(scale_w, scale_h)
            h_resized = int(crop_h * scale)
            w_resized = int(crop_w * scale)
        else:
            scale = 1.0
            h_resized = crop_h
            w_resized = crop_w

        if self.keep_ratio:
            pad_h = size_h - h_resized
            pad_w = size_w - w_resized
            pad_top = random.randint(0, pad_h) if pad_h > 0 else 0
            pad_left = random.randint(0, pad_w) if pad_w > 0 else 0
            cropped_img = img[crop_y:crop_y + crop_h, crop_x:crop_x + crop_w]
            if need_resize:
                resized_img = cv2.resize(cropped_img, (w_resized, h_resized))
            else:
                resized_img = cropped_img
            padimg = np.zeros((size_h, size_w, img.shape[2]), img.dtype)
            padimg[pad_top:pad_top + h_resized, pad_left:pad_left + w_resized] = resized_img
            img = padimg
        else:
            img = cv2.resize(
                img[crop_y:crop_y + crop_h, crop_x:crop_x + crop_w],
                tuple(self.size))
            pad_left = 0
            pad_top = 0

        valid_care_indices_set = {care_idx for care_idx, _ in valid_care_data}
        care_idx_to_clipped = {
            care_idx: clipped for care_idx, clipped in valid_care_data}

        text_polys_crop = []
        ignore_tags_crop = []
        texts_crop = []
        for all_idx, (poly, text, tag) in enumerate(
                zip(text_polys, texts, ignore_tags)):
            if tag:
                if not _is_poly_outside_rect(poly, crop_x, crop_y, crop_w, crop_h):
                    adjusted_poly = (poly - (crop_x, crop_y)) * scale + (pad_left, pad_top)
                    adjusted_poly[:, 0] = np.clip(adjusted_poly[:, 0], 0, size_w)
                    adjusted_poly[:, 1] = np.clip(adjusted_poly[:, 1], 0, size_h)
                    text_polys_crop.append(adjusted_poly.tolist())
                    ignore_tags_crop.append(tag)
                    texts_crop.append(text)
            else:
                try:
                    care_idx = care_indices.index(all_idx)
                except ValueError:
                    continue
                if care_idx not in valid_care_indices_set:
                    continue
                clipped_poly = care_idx_to_clipped[care_idx]
                if clipped_poly is None:
                    adjusted_poly = (poly - (crop_x, crop_y)) * scale + (pad_left, pad_top)
                else:
                    adjusted_poly = (clipped_poly - (crop_x, crop_y)) * scale + (pad_left, pad_top)
                text_polys_crop.append(adjusted_poly.tolist())
                ignore_tags_crop.append(tag)
                texts_crop.append(text)

        data["image"] = img
        if text_polys_crop:
            data["polys"] = [np.array(p, dtype=np.float32) for p in text_polys_crop]
        else:
            data["polys"] = []
        data["ignore_tags"] = ignore_tags_crop
        data["texts"] = texts_crop
        return data
