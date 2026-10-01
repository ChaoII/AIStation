"""Layer 0 · 共享基础设施：布局常量、标注批量查询、几何换算、文件写入

由原 ``exporter.py`` 拆分而来（原文件 2291 行，混合了数据集导出、模型权重入库、
DB 访问与 S3 操作四类职责）。拆分依据是模块内定义的**依赖 DAG**——先验证过
无强连通分量，故按拓扑序切分不会产生循环导入。

函数体**逐字节原样搬运**，未做任何编辑；拆分后用 ast.dump 逐个比对确认一致。
"""

import json
import math
import os

from sqlalchemy import desc, select

from app.api.v1.module_annotation.annotation.model import (
    AnnotationRecordModel,
)
from app.core.logger import log

YOLO_LAYOUT = "ultralytics"


async def _load_latest_anns_by_image(db, image_ids: list[int], annotation_task_id: int | None) -> dict[int, list]:
    """一次性查出所有图片的最新版本标注，返回 ``image_id -> annotation_data`` 映射。

    原实现逐图 ``select(...).where(image_id == img.id).order_by(version desc).limit(1)``
    造成逐图 N+1 查询；此处改为 ``image_id IN (...)`` 一次查出全部记录后按版本降序
    排序，每图仅取第一条（即最新版本），把 N 次查询收敛为 1 次。
    """
    if not image_ids:
        return {}
    query = select(AnnotationRecordModel).where(AnnotationRecordModel.image_id.in_(image_ids))
    if annotation_task_id:
        query = query.where(AnnotationRecordModel.task_id == annotation_task_id)
    query = query.order_by(AnnotationRecordModel.image_id, desc(AnnotationRecordModel.version))
    rows = (await db.execute(query)).scalars().all()
    anns_by_img: dict[int, list] = {}
    for rec in rows:
        if rec.image_id in anns_by_img:
            # 已取到该图最新版本（按 version desc 排最前），跳过旧版本
            continue
        anns_by_img[rec.image_id] = rec.annotation_data if rec.annotation_data else []
    return anns_by_img


def _write_lines(path: str, lines: list[str]) -> None:
    """写清单文件；**空集直接跳过不写**。

    TorchKiln 侧 ``SimpleDataSet`` / ``ClsDataset`` / ``DetDataset`` 都会把清单
    读成样本列表——写一个空清单等于声明「这个数据集有 0 个样本」，训练第一步
    （取 batch / 除零）就崩，报错还指向 DataLoader，看不出根因。
    """
    if not lines:
        log.info("torchkiln index: 跳过空清单 {}", path)
        return
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(lines) + "\n")
    log.info("torchkiln index: {} ({} 行)", path, len(lines))


def build_class_mapping(class_ids: set[int]) -> dict[int, int]:
    """把稀疏的原始类 id 映射为连续 0..n-1（按原始 id 升序）。"""
    return {raw: idx for idx, raw in enumerate(sorted(class_ids))}


def rotated_box_to_obb_corners(cx: float, cy: float, w: float, h: float,
                               angle_rad: float, reorder: bool = True) -> list[float]:
    """归一化旋转框 → YOLO OBB 8 点（左上→右上→右下→左下）。

    先在框自身坐标系取四角，再绕中心按 angle_rad（弧度）旋转。
    reorder=True（默认）：从页面左上（x+y 最小）起按顺时针重排，保证任意角度下
    顺序都是 左上→右上→右下→左下（YOLO OBB 约定）。
    reorder=False：保留原始局部顺序 [TL, TR, BR, BL] 旋转后的结果，保证
    ``p0->p1`` 恒为宽边（x-anylabeling 导入按首边解析宽高时需要）。

    注意：仅在 (45°,135°) 等区间 min(x+y) 起点会落在高边，reorder 后才改变首边语义。
    """
    hw, hh = w / 2.0, h / 2.0
    cos_a, sin_a = math.cos(angle_rad), math.sin(angle_rad)
    local = [(-hw, -hh), (hw, -hh), (hw, hh), (-hw, hh)]
    corners: list[tuple[float, float]] = []
    for dx, dy in local:
        corners.append((
            cx + dx * cos_a - dy * sin_a,
            cy + dx * sin_a + dy * cos_a,
        ))
    if reorder:
        start = min(range(len(corners)), key=lambda i: corners[i][0] + corners[i][1])
        ordered = corners[start:] + corners[:start]
    else:
        ordered = corners
    out: list[float] = []
    for x, y in ordered:
        out.extend([x, y])
    return out


def _px(v: float, scale: int) -> float:
    return round(float(v) * scale, 4)


def pose_extra_yaml(anns_by_img: dict[int, list]) -> dict:
    """当存在关键点标注时，返回 pose 训练所需的 kpt_shape / flip_idx。"""
    k = 0
    for anns in anns_by_img.values():
        for ann in anns:
            if ann.get("type") in ("Keypoint", "keypoint"):
                k = max(k, len(ann.get("keypoints", [])))
    if k <= 0:
        return {}
    return {"kpt_shape": f"[{k}, 3]", "flip_idx": "[" + ", ".join(str(i) for i in range(k)) + "]"}


