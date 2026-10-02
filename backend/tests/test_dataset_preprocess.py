"""数据落地（抽帧/清洗）模块测试。"""
import time
from uuid import uuid4

import numpy as np


# ── 纯函数：感知哈希 / 抽帧 / 清洗判定 ─────────────────────────────────
def test_phash_similar_images_near():
    from app.api.v1.module_annotation.dataset.preprocess.frames import (
        frame_from_image,
        hamming,
    )

    # 用不同纹理构造 image
    fa = frame_from_image(_textured(64, 64, seed=1))
    fb = frame_from_image(_textured(64, 64, seed=1))
    fc = frame_from_image(_textured(64, 64, seed=999))
    assert fa and fb and fc
    # 同 seed → 完全一致内容哈希 + 感知哈希为 0
    assert fa.content_hash == fb.content_hash
    assert hamming(fa.phash, fb.phash) == 0
    # 不同内容 → 感知哈希距离应较大（> 阈值）
    assert hamming(fa.phash, fc.phash) > 6


def test_extract_video_frames_interval():
    from app.api.v1.module_annotation.dataset.preprocess.config import ExtractConfig
    from app.api.v1.module_annotation.dataset.preprocess.frames import (
        extract_video_frames,
    )

    path = _write_video(seconds=3, fps=10)
    frames = extract_video_frames(
        path, ExtractConfig(interval_seconds=1.0, max_frames=0, scene_change=False)
    )
    # 10fps、间隔1s → 首帧 + 每10帧 → 约 3~4 帧
    assert 3 <= len(frames) <= 4
    assert all(f.width == 64 and f.height == 48 for f in frames)
    _cleanup(path)


def test_extract_video_frames_max_cap():
    from app.api.v1.module_annotation.dataset.preprocess.config import ExtractConfig
    from app.api.v1.module_annotation.dataset.preprocess.frames import (
        extract_video_frames,
    )

    path = _write_video(seconds=3, fps=10)
    frames = extract_video_frames(
        path, ExtractConfig(interval_seconds=0.2, max_frames=5, scene_change=False)
    )
    assert len(frames) == 5
    _cleanup(path)


def test_decide_reason_priority():
    from app.api.v1.module_annotation.dataset.preprocess.config import CleaningConfig
    from app.api.v1.module_annotation.dataset.preprocess.frames import (
        FrameInfo,
        decide_reason,
    )

    cfg = CleaningConfig(min_side=320, blur_variance=30.0,
                         brightness_min=20.0, brightness_max=240.0, phash_threshold=6)

    def _info(w=640, h=480, bright=128, blur=500, ph=1, hsh="h1"):
        return FrameInfo(0, 0.0, b"", w, h, bright, blur, ph, hsh)

    seen, plist = set(), []
    # 太小
    assert decide_reason(_info(w=100, h=100), cfg, seen, plist) == "too_small"
    # 模糊
    assert decide_reason(_info(blur=5), cfg, seen, plist) == "blur"
    # 黑暗
    assert decide_reason(_info(bright=5), cfg, seen, plist) == "dark"
    # 过曝
    assert decide_reason(_info(bright=250), cfg, seen, plist) == "bright"
    # 内容哈希重复
    assert decide_reason(_info(hsh="dup", ph=0), cfg, seen, plist) is None
    assert decide_reason(_info(hsh="dup"), cfg, seen, plist) == "duplicate"
    # 感知哈希近重复
    assert decide_reason(_info(hsh="a", ph=63), cfg, seen, plist) == "duplicate"
    assert decide_reason(_info(hsh="b", ph=127), cfg, seen, plist) is None


def test_config_parsing_defaults_and_invalid():
    from app.api.v1.module_annotation.dataset.preprocess.config import (
        CleaningConfig,
        ExtractConfig,
    )

    ec = ExtractConfig.from_params(interval="abc", max_frames="5", scene_change="true")
    assert ec.interval_seconds == 1.0  # 非法回退默认
    assert ec.max_frames == 5
    assert ec.scene_change is True

    cc = CleaningConfig.from_params(min_side="0", blur="0", phash="0")
    assert cc.min_side == 0
    assert cc.blur_variance == 0.0
    assert cc.phash_threshold == 0


# ── 集成：图片清洗入库（后台任务轮询）──────────────────────────────────
def test_images_preprocess_ingests_and_dedups(test_client, auth_headers, monkeypatch):
    monkeypatch.setattr("app.utils.s3_client.s3_client.ensure_bucket", lambda *a, **k: None)
    monkeypatch.setattr("app.utils.s3_client.s3_client.upload_fileobj", lambda *a, **k: None)

    ds = test_client.post(
        "/api/v1/annotation/dataset/create",
        json={"name": f"pre-{uuid4().hex[:8]}"}, headers=auth_headers,
    ).json()["data"]
    ds_id = ds["id"]

    img = _textured(480, 400, seed=7)
    r = test_client.post(
        "/api/v1/annotation/dataset/preprocess/images",
        params={"dataset_id": ds_id},
        files=[
            ("files", ("a.png", img, "image/png")),
            ("files", ("b.png", img, "image/png")),  # 内容相同 → 重复被剔除
        ],
        headers=auth_headers,
    )
    assert r.status_code == 200, r.text
    job_id = r.json()["data"]["job_id"]
    job = _wait_job(test_client, auth_headers, job_id)
    assert job["status"] == "done", job
    assert job["ingested"] == 1
    assert job["dropped_duplicate"] == 1

    # 数据集图片数应更新为 1
    total = test_client.get(
        f"/api/v1/annotation/dataset/{ds_id}/images", headers=auth_headers
    ).json()["data"]["total"]
    assert total == 1


