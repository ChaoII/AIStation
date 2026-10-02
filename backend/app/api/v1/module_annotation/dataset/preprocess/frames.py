"""视频抽帧 + 图片清洗的核心算法（纯函数，便于单测）。

所有函数只依赖 opencv / numpy，不触碰数据库与对象存储，
方便在后台线程里跑 CPU 密集的解码、画质测量与感知哈希。
"""
import hashlib

import cv2
import numpy as np

from .config import CleaningConfig, ExtractConfig


class FrameInfo:
    """一帧（或一张已解码图片）的画像：字节 + 画质指标 + 感知哈希 + 内容哈希。"""

    __slots__ = (
        "idx", "ts", "jpeg", "width", "height",
        "brightness", "blur_var", "phash", "content_hash",
    )

    def __init__(self, idx, ts, jpeg, width, height,
                 brightness, blur_var, phash, content_hash):
        self.idx = idx
        self.ts = ts
        self.jpeg = jpeg
        self.width = width
        self.height = height
        self.brightness = brightness
        self.blur_var = blur_var
        self.phash = phash
        self.content_hash = content_hash


def phash(gray: np.ndarray, hash_size: int = 8) -> int:
    """感知哈希：32x32 灰度 → 8x8 低频 DCT 系数 → 相对中值二值化打包成 int。"""
    resized = cv2.resize(gray, (32, 32), interpolation=cv2.INTER_AREA)
    dct = cv2.dct(np.float32(resized))
    low = dct[:hash_size, :hash_size]
    med = float(np.median(low))
    bits = (low > med).flatten()
    val = 0
    for b in bits:
        val = (val << 1) | int(b)
    return val


def hamming(a: int, b: int) -> int:
    """两个感知哈希的汉明距离（0~64）。"""
    return bin(a ^ b).count("1")


def _measure(gray: np.ndarray) -> tuple[int, int, float, float]:
    """返回 (width, height, brightness, blur_var)。"""
    h, w = gray.shape
    brightness = float(gray.mean())
    blur_var = float(cv2.Laplacian(gray, cv2.CV_64F).var())
    return w, h, brightness, blur_var


def _to_frame_info(idx: int, ts: float, frame: np.ndarray) -> FrameInfo | None:
    """BGR 帧 → FrameInfo；编码失败返回 None。"""
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    w, h, brightness, blur_var = _measure(gray)
    okj, buf = cv2.imencode(".jpg", frame)
    if not okj:
        return None
    jpeg = buf.tobytes()
    return FrameInfo(
        idx=idx, ts=ts, jpeg=jpeg, width=w, height=h,
        brightness=brightness, blur_var=blur_var,
        phash=phash(gray), content_hash=hashlib.sha256(jpeg).hexdigest(),
    )


def extract_video_frames(path: str, cfg: ExtractConfig) -> list[FrameInfo]:
    """按间隔/场景变化采样视频帧，返回 FrameInfo 列表。

    读不到视频流则抛 ValueError；其余逐帧读取。
    """
    cap = cv2.VideoCapture(path)
    if not cap.isOpened():
        raise ValueError("无法读取视频")
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    if fps <= 0:
        fps = 30.0
    interval_frames = max(1, int(round(cfg.interval_seconds * fps)))

    out: list[FrameInfo] = []
    prev_gray: np.ndarray | None = None
    idx = 0
    last_taken = -(1 << 30)  # 保证首帧始终被取
    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                break
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

            mean_diff = 0.0
            if cfg.scene_change and prev_gray is not None:
                mean_diff = float(cv2.absdiff(gray, prev_gray).mean())

            by_interval = (idx - last_taken) >= interval_frames
            by_scene = cfg.scene_change and mean_diff >= cfg.scene_threshold
            if idx == 0 or by_interval or by_scene:
                last_taken = idx
                info = _to_frame_info(idx, round(idx / fps, 3), frame)
                if info is not None:
                    out.append(info)
                if cfg.max_frames and len(out) >= cfg.max_frames:
                    break

            prev_gray = gray
            idx += 1
    finally:
        cap.release()
    return out


def frame_from_image(content: bytes) -> FrameInfo | None:
    """把单张上传图片字节解码为 FrameInfo（统一转 jpeg 存储）。解码失败返回 None。"""
    arr = np.frombuffer(content, np.uint8)
    frame = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if frame is None:
        return None
    return _to_frame_info(0, 0.0, frame)


def decide_reason(
    info: FrameInfo,
    cfg: CleaningConfig,
    seen_hashes: set[str],
    phash_list: list[int],
) -> str | None:
    """返回剔除原因，None 表示通过。

    判定顺序：尺寸 → 模糊 → 过暗 → 过亮 → 重复（先内容哈希、再感知哈希）。
    仅当通过时才会把哈希/感知哈希登记进后续去重集合。
    """
    if cfg.min_side and min(info.width, info.height) < cfg.min_side:
        return "too_small"
    if cfg.blur_variance and info.blur_var < cfg.blur_variance:
        return "blur"
    if cfg.brightness_min and info.brightness < cfg.brightness_min:
        return "dark"
    if cfg.brightness_max and info.brightness > cfg.brightness_max:
        return "bright"
    if info.content_hash in seen_hashes:
        return "duplicate"
    if cfg.phash_threshold:
        for p in phash_list:
            if hamming(info.phash, p) <= cfg.phash_threshold:
                return "duplicate"
    seen_hashes.add(info.content_hash)
    phash_list.append(info.phash)
    return None
