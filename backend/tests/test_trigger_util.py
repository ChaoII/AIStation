from datetime import datetime

import pytest
from croniter import croniter

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


# ============================================================ Task A2：触发器构造 / 描述 / 下次运行时间

BASE = datetime(2026, 10, 18, 12, 0)  # 2026-10-18 是周日

#: 标准 crontab 语义下的期望下次触发（用于交叉验证，写死避免自证）
EXPECTED = {
    "0 9 * * 1": datetime(2026, 10, 19, 9, 0),
    "0 9 * * 5": datetime(2026, 10, 23, 9, 0),
    "0 9 * * 0": datetime(2026, 10, 25, 9, 0),
    "0 9 * * 7": datetime(2026, 10, 25, 9, 0),
    "0 9 * * 1-5": datetime(2026, 10, 19, 9, 0),
}


@pytest.mark.parametrize("expr", list(EXPECTED))
def test_next_run_is_standard_crontab_semantics(expr):
    """统一层的下次触发必须符合标准 crontab（锁死 D1：1=周一、0/7=周日）。"""
    ours = TriggerUtil.next_run("cron", expr, BASE)
    assert ours.replace(tzinfo=None) == EXPECTED[expr]


@pytest.mark.parametrize("expr", ["0 9 * * 1", "0 9 * * 5", "0 9 * * 1-5"])
def test_next_run_matches_croniter(expr):
    """交叉验证：与 croniter（标准 crontab 实现）同一时刻。"""
    ours = TriggerUtil.next_run("cron", expr, BASE)
    theirs = croniter(expr, BASE).get_next(datetime)
    assert ours.replace(tzinfo=None) == theirs


def test_cron_trigger_is_asia_shanghai():
    trig = TriggerUtil.to_cron_trigger("0 9 * * mon")
    assert str(trig.timezone) == "Asia/Shanghai"


def test_describe_cron_is_chinese():
    assert "周一" in TriggerUtil.describe_cron("0 9 * * 1")


# ------------------------------------------------------------ A1 遗留 ⚠️：下游可构造性扫描
#: A1 判合法（含区间展开/等值区间/列表/步长/通配混写/名称）的样本，规范化后必须能被两个下游接受
VALID_EXPRESSIONS = [
    "0 9 * * *",
    "0 9 * * 0",
    "0 9 * * 7",
    "0 9 * * 1",
    "0 9 * * SUN",
    "*/15 * * * *",
    "0 */2 * * *",
    "0 9 1,15 * *",
    "0 9 1-15 * *",
    "0 9 * 1-6 *",
    "0 0 1 1 *",
    "30 8 * * 1-5",
    "0 9 * * mon-fri",
    "0 9 * * 1-5",
    "0 9 * * 0-6",
    "0 9 * * 5-7",
    "0 9 * * 0-7",
    "0 9 * * 1-1",
    "0 9 * * 7-7",
    "0 9 * * 0,7",
    "0 9 * * 1,3,5",
    "0 9 * * sat,sun",
    "0 9 * * *,mon",
    "0 9 * * 1,*",
    "0 9 5-5 * *",
    "10-10 * * * *",
    "0 9-9 * * *",
]


@pytest.mark.parametrize("expr", VALID_EXPRESSIONS)
def test_normalized_cron_is_constructible_downstream(expr):
    """A1 遗留 ⚠️：校验通过 ⇒ 一定能被 APScheduler 构造、被 croniter 解析（下游可构造性）。"""
    normalized = TriggerUtil.normalize_cron(expr)
    TriggerUtil.to_cron_trigger(expr)  # APScheduler CronTrigger 构造
    croniter(normalized).get_next(datetime)  # croniter 解析 + 求下次
    # 周字段的区间必须已展开为显式名称列表（消除两套库对名称区间的相反解释）
    assert "-" not in normalized.split()[4]


