"""语义分割掩码 + COCO Panoptic 导出

由原 ``exporter.py`` 拆分而来（原文件 2291 行，混合了数据集导出、模型权重入库、
DB 访问与 S3 操作四类职责）。拆分依据是模块内定义的**依赖 DAG**——先验证过
无强连通分量，故按拓扑序切分不会产生循环导入。

函数体**逐字节原样搬运**，未做任何编辑；拆分后用 ast.dump 逐个比对确认一致。
"""

import os

from app.core.database import async_db_session
from app.core.logger import log

from .common import _load_latest_anns_by_image, _write_torchkiln_index, build_class_mapping

SEMANTIC_IGNORE_INDEX = 255


def _semantic_label_map(class_names: dict[int, str], is_instance: dict[int, bool]) -> dict[int, int]:
    """语义分割的「类别 id → 掩码像素值」映射。

    TorchKiln 的 ``SemDataset`` 直接把掩码像素值当类别下标用，所以像素值必须
    是 **0..C-1 的连续值**：0 天然是背景（``ignore_index`` 是 255，不冲突）。

    ⚠️ 本平台的类别可能同时含 thing 类（is_instance=True）与 stuff 类。语义分割
    天然无法表达「同类多个实例」，所以这里把 is_instance 类排在后面统一当普通
    类别处理——若你期望的是全景语义，请改走 panoptic（当前 TorchKiln 不支持）。
    """
    ids = sorted(class_names.keys()) if class_names else []
    return {cid: idx for idx, cid in enumerate(ids)}


def _paint_semantic_mask(anns: list, img_w: int, img_h: int,
                         class_id_map: dict[int, int], to_pixel: dict[int, int]) -> "object":
    """把标注光栅化成 uint8 类别索引图（不依赖 cv2/numpy 之外的东西）。"""
    import numpy as np

    mask = np.zeros((img_h, img_w), dtype=np.uint8)
    for ann in anns:
        raw_cls = ann.get("class_id")
        if raw_cls is None or raw_cls == -1:
            continue
        mapped = class_id_map.get(raw_cls)
        if mapped is None:
            continue
        value = min(to_pixel.get(mapped, mapped), SEMANTIC_IGNORE_INDEX - 1)

        ann_type = ann.get("type", "")
        if ann_type in ("Polygon", "polygon"):
            pts_raw = ann.get("points", [])
            pts = []
            for p in pts_raw:
                px = p.get("x") if isinstance(p, dict) else p[0]
                py = p.get("y") if isinstance(p, dict) else p[1]
                pts.append((float(px) * img_w, float(py) * img_h))
            if len(pts) < 3:
                continue
            arr = np.array(pts, dtype=np.int32).reshape(-1, 1, 2)
            try:
                import cv2
                cv2.fillPoly(mask, [arr], int(value))
            except Exception as e:  # noqa: BLE001
                log.warning("semantic fillPoly 失败: {}", e)
        else:
            # 框类标注退化成矩形填充：语义分割任务里少见，但不该静默丢标注
            if "x1" in ann:
                x1, y1, x2, y2 = ann["x1"], ann["y1"], ann["x2"], ann["y2"]
            else:
                xc, yc, w, h = ann["x"], ann["y"], ann["width"], ann["height"]
                x1, y1, x2, y2 = xc - w / 2, yc - h / 2, xc + w / 2, yc + h / 2
            cx1 = max(0, min(img_w, int(x1 * img_w)))
            cy1 = max(0, min(img_h, int(y1 * img_h)))
            cx2 = max(0, min(img_w, int(x2 * img_w)))
            cy2 = max(0, min(img_h, int(y2 * img_h)))
            if cx2 > cx1 and cy2 > cy1:
                mask[cy1:cy2, cx1:cx2] = int(value)
    return mask


