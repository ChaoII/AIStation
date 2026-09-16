"""边缘接入与交互路由限流隔离回归（审计 §并发-4 后续项）。

设备侧接入/回调路径（detection/callback、edge/heartbeat、record webhook）由
``settings.RATE_LIMIT_PATH_OVERRIDES`` 单独给到 ``EDGE_INGEST_*`` 限额；``video``
模块交互路由回落到 60/10s，二者不再共用同一限额（否则机队峰值会 429 丢告警）。
逐路径生效解析见 ``tests/test_rate_limit_paths.py``。
"""
from app.config.setting import settings


def test_edge_ingest_paths_have_dedicated_high_limit():
    per_second = (
        settings.EDGE_INGEST_RATE_LIMIT_TIMES / settings.EDGE_INGEST_RATE_LIMIT_SECONDS
    )
    assert per_second > 6, f"接入限流过低（旧值 6/s）：{per_second}/s"
    assert per_second >= 100, f"接入限流不足以支撑边缘机队：{per_second}/s"

    keys = set(settings.RATE_LIMIT_PATH_OVERRIDES)
    for suffix in (
        "/video/algorithm/detection/callback",
        "/video/edge/heartbeat",
        "/video/record/webhook/on_record_mp4",
    ):
        matched = [k for k in keys if k.endswith(suffix)]
        assert len(matched) == 1, f"缺少设备路径限流覆盖: {suffix}"
        cfg = settings.RATE_LIMIT_PATH_OVERRIDES[matched[0]]
        assert cfg["times"] == settings.EDGE_INGEST_RATE_LIMIT_TIMES
        assert cfg["seconds"] == settings.EDGE_INGEST_RATE_LIMIT_SECONDS


def test_video_interactive_limit_is_protected_and_below_ingest():
    video = settings.RATE_LIMIT_OVERRIDES["video"]
    assert video["times"] == 60
    assert video["seconds"] == 10
    assert video["times"] < settings.EDGE_INGEST_RATE_LIMIT_TIMES
