"""YOLO 检测 / 分类 / 姿态导出。

TorchKiln 的训练与评估数据也走此布局——那正是 ``YOLO_LAYOUT`` 的由来：
自研平台的标注数据复用 YOLO 目录结构（images/ + labels/ + train.txt）。

由原 ``exporter.py`` 拆分而来（原文件 2291 行，混合了数据集导出、模型权重入库、
DB 访问与 S3 操作四类职责）。拆分依据是模块内定义的**依赖 DAG**——先验证过
无强连通分量，故按拓扑序切分不会产生循环导入。

函数体**逐字节原样搬运**，未做任何编辑；拆分后用 ast.dump 逐个比对确认一致。
"""

import math
import os

from app.core.database import async_db_session
from app.core.logger import log

from .common import (
    _load_latest_anns_by_image,
    _write_lines,
    _write_torchkiln_index,
    _write_yaml,
    _write_yolo_cls_yaml,
    build_class_mapping,
    pose_extra_yaml,
    rotated_box_to_obb_corners,
)


async def _export_yolo(dataset_id: int, task_id: int, images: list, output_dir: str, task_type: str = "detection", annotation_task_id: int | None = None, train_ratio: float = 0.8, class_names: dict | None = None, for_training: bool = False, for_eval: bool = False, torchkiln_index: bool = False) -> None:
    """Export to YOLO format with train/val split. for_training controls YAML path.

    for_eval=True 时全部图片进 ``images/val``、不 shuffle，保证评估全量且可复现
    （``yolo val`` 读 ``val:`` 分片，train 目录仍创建但为空）。

    两遍式：先收集所有图片的最新标注与全局类 id 集合，构建连续映射后再下载图片、
    按映射写标签，避免稀疏类 id（类别删除后）导致 nc/names 越界。
    """
    import random

    from app.utils.s3_client import s3_client

    anns_by_img: dict[int, list] = {}
    used_ids: set[int] = set()
    async with async_db_session() as db:
        # 批量 IN 查出全部图片标注，避免逐图 N+1
        anns_by_img = await _load_latest_anns_by_image(db, [img.id for img in images], annotation_task_id)
        for anns in anns_by_img.values():
            for ann in anns:
                cid = ann.get("class_id")
                if cid is not None and cid != -1:
                    used_ids.add(int(cid))

    class_id_map = build_class_mapping(used_ids)

    if for_eval:
        # 评估：全量进 val、不 shuffle，保证每次评估同一批图片
        train_imgs, val_imgs = [], images
    else:
        random.shuffle(images)
        split_idx = max(1, int(len(images) * train_ratio))
        train_imgs = images[:split_idx]
        val_imgs = images[split_idx:]

    for split_name, split_imgs in [("train", train_imgs), ("val", val_imgs)]:
        img_split = os.path.join(output_dir, "images", split_name)
        label_split = os.path.join(output_dir, "labels", split_name)
        os.makedirs(img_split, exist_ok=True)
        os.makedirs(label_split, exist_ok=True)
        for img in split_imgs:
            img_path = os.path.join(img_split, img.filename)
            if not os.path.exists(img_path):
                try:
                    data = s3_client.download_fileobj(img.object_key)
                    with open(img_path, "wb") as f:
                        f.write(data.read())
                except Exception as e:
                    log.warning(f"skip {img.filename}: {e}")
                    continue
            anns = anns_by_img.get(img.id, [])
            lines = _format_yolo_lines(anns, task_type, class_id_map=class_id_map,
                                       img_w=img.width or 1, img_h=img.height or 1)
            if lines:
                label_path = os.path.join(label_split,
                                          img.filename.rsplit(".", 1)[0] + ".txt")
                with open(label_path, "w") as f:
                    f.write("\n".join(lines))

    base_path = "/data" if for_training else "."
    sorted_out = list(range(len(class_id_map)))
    extra = pose_extra_yaml(anns_by_img) if task_type in ("keypoint", "pose") else None
    _write_yaml(os.path.join(output_dir, "dataset.yaml"), base_path, sorted_out,
                class_names or {}, class_id_map=class_id_map, extra_yaml=extra)
    if torchkiln_index:
        _write_torchkiln_index(output_dir)
    log.info(f"yolo: train={len(train_imgs)} val={len(val_imgs)} classes={len(sorted_out)} → {output_dir}")


