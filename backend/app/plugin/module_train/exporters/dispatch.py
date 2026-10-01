"""Layer 2 · 入口与格式分发：训练 / 评估 / 数据集下载三条入口

由原 ``exporter.py`` 拆分而来（原文件 2291 行，混合了数据集导出、模型权重入库、
DB 访问与 S3 操作四类职责）。拆分依据是模块内定义的**依赖 DAG**——先验证过
无强连通分量，故按拓扑序切分不会产生循环导入。

函数体**逐字节原样搬运**，未做任何编辑；拆分后用 ast.dump 逐个比对确认一致。
"""

import os

from sqlalchemy import select

from app.api.v1.module_annotation.dataset.model import (
    AnnotationImageModel,
)
from app.core.database import async_db_session
from app.core.logger import log

from .common import YOLO_LAYOUT
from .events import (
    _export_audio_event,
    _export_text_ner,
    _export_time_series_event,
    _export_video_event,
)
from .mono3d import _export_mono3d
from .paddle import _export_paddle_mlcls, _export_paddle_ocr
from .semantic import _export_coco_panoptic, _export_yolo_semantic
from .torchkiln_ocr import _export_torchkiln_ocr
from .video import _export_video_detection
from .xanylabeling import _export_x_anylabeling
from .yolo import _export_yolo, _export_yolo_cls


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
    """Core export logic shared by training and download.

    ``format`` 额外认 ``torchkiln-<任务类型>`` 前缀（如
    ``torchkiln-segmentation``）：它等价于 ``yolo-<任务类型>``，并**强制**生成
    TorchKiln 的 ``train.txt`` / ``val.txt`` 清单。

    为什么需要这个前缀：TorchKiln 的数据集就是「YOLO 文本标签 + 清单」，而清单
    每行的写法**按任务不同**——检测/旋转框/分割/关键点/语义分割是纯图片路径、
    分类是「路径 类下标」、OCR det 是「路径\\t四点 JSON」、OCR rec 是「路径\\t整图
    文本」（完整对照表见 :func:`prepare_training_data_for_task`）。下载导出原本
    只能选 ``yolo-*``，拿到的目录没有清单，用户得在 TorchKiln 侧自己拼；而拼错
    （漏清单、清单分隔符写错）**不会报错**，只是训练读到 0 个样本。
    """
    if framework.startswith("torchkiln-"):
        framework = "yolo-" + framework[len("torchkiln-"):]
        torchkiln_index = True

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

    # ⚠️ 这里的 "ultralytics" 是**数据布局名**（见 YOLO_LAYOUT），不是已退场的
    # 训练框架。TorchKiln 的标注数据复用 YOLO 目录结构（images/ + labels/ +
    # train.txt），所以调用方也传这个值来选布局。Ultralytics 作为训练框架已退场，
    # 本分支只负责摆文件。
    if framework == YOLO_LAYOUT or framework.startswith("yolo-"):
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
        elif task_type in ("cuboid", "det3d", "mono3d"):
            await _export_mono3d(
                dataset_id, task_id, images, output_dir,
                annotation_task_id, train_ratio=train_ratio,
                class_names=class_names, for_eval=for_eval,
                torchkiln_index=torchkiln_index,
            )
        else:
            await _export_yolo(dataset_id, task_id, images, output_dir, task_type, annotation_task_id, train_ratio=train_ratio, class_names=class_names, for_training=for_training, for_eval=for_eval, torchkiln_index=torchkiln_index)
    elif framework == "x-anylabeling":
        await _export_x_anylabeling(dataset_id, task_id, images, output_dir, annotation_task_id, class_names=class_names)
    elif framework == "paddle-ocr":
        # 数据集下载导出 PaddleOCR 格式（det/rec 由 ocr_rec 控制）。
        # ⚠️ 这不是 PaddleX **训练**通路：它是"把数据集导成 PaddleOCR 标注格式给外部
        # 工具用"的能力，与 X-AnyLabeling / COCO Panoptic 同属数据可移植格式，
        # 因此 PaddleX 训练退场后**保留**。原先还有一个完全重复的 `paddlex`
        # 分支指向同一函数，那是训练侧的别名，已移除。
        await _export_paddle_ocr(dataset_id, task_id, images, output_dir, annotation_task_id,
                                 export_rec=ocr_rec, train_ratio=train_ratio, for_eval=for_eval)
    elif framework == "paddle-mlcls":
        await _export_paddle_mlcls(dataset_id, task_id, images, output_dir, annotation_task_id,
                                   class_names=class_names)
    elif framework == "coco-panoptic":
        await _export_coco_panoptic(dataset_id, task_id, images, output_dir,
                                    annotation_task_id, class_meta=class_meta)
    else:
        raise ValueError(f"不支持的导出框架: {framework}")

    log.info(f"export {framework} to {output_dir}")