def test_images_preprocess_blur_drop(test_client, auth_headers, monkeypatch):
    monkeypatch.setattr("app.utils.s3_client.s3_client.ensure_bucket", lambda *a, **k: None)
    monkeypatch.setattr("app.utils.s3_client.s3_client.upload_fileobj", lambda *a, **k: None)

    ds = test_client.post(
        "/api/v1/annotation/dataset/create",
        json={"name": f"preb-{uuid4().hex[:8]}"}, headers=auth_headers,
    ).json()["data"]
    ds_id = ds["id"]

    # 纯色图 → Laplacian 方差≈0，判模糊剔除
    flat = _plain(480, 400, 128)
    r = test_client.post(
        "/api/v1/annotation/dataset/preprocess/images",
        params={"dataset_id": ds_id, "blur": 30.0},
        files={"files": ("flat.png", flat, "image/png")},
        headers=auth_headers,
    )
    job = _wait_job(test_client, auth_headers, r.json()["data"]["job_id"])
    assert job["status"] == "done", job
    assert job["ingested"] == 0
    assert job["dropped_blur"] == 1


# ── 集成：视频抽帧入库 ─────────────────────────────────────────────────
def test_video_preprocess_ingests_frames(test_client, auth_headers, monkeypatch):
    monkeypatch.setattr("app.utils.s3_client.s3_client.ensure_bucket", lambda *a, **k: None)
    monkeypatch.setattr("app.utils.s3_client.s3_client.upload_fileobj", lambda *a, **k: None)

    ds = test_client.post(
        "/api/v1/annotation/dataset/create",
        json={"name": f"prev-{uuid4().hex[:8]}"}, headers=auth_headers,
    ).json()["data"]
    ds_id = ds["id"]

    path = _write_video(seconds=2, fps=10)
    with open(path, "rb") as f:
        content = f.read()
    _cleanup(path)

    r = test_client.post(
        "/api/v1/annotation/dataset/preprocess/video",
        params={"dataset_id": ds_id, "interval": 1.0, "min_side": 0},
        files={"video": ("clip.mp4", content, "video/mp4")},
        headers=auth_headers,
    )
    assert r.status_code == 200, r.text
    job = _wait_job(test_client, auth_headers, r.json()["data"]["job_id"])
    assert job["status"] == "done", job
    assert job["ingested"] >= 2  # 2s @1s 间隔 ≈ 首帧+末尾帧


# ── helpers ───────────────────────────────────────────────────────────
def _wait_job(test_client, auth_headers, job_id, timeout=30.0):
    job = None
    deadline = time.time() + timeout
    while time.time() < deadline:
        job = test_client.get(
            f"/api/v1/annotation/dataset/preprocess/{job_id}", headers=auth_headers
        ).json()["data"]
        if job and job["status"] in ("done", "failed"):
            return job
        time.sleep(0.2)
    return job


def _textured(w: int, h: int, seed: int) -> bytes:
    import cv2

    rng = np.random.default_rng(seed)
    img = np.zeros((h, w, 3), dtype=np.uint8)
    img[:, :] = rng.integers(30, 220, size=(h, w, 3), dtype=np.uint8)
    ok, buf = cv2.imencode(".png", img)
    assert ok
    return buf.tobytes()


def _plain(w: int, h: int, val: int) -> bytes:
    import cv2

    img = np.full((h, w, 3), val, dtype=np.uint8)
    ok, buf = cv2.imencode(".png", img)
    assert ok
    return buf.tobytes()


def _write_video(seconds: int, fps: int) -> str:
    import os
    import tempfile

    import cv2

    fd, path = tempfile.mkstemp(suffix=".mp4")
    os.close(fd)
    writer = cv2.VideoWriter(path, cv2.VideoWriter_fourcc(*"mp4v"), fps, (64, 48))
    total = int(seconds * fps)
    rng = np.random.default_rng(1)
    for i in range(total):
        base = 100 + (i * 3) % 100  # 基准亮度 100~199，避免被判黑帧
        frame = np.full((48, 64, 3), base, dtype=np.uint8)
        frame += rng.integers(0, 40, size=frame.shape, dtype=np.uint8)
        writer.write(frame.astype(np.uint8))
    writer.release()
    return path


def _cleanup(path: str) -> None:
    import os

    if os.path.exists(path):
        os.unlink(path)
