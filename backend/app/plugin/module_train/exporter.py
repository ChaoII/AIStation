import json
import math
import os
import subprocess

from sqlalchemy import desc, select

from app.api.v1.module_annotation.annotation.model import AnnotationRecordModel
from app.api.v1.module_annotation.dataset.model import AnnotationImageModel
from app.core.database import async_db_session
from app.core.logger import log

from .model import TrainModelRepo


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


async def prepare_training_data_for_task(dataset_id: int, task_id: int, framework: str, output_dir: str, annotation_task_id: int | None = None, train_ratio: float = 0.8, ocr_rec: bool = False, torchkiln_index: bool = False) -> str:
    """Export dataset for training — unified with download, just different YAML path.

    ``torchkiln_index=True`` 时，让**各导出器自己**写 TorchKiln 需要的
    ``train.txt`` / ``val.txt`` 清单——而不是导出完再补一层。因为不同任务的
    清单内容规则并不相同（此前正是这里出的问题）：

    ==================  ==========================================================
    任务                 清单每行格式
    ==================  ==========================================================
    检测/旋转框/分割/关键点 ``images/<split>/<name>.jpg``（纯路径，标签靠
                          ``images/``→``labels/`` 路径替换推导）
    分类（单标签）        ``train/<类名>/<name>.jpg <类下标>``
    分类（多标签）        ``train/<name>.jpg <v1> <v2> … <vC>``
    语义分割              ``images/<split>/<name>.jpg``（掩码靠 ``images/``→``masks/``）
    OCR det              ``images/<split>/<name>.jpg\\t[{"transcription","points"}]``
    OCR rec              ``images/<split>/<name>.jpg\\t<识别文本>``
    ==================  ==========================================================

    ⚠️ 两条路径规则容易踩坑：**清单里的图片路径相对 ``data_dir``**，但
    ``label_file_list`` 本身**不做** ``data_dir`` 拼接——TorchKiln 侧对
    classification / ocr / semantic 等 12 个任务族是直接 ``open()`` 的，
    所以必须传绝对路径。
    """
    # for_training=True 时 YOLO YAML 里的 path 写容器内路径 /data
    return await _export_core(dataset_id, task_id, framework, output_dir, annotation_task_id=annotation_task_id, train_ratio=train_ratio, for_training=True, ocr_rec=ocr_rec, torchkiln_index=torchkiln_index)


def _write_lines(path: str, lines: list[str]) -> None:
    """写清单文件；**空集直接跳过不写**。

    TorchKiln 侧 ``SimpleDataSet`` / ``ClsDataset`` / ``DetDataset`` 都会把清单
    读成样本列表——写一个空清单等于声明「这个数据集有 0 个样本」，训练第一步
    （取 batch / 除零）就崩，报错还指向 DataLoader，看不出根因。
    """
    if not lines:
        log.info("torchkiln index: 跳过空清单 %s", path)
        return
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(lines) + "\n")
    log.info("torchkiln index: %s (%d 行)", path, len(lines))