def _format_yolo_lines(anns: list, task_type: str, class_id_map: dict[int, int] | None = None, img_w: int = 1, img_h: int = 1) -> list[str]:
    """Convert annotations to YOLO label lines based on task_type.

    class_id_map 把原始类 id 映射为连续下标；img_w/img_h 预留给像素坐标标注的归一化。
    坐标约定：本工作台标注为归一化 [0,1]，YOLO 也需归一化，故此处不做缩放。
    """
    lines = []
    for ann in anns:
        raw_cls = ann.get("class_id")
        # 与收集器一致：class_id 缺失或为 -1 的标注不产生标签行，避免 -1/越界类 id 写入
        if raw_cls is None or raw_cls == -1:
            continue
        cls_id = (class_id_map or {}).get(raw_cls, raw_cls)
        ann_type = ann.get("type", "")
        if ann_type in ("AxisAlignedBox", "box"):
            if "x1" in ann:
                x1, y1, x2, y2 = ann["x1"], ann["y1"], ann["x2"], ann["y2"]
            else:
                xc_a, yc_a, w_a, h_a = ann["x"], ann["y"], ann["width"], ann["height"]
                x1, y1, x2, y2 = xc_a - w_a / 2, yc_a - h_a / 2, xc_a + w_a / 2, yc_a + h_a / 2
            if task_type == "rotated_detection":
                lines.append(f"{cls_id} {x1:.6f} {y1:.6f} {x2:.6f} {y1:.6f} {x2:.6f} {y2:.6f} {x1:.6f} {y2:.6f}")
            else:
                lines.append(f"{cls_id} {(x1 + x2) / 2:.6f} {(y1 + y2) / 2:.6f} {x2 - x1:.6f} {y2 - y1:.6f}")
        elif ann_type in ("RotatedBox", "rotated_box"):
            cx, cy = ann["cx"], ann["cy"]
            w, h = ann["width"], ann["height"]
            ang = float(ann.get("angle", 0) or 0)
            if task_type in ("rotated_detection", "obb"):
                # 旋转必须按像素空间计算（x/y 缩放不同），再归一化回 [0,1] 写入标签
                px = rotated_box_to_obb_corners(cx * img_w, cy * img_h, w * img_w, h * img_h, ang)
                pts = [px[i] / (img_w if i % 2 == 0 else img_h) for i in range(8)]
                lines.append(f"{cls_id} " + " ".join(f"{v:.6f}" for v in pts))
            else:
                lines.append(f"{cls_id} {cx:.6f} {cy:.6f} {w:.6f} {h:.6f} {math.degrees(ang):.6f}")
        elif ann_type in ("Polygon", "polygon") and task_type in ("segmentation", "seg"):
            # YOLO Seg: cls_id x1 y1 x2 y2 ... (归一化多边形顶点)
            pts = []
            for p in ann.get("points", []):
                px = p.get("x") if isinstance(p, dict) else p[0]
                py = p.get("y") if isinstance(p, dict) else p[1]
                pts.append(f"{px:.6f} {py:.6f}")
            if len(pts) >= 3:
                lines.append(f"{cls_id} {' '.join(pts)}")
        elif ann_type in ("Keypoint", "keypoint") and task_type in ("keypoint", "pose"):
            # YOLO Pose: cls_id cx cy w h kpx kpy kpv ...（bbox + 关键点，visibility 0/1/2）
            bb = ann.get("bounding_box", {})
            cx, cy = bb.get("cx", 0), bb.get("cy", 0)
            w, h = bb.get("width", 0), bb.get("height", 0)
            keypoints = ann.get("keypoints") or []
            # ⚠️ 原来的守卫写的是 ``if len(parts) > 4``，而 ``parts`` 是
            #    [单个拼接好的字符串]（长度恒为 1），所以**关键点标签从来没有被写出过**
            #    ——训练照常跑完，但 PoseDataset 读到的是全空的 labels/，
            #    等于在空数据集上训练。正确判据是「关键点数量 > 0」。
            if not keypoints:
                continue
            parts = [f"{cx:.6f} {cy:.6f} {w:.6f} {h:.6f}"]
            vis_map = {"Visible": 2, "Occluded": 1, "Hidden": 0}
            for kp in keypoints:
                kx = kp.get("x", 0)
                ky = kp.get("y", 0)
                kv = vis_map.get(kp.get("visibility", ""), 0)
                parts.append(f"{kx:.6f} {ky:.6f} {kv}")
            lines.append(f"{cls_id} {' '.join(parts)}")
    return lines


