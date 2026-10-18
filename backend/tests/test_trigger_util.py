from datetime import datetime, timedelta

import pytest
from croniter import croniter

from app.core.exceptions import CustomException
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


# ------------------------------------------------------------ 永不触发的日/月组合（契约：返回 None）
@pytest.mark.parametrize("expr", ["0 9 31 6 *", "0 9 30 2 *", "0 9 31 2 *"])
def test_next_run_returns_none_for_never_firing_day_month(expr):
    """契约是 `datetime | None`：永不触发的日/月组合必须返回 None，而不是抛 OSError。

    注意：校验层此刻仍判其**合法**（「永不触发组合判非法」由后续任务在 validate 分派层收紧），
    因此这里同时锁定「validate 通过 + next_run 返回 None」这一组合。
    """
    ok, reason = TriggerUtil.validate_cron(expr)
    assert ok is True and reason == ""
    assert TriggerUtil.next_run("cron", expr, BASE) is None


def test_next_run_leap_day_is_asia_shanghai():
    """闰年 2 月 29 日可触发：返回 Asia/Shanghai 的 2028-02-29 09:00。"""
    result = TriggerUtil.next_run("cron", "0 9 29 2 *", BASE)
    assert result is not None
    assert str(result.tzinfo) == "Asia/Shanghai"
    assert result.replace(tzinfo=None) == datetime(2028, 2, 29, 9, 0)


# ============================================================ Task A3：分派层（interval / date / now）
# Review Focus 2（date 填过去时间必须报错）、3（interval 全 0 必须报错）、5（时区必须 Asia/Shanghai）


def test_interval_normalize_fills_defaults():
    t, args = TriggerUtil.normalize("interval", {"hours": 2, "minutes": 30})
    assert t == "interval"
    assert args == {"weeks": 0, "days": 0, "hours": 2, "minutes": 30, "seconds": 0}


def test_interval_all_zero_is_invalid():
    ok, reason = TriggerUtil.validate(
        "interval", {"weeks": 0, "days": 0, "hours": 0, "minutes": 0, "seconds": 0}
    )
    assert ok is False and "至少" in reason


def test_date_in_the_past_is_invalid():
    past = (datetime.now() - timedelta(minutes=1)).strftime("%Y-%m-%d %H:%M:%S")
    ok, reason = TriggerUtil.validate("date", past)
    assert ok is False and "过去" in reason


def test_date_future_is_valid_and_asia_shanghai():
    future = (datetime.now() + timedelta(hours=1)).strftime("%Y-%m-%d %H:%M:%S")
    ok, reason = TriggerUtil.validate("date", future)
    assert ok is True and reason == ""
    trig = TriggerUtil.to_trigger("date", future)
    # APScheduler 3.11 的 DateTrigger 只存 run_date（无 timezone 属性），时区体现在 run_date.tzinfo
    assert str(trig.run_date.tzinfo) == "Asia/Shanghai"


def test_now_has_no_args_and_fires_once_soon():
    ok, reason = TriggerUtil.validate("now", None)
    assert ok is True and reason == ""
    trig = TriggerUtil.to_trigger("now", None)
    assert trig.run_date - datetime.now(trig.run_date.tzinfo) < timedelta(seconds=10)


def test_unknown_trigger_type_raises():
    with pytest.raises(CustomException):
        TriggerUtil.to_trigger("weekly", None)


# ------------------------------------------------------------ 分派层：normalize
def test_normalize_dispatches_by_trigger():
    assert TriggerUtil.normalize("cron", "0 9 * * 1") == ("cron", "0 9 * * mon")
    assert TriggerUtil.normalize("interval", {"hours": 2, "minutes": 30}) == (
        "interval",
        {"weeks": 0, "days": 0, "hours": 2, "minutes": 30, "seconds": 0},
    )
    assert TriggerUtil.normalize("date", "2026-10-20 09:00:00") == ("date", "2026-10-20 09:00:00")
    assert TriggerUtil.normalize("now", None) == ("now", None)


def test_normalize_unknown_trigger_raises_custom_exception():
    with pytest.raises(CustomException):
        TriggerUtil.normalize("weekly", None)


# ------------------------------------------------------------ 分派层：validate
def test_validate_cron_valid_and_invalid():
    assert TriggerUtil.validate("cron", "0 9 * * 1") == (True, "")
    ok, reason = TriggerUtil.validate("cron", "0 9 * * 5-1")
    assert ok is False and "跨周" in reason


def test_validate_interval_positive_is_valid():
    assert TriggerUtil.validate("interval", {"hours": 2}) == (True, "")


def test_validate_now_is_always_valid():
    assert TriggerUtil.validate("now", None) == (True, "")


def test_validate_unknown_trigger_returns_false_not_raises():
    """未知类型在唯一校验入口返回可读原因（供接口 400 直接回显），不抛异常。"""
    ok, reason = TriggerUtil.validate("weekly", None)
    assert ok is False and "weekly" in reason


