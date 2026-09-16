"""快照引用的本地服务与对象存储归一化。

DB 中 ``snapshot_path`` 可能是：
- 本机 worker 保存的绝对路径（如 ``D:\\...\\data\\detections\\2026-09-12\\x.jpg``）；
- 相对路径（``{date}/{name}.jpg``）；
- 边缘 Agent 上报的对象存储相对引用 / ``s3://key``。

本模块统一转换为前端可访问 URL，供告警列表/详情展示。
"""
from pathlib import Path

from app.config.setting import settings

PREFIX = "/api/v1/video/detections"
_OBJECT_SCHEMES = ("s3://", "oss://", "minio://")


def detections_base() -> Path:
    """返回 DETECTIONS_DIR 的绝对路径。"""
    return Path(settings.DETECTIONS_DIR)


def safe_detections_path(file_path: str) -> Path | None:
    """在 DETECTIONS_DIR 下归一化路径；目录穿越/越界返回 None（不要求文件存在）。

    供写盘前校验：拒绝 ``../`` 与落在 DETECTIONS_DIR 之外的绝对路径。
    """
    if not file_path:
        return None
    base = detections_base().resolve()
    try:
        target = (base / file_path).resolve()
    except OSError:
        return None
    if target != base and base not in target.parents:
        return None
    return target


def safe_local_snapshot(file_path: str) -> Path | None:
    """在 DETECTIONS_DIR 下解析文件路径；目录穿越或文件不存在返回 None。"""
    target = safe_detections_path(file_path)
    return target if target is not None and target.is_file() else None


def _presign(object_key: str) -> str | None:
    """对象存储 key → 预签名 URL；不可用或失败返回 None。"""
    try:
        from app.utils.s3_client import s3_client

        return s3_client.presigned_url(object_key)
    except Exception:
        return None


def resolve_snapshot_url(value: str | None) -> str | None:
    """把快照引用归一化为前端可访问 URL（失败返回 None）。

    规则：
    1. 空 → None；
    2. ``http(s)://`` → 原样；
    3. ``s3://`` / ``oss://`` / ``minio://`` → 去 scheme 后预签名；
    4. 命中 DETECTIONS_DIR 下的本地文件 → ``/api/v1/video/detections/{rel}``；
    5. 其余按对象存储 key 尽力预签名，失败 → None。
    """
    if not value:
        return None
    raw = value.strip()
    if not raw:
        return None
    if raw.startswith(("http://", "https://")):
        return raw
    for scheme in _OBJECT_SCHEMES:
        if raw.startswith(scheme):
            return _presign(raw[len(scheme):])

    base = detections_base().resolve()
    p = Path(raw)
    try:
        target = p.resolve() if p.is_absolute() else (base / raw).resolve()
    except OSError:
        return None
    if target.is_file() and (target == base or base in target.parents):
        rel = target.relative_to(base).as_posix()
        return f"{PREFIX}/{rel}"
    return _presign(raw)