# ------------------------------------------------------------ A1 遗留 Minor：原因具体性
@pytest.mark.parametrize(
    ("expr", "phrase"),
    [
        ("0 0 9 L * *", "不支持 L"),
        ("0 0 9 15W * *", "不支持 W"),
        ("0 0 9 * * 1#2", "不支持 #"),
        ("0 0 9 ? * *", "不支持 ?"),
        ("0 0 9 * * * 2030", "7 段"),
        ("30 * * * * *", "秒位"),
        ("0 0 9 * * *", "6 段"),
        ("0 9 * * 5-1", "跨周"),
        ("0 9 * * */2", "不支持步长"),
        ("5-5/1 * * * *", "等值区间无需步长"),
        ("1/2 * * * *", "步长写法非法"),
    ],
)
def test_validate_cron_reason_is_specific(expr, phrase):
    """A1 遗留 Minor：关键反例的原因必须具体（而不只是「原因非空」）。"""
    ok, reason = TriggerUtil.validate_cron(expr)
    assert ok is False
    assert phrase in reason


# ------------------------------------------------------------ A1 遗留 Minor：通配与列表混写
@pytest.mark.parametrize(
    ("expr", "normalized"),
    [
        ("0 9 * * *,mon", "0 9 * * *"),
        ("0 9 * * mon,*", "0 9 * * *"),
        ("0 9 1,* * *", "0 9 * * *"),
        ("*,30 * * * *", "* * * * *"),
    ],
)
def test_normalize_cron_wildcard_mix_collapses_to_star(expr, normalized):
    """A1 遗留 Minor：通配与列表混写归一为 `*`（规格 §4.1）。"""
    assert TriggerUtil.normalize_cron(expr) == normalized


# ------------------------------------------------------------ describe_cron（中文短句）
@pytest.mark.parametrize(
    ("expr", "expected"),
    [
        ("0 9 * * *", "每天 09:00"),
        ("0 9 * * 1", "每周一 09:00"),
        ("30 8 * * 0", "每周日 08:30"),
        ("0 9 * * 1-5", "每周一、周二、周三、周四、周五 09:00"),
        ("0 9 * * 5-7", "每周五、周六、周日 09:00"),
        ("0 9 * * mon,wed", "每周一、周三 09:00"),
        ("15 * * * *", "每小时第 15 分"),
        ("0,30 * * * *", "每小时第 0、30 分"),
        ("0 * * * *", "每小时整点"),
        ("* * * * *", "每分钟"),
        ("0 0 1 * *", "每月 1 日 00:00"),
        ("0 9 15 * *", "每月 15 日 09:00"),
        ("0 9 * 1 *", "每年 1 月 09:00"),
        ("0 9 1 1 *", "每年 1 月 1 日 09:00"),
        ("0,30 9,18 * * *", "每天 09:00、09:30、18:00、18:30"),
        ("*/15 * * * *", "每 15 分钟"),
        ("0 */2 * * *", "每 2 小时整点"),
        ("30 */2 * * *", "每 2 小时第 30 分"),
        ("*/15 9 * * 1", "每周一 9 点的每 15 分钟"),
        ("0 9-18 * * *", "每天 9-18 点的第 0 分"),
        ("0 9 */2 * *", "每 2 日 09:00"),
        ("0 9 1-15 * *", "每月 1-15 日 09:00"),
        ("0 9 * */3 *", "每 3 月 09:00"),
    ],
)
def test_describe_cron_zh(expr, expected):
    assert TriggerUtil.describe_cron(expr) == expected


def test_describe_cron_raises_on_invalid():
    """非法表达式的描述与 `normalize_cron` 同源：抛 `ValueError`（原因文案一致）。"""
    with pytest.raises(ValueError):
        TriggerUtil.describe_cron("0 9 * * 5-1")


def test_to_cron_trigger_raises_on_invalid():
    with pytest.raises(ValueError):
        TriggerUtil.to_cron_trigger("0 9 * * 5-1")