async def _export_yolo_semantic(
    dataset_id: int, task_id: int, images: list, output_dir: str, task_type: str,
    annotation_task_id: int | None = None, train_ratio: float = 0.8,
    class_names: dict | None = None, for_eval: bool = False,
    torchkiln_index: bool = False,
) -> None:
    """导出语义分割：``images/<split>/*.jpg`` + ``masks/<split>/*.png``（uint8 索引图）。

    TorchKiln ``SemDataset`` 的掩码路径推导规则与检测一致——把清单图片路径里的
    ``images/`` 换成 ``masks/`` 再改扩展名——所以目录布局照抄检测即可，只有标签
    载体从 ``labels/*.txt`` 换成 ``masks/*.png``。

    ⚠️ 必须是**单通道 uint8**：``IMREAD_GRAYSCALE`` 会把调色板 PNG 转成灰度而非
    索引值，存成调色板图会导致像素值全错。
    """
    import random

    from app.utils.s3_client import s3_client

    async with async_db_session() as db:
        anns_by_img = await _load_latest_anns_by_image(db, [img.id for img in images], annotation_task_id)

    used_ids: set[int] = set()
    for anns in anns_by_img.values():
        for ann in anns:
            cid = ann.get("class_id")
            if cid is not None and cid != -1:
                used_ids.add(int(cid))
    class_id_map = build_class_mapping(used_ids)

    if for_eval:
        train_imgs, val_imgs = [], list(images)
    else:
        images = list(images)
        random.shuffle(images)
        split_idx = max(1, int(len(images) * train_ratio))
        train_imgs, val_imgs = images[:split_idx], images[split_idx:]

    n_mask = 0
    for split_name, split_imgs in [("train", train_imgs), ("val", val_imgs)]:
        img_split = os.path.join(output_dir, "images", split_name)
        mask_split = os.path.join(output_dir, "masks", split_name)
        os.makedirs(img_split, exist_ok=True)
        os.makedirs(mask_split, exist_ok=True)
        for img in split_imgs:
            img_path = os.path.join(img_split, img.filename)
            if not os.path.exists(img_path):
                try:
                    data = s3_client.download_fileobj(img.object_key)
                    with open(img_path, "wb") as f:
                        f.write(data.read())
                except Exception as e:
                    log.warning("skip {}: {}", img.filename, e)
                    continue
            anns = anns_by_img.get(img.id, [])
            if not anns:
                continue
            w, h = img.width or 1, img.height or 1
            mask = _paint_semantic_mask(anns, w, h, class_id_map, class_id_map)
            mask_path = os.path.join(mask_split, img.filename.rsplit(".", 1)[0] + ".png")
            try:
                from PIL import Image
                Image.fromarray(mask, mode="L").save(mask_path)
                n_mask += 1
            except Exception as e:
                log.warning("semantic mask 写入失败 {}: {}", mask_path, e)

    if torchkiln_index:
        _write_torchkiln_index(output_dir)
    log.info(f"yolo-semantic: images={len(train_imgs) + len(val_imgs)} masks={n_mask} "
             f"classes={len(class_id_map)} → {output_dir}")


_PANOPTIC_VOID = -1


def _panoptic_mask(anns: list, img_w: int, img_h: int,
                   class_meta: dict[int, dict]) -> tuple["np.ndarray", list[dict]]:
    """把多边形标注栅格化为 COCO Panoptic 掩码并返回每段元数据。

    class_meta: {class_id: {"name": str, "is_instance": bool}}。
    panoptic_id = category_id * 1000 + instance_id（thing 按类别内数组顺序从 1 编号；stuff 恒 0）。
    先铺 stuff 垫底，再叠 thing（后画覆盖前画）；同类 stuff 因同 pid 自动合并为一段。
    """
    import numpy as np
    from PIL import Image, ImageDraw

    class_meta = class_meta or {}
    if img_w <= 0 or img_h <= 0:
        return np.zeros((max(img_h, 1), max(img_w, 1)), dtype=np.uint32), []

    def _pts(a: dict) -> list[tuple[float, float]]:
        return [
            ((p["x"] if isinstance(p, dict) else p[0]) * img_w,
             (p["y"] if isinstance(p, dict) else p[1]) * img_h)
            for p in (a.get("points") or [])
        ]

    def _is_instance(a: dict) -> bool:
        return bool(class_meta.get(a.get("class_id"), {}).get("is_instance"))

    polys = [a for a in anns if a.get("type") in ("Polygon", "polygon")]
    stuff = [a for a in polys if not _is_instance(a)]
    things = [a for a in polys if _is_instance(a)]

    # thing 实例号：类别分组、组内按数组顺序从 1 编号
    counters: dict[int, int] = {}
    thing_pids: dict[int, int] = {}
    for a in things:
        cid = a.get("class_id")
        n = counters.get(cid, 0) + 1
        counters[cid] = n
        thing_pids[id(a)] = cid * 1000 + n

    def _flat(a: dict) -> list[float]:
        """多边形点集 -> 扁平像素坐标列表 [x0,y0,x1,y1,...]。"""
        out: list[float] = []
        for p in (a.get("points") or []):
            out.append((p["x"] if isinstance(p, dict) else p[0]) * img_w)
            out.append((p["y"] if isinstance(p, dict) else p[1]) * img_h)
        return out

    im = Image.new("I", (img_w, img_h), _PANOPTIC_VOID)
    draw = ImageDraw.Draw(im)
    # pid -> 贡献该段的全部多边形点集（COCO segmentation 为列表，元素为扁平点集）
    pid_polys: dict[int, list[list[float]]] = {}
    for a in stuff:
        pid = int(a.get("class_id")) * 1000
        pts = _pts(a)
        if len(pts) >= 3:
            draw.polygon(pts, fill=pid)
            pid_polys.setdefault(pid, []).append(_flat(a))
    for a in things:
        pid = int(thing_pids[id(a)])
        pts = _pts(a)
        if len(pts) >= 3:
            draw.polygon(pts, fill=pid)
            pid_polys.setdefault(pid, []).append(_flat(a))

    mask = np.array(im, dtype=np.uint32)
    segments: list[dict] = []
    for pid in pid_polys:
        pid = int(pid)
        region = mask == pid
        ys, xs = np.nonzero(region)
        if len(xs) == 0:
            continue
        x0, x1 = int(xs.min()), int(xs.max())
        y0, y1 = int(ys.min()), int(ys.max())
        category_id = pid // 1000
        instance_id = pid % 1000
        segments.append({
            "id": pid,
            "category_id": category_id,
            "instance_id": instance_id,
            "area": int(region.sum()),
            "bbox": [x0, y0, x1 - x0 + 1, y1 - y0 + 1],
            "segmentation": pid_polys.get(pid, []),
        })
    return mask, segments


