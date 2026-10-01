"""视频检测按帧导出测试。

验证：对视频任务导出时逐视频 ffmpeg 抽帧，逐帧取标注组装为标准检测样本，
复用既有 YOLO / x-anylabeling 格式器输出，帧号命名（``<视频名>_frame_<N>.jpg``）。
抽帧与 ``load_video_annotations`` 全部 mock，外部调用（s3/ffmpeg）与既有导出
测试一致不做真实执行。
"""
import asyncio
import os
from io import BytesIO

from app.api.v1.module_annotation.annotation.service import AnnotationService
from app.api.v1.module_annotation.dataset.model import (
    AnnotationType,
    AnnotationVideoModel,
    DatasetModel,
)
from app.api.v1.module_annotation.task.model import AnnotationTaskModel
from app.core.database import async_db_session
from app.plugin.module_train.exporter import _export_core, _export_video_detection
from app.plugin.module_train.exporters import video


def _make_video() -> tuple[int, int]:
    """建数据集 + 视频行，返回 (dataset_id, video_id)。"""

    async def _run():
        async with async_db_session.begin() as db:
            ds = DatasetModel(name="视频导出集")
            db.add(ds)
            await db.flush()
            video = AnnotationVideoModel(
                dataset_id=ds.id,
                name="demo.mp4",
                object_key="demo.mp4",
                width=1920,
                height=1080,
                duration=10.0,
                fps=25.0,
                frame_count=250,
                status="unannotated",
            )
            db.add(video)
            await db.flush()
            return ds.id, video.id

    return asyncio.run(_run())


def _make_video_with_task() -> tuple[int, int, int]:
    """建数据集 + 视频 + video_detection 标注任务（无 AnnotationImageModel 行），
    返回 (dataset_id, video_id, task_id)。"""

    async def _run():
        async with async_db_session.begin() as db:
            ds = DatasetModel(name="视频导出入口集")
            db.add(ds)
            await db.flush()
            video = AnnotationVideoModel(
                dataset_id=ds.id,
                name="demo.mp4",
                object_key="demo.mp4",
                width=1920,
                height=1080,
                duration=10.0,
                fps=25.0,
                frame_count=250,
                status="unannotated",
            )
            db.add(video)
            await db.flush()
            task = AnnotationTaskModel(
                dataset_id=ds.id,
                name="视频检测任务",
                task_type=AnnotationType.VIDEO_DETECTION,
                classes=[{"id": 0, "name": "cat"}],
            )
            db.add(task)
            await db.flush()
            return ds.id, video.id, task.id

    return asyncio.run(_run())


def _fake_extract(video_path, fps, out_dir):
    """模拟 ffmpeg 抽帧：生成 3 张假帧文件并返回按帧号升序的路径列表。"""
    os.makedirs(out_dir, exist_ok=True)
    paths = []
    for i in range(3):
        p = os.path.join(out_dir, f"frame_{i + 1:06d}.jpg")
        with open(p, "wb") as f:
            f.write(b"fake-image")
        paths.append(p)
    return paths


def _patch_video_mocks(monkeypatch):
    """打桩抽帧 / 下载 / 逐帧标注的可复用夹具。"""
    ds_id, video_id = _make_video()
    boxes = [
        {"type": "AxisAlignedBox", "class_id": 0,
         "x1": 0.1, "y1": 0.1, "x2": 0.2, "y2": 0.2},
        {"type": "AxisAlignedBox", "class_id": 0,
         "x1": 0.5, "y1": 0.5, "x2": 0.8, "y2": 0.9},
    ]

    async def _load(task_id, v_id, frame_index):
        # 仅第 1 帧有标注，其余帧无标注
        return boxes if frame_index == 1 else []

    monkeypatch.setattr(AnnotationService, "load_video_annotations", _load)
    monkeypatch.setattr(video, "_extract_frames", _fake_extract)

    from app.utils.s3_client import s3_client
    monkeypatch.setattr(
        s3_client, "download_fileobj", lambda key: BytesIO(b"fake-video")
    )
    return ds_id, video_id, boxes


def test_video_export_yolo_frames(monkeypatch, tmp_path):
    """YOLO：抽帧 + 逐帧 bbox 写入，帧号命名。"""
    ds_id, video_id, boxes = _patch_video_mocks(monkeypatch)
    out = str(tmp_path / "out")

    asyncio.run(_export_video_detection(
        ds_id, 5, out, "ultralytics",
        annotation_task_id=5, class_names={0: "cat"}, train_ratio=1.0,
    ))

    img_dir = os.path.join(out, "images", "train")
    lbl_dir = os.path.join(out, "labels", "train")
    # 三帧均导出（帧号命名）
    for n in (0, 1, 2):
        assert os.path.exists(os.path.join(img_dir, f"demo_frame_{n:06d}.jpg"))
    # 仅第 1 帧有标注 → 生成 label 文件
    lbl = os.path.join(lbl_dir, "demo_frame_000001.txt")
    assert os.path.exists(lbl)
    lines = open(lbl, encoding="utf-8").read().strip().splitlines()
    assert len(lines) == 2
    for line in lines:
        parts = line.split()
        # cls + cx cy w h（归一化），类 id 连续化后为 0
        assert parts[0] == "0"
        assert len(parts) == 5
    # 无标注帧不产生 label 文件
    assert not os.path.exists(os.path.join(lbl_dir, "demo_frame_000000.txt"))
    # 类名映射进 dataset.yaml
    yaml_text = open(os.path.join(out, "dataset.yaml"), encoding="utf-8").read()
    assert '"0": "cat"' in yaml_text