async def _export_yolo_cls(dataset_id: int, task_id: int, images: list, output_dir: str, annotation_task_id: int | None = None, train_ratio: float = 0.8, class_names: dict | None = None, for_training: bool = False, multi_label: bool = False, for_eval: bool = False, torchkiln_index: bool = False) -> None:
    """Export classification to YOLO CLS format with train/val split.

    single_label: train/<cls>/<img>.jpg (目录结构)
    multi_label:  train/<img>.jpg + train/labels/<img>.txt (每行一个 class id)

    for_eval=True 时全部图片进 ``val``、不 shuffle（评估全量可复现）。
    """
    import random

    from app.utils.s3_client import s3_client

    task_cn: dict[int, str] = class_names or {}
    if not task_cn and annotation_task_id:
        from app.api.v1.module_annotation.task.model import AnnotationTaskModel
        async with async_db_session() as db:
            ann_task = await db.get(AnnotationTaskModel, annotation_task_id)
            if ann_task and ann_task.classes:
                for c in (ann_task.classes if isinstance(ann_task.classes, list) else []):
                    task_cn[c["id"]] = c.get("name", f"class_{c['id']}")

    # Collect per-image labels: {img_id: [class_id, ...]} (multi) or {img_id: class_id} (single)
    img_labels: dict[int, list[int]] = {}
    async with async_db_session() as db:
        # 批量 IN 查出全部图片标注，避免逐图 N+1
        anns_by_img = await _load_latest_anns_by_image(db, [img.id for img in images], annotation_task_id)
        for img_id, anns in anns_by_img.items():
            ids: list[int] = []
            for ann in anns:
                cid = ann.get("class_id")
                if cid is not None and cid != -1:
                    ids.append(cid)
                if isinstance(ann.get("class_ids"), list):
                    for c in ann["class_ids"]:
                        if c is not None and c != -1:
                            ids.append(c)
            if ids:
                # 去重保持顺序
                seen = set()
                ids = [c for c in ids if not (c in seen or seen.add(c))]
                img_labels[img_id] = ids

    if multi_label:
        # Multi-label: flat train/val dirs + labels/*.txt (one class id per line)
        if for_eval:
            train_sub, val_sub = [], images
        else:
            random.shuffle(images)
            split_idx = max(1, int(len(images) * train_ratio)) if images else 0
            train_sub, val_sub = images[:split_idx], images[split_idx:]
        # TorchKiln 清单：每行 ``<相对 data_dir 的路径> <v1> … <vC>``，**稠密向量**
        # ⚠️ 必须稠密：ClsDataset 的 ``label_ratio`` 与 collate 都按「向量下标 == 类下标」
        #    对齐（``label[: len(lb)]``），稀疏写 ``0 0 0 1`` 会被当成「第 0 类命中」。
        tk_rows: dict[str, list[str]] = {"train": [], "val": []}
        class_id_map = build_class_mapping({
            cid for ids in img_labels.values() for cid in ids
        })
        n_class = len(class_id_map)
        for split_name, sub in [("train", train_sub), ("val", val_sub)]:
            img_dir = os.path.join(output_dir, split_name)
            lbl_dir = os.path.join(output_dir, split_name, "labels")
            os.makedirs(img_dir, exist_ok=True)
            os.makedirs(lbl_dir, exist_ok=True)
            for img in sub:
                ids = img_labels.get(img.id, [])
                if not ids:
                    continue
                try:
                    data = s3_client.download_fileobj(img.object_key)
                    with open(os.path.join(img_dir, img.filename), "wb") as f:
                        f.write(data.read())
                except Exception:
                    continue
                stem = os.path.splitext(img.filename)[0]
                with open(os.path.join(lbl_dir, stem + ".txt"), "w") as f:
                    f.write("\n".join(str(cid) for cid in sorted(set(ids))))
                if torchkiln_index:
                    vec = [0.0] * n_class
                    for cid in set(ids):
                        vec[class_id_map[cid]] = 1.0
                    tk_rows[split_name].append(
                        f"{split_name}/{img.filename} " + " ".join(str(int(v)) for v in vec))
        _write_yolo_cls_yaml(output_dir, for_training)
        if torchkiln_index:
            _write_lines(os.path.join(output_dir, "train.txt"), tk_rows["train"])
            _write_lines(os.path.join(output_dir, "val.txt"), tk_rows["val"])
        log.info(f"yolo-cls (multi): exported to {output_dir}"
                 + (f" torchkiln 类别数={n_class}" if torchkiln_index else ""))
        return

    # Single-label: existing directory structure
    class_imgs: dict[int, list] = {}
    for img in images:
        ids = img_labels.get(img.id, [])
        if ids:
            class_imgs.setdefault(ids[0], []).append(img)
    # TorchKiln 清单：每行 ``<相对 data_dir 的路径> <类下标>``。类下标取
    # ``build_class_mapping`` 的连续映射（按原始 id 升序），**不是**原始 class_id——
    # 原始 id 稀疏时（类别被删过）直接写会让模型 head 的 num_classes 与标签越界。
    class_id_map = build_class_mapping(set(class_imgs.keys()))
    tk_rows: dict[str, list[str]] = {"train": [], "val": []}
    for cid, imgs in class_imgs.items():
        if for_eval:
            train_sub, val_sub = [], imgs
        else:
            random.shuffle(imgs)
            split = max(0, int(len(imgs) * train_ratio))
            train_sub, val_sub = imgs[:split], imgs[split:]
        for split_name, sub in [("train", train_sub), ("val", val_sub)]:
            cls_name = task_cn.get(cid, f"class_{cid}")
            dst_dir = os.path.join(output_dir, split_name, cls_name)
            os.makedirs(dst_dir, exist_ok=True)
            for img in sub:
                try:
                    data = s3_client.download_fileobj(img.object_key)
                    with open(os.path.join(dst_dir, img.filename), "wb") as f:
                        f.write(data.read())
                except Exception:
                    continue
                if torchkiln_index:
                    tk_rows[split_name].append(
                        f"{split_name}/{cls_name}/{img.filename} {class_id_map[cid]}")
    _write_yolo_cls_yaml(output_dir, for_training)
    if torchkiln_index:
        _write_lines(os.path.join(output_dir, "train.txt"), tk_rows["train"])
        _write_lines(os.path.join(output_dir, "val.txt"), tk_rows["val"])
    log.info(f"yolo-cls: exported to {output_dir}"
             + (f" torchkiln 类别数={len(class_id_map)}" if torchkiln_index else ""))