async def _export_coco_panoptic(dataset_id: int, task_id: int, images: list,
                                output_dir: str, annotation_task_id: int | None = None,
                                class_meta: dict | None = None) -> None:
    """导出为 COCO Panoptic：每图一张 panoptic PNG 掩码 + panoptic.json 段表。"""
    import json  # noqa: F811  —— 函数体内原有的局部导入，遮蔽模块级的；保留以维持函数体逐字节不变

    import numpy as np
    from PIL import Image

    class_meta = class_meta or {}
    img_dir = os.path.join(output_dir, "images")
    mask_dir = os.path.join(output_dir, "panoptic_masks")
    os.makedirs(img_dir, exist_ok=True)
    os.makedirs(mask_dir, exist_ok=True)
    from app.utils.s3_client import s3_client

    categories = [
        {"id": cid, "name": meta.get("name", f"class_{cid}"),
         "isthing": 1 if meta.get("is_instance") else 0}
        for cid, meta in sorted(class_meta.items(), key=lambda kv: kv[0])
    ]
    images_json: list[dict] = []
    annotations: list[dict] = []
    ann_id = 1000000
    downloaded = 0

    async with async_db_session() as db:
        anns_by_img = await _load_latest_anns_by_image(db, [img.id for img in images], annotation_task_id)
        for img in images:
            img_path = os.path.join(img_dir, img.filename)
            if not os.path.exists(img_path):
                try:
                    data = s3_client.download_fileobj(img.object_key)
                    with open(img_path, "wb") as f:
                        f.write(data.read())
                    downloaded += 1
                except Exception as e:
                    log.warning(f"skip image {img.filename}: {e}")
                    continue
            w, h = img.width or 0, img.height or 0
            anns = anns_by_img.get(img.id, [])
            mask, segs = _panoptic_mask(anns, w, h, class_meta)
            stem = img.filename.rsplit(".", 1)[0]
            # mask 为 uint32，写入的 -1 哨兵经转换后变为 0xFFFFFFFF；先转 int32 再按哨兵比对，
            # 把未标注背景（哨兵）映射回 COCO void 0，避免其落入 stuff 段 0。
            mask_png = np.where(mask.astype(np.int32) == _PANOPTIC_VOID, 0, mask)
            Image.fromarray(mask_png.astype(np.int32), mode="I").save(
                os.path.join(mask_dir, f"{stem}.png"))
            images_json.append({"id": img.id, "file_name": img.filename, "width": w, "height": h})
            for seg in segs:
                ann_id += 1
                annotations.append({
                    "id": ann_id,
                    "image_id": img.id,
                    "category_id": seg["category_id"],
                    "segment_id": seg["id"],
                    "iscrowd": 0,
                    "area": seg["area"],
                    "bbox": seg["bbox"],
                    "segmentation": seg["segmentation"],
                })

    with open(os.path.join(output_dir, "panoptic.json"), "w", encoding="utf-8") as f:
        json.dump({
            "info": {"description": "AIStation panoptic segmentation"},
            "categories": categories,
            "images": images_json,
            "annotations": annotations,
        }, f, ensure_ascii=False, indent=2)

    log.info(f"exported {downloaded} images to coco-panoptic format in {output_dir}")