def test_video_export_xanylabeling_frames(monkeypatch, tmp_path):
    """x-anylabeling：逐帧 JSON sidecar + 帧号命名。"""
    ds_id, video_id, boxes = _patch_video_mocks(monkeypatch)
    out = str(tmp_path / "outxany")

    asyncio.run(_export_video_detection(
        ds_id, 5, out, "x-anylabeling",
        annotation_task_id=5, class_names={0: "cat"},
    ))

    img_dir = os.path.join(out, "images")
    for n in (0, 1, 2):
        assert os.path.exists(os.path.join(img_dir, f"demo_frame_{n:06d}.jpg"))
    import json
    js = json.load(open(os.path.join(img_dir, "demo_frame_000001.json"),
                        encoding="utf-8"))
    assert js["imagePath"] == "demo_frame_000001.jpg"
    assert len(js["shapes"]) == 2
    assert all(s["shape_type"] == "rectangle" and s["label"] == "cat"
               for s in js["shapes"])
    # 无标注帧的 JSON shapes 为空
    js0 = json.load(open(os.path.join(img_dir, "demo_frame_000000.json"),
                         encoding="utf-8"))
    assert js0["shapes"] == []


def test_video_export_skips_unknown_fps_video(monkeypatch, tmp_path):
    """fps 未知的视频应跳过并告警，不阻断导出。"""
    ds_id, video_id = _make_video()
    # 把视频 fps 置 0 模拟无法确定帧号映射

    async def _zero_fps(vid: int):
        async with async_db_session.begin() as db:
            v = await db.get(AnnotationVideoModel, vid)
            v.fps = 0.0

    asyncio.run(_zero_fps(video_id))

    monkeypatch.setattr(AnnotationService, "load_video_annotations",
                        lambda *a, **k: _async_noop())
    monkeypatch.setattr(video, "_extract_frames", _fake_extract)
    from app.utils.s3_client import s3_client
    monkeypatch.setattr(s3_client, "download_fileobj",
                        lambda key: BytesIO(b"fake-video"))

    out = str(tmp_path / "outskip")
    asyncio.run(_export_video_detection(
        ds_id, 5, out, "ultralytics",
        annotation_task_id=5, class_names={0: "cat"},
    ))
    # 无帧导出
    img_dir = os.path.join(out, "images", "train")
    assert not os.path.exists(img_dir) or not os.listdir(img_dir)


def test_video_export_through_core_entry(monkeypatch, tmp_path):
    """真实入口 `_export_core`：video-only 数据集（无 AnnotationImageModel 行）应走到视频导出。

    回归 Critical：图片空集守卫若在视频分支之前 return，视频导出永远不会执行。
    """
    ds_id, video_id, task_id = _make_video_with_task()

    async def _load(task_id, v_id, frame_index):
        # 仅第 1 帧有标注，其余帧无标注
        if frame_index == 1:
            return [
                {"type": "AxisAlignedBox", "class_id": 0,
                 "x1": 0.1, "y1": 0.1, "x2": 0.2, "y2": 0.2},
            ]
        return []

    monkeypatch.setattr(AnnotationService, "load_video_annotations", _load)
    monkeypatch.setattr(video, "_extract_frames", _fake_extract)
    from app.utils.s3_client import s3_client
    monkeypatch.setattr(s3_client, "download_fileobj",
                        lambda key: BytesIO(b"fake-video"))

    out = str(tmp_path / "outcore")
    asyncio.run(_export_core(
        ds_id, task_id, "ultralytics", out, annotation_task_id=task_id,
        train_ratio=1.0,
    ))

    img_dir = os.path.join(out, "images", "train")
    lbl_dir = os.path.join(out, "labels", "train")
    for n in (0, 1, 2):
        assert os.path.exists(os.path.join(img_dir, f"demo_frame_{n:06d}.jpg"))
    # 仅第 1 帧有标注 → 生成 label 文件（证明确实走了视频导出而非提前 return）
    assert os.path.exists(os.path.join(lbl_dir, "demo_frame_000001.txt"))


async def _async_noop():
    return []


