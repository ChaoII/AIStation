import pytest

from app.utils.trigger_util import TriggerUtil


def test_normalize_cron_maps_weekday_numbers_to_names():
    assert TriggerUtil.normalize_cron("0 9 * * 1") == "0 9 * * mon"
    assert TriggerUtil.normalize_cron("0 9 * * 0") == "0 9 * * sun"
    assert TriggerUtil.normalize_cron("0 9 * * 7") == "0 9 * * sun"
    assert TriggerUtil.normalize_cron("0 9 * * 1-5") == "0 9 * * mon-fri"
    assert TriggerUtil.normalize_cron("0 9 * * 1,3,5") == "0 9 * * mon,wed,fri"
    assert TriggerUtil.normalize_cron("0  9   *  *  SUN ") == "0 9 * * sun"


@pytest.mark.parametrize("expr", [
    "0 0 9 L * *", "0 0 9 15W * *", "0 0 9 * * 1#2", "0 0 9 ? * *",
    "0 0 9 * * * 2030", "30 * * * * *", "0 9 * * */2", "0 9 * * mon/2",
    "0 9 * * 9", "0 9 * *", "0 9 * * 1 2 3",
])
def test_validate_cron_rejects(expr):
    ok, reason = TriggerUtil.validate_cron(expr)
    assert ok is False and reason


@pytest.mark.parametrize("expr", ["0 9 * * *", "0 9 * * 7", "*/15 * * * *", "0 9 1,15 * *", "0 9 * * mon-fri"])
def test_validate_cron_accepts(expr):
    ok, reason = TriggerUtil.validate_cron(expr)
    assert ok is True and reason == ""
