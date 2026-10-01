"""视频检测导出：ffmpeg 抽帧后复用检测 / JSON 格式器

由原 ``exporter.py`` 拆分而来（原文件 2291 行，混合了数据集导出、模型权重入库、
DB 访问与 S3 操作四类职责）。拆分依据是模块内定义的**依赖 DAG**——先验证过
无强连通分量，故按拓扑序切分不会产生循环导入。

函数体**逐字节原样搬运**，未做任何编辑；拆分后用 ast.dump 逐个比对确认一致。
"""

import json
import os
import subprocess

from sqlalchemy import select

from app.core.database import async_db_session
from app.core.logger import log

from .common import _write_yaml, build_class_mapping
from .xanylabeling import xany_classification_flags, xany_shapes
from .yolo import _format_yolo_lines


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
