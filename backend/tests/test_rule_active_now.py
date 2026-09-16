"""规则灰度 gating 纯函数测试。"""
import zlib
from datetime import datetime, timezone

from app.api.v1.module_video.inference.gating import rule_active_now

# 固定事件时间（epoch 秒，UTC）：2027-01-15T08:00:00Z → ISO 星期 4（周五）、8 点
NOW = 1_800_000_000.0


def _utc_day_hour(ts: float) -> tuple[int, int]:
    """由事件 epoch 秒推导 UTC 的 ISO 星期（0=周一）与小时。"""
    dt = datetime.fromtimestamp(ts, tz=timezone.utc)
    return dt.weekday(), dt.hour


def test_default_is_active():
    assert rule_active_now(None, None, 1, NOW, rule_id=1) == (True, "all")
    assert rule_active_now({}, {}, 1, NOW, rule_id=1) == (True, "all")


def test_blacklist_skips_and_whitelist_forces():
    r = {"percent": 0, "whitelist": [7], "blacklist": [8]}
    assert rule_active_now(None, r, 8, NOW, rule_id=1) == (False, "blacklist")
    assert rule_active_now(None, r, 7, NOW, rule_id=1) == (True, "whitelist")  # 白名单忽略 percent=0
    assert rule_active_now(None, r, 9, NOW, rule_id=1) == (False, "rollout_zero")


def test_blacklist_has_priority_over_whitelist():
    # 名单交集由 Task 1 校验拦截；此处锁定 gating 优先级：黑名单先于白名单
    r = {"whitelist": [7], "blacklist": [7]}
    assert rule_active_now(None, r, 7, NOW, rule_id=1) == (False, "blacklist")


def test_percent_bounds():
    assert rule_active_now(None, {"percent": 100}, 5, NOW, rule_id=1) == (True, "rollout_all")
    assert rule_active_now(None, {"percent": 0}, 5, NOW, rule_id=1) == (False, "rollout_zero")


def test_bucket_reason_and_bounds():
    r = {"percent": 50}
    active, reason = rule_active_now(None, r, 42, NOW, rule_id=9)
    assert reason == "rollout_bucket"
    assert active is ((zlib.crc32(b"9:42") % 100) < 50)


def test_bucket_is_stable_and_deterministic():
    r = {"percent": 50}
    first = rule_active_now(None, r, 42, NOW, rule_id=9)
    for _ in range(20):
        assert rule_active_now(None, r, 42, NOW, rule_id=9) == first


def test_different_rule_ids_bucket_independently():
    r = {"percent": 50}
    hits = {
        (rid, cid): rule_active_now(None, r, cid, NOW, rule_id=rid)[0]
        for rid in range(3)
        for cid in range(20)
    }
    # 对同一相机，至少存在两个 rule_id 的分桶结果不同 → 分桶与 rule_id 相关
    assert any(hits[(0, cid)] != hits[(1, cid)] for cid in range(20))
    # 分桶结果同时存在命中与未命中
    assert set(hits.values()) == {True, False}


def test_schedule_window_gates():
    day, hour = _utc_day_hour(NOW)
    other_day = (day + 1) % 7

    # 空/缺失 slots = 全天生效
    assert rule_active_now({"slots": []}, None, 1, NOW, rule_id=1) == (True, "all")
    assert rule_active_now({"type": "weekly", "slots": []}, None, 1, NOW, rule_id=1) == (True, "all")
    assert rule_active_now(None, None, 1, NOW, rule_id=1) == (True, "all")

    # 星期不匹配 → 跳过
    assert rule_active_now(
        {"slots": [{"day": other_day, "start": 0, "end": 24}]}, None, 1, NOW, rule_id=1
    ) == (False, "schedule")

    # 星期命中且 hour ∈ [start, end) → 生效；start 含
    assert rule_active_now(
        {"slots": [{"day": day, "start": hour, "end": 24}]}, None, 1, NOW, rule_id=1
    ) == (True, "all")

    # end 不含：窗口 [0, hour) 不含当前小时 → 跳过
    assert rule_active_now(
        {"slots": [{"day": day, "start": 0, "end": hour}]}, None, 1, NOW, rule_id=1
    ) == (False, "schedule")


def test_schedule_invalid_container_fails_open():
    # 非 dict / slots 非列表 → 全天生效（与边缘 parse_schedule 一致）
    for bad in ("x", 123, [], {"slots": "nope"}):
        assert rule_active_now(bad, None, 1, NOW, rule_id=1)[0] is True


def test_invalid_rollout_fails_open():
    for bad in (
        {"percent": "x"},
        {"percent": 50.5},
        {"percent": True},
        {"percent": -5},
        {"percent": 999},
        {"whitelist": "1"},
        {"whitelist": [0, -1]},
        "not-a-dict",
        123,
    ):
        assert rule_active_now(None, bad, 1, NOW, rule_id=1)[0] is True


def test_schedule_takes_priority_over_rollout():
    day, hour = _utc_day_hour(NOW)
    other_day = (day + 1) % 7
    # 时间段未命中优先于白名单强制
    schedule = {"slots": [{"day": other_day, "start": 0, "end": 24}]}
    r = {"percent": 100, "whitelist": [1]}
    assert rule_active_now(schedule, r, 1, NOW, rule_id=1) == (False, "schedule")
