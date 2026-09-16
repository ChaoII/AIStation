"""边缘事件接入限流配置回归（审计 §并发-4：60/10s = 6 事件/s 会丢告警）。

边缘事件 HTTP 接入 `POST /api/v1/video/algorithm/detection/callback` 与视频模块共用
同一个路由级限流器，故校验 video 覆盖值必须显著高于旧值。彻底按路径独立限额需要
路由装配层（init_app.py）支持，属后续项；本测试锁定当前配置下界。
"""
from app.config.setting import settings


def test_edge_ingest_rate_limit_is_high_enough():
    video = settings.RATE_LIMIT_OVERRIDES["video"]
    assert video["times"] == settings.EDGE_INGEST_RATE_LIMIT_TIMES
    assert video["seconds"] == settings.EDGE_INGEST_RATE_LIMIT_SECONDS
    per_second = video["times"] / video["seconds"]
    assert per_second > 6, f"接入限流过低（旧值 6/s）：{per_second}/s"
    assert per_second >= 100, f"接入限流不足以支撑边缘机队：{per_second}/s"
