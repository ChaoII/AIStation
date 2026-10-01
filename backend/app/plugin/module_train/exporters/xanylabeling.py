"""X-AnyLabeling（LabelMe JSON）导出

由原 ``exporter.py`` 拆分而来（原文件 2291 行，混合了数据集导出、模型权重入库、
DB 访问与 S3 操作四类职责）。拆分依据是模块内定义的**依赖 DAG**——先验证过
无强连通分量，故按拓扑序切分不会产生循环导入。

函数体**逐字节原样搬运**，未做任何编辑；拆分后用 ast.dump 逐个比对确认一致。
"""

import json
import math
import os

from app.core.database import async_db_session
from app.core.logger import log

from .common import _load_latest_anns_by_image, _px, rotated_box_to_obb_corners


def xany_shapes(anns: list, img_w: int, img_h: int, class_names: dict[int, str]) -> list[dict]:
    """工作台归一化标注 → LabelMe/x-anylabeling shapes（像素坐标）。"""
    shapes: list[dict] = []
    for ann in anns:
        cid = ann.get("class_id", 0)
        label = class_names.get(cid, f"class_{cid}")
        base = {"label": label, "group_id": None, "flags": {}}
        t = ann.get("type", "")
        if t in ("AxisAlignedBox", "box"):
            if "x1" in ann:
                x1, y1, x2, y2 = ann["x1"], ann["y1"], ann["x2"], ann["y2"]
            else:
                xc, yc, w, h = ann["x"], ann["y"], ann["width"], ann["height"]
                x1, y1, x2, y2 = xc - w / 2, yc - h / 2, xc + w / 2, yc + h / 2
            pts = [[_px(x1, img_w), _px(y1, img_h)], [_px(x2, img_w), _px(y1, img_h)],
                   [_px(x2, img_w), _px(y2, img_h)], [_px(x1, img_w), _px(y2, img_h)]]
            shapes.append({**base, "points": pts, "shape_type": "rectangle"})
        elif t in ("RotatedBox", "rotated_box"):
            # 旋转必须按像素空间计算（x/y 缩放不同），结果本身就是像素坐标
            # reorder=False：保持 [TL,TR,BR,BL] 原始顺序，使首边恒为宽边，
            # 与 importer._shape_to_annotation 的解析约定一致（避免往返几何损坏）
            px = rotated_box_to_obb_corners(ann["cx"] * img_w, ann["cy"] * img_h,
                                            ann["width"] * img_w, ann["height"] * img_h,
                                            float(ann.get("angle", 0) or 0),
                                            reorder=False)
            pts = [[px[i], px[i + 1]] for i in range(0, 8, 2)]
            shapes.append({**base, "points": pts, "shape_type": "rotation"})
        elif t in ("Cuboid", "cuboid"):
            # 底面为平行四边形，由两条边方向角 angle1/angle2 展开 4 顶点（像素坐标），
            # 顶面仅用参数表达（不额外产出面）。
            a1 = float(ann.get("angle1", ann.get("yaw", 0) or 0))
            a2 = float(ann.get("angle2", a1 + math.pi / 2))
            hw = ann["w"] * img_w / 2
            hh = ann["h"] * img_h / 2
            cx_px = ann["cx"] * img_w
            cy_px = ann["cy"] * img_h
            d1x, d1y = math.cos(a1), math.sin(a1)
            d2x, d2y = math.cos(a2), math.sin(a2)
            corners = [
                (cx_px - hw * d1x - hh * d2x, cy_px - hw * d1y - hh * d2y),
                (cx_px + hw * d1x - hh * d2x, cy_px + hw * d1y - hh * d2y),
                (cx_px + hw * d1x + hh * d2x, cy_px + hw * d1y + hh * d2y),
                (cx_px - hw * d1x + hh * d2x, cy_px - hw * d1y + hh * d2y),
            ]
            pts = [[corners[i][0], corners[i][1]] for i in range(4)]
            shapes.append({
                **base,
                "points": pts,
                "shape_type": "cuboid",
                "attributes": {
                    "cx": ann.get("cx", 0),
                    "cy": ann.get("cy", 0),
                    "w": ann.get("w", 0),
                    "h": ann.get("h", 0),
                    "yaw": ann.get("yaw", ann.get("angle1", 0)),
                    "angle1": ann.get("angle1", ann.get("yaw", 0)),
                    "angle2": ann.get("angle2", float(ann.get("yaw", 0)) + math.pi / 2),
                    "depth": ann.get("depth", 0),
                    "top_cy": ann.get("top_cy", 0),
                },
            })
        elif t in ("Polygon", "polygon"):
            pts = [[_px(p["x"] if isinstance(p, dict) else p[0], img_w),
                    _px(p["y"] if isinstance(p, dict) else p[1], img_h)] for p in ann.get("points", [])]
            if len(pts) >= 3:
                shapes.append({**base, "points": pts, "shape_type": "polygon"})
        elif t in ("Polyline", "polyline", "line"):
            pts = [[_px(p["x"] if isinstance(p, dict) else p[0], img_w),
                    _px(p["y"] if isinstance(p, dict) else p[1], img_h)] for p in ann.get("points", [])]
            if len(pts) >= 2:
                shapes.append({**base, "points": pts, "shape_type": "line"})
        elif t in ("Keypoint", "keypoint"):
            for kp in ann.get("keypoints", []):
                shapes.append({**base,
                               "points": [[_px(kp.get("x", 0), img_w), _px(kp.get("y", 0), img_h)]],
                               "shape_type": "point"})
        elif t in ("Ocr", "ocr"):
            pts = [[_px(p["x"] if isinstance(p, dict) else p[0], img_w),
                    _px(p["y"] if isinstance(p, dict) else p[1], img_h)] for p in ann.get("points", [])]
            if len(pts) >= 3:
                shapes.append({**base, "points": pts, "shape_type": "polygon",
                               "description": ann.get("text", "")})
    return shapes


