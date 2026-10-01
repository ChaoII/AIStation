"""PaddleOCR / Paddle MLCLS 数据格式导出。

⚠️ 这是**数据集可移植格式**（把标注导给外部工具用），不是 PaddleX 训练通路——
后者已退场。保留理由与 ``exporter.py`` 中的 ``paddle-ocr`` 分支相同。

由原 ``exporter.py`` 拆分而来（原文件 2291 行，混合了数据集导出、模型权重入库、
DB 访问与 S3 操作四类职责）。拆分依据是模块内定义的**依赖 DAG**——先验证过
无强连通分量，故按拓扑序切分不会产生循环导入。

函数体**逐字节原样搬运**，未做任何编辑；拆分后用 ast.dump 逐个比对确认一致。
"""

import json
import os

from app.core.database import async_db_session
from app.core.logger import log

from .common import _load_latest_anns_by_image, paddle_ocr_det_entries


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
            "paddleocr rec: 未找到官方 ppocrv6_dict.txt，词表退化为数据字符集"
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