def _write_yaml(
    path: str,
    base_path: str,
    sorted_classes: list,
    class_names: dict,
    class_id_map: dict[int, int] | None = None,
    extra_yaml: dict | None = None,
) -> None:
    """Write dataset.yaml.

    sorted_classes 为**映射后**的连续下标列表；class_id_map 用于把下标回指原始
    id 以取真实名称（不传时按下标直接取）。
    """
    names_dict: dict[str, str] = {}
    for out_id in sorted_classes:
        raw_id = out_id
        if class_id_map:
            for raw, mapped in class_id_map.items():
                if mapped == out_id:
                    raw_id = raw
                    break
        names_dict[str(out_id)] = class_names.get(raw_id, str(out_id))
    with open(path, "w") as f:
        f.write(f"path: {base_path}\n")
        f.write("train: images/train\n")
        f.write("val: images/val\n")
        f.write(f"nc: {len(sorted_classes)}\n")
        f.write(f"names: {json.dumps(names_dict, ensure_ascii=False)}\n")
        for k, v in (extra_yaml or {}).items():
            f.write(f"{k}: {v}\n")


def _write_yolo_cls_yaml(output_dir: str, for_training: bool) -> None:
    """Write minimal dataset.yaml for classification.

    YOLO cls reads class names from the directory structure (single-label) or
    per-image label files (multi-label), so only path/train/val are required.
    """
    base_path = "/data" if for_training else "."
    with open(os.path.join(output_dir, "dataset.yaml"), "w") as f:
        f.write(f"path: {base_path}\n")
        f.write("train: train\n")
        f.write("val: val\n")


def _write_torchkiln_index(output_dir: str) -> None:
    """生成 TorchKiln 的 ``train.txt`` / ``val.txt``（相对 data_dir 的图片路径）。

    一行一个图片，路径形如 ``images/train/0001.jpg``，TorchKiln 据此推导
    ``labels/train/0001.txt`` 读标注。空目录**跳过不写空文件**——写空列表会让
    dataset 长度为 0 并在训练第一步直接崩。
    """
    for split in ("train", "val"):
        img_dir = os.path.join(output_dir, "images", split)
        if not os.path.isdir(img_dir):
            continue
        names = sorted(
            f for f in os.listdir(img_dir)
            if f.lower().endswith((".jpg", ".jpeg", ".png", ".bmp", ".webp", ".tif", ".tiff"))
        )
        if not names:
            continue
        list_path = os.path.join(output_dir, f"{split}.txt")
        with open(list_path, "w", encoding="utf-8", newline="\n") as f:
            for n in names:
                # 统一正斜杠：训练环境可能是 Linux 容器
                f.write(f"images/{split}/{n}\n")
        log.info("torchkiln index: {} ({} images)", list_path, len(names))


def paddle_ocr_det_entries(anns: list, img_w: int, img_h: int,
                           text_by_ann: dict | None = None) -> list[dict]:
    """把矩形/多边形/OCR 标注统一成 PaddleOCR det 条目（像素 4 点）。

    AxisAlignedBox（支持 x1/y1/x2/y2 或中心式 x/y/width/height）、Polygon、Ocr
    统一转成 PaddleX 的 ``{"transcription", "points"}``；points 为像素坐标四角点，
    顺序为 左上→右上→右下→左下。text_by_ann 可在标注自身无 text 时按标注 id 补文本。
    """
    entries: list[dict] = []
    text_by_ann = text_by_ann or {}
    for ann in anns:
        t = ann.get("type", "")
        text = ann.get("text", "") or ""
        if not text and ann.get("id") is not None:
            text = text_by_ann.get(ann["id"], "") or ""
        if t in ("AxisAlignedBox", "box"):
            if "x1" in ann:
                x1, y1, x2, y2 = ann["x1"], ann["y1"], ann["x2"], ann["y2"]
            else:
                xc, yc, w, h = ann["x"], ann["y"], ann["width"], ann["height"]
                x1, y1, x2, y2 = xc - w / 2, yc - h / 2, xc + w / 2, yc + h / 2
            points = [[x1 * img_w, y1 * img_h], [x2 * img_w, y1 * img_h],
                      [x2 * img_w, y2 * img_h], [x1 * img_w, y2 * img_h]]
        elif t in ("Polygon", "polygon", "Ocr", "ocr"):
            pts = ann.get("points", [])
            if len(pts) < 4:
                continue
            points = [[(p["x"] if isinstance(p, dict) else p[0]) * img_w,
                       (p["y"] if isinstance(p, dict) else p[1]) * img_h] for p in pts[:4]]
        else:
            continue
        entries.append({"transcription": text, "points": points})
    return entries
