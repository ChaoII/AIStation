"""数据落地（抽帧/清洗）的可配置参数。

阈值为 0 / 负数表示「不启用」该检查项，便于前端用开关关闭。
"""
from dataclasses import dataclass


def _num(raw, default: float) -> float:
    """把查询参数的安全转换为 float，非法回退默认值。"""
    if raw is None:
        return default
    try:
        return float(raw)
    except (TypeError, ValueError):
        return default


def _int(raw, default: int) -> int:
    return int(_num(raw, float(default)))


def _bool(raw, default: bool) -> bool:
    if raw is None:
        return default
    if isinstance(raw, bool):
        return raw
    s = str(raw).strip().lower()
    if s in ("1", "true", "yes", "on"):
        return True
    if s in ("0", "false", "no", "off"):
        return False
    return default


@dataclass
class ExtractConfig:
    """视频抽帧参数。"""

    interval_seconds: float = 1.0  # 每隔多少秒取一帧
    max_frames: int = 0  # 最多抽帧数，0=不限
    scene_change: bool = False  # 是否按场景变化额外取帧
    scene_threshold: float = 25.0  # 场景变化判定的帧间平均灰度差阈值

    @classmethod
    def from_params(
        cls,
        interval=None,
        max_frames=None,
        scene_change=None,
        scene_threshold=None,
    ) -> "ExtractConfig":
        return cls(
            interval_seconds=max(_num(interval, 1.0), 0.05),
            max_frames=max(_int(max_frames, 0), 0),
            scene_change=_bool(scene_change, False),
            scene_threshold=max(_num(scene_threshold, 25.0), 0.0),
        )


@dataclass
class CleaningConfig:
    """图片清洗参数。阈值为 0 / 负数表示不启用该项。"""

    min_side: int = 320  # 短边最小像素
    blur_variance: float = 30.0  # Laplacian 方差下限（低于判模糊，值越大越严格）
    brightness_min: float = 20.0  # 平均亮度下限（低于判黑帧）
    brightness_max: float = 240.0  # 平均亮度上限（高于判过曝）
    phash_threshold: int = 6  # 近重复汉明距离阈值（0 关闭）

    @classmethod
    def from_params(
        cls,
        min_side=None,
        blur=None,
        brightness_min=None,
        brightness_max=None,
        phash=None,
    ) -> "CleaningConfig":
        return cls(
            min_side=max(_int(min_side, 320), 0),
            blur_variance=max(_num(blur, 30.0), 0.0),
            brightness_min=_num(brightness_min, 20.0),
            brightness_max=_num(brightness_max, 240.0),
            phash_threshold=max(_int(phash, 6), 0),
        )


# 剔除原因 → 中文说明（供前端报表展示）
REASON_LABELS: dict[str, str] = {
    "too_small": "分辨率过低",
    "blur": "画面模糊",
    "dark": "过暗/黑帧",
    "bright": "过曝/白帧",
    "duplicate": "重复或高度相似",
    "unreadable": "无法解码",
}