def _write_torchkiln_index(output_dir: str) -> None:
    """生成 TorchKiln 的 ``train.txt`` / ``val.txt``（相对 data_dir 的图片路径）。

    一行一个图片，路径形如 ``images/train/0001.jpg``，TorchKiln 据此推导
    ``labels/train/0001.txt`` 读标注。空目录**跳过不写空文件**——写空列表会让
    dataset 长度��� 0 并在训练第一步直接崩。
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
        log.info("torchkiln index: %s (%d images)", list_path, len(names))


async def prepare_eval_data_for_task(dataset_id: int, task_id: int, framework: str, output_dir: str, annotation_task_id: int | None = None, ocr_mode: str = "det") -> str:
    """评估数据导出：全量、确定性，不随机切分。

    - YOLO：全部图片进 ``images/val``（``train`` 为空），``yolo val`` 读 ``val`` 即全量；
    - PaddleOCR：全部记录进 ``val.txt``（``train.txt`` 为空）。
    相比训练导出必须显式传 ``annotation_task_id``，否则任务类型默认 detection，
    分类/分割评估会导出错误格式。
    """
    # for_training=True 仅用于让 YOLO YAML 的 path 写容器内基础路径 /data；
    # 切分逻辑仍由 for_eval 控制（全量进 val），二者互不冲突。
    return await _export_core(dataset_id, task_id, framework, output_dir,
                              annotation_task_id=annotation_task_id,
                              ocr_rec=(ocr_mode == "rec"), for_eval=True,
                              for_training=True)


async def export_dataset_for_download(
    dataset_id: int, task_id: int, format: str, output_dir: str,
    annotation_task_id: int | None = None, ocr_rec: bool = True, train_ratio: float = 0.8
) -> str:
    """Export dataset for user download — train/val split, user-friendly YAML."""
    return await _export_core(dataset_id, task_id, format, output_dir, annotation_task_id=annotation_task_id, ocr_rec=ocr_rec, train_ratio=train_ratio, for_training=False)


async def _export_core(
    dataset_id: int, task_id: int, framework: str, output_dir: str,
    annotation_task_id: int | None = None, ocr_rec: bool = True,
    train_ratio: float = 0.8, for_training: bool = False, for_eval: bool = False,
    torchkiln_index: bool = False,
) -> str:
    """Core export logic shared by training and download."""
    os.makedirs(output_dir, exist_ok=True)
    async with async_db_session() as db:
        result = await db.execute(
            select(AnnotationImageModel).where(AnnotationImageModel.dataset_id == dataset_id)
        )
        images = result.scalars().all()

    # Determine task_type and class names
    task_type = "detection"
    class_names: dict[int, str] = {}
    class_meta: dict[int, dict] = {}
    classification_mode: str | None = None
    if annotation_task_id:
        from app.api.v1.module_annotation.task.model import AnnotationTaskModel
        async with async_db_session() as db:
            ann_task = await db.get(AnnotationTaskModel, annotation_task_id)
            if ann_task:
                task_type = ann_task.task_type
                classification_mode = ann_task.classification_mode
                if ann_task.classes:
                    for c in (ann_task.classes if isinstance(ann_task.classes, list) else []):
                        class_names[c["id"]] = c.get("name", f"class_{c['id']}")
                        class_meta[c["id"]] = {
                            "name": c.get("name", f"class_{c['id']}"),
                            "is_instance": bool(c.get("is_instance", False)),
                        }

    # 视频检测：按帧抽帧导出，复用既有检测格式器（YOLO / x-anylabeling）。
    # 必须放在 `if not images: return` 守卫之前：视频数据集的帧通过
    # AnnotationVideoModel + frame_index 存储，可能没有任何 AnnotationImageModel 行，
    # 若先按图片空集提前 return，视频导出永远不会执行（Critical 修复）。
    if task_type == "video_detection":
        await _export_video_detection(
            dataset_id, task_id, output_dir, framework,
            annotation_task_id=annotation_task_id, class_names=class_names,
            train_ratio=train_ratio, for_training=for_training, for_eval=for_eval,
        )
        return

    # 文本 NER：按文档导出字符级 BIO/BIESO + 关系 JSONL。
    # 同理放在图片空集守卫之前：text_ner 数据集可能没有任何 AnnotationImageModel 行。
    # 必须传「标注任务 id」而非训练任务 id（同视频导出修复，否则标注静默为空）。
    if task_type == "text_ner":
        await _export_text_ner(dataset_id, output_dir, annotation_task_id=annotation_task_id)
        return

    # 音频事件：按音频导出 SED 事件 JSONL（可选 CSV）。
    # 同样放在图片空集守卫之前：audio_event 数据集可能没有任何 AnnotationImageModel 行。
    # 必须传「标注任务 id」而非训练任务 id（同视频/文本导出修复，否则标注静默为空）。
    if task_type == "audio_event":
        await _export_audio_event(
            dataset_id, output_dir, annotation_task_id=annotation_task_id,
            csv=(framework == "audio-csv"),
        )
        return

    # 时间序列区间事件：按序列导出区间 JSONL（可选 CSV）。
    # 同样放在图片空集守卫之前：time_series_event 数据集可能没有任何 AnnotationImageModel 行。
    # 必须传「标注任务 id」而非训练任务 id（同视频/文本/音频导出修复，否则标注静默为空）。
    if task_type == "time_series_event":
        await _export_time_series_event(
            dataset_id, output_dir, annotation_task_id=annotation_task_id,
            csv=(framework == "time-series-csv"),
        )
        return

    # 视频时间轴事件：按视频导出区间事件 JSONL（可选 CSV）。
    # 同样放在图片空集守卫之前：video_event 数据集可能没有任何 AnnotationImageModel 行。
    # 必须传「标注任务 id」而非训练任务 id（同视频/文本/音频/时间序列导出修复）。
    if task_type == "video_event":
        await _export_video_event(
            dataset_id, output_dir, annotation_task_id=annotation_task_id,
            csv=(framework == "video-event-csv"),
        )
        return

    if not images:
        log.warning(f"export: dataset {dataset_id} has no images")
        return

    if framework == "ultralytics" or framework.startswith("yolo-"):
        if framework.startswith("yolo-"):
            task_type = framework.replace("yolo-", "")
        if task_type in ("cls", "classification"):
            await _export_yolo_cls(
                dataset_id, task_id, images, output_dir, annotation_task_id,
                train_ratio=train_ratio, class_names=class_names, for_training=for_training,
                multi_label=(classification_mode == "multi"), for_eval=for_eval,
                torchkiln_index=torchkiln_index,
            )
        elif task_type in ("semantic", "semantic_segmentation", "lane_seg"):
            await _export_yolo_semantic(
                dataset_id, task_id, images, output_dir, task_type,
                annotation_task_id, train_ratio=train_ratio,
                class_names=class_names, for_eval=for_eval,
                torchkiln_index=torchkiln_index,
            )
        elif task_type == "ocr":
            # TorchKiln 的 OCR 系只认「图片路径 + TAB + 标签」这一种清单，
            # 与 PaddleOCR 的 det/rec 布局一致，直接复用同一份转换逻辑。
            await _export_torchkiln_ocr(
                dataset_id, task_id, images, output_dir,
                annotation_task_id, train_ratio=train_ratio,
                for_eval=for_eval, export_rec=ocr_rec,
                torchkiln_index=torchkiln_index,
            )
        else:
            await _export_yolo(dataset_id, task_id, images, output_dir, task_type, annotation_task_id, train_ratio=train_ratio, class_names=class_names, for_training=for_training, for_eval=for_eval, torchkiln_index=torchkiln_index)
    elif framework == "x-anylabeling":
        await _export_x_anylabeling(dataset_id, task_id, images, output_dir, annotation_task_id, class_names=class_names)
    elif framework == "paddle-ocr":
        # 数据集下载导出 PaddleOCR 格式（det/rec 由 ocr_rec 控制）
        await _export_paddle_ocr(dataset_id, task_id, images, output_dir, annotation_task_id,
                                 export_rec=ocr_rec, train_ratio=train_ratio, for_eval=for_eval)
    elif framework == "paddle-mlcls":
        await _export_paddle_mlcls(dataset_id, task_id, images, output_dir, annotation_task_id,
                                   class_names=class_names)
    elif framework == "paddlex":
        # PaddleX OCR：ocr_rec 区分 det(false) / rec(true)
        await _export_paddle_ocr(dataset_id, task_id, images, output_dir, annotation_task_id,
                                 export_rec=ocr_rec, train_ratio=train_ratio, for_eval=for_eval)
    elif framework == "coco-panoptic":
        await _export_coco_panoptic(dataset_id, task_id, images, output_dir,
                                    annotation_task_id, class_meta=class_meta)
    else:
        raise ValueError(f"不支持的导出框架: {framework}")

    log.info(f"export {framework} to {output_dir}")


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


# 语义分割的「未标注」像素值。与 TorchKiln 的 SemDataset 对齐：
# ``cv2.imread(..., IMREAD_GRAYSCALE)`` + ``ignore_index`` 默认 255。
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
                log.warning("semantic fillPoly 失败: %s", e)
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
                    log.warning("skip %s: %s", img.filename, e)
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
                log.warning("semantic mask 写入失败 %s: %s", mask_path, e)

    if torchkiln_index:
        _write_torchkiln_index(output_dir)
    log.info(f"yolo-semantic: images={len(train_imgs) + len(val_imgs)} masks={n_mask} "
             f"classes={len(class_id_map)} → {output_dir}")


async def _export_torchkiln_ocr(
    dataset_id: int, task_id: int, images: list, output_dir: str,
    annotation_task_id: int | None = None, train_ratio: float = 0.8,
    for_eval: bool = False, export_rec: bool = False,
    torchkiln_index: bool = True,
) -> None:
    """导出 TorchKiln OCR 清单：``images/<split>/*.jpg`` + 每行 ``路径\\t标签``。

    - det（``export_rec=False``）：标签是 JSON 数组，元素 ``{"transcription", "points"}``，
      **points 是像素坐标**（TorchKiln 直接在原图分辨率上画多边形）。
    - rec（``export_rec=True``）：标签是识别文本本身。

    清单分隔符固定 ``\\t``（TorchKiln ``SimpleDataSet`` 的 ``delimiter`` 默认值），
    且**必须有第二段**——缺列会被 ``substr[1]`` 抛 IndexError 后静默丢样本。
    """
    import random

    from app.utils.s3_client import s3_client

    async with async_db_session() as db:
        anns_by_img = await _load_latest_anns_by_image(db, [img.id for img in images], annotation_task_id)

    if for_eval:
        train_imgs, val_imgs = [], list(images)
    else:
        images = list(images)
        random.shuffle(images)
        split_idx = max(1, int(len(images) * train_ratio))
        train_imgs, val_imgs = images[:split_idx], images[split_idx:]

    rows: dict[str, list[str]] = {"train": [], "val": []}
    n_img = 0
    for split_name, split_imgs in [("train", train_imgs), ("val", val_imgs)]:
        img_split = os.path.join(output_dir, "images", split_name)
        os.makedirs(img_split, exist_ok=True)
        for img in split_imgs:
            img_path = os.path.join(img_split, img.filename)
            if not os.path.exists(img_path):
                try:
                    data = s3_client.download_fileobj(img.object_key)
                    with open(img_path, "wb") as f:
                        f.write(data.read())
                except Exception as e:
                    log.warning("skip %s: %s", img.filename, e)
                    continue
            anns = anns_by_img.get(img.id, [])
            w, h = img.width or 1, img.height or 1
            rel = f"images/{split_name}/{img.filename}"
            if export_rec:
                # rec：一张图对应一段识别文本。多标注时按标注顺序拼接
                # （rec 数据集的语义是「整图一个字符串」，不是多行）。
                text = "".join(
                    (a.get("text", "") or "") for a in anns
                    if a.get("type", "") in ("Ocr", "ocr", "AxisAlignedBox", "box", "Polygon", "polygon")
                )
                if not text:
                    continue
                rows[split_name].append(f"{rel}\t{text}")
            else:
                entries = paddle_ocr_det_entries(anns, w, h)
                if not entries:
                    continue
                payload = json.dumps(entries, ensure_ascii=False)
                rows[split_name].append(f"{rel}\t{payload}")
            n_img += 1

    if torchkiln_index:
        _write_lines(os.path.join(output_dir, "train.txt"), rows["train"])
        _write_lines(os.path.join(output_dir, "val.txt"), rows["val"])
    log.info(f"torchkiln-ocr({'rec' if export_rec else 'det'}): images={n_img} → {output_dir}")


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


# COCO Panoptic 约定掩码值 0 = void/ignore，但 stuff 类 id=0 的段（pid=0）也占用 0。
# 为避免「未标注背景」像素与 stuff-0 段合并、被 COCO 消费方当作 void 丢弃，
# 用负数哨兵 _PANOPTIC_VOID 标记未标注背景（"I" 模式是有符号 int32 可存 -1，
# 且任何 category_id*1000+instance_id >= 0 都不会等于负数），保存 PNG 时再映射回 0。
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


def _extract_frames(video_path: str, fps: float, frames_dir: str) -> list[str]:
    """用 ffmpeg 按目标 fps 抽帧到 frames_dir，返回按帧号升序的本地帧文件路径。

    以 ``fps=<fps>`` 抽帧：输出帧按时间升序排列，第 N 个输出帧（0 基）即源视频
    第 N 帧，因此 ``frame_index = N``，帧号映射确定且无需额外推算。抽帧失败
    （ffmpeg 非零返回码）抛 ``CalledProcessError``，由调用方跳过该视频。
    """
    os.makedirs(frames_dir, exist_ok=True)
    out_pattern = os.path.join(frames_dir, "frame_%06d.jpg")
    subprocess.run(
        ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
         "-i", video_path, "-vf", f"fps={fps}", "-q:v", "2", out_pattern],
        capture_output=True, text=True, check=True,
    )
    names = [n for n in os.listdir(frames_dir)
             if n.startswith("frame_") and n.endswith(".jpg")]
    names.sort(key=lambda n: int(n.split("_")[-1].split(".")[0]))
    return [os.path.join(frames_dir, n) for n in names]


def _write_video_yolo(output_dir: str, samples: list, frame_anns: dict,
                      used_ids: set[int], class_names: dict,
                      train_ratio: float = 0.8,
                      for_training: bool = False, for_eval: bool = False) -> None:
    """把抽帧样本（帧图 + 该帧 AxisAlignedBox）写入 YOLO 目录布局。

    复用图片导出的 train/val 切分逻辑：非评估模式按 ``train_ratio`` 随机切分并
    shuffle，保证训练导出有一个非空的 val 子集（与图片导出行为一致）；
    ``for_eval=True`` 时全量进 val、不 shuffle，保证评估全量可复现。
    """
    import random
    import shutil

    class_id_map = build_class_mapping(used_ids)
    if for_eval:
        train_imgs, val_imgs = [], samples
    else:
        random.shuffle(samples)
        split_idx = max(1, int(len(samples) * train_ratio)) if samples else 0
        train_imgs = samples[:split_idx]
        val_imgs = samples[split_idx:]

    for split_name, split_imgs in [("train", train_imgs), ("val", val_imgs)]:
        img_split = os.path.join(output_dir, "images", split_name)
        label_split = os.path.join(output_dir, "labels", split_name)
        os.makedirs(img_split, exist_ok=True)
        os.makedirs(label_split, exist_ok=True)
        for s in split_imgs:
            dst = os.path.join(img_split, s["filename"])
            if not os.path.exists(dst):
                shutil.copyfile(s["img_path"], dst)
            anns = frame_anns.get(s["filename"], [])
            lines = _format_yolo_lines(anns, "detection", class_id_map=class_id_map,
                                       img_w=s["width"] or 1, img_h=s["height"] or 1)
            if lines:
                label_path = os.path.join(label_split,
                                          os.path.splitext(s["filename"])[0] + ".txt")
                with open(label_path, "w") as f:
                    f.write("\n".join(lines))

    base_path = "/data" if for_training else "."
    _write_yaml(os.path.join(output_dir, "dataset.yaml"), base_path,
                list(range(len(class_id_map))), class_names, class_id_map=class_id_map)


def _write_video_xany(output_dir: str, samples: list, frame_anns: dict,
                      class_names: dict) -> None:
    """把抽帧样本写入 x-anylabeling（LabelMe JSON）目录布局。"""
    import shutil

    img_dir = os.path.join(output_dir, "images")
    os.makedirs(img_dir, exist_ok=True)
    for s in samples:
        dst = os.path.join(img_dir, s["filename"])
        if not os.path.exists(dst):
            shutil.copyfile(s["img_path"], dst)
        anns = frame_anns.get(s["filename"], [])
        shapes = xany_shapes(anns, s["width"] or 0, s["height"] or 0, class_names)
        flags = xany_classification_flags(anns, class_names)
        js = {
            "version": "3.2.1",
            "flags": flags,
            "shapes": shapes,
            "imagePath": s["filename"],
            "imageData": None,
            "imageHeight": s["height"] or 0,
            "imageWidth": s["width"] or 0,
        }
        json_path = os.path.join(img_dir, os.path.splitext(s["filename"])[0] + ".json")
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(js, f, ensure_ascii=False, indent=2)


async def _export_video_detection(
    dataset_id: int, task_id: int, output_dir: str, framework: str,
    annotation_task_id: int | None = None, class_names: dict | None = None,
    train_ratio: float = 0.8, for_training: bool = False, for_eval: bool = False,
) -> None:
    """视频检测任务按帧导出：抽帧 + 逐帧标注 → 复用检测格式器。

    对数据集的每个视频：从 RustFS 下载 → ffmpeg 按视频原生 ``fps`` 抽帧到临时目录，
    输出帧按时间升序，第 N 个输出帧（0 基）对应 ``frame_index = N``；逐帧调用
    ``AnnotationService.load_video_annotations(task_id, video_id, frame_index)``
    取该帧的 AxisAlignedBox，组装为检测样本（帧图 + bbox）后交给既有检测格式器
    （YOLO / x-anylabeling）输出，帧号命名 ``<视频名>_frame_<N>.jpg``。
    抽帧/探测失败的视频跳过并告警，不阻断整次导出。
    """
    import asyncio
    import shutil
    import tempfile

    from app.api.v1.module_annotation.annotation.service import AnnotationService
    from app.api.v1.module_annotation.dataset.model import AnnotationVideoModel
    from app.utils.s3_client import s3_client

    async with async_db_session() as db:
        videos = (await db.execute(
            select(AnnotationVideoModel).where(
                AnnotationVideoModel.dataset_id == dataset_id,
                AnnotationVideoModel.is_deleted == False,  # noqa: E712
            )
        )).scalars().all()

    if not videos:
        log.warning(f"video export: dataset {dataset_id} has no videos")
        return

    samples: list[dict] = []
    frame_anns: dict[str, list] = {}
    used_ids: set[int] = set()
    used_stems: set[str] = set()
    tmp_dirs: list[str] = []

    for video in videos:
        fps = video.fps or 0
        if fps <= 0:
            log.warning(f"skip video {video.name}: fps 未知，无法确定帧号映射")
            continue
        try:
            tmp = tempfile.mkdtemp(prefix=f"video_export_{video.id}_")
            tmp_dirs.append(tmp)
            video_path = os.path.join(tmp, video.name)
            data = await asyncio.to_thread(s3_client.download_fileobj, video.object_key)
            with open(video_path, "wb") as f:
                f.write(data.read())
            frames_dir = os.path.join(tmp, "frames")
            frames = await asyncio.to_thread(_extract_frames, video_path, fps, frames_dir)
            stem = os.path.splitext(video.name)[0] or f"video_{video.id}"
            # 同名视频会撞帧文件名（覆盖/标注错配），命名冲突时用 video.id 消除歧义
            if stem in used_stems:
                stem = f"{stem}_{video.id}"
            used_stems.add(stem)
            for frame_index, frame_path in enumerate(frames):
                fname = f"{stem}_frame_{frame_index:06d}.jpg"
                # 关键：必须用「标注任务 id」而非训练任务 id 查帧标注。
                # 训练/评估路径 `_export_core(task_id=训练任务id, annotation_task_id=标注任务id)`
                # 传入的 ``task_id`` 是训练任务 id，其不在 ``annotation_task`` 中，
                # 若传给 ``load_video_annotations`` 会被 ``_verify_video_task_relation``
                # 拒绝并吞掉，导致训练/评估导出静默为空。
                anns = await AnnotationService.load_video_annotations(
                    annotation_task_id if annotation_task_id is not None else task_id,
                    video.id, frame_index,
                )
                anns = anns or []
                samples.append({
                    "filename": fname,
                    "img_path": frame_path,
                    "width": video.width or 0,
                    "height": video.height or 0,
                })
                frame_anns[fname] = anns
                for a in anns:
                    cid = a.get("class_id")
                    if cid is not None and cid != -1:
                        used_ids.add(int(cid))
        except Exception as e:  # noqa: BLE001
            log.warning(f"skip video {video.name}: {e}")

    try:
        if framework == "x-anylabeling":
            _write_video_xany(output_dir, samples, frame_anns, class_names or {})
        else:
            _write_video_yolo(output_dir, samples, frame_anns, used_ids,
                              class_names or {}, train_ratio=train_ratio,
                              for_training=for_training, for_eval=for_eval)
        log.info(f"video-detection {framework}: exported {len(samples)} frames to {output_dir}")
    finally:
        for d in tmp_dirs:
            shutil.rmtree(d, ignore_errors=True)


def _iter_sentence_spans(text: str):
    """按换行切分句子，产出 ``(句子, 句首绝对 UTF-16 偏移)``。

    偏移以 UTF-16 code unit 计（与前端/CodeMirror 一致）；每个换行符占 1 个
    code unit，逐句累加得到全局偏移，用于把文档级实体 span 映射到句内。
    """
    pos = 0
    for line in text.split("\n"):
        yield line, pos
        pos += len(line.encode("utf-16-le")) // 2 + 1


def _line_bio_tags(line: str, entities: list[dict], mode: str) -> list[str]:
    """对单个句子按句内 UTF-16 偏移计算逐字符 BIO/BIESO 标签。

    ``entities`` 为该句内实体（``start/end`` 为句内 UTF-16 偏移，含 ``label`` 名称）。
    每个字符（code point）产出一个标签，字符的 UTF-16 宽度按 BMP=1、代理对=2 累加，
    因此多 code unit 字符也能与实体偏移精确对应。``mode`` 为 ``bio`` 或 ``bieso``：
    - ``bio``：实体首字符 ``B-``，其余 ``I-``；
    - ``bieso``：单字符实体 ``S-``，多字符首 ``B-``、尾 ``E-``、中间 ``I-``。
    """
    spans: list[tuple[int, int]] = []
    pos = 0
    for ch in line:
        width = len(ch.encode("utf-16-le")) // 2
        spans.append((pos, pos + width))
        pos += width

    tags: list[str] = []
    for cs, ce in spans:
        tag = "O"
        for ent in entities:
            if ent["start"] <= cs and ce <= ent["end"]:
                first = cs == ent["start"]
                last = ce == ent["end"]
                single = (ent["end"] - ent["start"]) == (ce - cs)
                if first and last and single and mode == "bieso":
                    tag = f"S-{ent['label']}"
                elif first:
                    tag = f"B-{ent['label']}"
                elif last and mode == "bieso":
                    tag = f"E-{ent['label']}"
                else:
                    tag = f"I-{ent['label']}"
                break
        tags.append(tag)
    return tags


async def _export_text_ner(
    dataset_id: int, output_dir: str, annotation_task_id: int | None = None,
    mode: str = "bio",
) -> None:
    """文本 NER 导出：字符级 BIO/BIESO 序列 + 关系 JSONL。

    对数据集每个文档：读全文（RustFS，UTF-8）+ ``load_text_annotations`` 取标注，
    生成 ``<stem>_{document_id}.txt``（按换行分句，每句逐字符 ``字符\\t标签``，句间空行）
    与 ``<stem>_{document_id}.relations.jsonl``（每行一个关系）。
    关键：必须用「标注任务 id」而非训练任务 id 读标注——训练/评估路径经
    ``_export_core(task_id=训练任务id, annotation_task_id=标注任务id)`` 进入，误传
    训练任务 id 会被 ``_verify_document_task_relation`` 拒绝、导致标注静默为空。
    """
    import asyncio

    from app.api.v1.module_annotation.annotation.service import AnnotationService
    from app.api.v1.module_annotation.dataset.model import AnnotationDocumentModel
    from app.api.v1.module_annotation.task.model import AnnotationTaskModel
    from app.utils.s3_client import s3_client

    os.makedirs(output_dir, exist_ok=True)
    entity_names: dict[int, str] = {}
    relation_names: dict[int, str] = {}
    if annotation_task_id:
        async with async_db_session() as db:
            ann_task = await db.get(AnnotationTaskModel, annotation_task_id)
            if ann_task and isinstance(ann_task.classes, dict):
                for e in ann_task.classes.get("entities", []):
                    entity_names[int(e["id"])] = e.get("name", f"class_{e['id']}")
                for r in ann_task.classes.get("relations", []):
                    relation_names[int(r["id"])] = r.get("name", f"class_{r['id']}")

    async with async_db_session() as db:
        docs = (await db.execute(
            select(AnnotationDocumentModel).where(
                AnnotationDocumentModel.dataset_id == dataset_id,
                AnnotationDocumentModel.is_deleted == False,  # noqa: E712
            )
        )).scalars().all()

    if not docs:
        log.warning(f"text-ner export: dataset {dataset_id} has no documents")
        return

    for doc in docs:
        data = await asyncio.to_thread(s3_client.download_fileobj, doc.object_key)
        text = data.read().decode("utf-8")
        anns = await AnnotationService.load_text_annotations(annotation_task_id, doc.id)
        ann_data = anns.get("annotation_data") or []
        entities = [a for a in ann_data if a.get("type") == "EntitySpan"]
        relations = [a for a in ann_data if a.get("type") == "Relation"]

        stem = os.path.splitext(doc.filename)[0] or f"doc_{doc.id}"
        # 构造 BIO/BIESO 序列：逐句映射文档级实体到句内偏移
        blocks: list[list[str]] = []
        for sentence, abs_start in _iter_sentence_spans(text):
            if not sentence:
                continue
            line_len = len(sentence.encode("utf-16-le")) // 2
            local_entities = [
                {
                    "start": e["start"] - abs_start,
                    "end": e["end"] - abs_start,
                    "label": entity_names.get(
                        int(e["label_id"]), f"class_{e['label_id']}"
                    ),
                }
                for e in entities
                if e["start"] >= abs_start and e["end"] <= abs_start + line_len
            ]
            tags = _line_bio_tags(sentence, local_entities, mode)
            blocks.append([f"{ch}\t{tag}" for ch, tag in zip(sentence, tags, strict=True)])

        seq_lines: list[str] = []
        for i, block in enumerate(blocks):
            seq_lines.extend(block)
            if i < len(blocks) - 1:
                seq_lines.append("")
        txt_path = os.path.join(output_dir, f"{stem}_{doc.id}.txt")
        with open(txt_path, "w", encoding="utf-8") as f:
            f.write("\n".join(seq_lines) + ("\n" if seq_lines else ""))

        # 关系 JSONL：每行一个关系
        rel_path = os.path.join(output_dir, f"{stem}_{doc.id}.relations.jsonl")
        with open(rel_path, "w", encoding="utf-8") as f:
            for rel in relations:
                rt = rel.get("relation_type")
                f.write(json.dumps({
                    "from": rel.get("from"),
                    "to": rel.get("to"),
                    "relation_type": rt,
                    "label": relation_names.get(
                        int(rt), f"class_{rt}" if rt is not None else "class_None"
                    ),
                }, ensure_ascii=False) + "\n")


async def _export_audio_event(
    dataset_id: int, output_dir: str, annotation_task_id: int | None = None,
    csv: bool = False,
) -> None:
    """音频事件导出：SED 事件 JSONL（可选 CSV）。

    对数据集每个音频用 ``load_audio_annotations`` 读事件标注，生成
    ``<stem>_{audio_id}.jsonl``（每行 ``{"start","end","label"}``，秒级 float，
    label 取任务 ``classes`` 中 ``label_id`` 对应的名称）；``csv=True`` 时再产出
    ``<stem>_{audio_id}.csv``（表头 ``start,end,label``）。
    关键：必须用「标注任务 id」而非训练任务 id 读标注——训练/评估路径经
    ``_export_core(task_id=训练任务id, annotation_task_id=标注任务id)`` 进入，误传
    训练任务 id 会被 ``_verify_audio_task_relation`` 拒绝、导致标注静默为空。
    音频事件导出只依赖标注元数据，无需下载音频文件本身。
    """

    if not annotation_task_id:
        log.warning(f"audio-event export: dataset {dataset_id} has no annotation_task_id, skip")
        return

    from app.api.v1.module_annotation.annotation.service import AnnotationService
    from app.api.v1.module_annotation.dataset.model import AnnotationAudioModel
    from app.api.v1.module_annotation.task.model import AnnotationTaskModel

    os.makedirs(output_dir, exist_ok=True)
    label_names: dict[int, str] = {}
    if annotation_task_id:
        async with async_db_session() as db:
            ann_task = await db.get(AnnotationTaskModel, annotation_task_id)
            if ann_task and isinstance(ann_task.classes, list):
                for c in ann_task.classes:
                    label_names[int(c["id"])] = c.get("name", f"class_{c['id']}")

    async with async_db_session() as db:
        audios = (await db.execute(
            select(AnnotationAudioModel).where(
                AnnotationAudioModel.dataset_id == dataset_id,
                AnnotationAudioModel.is_deleted == False,  # noqa: E712
            )
        )).scalars().all()

    if not audios:
        log.warning(f"audio-event export: dataset {dataset_id} has no audios")
        return

    for audio in audios:
        anns = await AnnotationService.load_audio_annotations(annotation_task_id, audio.id)
        ann_data = anns.get("annotation_data") or []
        events = [a for a in ann_data if a.get("type") == "AudioSegment"]
        stem = os.path.splitext(audio.name)[0] or f"audio_{audio.id}"
        base = os.path.join(output_dir, f"{stem}_{audio.id}")
        with open(base + ".jsonl", "w", encoding="utf-8") as f:
            for ev in events:
                lid = ev.get("label_id")
                label = label_names.get(int(lid), f"class_{lid}")
                f.write(json.dumps({
                    "start": float(ev["start"]),
                    "end": float(ev["end"]),
                    "label": label,
                }, ensure_ascii=False) + "\n")
        if csv:
            with open(base + ".csv", "w", encoding="utf-8", newline="") as f:
                f.write("start,end,label\n")
                for ev in events:
                    lid = ev.get("label_id")
                    label = label_names.get(int(lid), f"class_{lid}")
                    f.write(f"{float(ev['start'])},{float(ev['end'])},{label}\n")


async def _export_time_series_event(
    dataset_id: int, output_dir: str, annotation_task_id: int | None = None,
    csv: bool = False,
) -> None:
    """时间序列区间事件导出：区间 JSONL（可选 CSV）。

    对数据集每个时间序列用 ``load_time_series_annotations`` 读区间标注，生成
    ``<stem>_{time_series_id}.jsonl``（每行 ``{"start","end","label"}``，start/end
    为该序列时间戳值并保留原始精度，label 取任务 ``classes`` 中 ``label_id`` 对应
    的名称）；``csv=True`` 时再产出 ``<stem>_{time_series_id}.csv``（表头
    ``start,end,label``）。
    关键：必须用「标注任务 id」而非训练任务 id 读标注——训练/评估路径经
    ``_export_core(task_id=训练任务id, annotation_task_id=标注任务id)`` 进入，误传
    训练任务 id 会被 ``_verify_time_series_task_relation`` 拒绝、导致标注静默为空。
    时间序列事件导出只依赖标注元数据，无需下载序列文件本身。
    """

    if not annotation_task_id:
        log.warning(f"time-series-event export: dataset {dataset_id} has no annotation_task_id, skip")
        return

    from app.api.v1.module_annotation.annotation.service import AnnotationService
    from app.api.v1.module_annotation.dataset.model import AnnotationTimeSeriesModel
    from app.api.v1.module_annotation.task.model import AnnotationTaskModel

    os.makedirs(output_dir, exist_ok=True)
    label_names: dict[int, str] = {}
    if annotation_task_id:
        async with async_db_session() as db:
            ann_task = await db.get(AnnotationTaskModel, annotation_task_id)
            if ann_task and isinstance(ann_task.classes, list):
                for c in ann_task.classes:
                    label_names[int(c["id"])] = c.get("name", f"class_{c['id']}")

    async with async_db_session() as db:
        series_list = (await db.execute(
            select(AnnotationTimeSeriesModel).where(
                AnnotationTimeSeriesModel.dataset_id == dataset_id,
                AnnotationTimeSeriesModel.is_deleted == False,  # noqa: E712
            )
        )).scalars().all()

    if not series_list:
        log.warning(f"time-series-event export: dataset {dataset_id} has no time series")
        return

    for series in series_list:
        anns = await AnnotationService.load_time_series_annotations(annotation_task_id, series.id)
        ann_data = anns.get("annotation_data") or []
        events = [a for a in ann_data if a.get("type") == "TimeSeriesSegment"]
        stem = os.path.splitext(series.name)[0] or f"time_series_{series.id}"
        base = os.path.join(output_dir, f"{stem}_{series.id}")
        with open(base + ".jsonl", "w", encoding="utf-8") as f:
            for ev in events:
                lid = ev.get("label_id")
                label = label_names.get(int(lid), f"class_{lid}")
                f.write(json.dumps({
                    "start": ev["start"],
                    "end": ev["end"],
                    "label": label,
                }, ensure_ascii=False) + "\n")
        if csv:
            with open(base + ".csv", "w", encoding="utf-8", newline="") as f:
                f.write("start,end,label\n")
                for ev in events:
                    lid = ev.get("label_id")
                    label = label_names.get(int(lid), f"class_{lid}")
                    f.write(f"{ev['start']},{ev['end']},{label}\n")


async def _export_video_event(
    dataset_id: int, output_dir: str, annotation_task_id: int | None = None,
    csv: bool = False,
) -> None:
    """视频时间轴事件导出：区间事件 JSONL（可选 CSV）。

    对数据集每个视频用 ``load_video_event_annotations`` 读事件标注，生成
    ``<stem>_{video_id}.jsonl``（每行 ``{"start","end","label"}``，秒级 float，
    label 取任务 ``classes`` 中 ``label_id`` 对应的名称）；``csv=True`` 时再产出
    ``<stem>_{video_id}.csv``（表头 ``start,end,label``）。
    关键：必须用「标注任务 id」而非训练任务 id 读标注——训练/评估路径经
    ``_export_core(task_id=训练任务id, annotation_task_id=标注任务id)`` 进入，误传
    训练任务 id 会被 ``_verify_video_event_task_relation`` 拒绝、导致标注静默为空。
    视频事件导出只依赖标注元数据，无需下载视频文件本身。
    """

    if not annotation_task_id:
        log.warning(f"video-event export: dataset {dataset_id} has no annotation_task_id, skip")
        return

    from app.api.v1.module_annotation.annotation.service import AnnotationService
    from app.api.v1.module_annotation.dataset.model import AnnotationVideoModel
    from app.api.v1.module_annotation.task.model import AnnotationTaskModel

    os.makedirs(output_dir, exist_ok=True)
    label_names: dict[int, str] = {}
    if annotation_task_id:
        async with async_db_session() as db:
            ann_task = await db.get(AnnotationTaskModel, annotation_task_id)
            if ann_task and isinstance(ann_task.classes, list):
                for c in ann_task.classes:
                    label_names[int(c["id"])] = c.get("name", f"class_{c['id']}")

    async with async_db_session() as db:
        videos = (await db.execute(
            select(AnnotationVideoModel).where(
                AnnotationVideoModel.dataset_id == dataset_id,
                AnnotationVideoModel.is_deleted == False,  # noqa: E712
            )
        )).scalars().all()

    if not videos:
        log.warning(f"video-event export: dataset {dataset_id} has no videos")
        return

    for video in videos:
        anns = await AnnotationService.load_video_event_annotations(annotation_task_id, video.id)
        ann_data = anns.get("annotation_data") or []
        events = [a for a in ann_data if a.get("type") == "VideoSegment"]
        stem = os.path.splitext(video.name)[0] or f"video_{video.id}"
        base = os.path.join(output_dir, f"{stem}_{video.id}")
        with open(base + ".jsonl", "w", encoding="utf-8") as f:
            for ev in events:
                lid = ev.get("label_id")
                label = label_names.get(int(lid), f"class_{lid}")
                f.write(json.dumps({
                    "start": float(ev["start"]),
                    "end": float(ev["end"]),
                    "label": label,
                }, ensure_ascii=False) + "\n")
        if csv:
            with open(base + ".csv", "w", encoding="utf-8", newline="") as f:
                f.write("start,end,label\n")
                for ev in events:
                    lid = ev.get("label_id")
                    label = label_names.get(int(lid), f"class_{lid}")
                    f.write(f"{float(ev['start'])},{float(ev['end'])},{label}\n")


async def _export_coco_panoptic(dataset_id: int, task_id: int, images: list,
                                output_dir: str, annotation_task_id: int | None = None,
                                class_meta: dict | None = None) -> None:
    """导出为 COCO Panoptic：每图一张 panoptic PNG 掩码 + panoptic.json 段表。"""
    import json

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


def _find_official_ocr_dict() -> str | None:
    """在仓库中查找官方 PP-OCRv6 词表 ppocrv6_dict.txt，找不到返回 None。"""
    here = os.path.dirname(os.path.abspath(__file__))
    preferred = os.path.join(here, "assets", "ppocrv6_dict.txt")
    if os.path.isfile(preferred):
        return preferred
    # backend/ 根：module_train → plugin → app → backend
    backend_root = os.path.abspath(os.path.join(here, "..", "..", ".."))
    skip = {".venv", "node_modules", "__pycache__", ".git", ".ruff_cache", ".pytest_cache", "data"}
    for root, dirs, files in os.walk(backend_root):
        dirs[:] = [d for d in dirs if d not in skip]
        if "ppocrv6_dict.txt" in files:
            return os.path.join(root, "ppocrv6_dict.txt")
    return None


def _crop_text_region(img_path: str, quad: list, img_w: int = 1, img_h: int = 1):
    """透视矫正裁剪文本区域（复用 paddle-ocr 的裁剪逻辑）。

    quad 为像素坐标 4 角点。返回 BGR numpy 数组（可直接 cv2.imwrite），失败返回 None。
    """
    try:
        import cv2
        import numpy as np
        src = cv2.imread(img_path)
        if src is None:
            return None
        pts = np.array(quad, dtype=np.float32)
        if len(pts) < 4:
            return None
        rect = cv2.minAreaRect(pts)
        box = np.array(cv2.boxPoints(rect), dtype=np.float32)
        width, height = int(rect[1][0]), int(rect[1][1])
        if width < 1 or height < 1:
            return None
        dst_pts = np.array([[0, 0], [width - 1, 0], [width - 1, height - 1], [0, height - 1]], dtype=np.float32)
        M = cv2.getPerspectiveTransform(box, dst_pts)
        return cv2.warpPerspective(src, M, (width, height))
    except ImportError:
        # Fallback to simple axis-aligned crop if OpenCV not available
        try:
            import numpy as np
            from PIL import Image
            xs = [p[0] for p in quad]
            ys = [p[1] for p in quad]
            x1, y1, x2, y2 = int(min(xs)), int(min(ys)), int(max(xs)), int(max(ys))
            if x2 - x1 < 1 or y2 - y1 < 1:
                return None
            pil = Image.open(img_path).convert("RGB").crop((x1, y1, x2, y2))
            return np.array(pil)[:, :, ::-1]  # RGB → BGR
        except Exception:
            return None


async def _fetch_torchkiln_weights(task_id: int, export_dir: str) -> str | None:
    """从 TorchKiln 服务拉取该任务训练出的最优权重到本地 ``export_dir``。

    为什么需要：TorchKiln 跑在**独立服务**里（可能另一台机器/另一个容器），
    权重在它自己的 ``output_dir``，本项目必须下载回来才能入 RustFS、
    下发给评估/预测。服务不可达时抛异常，由调用方降级为「本次不建版本」——
    不能因为拉不到权重就把整个训练判成失败。
    """
    import os as _os

    from .model import TrainTask as _TrainTask
    from .torchkiln_client import TorchKilnClient

    async with async_db_session() as db:
        task = await db.get(_TrainTask, task_id)
        if task is None:
            raise ValueError(f"训练任务 {task_id} 不存在")
        job_id = (task.hyperparams or {}).get("__tk_job_id")
    if not job_id:
        raise ValueError("任务没有 TorchKiln 作业 id（未启动过训练？）")

    _os.makedirs(export_dir, exist_ok=True)
    async with TorchKilnClient() as client:
        info = await client.get_job(job_id)
        if str(info.get("status")) != "succeeded":
            raise ValueError(
                "TorchKiln 作业 {} 状态为 {}，未成功，不取权重".format(
                    job_id, info.get("status")))
        dest = _os.path.join(export_dir, "best_accuracy.pth")
        await client.fetch_file(job_id, "best_accuracy.pth", dest)
    log.info(f"torchkiln weights fetched -> {dest}")
    return dest


async def export_model(task_id: int, framework: str, export_dir: str, best_metrics: dict | None = None) -> dict:
    from .model import TrainModel, TrainTask

    # 0. TorchKiln：权重在训练服务的 output_dir（可能另一台机器/容器里），
    #    先把 best_accuracy.pth 拉回本地，后续流程与其它框架一致。
    if framework == "torchkiln":
        try:
            await _fetch_torchkiln_weights(task_id, export_dir)
        except Exception as e:  # noqa: BLE001
            log.error(f"从 TorchKiln 服务拉取权重失败: {e}")
            return {"repo_id": None, "storage_path": None}

    # 1. 优先从 YOLO/PaddleX 标准输出目录找模型文件
    best_path = None
    if framework == "paddlex":
        # PaddleX OCR train.py 保存 best_accuracy/latest .pdparams 到 save_model_dir(=/output/det 或 /output/rec)
        candidates = [
            os.path.join(export_dir, "det", "best_accuracy.pdparams"),
            os.path.join(export_dir, "rec", "best_accuracy.pdparams"),
            os.path.join(export_dir, "best_accuracy.pdparams"),
            os.path.join(export_dir, "det", "latest.pdparams"),
            os.path.join(export_dir, "rec", "latest.pdparams"),
            os.path.join(export_dir, "det", "best_model", "model.pdparams"),
            os.path.join(export_dir, "rec", "best_model", "model.pdparams"),
        ]
        for p in candidates:
            if os.path.isfile(p):
                best_path = p
                break
    else:
        extensions = (
            [".pt"] if framework == "ultralytics"
            else [".pth"] if framework == "torchkiln"
            else [".pdparams"]
        )
        for ext in extensions:
            candidates = [
                os.path.join(export_dir, "exp", "weights", f"best{ext}"),
                os.path.join(export_dir, "runs", "train", "exp", "weights", f"best{ext}"),
                os.path.join(export_dir, "weights", f"best{ext}"),
                os.path.join(export_dir, f"best_accuracy{ext}"),
                os.path.join(export_dir, f"best{ext}"),
            ]
            for p in candidates:
                if os.path.isfile(p):
                    best_path = p
                    break
            if best_path:
                break
    # 2. 降级：递归搜索，但排除 .models_cache 目录
    if not best_path:
        for root, dirs, files in os.walk(export_dir):
            dirs[:] = [d for d in dirs if d != ".models_cache"]
            for f in files:
                if framework == "paddlex" and f.endswith(".pdparams"):
                    best_path = os.path.join(root, f)
                    break
                if framework == "ultralytics" and f == "best.pt":
                    best_path = os.path.join(root, f)
                    break
                if framework == "torchkiln" and f in ("best_accuracy.pth", "final.pth"):
                    best_path = os.path.join(root, f)
                    break
            if best_path:
                break

    storage_path = None
    if best_path:
        rustfs_path = f"train/models/task_{task_id}/{os.path.basename(best_path)}"
        try:
            from app.utils.s3_client import s3_client
            with open(best_path, "rb") as f:
                s3_client.upload_fileobj(f, rustfs_path)
            storage_path = rustfs_path
        except Exception as e:
            log.error(f"upload model to RustFS failed: {e}，本次不创建模型版本")

    # 无训练产物（未找到 best_path 或上传失败）时直接返回，不写 DB：
    # 否则会在模型仓库留下一条无权重的最新版本，并污染 task.model_repo_id。
    if not storage_path:
        return {"repo_id": None, "storage_path": None}

    async with async_db_session.begin() as db:
        task = await db.get(TrainTask, task_id)
        if not task:
            return {"repo_id": None, "storage_path": storage_path}

        existing = await db.execute(
            select(TrainModel).where(TrainModel.name == task.name).order_by(TrainModel.id.desc()).limit(1)
        )
        last = existing.scalar_one_or_none()
        next_ver = 1
        if last and last.version:
            from .service import TrainService
            next_ver = TrainService._parse_version(last.version) + 1

        repo = (await db.execute(
            select(TrainModelRepo).where(TrainModelRepo.name == task.name)
        )).scalar_one_or_none()
        if not repo:
            repo = TrainModelRepo(name=task.name, framework=task.framework, created_id=task.created_id)
            db.add(repo)
            await db.flush()

        model_rec = TrainModel(
            repo_id=repo.id, name=task.name, framework=task.framework,
            version=f"v{next_ver}", storage_path=storage_path,
            format="pytorch",  # Original format is PyTorch
            annotation_dataset_id=task.dataset_id, created_id=task.created_id,
            metrics=best_metrics if best_metrics is not None else task.best_metrics,
        )
        db.add(model_rec)
        await db.flush()
        repo.latest_version_id = model_rec.id
        task.model_repo_id = model_rec.id

    return {"repo_id": model_rec.id, "storage_path": storage_path}


async def _export_paddle_ocr(dataset_id: int, task_id: int, images: list,
                             output_dir: str, annotation_task_id: int | None = None,
                             export_rec: bool = False, train_ratio: float = 0.8,
                             for_eval: bool = False) -> None:
    """导出 PaddleX OCR（PP-OCRv6）数据格式。

    det 始终导出：<output>/det/dataset/  (train.txt + val.txt + images/)  PaddleX JSON 标注。
    export_rec=True 时额外导出 rec：<output>/rec/dataset/  (train.txt + val.txt + images/)
    与词表 <output>/rec/dict.txt（优先官方 ppocrv6_dict.txt）。

    for_eval=True 时全部记录进 val.txt、train.txt 为空（评估全量可复现）。
    """
    import random

    from app.utils.s3_client import s3_client

    det_dataset_dir = os.path.join(output_dir, "det", "dataset")
    det_img_dir = os.path.join(det_dataset_dir, "images")
    os.makedirs(det_img_dir, exist_ok=True)

    # 收集所有图像 + 标注（det 条目统一由 paddle_ocr_det_entries 生成，含矩形）
    records = []  # (img_name, det_entries, rec_entries[(points, text)])
    async with async_db_session() as db:
        # 批量 IN 查出全部图片标注，避免逐图 N+1
        anns_by_img = await _load_latest_anns_by_image(db, [img.id for img in images], annotation_task_id)
        for img in images:
            img_path = os.path.join(det_img_dir, img.filename)
            try:
                if not os.path.exists(img_path):
                    data = s3_client.download_fileobj(img.object_key)
                    with open(img_path, "wb") as f:
                        f.write(data.read())
            except Exception:
                continue

            anns = anns_by_img.get(img.id, [])

            det_entries = paddle_ocr_det_entries(anns, img.width or 1, img.height or 1)
            rec_entries = [(e["points"], e["transcription"])
                           for e in det_entries if (e["transcription"] or "").strip()]
            records.append((img.filename, det_entries, rec_entries))

    if for_eval:
        # 评估：全部进 val、不 shuffle
        train_set, val_set = [], records
    else:
        random.shuffle(records)
        split_idx = max(1, int(len(records) * train_ratio)) if len(records) > 1 else len(records)
        train_set, val_set = records[:split_idx], records[split_idx:]

    def write_det_label(path: str, rows: list) -> None:
        lines = []
        for fname, entries, _rec in rows:
            if entries:
                lines.append(f"images/{fname}\t{json.dumps(entries, ensure_ascii=False)}")
        with open(path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))

    # det 始终导出
    write_det_label(os.path.join(det_dataset_dir, "train.txt"), train_set)
    write_det_label(os.path.join(det_dataset_dir, "val.txt"), val_set)
    log.info(f"paddlex det: exported {len(train_set)} train / {len(val_set)} val to {det_dataset_dir}")

    if not export_rec:
        return

    # rec：从 det 图像透视矫正裁剪文字区域（cv2 延迟导入，无 cv2 时仅 rec 分支失败）
    import cv2

    rec_dataset_dir = os.path.join(output_dir, "rec", "dataset")
    rec_img_dir = os.path.join(rec_dataset_dir, "images")
    os.makedirs(rec_img_dir, exist_ok=True)

    def crop_rec(rows: list) -> list[str]:
        lines: list[str] = []
        for fname, _entries, rec_entries in rows:
            base = os.path.splitext(fname)[0]
            for i, (quad, text) in enumerate(rec_entries):
                if not text.strip():
                    continue
                crop = _crop_text_region(os.path.join(det_img_dir, fname), quad)
                if crop is None:
                    continue
                crop_name = f"{base}_{i}.jpg"
                cv2.imwrite(os.path.join(rec_img_dir, crop_name), crop)
                lines.append(f"images/{crop_name}\t{text}")
        return lines

    rec_train = crop_rec(train_set)
    rec_val = crop_rec(val_set)
    with open(os.path.join(rec_dataset_dir, "train.txt"), "w", encoding="utf-8") as f:
        f.write("\n".join(rec_train))
    with open(os.path.join(rec_dataset_dir, "val.txt"), "w", encoding="utf-8") as f:
        f.write("\n".join(rec_val))

    # 词表：优先官方 ppocrv6_dict.txt（与官方预训练权重匹配），否则退化为数据字符集
    dict_path = os.path.join(output_dir, "rec", "dict.txt")
    official_dict = _find_official_ocr_dict()
    if official_dict:
        import shutil
        shutil.copyfile(official_dict, dict_path)
        log.info(f"paddlex rec: 使用官方词表 {official_dict} → {dict_path}")
    else:
        chars: list[str] = []
        seen: set[str] = set()
        for _fname, _entries, rec_entries in records:
            for _quad, text in rec_entries:
                for ch in text:
                    if ch not in seen:
                        seen.add(ch)
                        chars.append(ch)
        with open(dict_path, "w", encoding="utf-8") as f:
            f.write("\n".join(chars))
        log.warning(
            "paddlex rec: 未找到官方 ppocrv6_dict.txt，词表退化为数据字符集"
            f"（{len(chars)} 字），可能不与官方预训练权重匹配"
        )

    log.info(f"paddlex rec: exported {len(rec_train)} train / {len(rec_val)} val to {rec_dataset_dir}")


async def _export_paddle_mlcls(dataset_id: int, task_id: int, images: list, output_dir: str,
                               annotation_task_id: int | None = None,
                               class_names: dict | None = None) -> None:
    """导出多标签分类到 Paddle MLCLS 格式（train_list.txt：每行 image_path + 多个 class_id）。"""
    import random

    from app.utils.s3_client import s3_client

    img_dir = os.path.join(output_dir, "images")
    os.makedirs(img_dir, exist_ok=True)
    lines = []

    async with async_db_session() as db:
        # 批量 IN 查出全部图片标注，避免逐图 N+1
        anns_by_img = await _load_latest_anns_by_image(db, [img.id for img in images], annotation_task_id)
        for img in images:
            img_path = os.path.join(img_dir, img.filename)
            try:
                if not os.path.exists(img_path):
                    data = s3_client.download_fileobj(img.object_key)
                    with open(img_path, "wb") as f:
                        f.write(data.read())
            except Exception:
                continue

            anns = anns_by_img.get(img.id, [])

            class_ids = []
            for ann in anns:
                cid = ann.get("class_id")
                if cid is not None and cid != -1:
                    class_ids.append(str(cid))
                if isinstance(ann.get("class_ids"), list):
                    for c in ann["class_ids"]:
                        if c is not None and c != -1:
                            class_ids.append(str(c))
            if class_ids:
                # 去重保持顺序
                seen = set()
                uniq = [c for c in class_ids if not (c in seen or seen.add(c))]
                lines.append(f"{img.filename} {' '.join(uniq)}")

    random.shuffle(lines)
    label_file = os.path.join(img_dir, "train_list.txt")
    with open(label_file, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    log.info(f"paddle-mlcls: exported {len(lines)} labeled images to {output_dir}")
