"""TorchKiln OCR 导出（复用 PaddleOCR 标注格式，产出 TorchKiln 清单）

由原 ``exporter.py`` 拆分而来（原文件 2291 行，混合了数据集导出、模型权重入库、
DB 访问与 S3 操作四类职责）。拆分依据是模块内定义的**依赖 DAG**——先验证过
无强连通分量，故按拓扑序切分不会产生循环导入。

函数体**逐字节原样搬运**，未做任何编辑；拆分后用 ast.dump 逐个比对确认一致。
"""

import json
import os

from app.core.database import async_db_session
from app.core.logger import log

from .common import _load_latest_anns_by_image, _write_lines, paddle_ocr_det_entries


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
                    log.warning("skip {}: {}", img.filename, e)
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