def test_video_export_training_path_uses_annotation_task_id(monkeypatch, tmp_path):
    """训练式路径回归：传入的训练任务 id 与标注任务 id 不同。

    训练/评估 pipeline 通过 ``_export_core(task_id=训练任务id, annotation_task_id=标注任务id)``
    进入；逐帧标注查询必须用「标注任务 id」，否则 ``_verify_video_task_relation`` 拒绝、
    被逐视频 try/except 吞掉 → 静默空导出。断言实际传给 ``load_video_annotations``
    的确实是标注任务 id，且帧确实被导出（非空）。
    """
    ds_id, video_id, ann_task_id = _make_video_with_task()
    train_task_id = 9999  # 模拟训练任务 id，与标注任务 id 不同

    seen_ids: list[int] = []

    async def _load(task_id, v_id, frame_index):
        seen_ids.append(task_id)
        if frame_index == 1:
            return [{"type": "AxisAlignedBox", "class_id": 0,
                     "x1": 0.1, "y1": 0.1, "x2": 0.2, "y2": 0.2}]
        return []

    monkeypatch.setattr(AnnotationService, "load_video_annotations", _load)
    monkeypatch.setattr(video, "_extract_frames", _fake_extract)
    from app.utils.s3_client import s3_client
    monkeypatch.setattr(s3_client, "download_fileobj",
                        lambda key: BytesIO(b"fake-video"))

    out = str(tmp_path / "outtrain")
    asyncio.run(_export_video_detection(
        ds_id, train_task_id, out, "ultralytics",
        annotation_task_id=ann_task_id, class_names={0: "cat"},
        train_ratio=1.0,
    ))

    # 逐帧标注查询必须命中标注任务 id
    assert seen_ids and all(i == ann_task_id for i in seen_ids), seen_ids
    # 帧确实被导出（否则 load 失败被吞掉会返回空）
    img_dir = os.path.join(out, "images", "train")
    for n in (0, 1, 2):
        assert os.path.exists(os.path.join(img_dir, f"demo_frame_{n:06d}.jpg"))
    assert os.path.exists(os.path.join(
        out, "labels", "train", "demo_frame_000001.txt"))


def test_video_export_training_split(monkeypatch, tmp_path):
    """训练导出应用 train/val 切分（honor train_ratio），否则 val 目录为空。

    回归：图片导出按 train_ratio 切分，而视频导出原先把帧全丢进 train，导致
    ``val`` 目录为空、``dataset.yaml`` 指向空 val。现在应与图片行为一致。
    """
    ds_id, video_id = _make_video()

    async def _load(task_id, v_id, frame_index):
        if frame_index == 1:
            return [{"type": "AxisAlignedBox", "class_id": 0,
                     "x1": 0.1, "y1": 0.1, "x2": 0.2, "y2": 0.2}]
        return []

    monkeypatch.setattr(AnnotationService, "load_video_annotations", _load)
    monkeypatch.setattr(video, "_extract_frames", _fake_extract)
    from app.utils.s3_client import s3_client
    monkeypatch.setattr(s3_client, "download_fileobj",
                        lambda key: BytesIO(b"fake-video"))

    out = str(tmp_path / "outsplit")
    asyncio.run(_export_video_detection(
        ds_id, 5, out, "ultralytics",
        annotation_task_id=5, class_names={0: "cat"}, train_ratio=0.5,
    ))

    train_dir = os.path.join(out, "images", "train")
    val_dir = os.path.join(out, "images", "val")
    train_files = [f for f in os.listdir(train_dir) if f.endswith(".jpg")]
    val_files = [f for f in os.listdir(val_dir) if f.endswith(".jpg")]
    # train_ratio=0.5 且 3 帧 → split_idx = max(1, int(3*0.5)) = 1，两侧均有帧
    assert train_files, "train 目录不应为空"
    assert val_files, "val 目录不应为空（train/val 切分未生效）"
    assert len(train_files) + len(val_files) == 3


def test_video_export_eval_all_to_val(monkeypatch, tmp_path):
    """评估导出（for_eval=True）应全量进 val，不 shuffle、不切分。"""
    ds_id, video_id = _make_video()

    async def _load(task_id, v_id, frame_index):
        return [{"type": "AxisAlignedBox", "class_id": 0,
                 "x1": 0.1, "y1": 0.1, "x2": 0.2, "y2": 0.2}]

    monkeypatch.setattr(AnnotationService, "load_video_annotations", _load)
    monkeypatch.setattr(video, "_extract_frames", _fake_extract)
    from app.utils.s3_client import s3_client
    monkeypatch.setattr(s3_client, "download_fileobj",
                        lambda key: BytesIO(b"fake-video"))

    out = str(tmp_path / "outeval")
    asyncio.run(_export_video_detection(
        ds_id, 5, out, "ultralytics",
        annotation_task_id=5, class_names={0: "cat"},
        train_ratio=0.5, for_eval=True,
    ))

    val_dir = os.path.join(out, "images", "val")
    train_dir = os.path.join(out, "images", "train")
    assert len([f for f in os.listdir(val_dir) if f.endswith(".jpg")]) == 3
    assert not os.listdir(train_dir)