def xany_classification_flags(anns: list, class_names: dict[int, str]) -> dict:
    """收集图像级分类标注，返回 LabelMe/x-anylabeling 的 flags 字典。

    分类标注（type=Classification）在 x-anylabeling 中没有几何形状，若不额外承载
    会被静默丢弃。此处把单标 ``class_id`` 与多标 ``class_ids`` 统一成图像级
    ``{"classification": "cat,dog"}``（类名按首次出现顺序、逗号连接，已去重）；
    无有效分类标注时返回 {}。重新导入分类标注不在本期范围（Phase 1B importer）。
    """
    names: list[str] = []
    seen: set[str] = set()
    for ann in anns:
        cids: list = []
        if ann.get("type") == "Classification" and ann.get("class_id") not in (None, -1):
            cids.append(ann["class_id"])
        if isinstance(ann.get("class_ids"), list):
            cids.extend(ann["class_ids"])
        for cid in cids:
            if cid is None or cid == -1:
                continue
            label = class_names.get(cid, f"class_{cid}")
            if label not in seen:
                seen.add(label)
                names.append(label)
    if not names:
        return {}
    return {"classification": ",".join(names)}


async def _export_x_anylabeling(dataset_id: int, task_id: int, images: list, output_dir: str, annotation_task_id: int | None = None, class_names: dict | None = None) -> None:
    """Export dataset to x-anylabeling (LabelMe JSON) format: images + .json sidecar files."""
    img_dir = os.path.join(output_dir, "images")
    os.makedirs(img_dir, exist_ok=True)
    downloaded = 0

    from app.utils.s3_client import s3_client

    async with async_db_session() as db:
        # 批量 IN 查出全部图片标注，避免逐图 N+1
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

            # 用批量映射取标注，避免逐图查询
            anns = anns_by_img.get(img.id, [])

            # Convert to x-anylabeling format（归一化 → 像素；支持全部形状；使用真实类名）
            shapes = xany_shapes(anns, img.width or 0, img.height or 0, class_names or {})
            # 分类标注无几何形状，改以图像级 flags 承载，避免静默丢失
            flags = xany_classification_flags(anns, class_names or {})

            # Write JSON sidecar
            js = {
                "version": "3.2.1",
                "flags": flags,
                "shapes": shapes,
                "imagePath": img.filename,
                "imageData": None,
                "imageHeight": img.height or 0,
                "imageWidth": img.width or 0,
            }
            json_path = os.path.join(img_dir, img.filename.rsplit(".", 1)[0] + ".json")
            with open(json_path, "w", encoding="utf-8") as f:
                json.dump(js, f, ensure_ascii=False, indent=2)

    log.info(f"exported {downloaded} images to x-anylabeling format in {output_dir}")
