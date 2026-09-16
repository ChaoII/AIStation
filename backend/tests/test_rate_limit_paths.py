"""按路径限流解析回归（审计：边缘接入不再与 video 交互路由共用模块级限额）。

``resolve_rate_limit`` 是「某请求实际生效的每路径限额」的权威实现：
先按 ``"METHOD /path"`` 精确匹配设备路径覆盖，再回退模块级限额。
"""
from app.config.setting import settings
from app.scripts.init_app import resolve_rate_limit

INGEST = {
    "times": settings.EDGE_INGEST_RATE_LIMIT_TIMES,
    "seconds": settings.EDGE_INGEST_RATE_LIMIT_SECONDS,
}
VIDEO_INTERACTIVE = settings.RATE_LIMIT_OVERRIDES["video"]


def test_detection_callback_path_gets_ingest_limit():
    assert resolve_rate_limit("video", "POST", ["/video/algorithm/detection/callback"]) == INGEST
    # 带 ROOT_PATH 前缀也应命中
    assert (
        resolve_rate_limit("video", "POST", ["/api/v1/video/algorithm/detection/callback"])
        == INGEST
    )


def test_edge_heartbeat_and_record_webhook_get_ingest_limit():
    assert resolve_rate_limit("video", "POST", ["/video/edge/heartbeat"]) == INGEST
    assert (
        resolve_rate_limit("video", "POST", ["/video/record/webhook/on_record_mp4"])
        == INGEST
    )


def test_interactive_video_path_falls_back_to_module_limit():
    got = resolve_rate_limit("video", "POST", ["/video/algorithm/rule/list"])
    assert got == VIDEO_INTERACTIVE
    assert got["times"] < INGEST["times"], "交互路由必须比机队接入更严"


def test_method_must_match():
    # 同路径的其它方法不命中路径覆盖，回退模块级
    assert resolve_rate_limit("video", "GET", ["/video/edge/heartbeat"]) == VIDEO_INTERACTIVE


def test_unknown_module_uses_global_default():
    assert resolve_rate_limit("nope", "GET", ["/x"]) == {
        "times": settings.REQUEST_RATE_LIMIT_TIMES,
        "seconds": settings.REQUEST_RATE_LIMIT_SECONDS,
    }