# ------------------------------------------------------------ 分派层：describe
@pytest.mark.parametrize(
    ("trigger", "args", "expected"),
    [
        ("cron", "0 9 * * 1", "每周一 09:00"),
        (
            "interval",
            {"weeks": 0, "days": 0, "hours": 2, "minutes": 30, "seconds": 0},
            "每 2 小时 30 分一次",
        ),
        ("interval", {"days": 1}, "每 1 天一次"),
        ("date", "2026-10-20 09:00:00", "2026-10-20 09:00 执行一次"),
        ("now", None, "保存后立即执行一次"),
    ],
)
def test_describe_dispatch_zh(trigger, args, expected):
    assert TriggerUtil.describe(trigger, args) == expected


def test_describe_unknown_trigger_raises_custom_exception():
    with pytest.raises(CustomException):
        TriggerUtil.describe("weekly", None)


# ------------------------------------------------------------ 分派层：to_trigger
def test_to_trigger_interval_is_asia_shanghai():
    trig = TriggerUtil.to_trigger("interval", {"hours": 2, "minutes": 30})
    assert str(trig.timezone) == "Asia/Shanghai"
    assert trig.interval.total_seconds() == 2 * 3600 + 30 * 60


def test_to_trigger_cron_matches_legacy():
    trig = TriggerUtil.to_trigger("cron", "0 9 * * mon")
    assert str(trig.timezone) == "Asia/Shanghai"


# ------------------------------------------------------------ 分派层：next_run 非 cron 分支可达（A2 遗留 Minor）
def test_next_run_interval():
    result = TriggerUtil.next_run("interval", {"hours": 2}, BASE)
    assert result is not None
    assert str(result.tzinfo) == "Asia/Shanghai"
    assert result.replace(tzinfo=None) == BASE + timedelta(hours=2)


def test_next_run_date_future_and_past():
    future = (datetime.now() + timedelta(hours=1)).strftime("%Y-%m-%d %H:%M:%S")
    result = TriggerUtil.next_run("date", future, datetime.now())
    assert result is not None
    assert result.replace(tzinfo=None) == datetime.strptime(future, "%Y-%m-%d %H:%M:%S")
    # 过去时间：DateTrigger 无下次触发 → None（不抛异常）
    past = (datetime.now() - timedelta(minutes=1)).strftime("%Y-%m-%d %H:%M:%S")
    assert TriggerUtil.next_run("date", past, datetime.now()) is None


def test_next_run_now_is_soon():
    result = TriggerUtil.next_run("now", None)
    assert result is not None
    assert result - datetime.now(result.tzinfo) < timedelta(seconds=10)


# ------------------------------------------------------------ A2 遗留 Minor：next_run 的「基准命中」边界
def test_next_run_base_hit_returns_base_itself():
    """基准时刻正好命中触发点：APScheduler `get_next_fire_time` 返回基准本身（不是下一分钟）。

    锁定 A2 报告 Minor #3 的既有口径（brief 明确要求 `get_next_fire_time(None, base or now)`）。
    """
    result = TriggerUtil.next_run("cron", "* * * * *", datetime(2026, 10, 18, 12, 0, 0))
    assert result is not None
    assert result.replace(tzinfo=None) == datetime(2026, 10, 18, 12, 0, 0)


# ------------------------------------------------------------ A2 遗留裁决：永不触发的日/月组合判非法
@pytest.mark.parametrize("expr", ["0 9 31 6 *", "0 9 30 2 *"])
def test_validate_cron_rejects_never_firing_day_month(expr):
    """可调度性检查：4 年窗口内找不到下次触发即非法（validate_cron 仍只做语法校验）。"""
    ok, reason = TriggerUtil.validate("cron", expr)
    assert ok is False and "永远不会触发" in reason


def test_validate_cron_accepts_leap_day():
    """闰年 2 月 29 日可触发（4 年窗口内含 2028-02-29）→ 合法。"""
    assert TriggerUtil.validate("cron", "0 9 29 2 *") == (True, "")


# ------------------------------------------------------------ A2 遗留裁决：日与周不得同时为非 *
@pytest.mark.parametrize("expr", ["0 9 1 * mon", "0 9 15 * 1-5"])
def test_validate_cron_rejects_day_and_weekday_together(expr):
    """APScheduler 取 AND、croniter 取 OR → 语义不一致，判非法并引导只指定其一。"""
    ok, reason = TriggerUtil.validate("cron", expr)
    assert ok is False and "只指定其一" in reason


@pytest.mark.parametrize("expr", ["0 9 1 * *", "0 9 * * mon", "0 9 1 1 *"])
def test_validate_cron_accepts_single_of_day_or_weekday(expr):
    assert TriggerUtil.validate("cron", expr) == (True, "")
