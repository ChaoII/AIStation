import pytest

from app.utils.trigger_util import TriggerUtil


def test_normalize_cron_maps_weekday_numbers_to_names():
    assert TriggerUtil.normalize_cron("0 9 * * 1") == "0 9 * * mon"
    assert TriggerUtil.normalize_cron("0 9 * * 0") == "0 9 * * sun"
    assert TriggerUtil.normalize_cron("0 9 * * 7") == "0 9 * * sun"
    # 区间展开为显式列表（避免两套库对名称区间解释相反）
    assert TriggerUtil.normalize_cron("0 9 * * 1-5") == "0 9 * * mon,tue,wed,thu,fri"
    assert TriggerUtil.normalize_cron("0 9 * * 0-6") == "0 9 * * sun,mon,tue,wed,thu,fri,sat"
    assert TriggerUtil.normalize_cron("0 9 * * 1,3,5") == "0 9 * * mon,wed,fri"
    assert TriggerUtil.normalize_cron("0  9   *  *  SUN ") == "0 9 * * sun"


def test_normalize_cron_expands_weekday_range_by_raw_number():
    """区间是否跨周按原始数字 0..7 比较（`7` 不折成 `0`），展开逐日映射并去重。"""
    assert TriggerUtil.normalize_cron("0 9 * * 5-7") == "0 9 * * fri,sat,sun"
    assert TriggerUtil.normalize_cron("0 9 * * 0-7") == "0 9 * * sun,mon,tue,wed,thu,fri,sat"
    assert TriggerUtil.normalize_cron("0 9 * * 1-1") == "0 9 * * mon"
    assert TriggerUtil.normalize_cron("0 9 * * sat,sun") == "0 9 * * sat,sun"


def test_normalize_cron_equal_range_is_single_value():
    """数值字段的等值区间等价单值（与周字段 `1-1` → `mon` 一致）。"""
    assert TriggerUtil.normalize_cron("0 9 5-5 * *") == "0 9 5 * *"
    assert TriggerUtil.normalize_cron("10-10 * * * *") == "10 * * * *"
    assert TriggerUtil.normalize_cron("0 9-9 * * *") == "0 9 * * *"


@pytest.mark.parametrize(
    "expr",
    [
        "0 0 9 L * *",
        "0 0 9 15W * *",
        "0 0 9 * * 1#2",
        "0 0 9 ? * *",
        "0 0 9 * * * 2030",
        "30 * * * * *",
        "0 0 9 * * *",
        "0 9 * * */2",
        "0 9 * * mon/2",
        "0 9 * * 5-1",
        "0 9 * * 6-0",
        "0 9 * * 7-1",
        "0 9 * * fri-mon",
        "0 9 * * 9",
        "0 9 * *",
        "0 9 * * 1 2 3",
        "5-1 * * * *",
        "0 17-9 * * *",
        "0 9 15-1 * *",
    ],
)
def test_validate_cron_rejects(expr):
    ok, reason = TriggerUtil.validate_cron(expr)
    assert ok is False and reason


@pytest.mark.parametrize(
    "expr", ["0 9 * * *", "0 9 * * 7", "*/15 * * * *", "0 9 1,15 * *", "0 9 * * mon-fri"]
)
def test_validate_cron_accepts(expr):
    ok, reason = TriggerUtil.validate_cron(expr)
    assert ok is True and reason == ""
