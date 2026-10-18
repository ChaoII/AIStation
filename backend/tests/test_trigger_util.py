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


# ============================================================ Task A4：ap_scheduler 改走统一层


def _scheduler_util():
    """取中心调度器工具类。

    `ap_scheduler` 与 `app.plugin.module_task`（其 job controller 反向 import 调度器）存在**既有**
    循环导入：先 import `ap_scheduler` 会失败，先 import `module_task` 则成功。这里固定顺序，
    使本文件的用例在 `PYTEST_NO_APP=1` 快速模式下也能运行（该循环导入非本任务引入）。
    """
    import app.plugin.module_task  # noqa: F401  解开既有循环导入（先 module_task 后 ap_scheduler）
    from app.core import ap_scheduler

    return ap_scheduler.SchedulerUtil


def test_legacy_validators_are_gone():
    """A4：旧校验器必须删除，避免两套口径并存。"""
    import pytest as _pytest

    with _pytest.raises(ImportError):
        import app.utils.cron_util  # noqa: F401

    from app.utils.time_util import TimeUtil

    assert not hasattr(TimeUtil, "validate_cron_expression")


def test_add_cron_job_parses_via_trigger_util(monkeypatch, test_client):
    """A4：add_cron_job 的解析必须走 TriggerUtil（用 spy 断言，不依赖作业能否注册成功）。"""
    from types import SimpleNamespace

    from app.core import ap_scheduler
    from app.utils.trigger_util import TriggerUtil

    seen: dict = {}
    real = TriggerUtil.to_trigger

    def _spy(trigger, args, **kw):
        seen["trigger"], seen["args"] = trigger, args
        return real(trigger, args)

    monkeypatch.setattr(TriggerUtil, "to_trigger", staticmethod(_spy))
    node = SimpleNamespace(
        id=1,
        code="t",
        name="t",
        trigger="cron",
        trigger_args="0 9 * * 1",
        jobstore="default",
        executor="default",
        func="app.core.logger:log",
    )
    try:
        ap_scheduler.SchedulerUtil.add_cron_job(node)
    except Exception:  # noqa: BLE001 只断言解析路径，作业注册失败与本测试无关
        pass
    assert seen.get("trigger") == "cron" and seen.get("args") == "0 9 * * 1"


def test_add_interval_job_parses_json_via_trigger_util(monkeypatch):
    """A4：interval 新契约是 JSON，解析必须走 TriggerUtil（spy 断言收到的已是 dict）。"""
    from types import SimpleNamespace

    from app.utils.trigger_util import TriggerUtil

    scheduler_util = _scheduler_util()
    seen: dict = {}
    real = TriggerUtil.to_trigger

    def _spy(trigger, args, **kw):
        seen["trigger"], seen["args"] = trigger, args
        return real(trigger, args)

    monkeypatch.setattr(TriggerUtil, "to_trigger", staticmethod(_spy))
    node = SimpleNamespace(
        id=2,
        code="t",
        name="t",
        trigger="interval",
        trigger_args='{"hours": 2, "minutes": 30}',
        jobstore="default",
        executor="default",
        func="app.core.logger:log",
    )
    try:
        scheduler_util.add_interval_job(node)
    except Exception:  # noqa: BLE001 只断言解析路径，作业注册失败与本测试无关
        pass
    assert seen.get("trigger") == "interval"
    assert seen.get("args") == {"hours": 2, "minutes": 30}


def test_add_interval_job_accepts_legacy_string_args(monkeypatch):
    """A4：旧的「秒 分 时 天 周」字符串必须仍可解析（兼容存量数据）。"""
    from types import SimpleNamespace

    from app.utils.trigger_util import TriggerUtil

    scheduler_util = _scheduler_util()
    seen: dict = {}
    real = TriggerUtil.to_trigger

    def _spy(trigger, args, **kw):
        seen["trigger"], seen["args"] = trigger, args
        return real(trigger, args)

    monkeypatch.setattr(TriggerUtil, "to_trigger", staticmethod(_spy))
    node = SimpleNamespace(
        id=3,
        code="t",
        name="t",
        trigger="interval",
        trigger_args="30 5 2 1 0",  # 秒 分 时 天 周
        jobstore="default",
        executor="default",
        func="app.core.logger:log",
    )
    try:
        scheduler_util.add_interval_job(node)
    except Exception:  # noqa: BLE001 只断言解析路径，作业注册失败与本测试无关
        pass
    assert seen.get("args") == {"seconds": 30, "minutes": 5, "hours": 2, "days": 1, "weeks": 0}


def test_interval_legacy_string_warns_only_once():
    """A4：旧字符串解析只在日志里提示一次（避免每次注册都刷屏）。"""
    from loguru import logger as _logger

    scheduler_util = _scheduler_util()
    scheduler_util._legacy_interval_warned = False
    messages: list[str] = []
    sink_id = _logger.add(lambda message: messages.append(message), level="WARNING")
    try:
        first = scheduler_util.resolve_interval_args("30 5 2 1 0")
        second = scheduler_util.resolve_interval_args("0 0 1 0 0")
    finally:
        _logger.remove(sink_id)
        scheduler_util._legacy_interval_warned = False

    assert first == {"seconds": 30, "minutes": 5, "hours": 2, "days": 1, "weeks": 0}
    assert second == {"seconds": 0, "minutes": 0, "hours": 1, "days": 0, "weeks": 0}
    assert sum("interval" in message for message in messages) == 1


def test_resolve_interval_args_rejects_bad_input():
    """A4：既不是 JSON 对象、也不是 5 段旧字符串的输入必须报错（不静默吞掉）。"""
    scheduler_util = _scheduler_util()

    with pytest.raises(ValueError) as not_five_fields:
        scheduler_util.resolve_interval_args("0 0 1")
    assert "秒 分 时 天 周" in str(not_five_fields.value)

    with pytest.raises(ValueError):
        scheduler_util.resolve_interval_args("[1, 2, 3]")

    # dict 直接可用（统一层同样接受 dict）
    assert scheduler_util.resolve_interval_args({"minutes": 30}) == {"minutes": 30}


def test_add_date_job_parses_via_trigger_util(monkeypatch):
    """A4：add_date_job 的解析必须走 TriggerUtil。"""
    from types import SimpleNamespace

    from app.utils.trigger_util import TriggerUtil

    scheduler_util = _scheduler_util()
    seen: dict = {}
    real = TriggerUtil.to_trigger

    def _spy(trigger, args, **kw):
        seen["trigger"], seen["args"] = trigger, args
        return real(trigger, args)

    monkeypatch.setattr(TriggerUtil, "to_trigger", staticmethod(_spy))
    node = SimpleNamespace(
        id=4,
        code="t",
        name="t",
        trigger="date",
        trigger_args="2999-01-01 09:00:00",
        jobstore="default",
        executor="default",
        func="app.core.logger:log",
    )
    try:
        scheduler_util.add_date_job(node)
    except Exception:  # noqa: BLE001 只断言解析路径，作业注册失败与本测试无关
        pass
    assert seen.get("trigger") == "date" and seen.get("args") == "2999-01-01 09:00:00"


def test_apply_trigger_bounds_keeps_start_end_date():
    """A4：节点配置的开始/结束时间仍要套到统一层构造的触发器上（对外签名与行为不变）。"""
    scheduler_util = _scheduler_util()

    trigger = TriggerUtil.to_trigger("cron", "0 9 * * mon")
    scheduler_util._apply_trigger_bounds(trigger, "2026-11-01 00:00:00", "2026-12-01 00:00:00")
    assert trigger.start_date.strftime("%Y-%m-%d %H:%M:%S") == "2026-11-01 00:00:00"
    assert trigger.end_date.strftime("%Y-%m-%d %H:%M:%S") == "2026-12-01 00:00:00"
    assert str(trigger.start_date.tzinfo) == "Asia/Shanghai"


def test_node_service_validates_via_trigger_util():
    """A4：节点调试的校验改走 TriggerUtil.validate（源码级锁定，避免旧口径回流）。"""
    import inspect

    from app.plugin.module_task.cronjob.node import service as node_service

    source = inspect.getsource(node_service)
    assert "TriggerUtil.validate(trigger, trigger_args)" in source
    assert "CronUtil" not in source
    # Minor #2：未知类型会先被 TriggerUtil.validate 拦下 → 「不支持的触发方式」死分支已删
    assert "不支持的触发方式" not in source


# ------------------------------------------------------------ A4 修正：节点校验兼容旧 interval 字符串
def test_node_validate_interval_accepts_legacy_string_and_json():
    """A4 修正：节点校验对旧「秒 分 时 天 周」字符串与新 JSON 都判合法。

    C6 把节点页换成 `TriggerEditor` 之前，`IntervalTab` 仍 emit 旧串，
    因此服务层必须先按旧格式解析再交给统一层校验（统一层只认 JSON）。
    """
    from app.plugin.module_task.cronjob.node.service import NodeService

    # 旧串「秒 分 时 天 周」：30 分钟一次
    NodeService._validate_trigger_args("interval", "0 30 * * *")
    # 新契约 JSON：同样 30 分钟一次
    NodeService._validate_trigger_args("interval", '{"minutes": 30}')
    NodeService._validate_trigger_args("interval", {"minutes": 30})


def test_node_validate_interval_all_zero_reason_is_readable():
    """A4 修正：旧串全 0 / JSON 全 0 都给出可读原因（不产生每秒触发的无效作业）。"""
    from app.plugin.module_task.cronjob.node.service import NodeService

    with pytest.raises(CustomException) as legacy_all_zero:
        NodeService._validate_trigger_args("interval", "0 0 0 0 0")
    assert "至少" in legacy_all_zero.value.msg

    with pytest.raises(CustomException) as json_all_zero:
        NodeService._validate_trigger_args("interval", '{"hours": 0}')
    assert "至少" in json_all_zero.value.msg


def test_node_validate_interval_bad_input_reason_is_readable():
    """A4 修正：既非 JSON 对象也非旧串时，错误原因必须说明两种合法格式。"""
    from app.plugin.module_task.cronjob.node.service import NodeService

    with pytest.raises(CustomException) as exc:
        NodeService._validate_trigger_args("interval", "0 0 1")
    assert "JSON" in exc.value.msg and "秒 分 时 天 周" in exc.value.msg


def test_node_validate_cron_and_date_still_use_unified_layer():
    """A4 修正：cron / date 分支仍原样回传统一层原因（未因 interval 兼容而放松）。"""
    from app.plugin.module_task.cronjob.node.service import NodeService

    NodeService._validate_trigger_args("cron", "0 9 * * 1")
    with pytest.raises(CustomException) as cron_bad:
        NodeService._validate_trigger_args("cron", "0 9 * * 5-1")
    assert "跨周" in cron_bad.value.msg

    past = (datetime.now() - timedelta(minutes=1)).strftime("%Y-%m-%d %H:%M:%S")
    with pytest.raises(CustomException) as date_past:
        NodeService._validate_trigger_args("date", past)
    assert "过去" in date_past.value.msg


def test_node_validate_unknown_trigger_is_rejected_before_dispatch():
    """Minor #2：未知类型在校验阶段就被拦下（因此 dispatch 的 else 死分支可删）。"""
    from app.plugin.module_task.cronjob.node.service import NodeService

    with pytest.raises(CustomException) as exc:
        NodeService._validate_trigger_args("weekly", None)
    assert "weekly" in exc.value.msg


# ------------------------------------------------------------ A4 修正轮 2：节点校验兼容旧 Quartz cron 串
def test_node_validate_cron_accepts_legacy_quartz_strings():
    """A4 修正轮 2：节点页 `vue3-cron-plus` 输出的旧 Quartz 串在过渡期必须可用。

    - 7 段（秒=0，末段年为 `*`）：裁掉「不限年份」后等价 5 段 → 合法；
    - 6 段（秒=0，含 `?`）：去首段 + `?`→`*` → 合法；
    - 5 段新契约：原样合法。
    """
    from app.plugin.module_task.cronjob.node.service import NodeService

    NodeService._validate_trigger_args("cron", "0 0 9 * * ? *")
    NodeService._validate_trigger_args("cron", "0 0 9 ? * *")
    NodeService._validate_trigger_args("cron", "0 9 * * 1")


def test_node_validate_returns_normalized_args_usable_for_registration():
    """A4 修正轮 2：归一结果必须回传（否则校验通过、注册仍会因旧串报错）。"""
    from app.plugin.module_task.cronjob.node.service import NodeService

    # 7 段旧 Quartz 串 → 5 段，且能被统一层直接构造触发器（注册路径不会再报 7 段）
    cron_args = NodeService._validate_trigger_args("cron", "0 0 9 * * ? *")
    assert cron_args == "0 9 * * *"
    assert str(TriggerUtil.to_trigger("cron", cron_args).timezone) == "Asia/Shanghai"

    # 6 段含 `?` → 5 段
    assert NodeService._validate_trigger_args("cron", "0 0 9 ? * *") == "0 9 * * *"
    # 5 段新契约 → 规范化（周字段映射为星期名）
    assert NodeService._validate_trigger_args("cron", "0 9 * * 1") == "0 9 * * mon"

    # 旧 interval 串 → JSON 字典，且能被统一层直接构造触发器
    interval_args = NodeService._validate_trigger_args("interval", "0 30 * * *")
    assert interval_args == {"seconds": 0, "minutes": 30, "hours": 0, "days": 0, "weeks": 0}
    TriggerUtil.to_trigger("interval", interval_args)

    # date 原样返回
    assert (
        NodeService._validate_trigger_args("date", "2999-01-01 09:00:00") == "2999-01-01 09:00:00"
    )


def test_node_validate_cron_rejects_seconds_and_concrete_year_with_reason():
    """A4 修正轮 2：秒位非 0 / 带具体年份 → 可读错误，并提示改用 5 段。"""
    from app.plugin.module_task.cronjob.node.service import NodeService

    with pytest.raises(CustomException) as seconds:
        NodeService._validate_trigger_args("cron", "30 0 9 * * ? *")
    assert "秒" in seconds.value.msg and "5 段" in seconds.value.msg

    with pytest.raises(CustomException) as concrete_year:
        NodeService._validate_trigger_args("cron", "0 0 9 * * ? 2026")
    assert "7 段" in concrete_year.value.msg and "5 段" in concrete_year.value.msg


def test_node_validate_cron_legacy_normalization_keeps_weekday_semantics():
    """A4 修正轮 2：旧串规范化后周字段口径与统一层一致（1=周一、0/7=周日）。"""
    from app.plugin.module_task.cronjob.node.service import NodeService

    NodeService._validate_trigger_args("cron", "0 0 9 * * 2")  # 周二
    with pytest.raises(CustomException) as weekday_bad:
        NodeService._validate_trigger_args("cron", "0 0 9 * * 9")
    assert "周字段" in weekday_bad.value.msg


# ============================================================ Task A5：三处写入路径改走统一层
# 口径：写入即规范化（`0 9 * * 1-5` → `0 9 * * mon,tue,wed,thu,fri`）；「下次运行时间」
# 一律来自 `TriggerUtil.next_run`（修 D5 周字段错位：旧实现用 `CronTrigger.from_crontab`
# 解析，`1-5` 会按 APScheduler 的 mon=0 被读成周二~周六，比标准 crontab 整体后移一天）。


def _now_naive() -> datetime:
    """上海时区的「墙上时间」——与响应里 datetime 的编码口径一致（`%Y-%m-%d %H:%M:%S`）。"""
    from zoneinfo import ZoneInfo

    return datetime.now(ZoneInfo(TriggerUtil.TIMEZONE)).replace(tzinfo=None)


def _parse_response_datetime(value: str) -> datetime:
    """响应里的 datetime 一律是 `%Y-%m-%d %H:%M:%S`（见 common/response.py 自定义编码器）。"""
    return datetime.strptime(str(value), "%Y-%m-%d %H:%M:%S")


def _assert_next_run_is_standard_crontab(
    stored: datetime, expr: str, t0: datetime, t1: datetime
) -> None:
    """落库的下次运行时间必须等于「标准 crontab 语义」下的下一次触发（croniter 独立参照）。

    `t0`/`t1` 是**请求前后捕获**的基准时刻——对本次请求而言就是固定 base，不再用断言时刻的
    `now` 取参照（那会跨分钟边界 flaky）。若请求窗口恰好跨过一次触发点（每天一次的毫秒级
    窗口），两个候选值都接受；而旧实现（`from_crontab`，整体 +1 天）两个都不是，仍会被判出。
    """
    ref0 = croniter(expr, t0).get_next(datetime)
    ref1 = croniter(expr, t1).get_next(datetime)
    assert stored in ({ref0, ref1} if ref0 != ref1 else {ref0})


def _minimal_workflow_graph() -> dict:
    """最小可保存的工作流图（start → end）。"""
    return {
        "nodes": [
            {"id": "start", "type": "start", "data": {"variables": []}},
            {"id": "end", "type": "end", "data": {"output_template": "ok"}},
        ],
        "edges": [{"id": "e1", "source": "start", "target": "end"}],
    }


def _create_workflow(test_client, auth_headers, name: str) -> int:
    return test_client.post(
        "/api/v1/ai/workflows/create",
        json={"name": name, "graph": _minimal_workflow_graph()},
        headers=auth_headers,
    ).json()["data"]["id"]


def _delete_workflow(test_client, auth_headers, wf_id: int) -> None:
    test_client.request("DELETE", "/api/v1/ai/workflows/delete", json=[wf_id], headers=auth_headers)


def test_workflow_schedule_next_run_is_monday(test_client, auth_headers):
    """工作流定时调度：写入即规范化，下次运行时间来自统一层（改前周字段错位 → 周二）。"""
    wf = _create_workflow(test_client, auth_headers, "pytest-A5-定时调度")
    try:
        url = f"/api/v1/ai/workflows/{wf}/schedule"
        t0 = _now_naive()
        saved = test_client.put(
            url,
            json={"cron": "0 9 * * 1-5", "enabled": True},
            headers=auth_headers,
        )
        t1 = _now_naive()
        assert saved.status_code == 200, saved.text
        assert saved.json()["data"]["cron"] == "0 9 * * mon,tue,wed,thu,fri"

        d = test_client.get(url, headers=auth_headers).json()["data"]
        assert d["cron"] == "0 9 * * mon,tue,wed,thu,fri"
        assert d["trigger"] == "cron"
        assert d["trigger_args"] == "0 9 * * mon,tue,wed,thu,fri"

        next_run = _parse_response_datetime(d["next_run_time"])
        # 与独立参照（croniter，标准 crontab）一致 → 周字段未错位；且必须落在工作日
        _assert_next_run_is_standard_crontab(next_run, "0 9 * * mon,tue,wed,thu,fri", t0, t1)
        assert next_run.weekday() < 5
    finally:
        _delete_workflow(test_client, auth_headers, wf)


def test_workflow_schedule_rejects_invalid_cron_with_unified_reason(test_client, auth_headers):
    """工作流定时调度：非法表达式不落库，400 + 原因原样来自统一层（跨周区间）。"""
    wf = _create_workflow(test_client, auth_headers, "pytest-A5-非法调度")
    try:
        url = f"/api/v1/ai/workflows/{wf}/schedule"
        before = test_client.get(url, headers=auth_headers).json()["data"]
        r = test_client.put(
            url,
            json={"cron": "0 9 * * 5-1", "enabled": True},
            headers=auth_headers,
        )
        assert r.status_code == 400
        assert "跨周" in r.json()["msg"]
        # 非法表达式不落库：配置与提交前完全一致
        after = test_client.get(url, headers=auth_headers).json()["data"]
        assert after == before
        assert after["trigger_args"] != "0 9 * * 5-1"
    finally:
        _delete_workflow(test_client, auth_headers, wf)


def test_workflow_schedule_empty_cron_only_allowed_when_disabled(test_client, auth_headers):
    """I2：空表达式 + 启用 → 400（不留「已启用但永不触发」）；空 + 禁用 → 允许（清空配置）。"""
    from app.plugin.module_ai.workflow.service import _EMPTY_TRIGGER_MSG

    wf = _create_workflow(test_client, auth_headers, "pytest-A5-空表达式")
    try:
        url = f"/api/v1/ai/workflows/{wf}/schedule"
        on = test_client.put(url, json={"cron": "", "enabled": True}, headers=auth_headers)
        assert on.status_code == 400
        assert on.json()["msg"] == _EMPTY_TRIGGER_MSG

        off = test_client.put(url, json={"cron": "", "enabled": False}, headers=auth_headers)
        assert off.status_code == 200, off.text
        d = off.json()["data"]
        assert d["enabled"] is False
        # A10：空值口径统一为 None（原 workflow 副本返回 ""）
        assert d["trigger_args"] is None and d["cron"] == ""
        assert d["next_run_time"] is None

        # 未配置表达式时直接切「启用」同样被挡（只传 enabled，不传 cron）
        enable_only = test_client.put(url, json={"enabled": True}, headers=auth_headers)
        assert enable_only.status_code == 400
        assert enable_only.json()["msg"] == _EMPTY_TRIGGER_MSG
    finally:
        _delete_workflow(test_client, auth_headers, wf)


def test_workflow_schedule_is_not_due_when_unconfigured():
    """I2：轮询判定——未配置（next_run_time 为空）**不执行**（原先被当成到期，每 60 秒跑一次）。"""
    from zoneinfo import ZoneInfo

    from app.plugin.module_ai.workflow.service import AiWorkflowService

    now = datetime.now(ZoneInfo(TriggerUtil.TIMEZONE))
    assert AiWorkflowService._is_due(None, now) is False
    assert AiWorkflowService._is_due(now - timedelta(minutes=1), now) is True
    assert AiWorkflowService._is_due(now + timedelta(minutes=1), now) is False
    # SQLite 读回来是 naive：按 Asia/Shanghai 解释，不与 aware 的 now 混用抛错
    assert AiWorkflowService._is_due((now - timedelta(minutes=1)).replace(tzinfo=None), now) is True


def test_workspace_cron_writes_normalized_cron_and_unified_next_run(test_client, auth_headers):
    """工作台定时任务：写入即规范化（旧列已删，落 trigger/trigger_args），下次运行来自统一层。"""
    t0 = _now_naive()
    r = test_client.post(
        "/api/v1/ai/workspace/cron/create",
        json={
            "name": "pytest-A5-定时任务",
            "description": "",
            "cron": "0 9 * * 1-5",
            "target_type": "workflow",
            "target_id": 1,
            "enabled": True,
        },
        headers=auth_headers,
    )
    t1 = _now_naive()
    assert r.status_code == 200, r.text
    created = r.json()["data"]
    try:
        assert created["trigger"] == "cron"
        assert created["trigger_args"] == "0 9 * * mon,tue,wed,thu,fri"
        assert created["cron"] == "0 9 * * mon,tue,wed,thu,fri"
        _assert_next_run_is_standard_crontab(
            _parse_response_datetime(created["next_run_time"]),
            "0 9 * * mon,tue,wed,thu,fri",
            t0,
            t1,
        )

        # 列表接口读到的是同一份规范化值（不再有自算实现）
        listed = test_client.get("/api/v1/ai/workspace/cron/list", headers=auth_headers)
        items = listed.json()["data"]["items"]
        row = next(x for x in items if x["id"] == created["id"])
        assert row["trigger_args"] == "0 9 * * mon,tue,wed,thu,fri"

        # 非法表达式：400 + 原因来自统一层，且不落库
        bad = test_client.post(
            "/api/v1/ai/workspace/cron/create",
            json={
                "name": "pytest-A5-非法任务",
                "description": "",
                "cron": "0 9 * * 5-1",
                "target_type": "workflow",
                "target_id": 1,
                "enabled": True,
            },
            headers=auth_headers,
        )
        assert bad.status_code == 400
        assert "跨周" in bad.json()["msg"]
    finally:
        test_client.request(
            "DELETE",
            "/api/v1/ai/workspace/cron/delete",
            json=created["id"],
            headers=auth_headers,
        )


def test_workspace_cron_empty_cron_only_allowed_when_disabled(test_client, auth_headers):
    """I2：空表达式 + 启用 → 400；空 + 禁用 → 允许（`trigger_args` 空、无下次运行）。"""
    from app.plugin.module_ai.workspace.service import _EMPTY_TRIGGER_MSG

    payload = {
        "name": "pytest-A5-空表达式",
        "description": "",
        "cron": "",
        "target_type": "workflow",
        "target_id": 1,
    }
    on = test_client.post(
        "/api/v1/ai/workspace/cron/create",
        json={**payload, "enabled": True},
        headers=auth_headers,
    )
    assert on.status_code == 400
    assert on.json()["msg"] == _EMPTY_TRIGGER_MSG

    off = test_client.post(
        "/api/v1/ai/workspace/cron/create",
        json={**payload, "enabled": False},
        headers=auth_headers,
    )
    assert off.status_code == 200, off.text
    created = off.json()["data"]
    try:
        assert created["enabled"] is False
        # A10：空值口径统一为 None（原 workspace 副本返回 ""）
        assert created["trigger_args"] is None and created["cron"] == ""
        assert created["next_run_time"] is None

        # 只切「启用」而库里没有表达式：同样被挡
        enable_only = test_client.put(
            f"/api/v1/ai/workspace/cron/update/{created['id']}",
            json={"enabled": True},
            headers=auth_headers,
        )
        assert enable_only.status_code == 400
        assert enable_only.json()["msg"] == _EMPTY_TRIGGER_MSG
    finally:
        test_client.request(
            "DELETE",
            "/api/v1/ai/workspace/cron/delete",
            json=created["id"],
            headers=auth_headers,
        )


def test_workspace_cron_disable_clears_next_run_via_unified_layer(test_client, auth_headers):
    """工作台定时任务：禁用后下次运行时间为空（统一层口径），改回启用重新计算。"""
    created = test_client.post(
        "/api/v1/ai/workspace/cron/create",
        json={
            "name": "pytest-A5-启停",
            "description": "",
            "cron": "0 9 * * *",
            "target_type": "workflow",
            "target_id": 1,
            "enabled": True,
        },
        headers=auth_headers,
    ).json()["data"]
    try:
        off = test_client.put(
            f"/api/v1/ai/workspace/cron/update/{created['id']}",
            json={"enabled": False},
            headers=auth_headers,
        ).json()["data"]
        assert off["enabled"] is False and off["next_run_time"] is None
        assert off["trigger_args"] == "0 9 * * *"  # 表达式不因禁用被清掉

        t0 = _now_naive()
        on = test_client.put(
            f"/api/v1/ai/workspace/cron/update/{created['id']}",
            json={"enabled": True},
            headers=auth_headers,
        ).json()["data"]
        t1 = _now_naive()
        assert on["enabled"] is True
        _assert_next_run_is_standard_crontab(
            _parse_response_datetime(on["next_run_time"]), "0 9 * * *", t0, t1
        )
    finally:
        test_client.request(
            "DELETE",
            "/api/v1/ai/workspace/cron/delete",
            json=created["id"],
            headers=auth_headers,
        )


def test_train_schedule_writes_normalized_trigger_and_keeps_legacy_field():
    """训练定时计划：写入即规范化（cron_expr → trigger/trigger_args），列表保留旧字段兼容。"""
    import asyncio
    from types import SimpleNamespace as SN

    from app.plugin.module_train.schedule_service import ScheduleService

    def _data(cron_expr: str) -> SN:
        return SN(
            name="pytest-A5-定时训练",
            dataset_id=1,
            annotation_task_id=None,
            framework="torchkiln",
            hyperparams={},
            cron_expr=cron_expr,
        )

    auth = SN(user=SN(id=1))
    created = asyncio.run(ScheduleService.create_schedule(_data("0 9 * * 1-5"), auth))
    try:
        rows = asyncio.run(ScheduleService.list_schedules())
        row = next(r for r in rows if r["id"] == created["id"])
        assert row["trigger"] == "cron"
        assert row["trigger_args"] == "0 9 * * mon,tue,wed,thu,fri"
        # 前端 C 阶段切到新字段之前，列表仍读旧字段 `cron_expr`
        assert row["cron_expr"] == "0 9 * * mon,tue,wed,thu,fri"
    finally:
        asyncio.run(ScheduleService.delete_schedules([created["id"]]))

    with pytest.raises(CustomException) as invalid:
        asyncio.run(ScheduleService.create_schedule(_data("0 9 * * 5-1"), auth))
    assert "跨周" in invalid.value.msg


def test_train_schedule_empty_cron_only_allowed_when_disabled():
    """I2：训练计划（默认启用）空表达式 → 报错；改成禁用并清空表达式 → 允许；再启用 → 报错。"""
    import asyncio
    from types import SimpleNamespace as SN

    from app.plugin.module_train.schedule_service import _EMPTY_TRIGGER_MSG, ScheduleService

    def _data(cron_expr: str) -> SN:
        return SN(
            name="pytest-A5-空表达式训练",
            dataset_id=1,
            annotation_task_id=None,
            framework="torchkiln",
            hyperparams={},
            cron_expr=cron_expr,
        )

    auth = SN(user=SN(id=1))
    # 新建即启用（模型 enabled 默认 True）→ 空表达式必须当场报错
    with pytest.raises(CustomException) as empty_on_create:
        asyncio.run(ScheduleService.create_schedule(_data(""), auth))
    assert empty_on_create.value.msg == _EMPTY_TRIGGER_MSG
    assert empty_on_create.value.status_code == 400

    created = asyncio.run(ScheduleService.create_schedule(_data("0 9 * * *"), auth))
    try:
        # 禁用 + 清空表达式：允许（「关闭调度 / 清空配置」语义）
        asyncio.run(ScheduleService.update_schedule(created["id"], SN(cron_expr="", enabled=False)))
        rows = asyncio.run(ScheduleService.list_schedules())
        row = next(r for r in rows if r["id"] == created["id"])
        assert row["enabled"] is False
        assert row["trigger_args"] is None and row["cron_expr"] == ""

        # 未配置表达式时切「启用」：被挡
        with pytest.raises(CustomException) as empty_on_enable:
            asyncio.run(ScheduleService.update_schedule(created["id"], SN(enabled=True)))
        assert empty_on_enable.value.msg == _EMPTY_TRIGGER_MSG
    finally:
        asyncio.run(ScheduleService.delete_schedules([created["id"]]))


def test_empty_trigger_message_is_consistent_across_three_write_paths():
    """I2：三处写入路径对「启用中但空表达式」必须给出同一句可读错误（口径一致）。"""
    from app.plugin.module_ai.workflow.service import _EMPTY_TRIGGER_MSG as workflow_msg
    from app.plugin.module_ai.workspace.service import _EMPTY_TRIGGER_MSG as workspace_msg
    from app.plugin.module_train.schedule_service import _EMPTY_TRIGGER_MSG as train_msg

    assert workspace_msg == workflow_msg == train_msg
    assert "触发时间" in workspace_msg


def test_write_paths_no_longer_parse_cron_themselves():
    """源码级锁定：三处写入路径不得再出现旧解析器（from_crontab / croniter 自建判定）。"""
    import inspect

    from app.plugin.module_ai.workflow import service as workflow_service
    from app.plugin.module_ai.workspace import service as workspace_service
    from app.plugin.module_train import schedule_service

    for module in (workspace_service, workflow_service, schedule_service):
        source = inspect.getsource(module)
        assert "from_crontab" not in source
        assert "import croniter" not in source
        assert "croniter(" not in source
    assert "_compute_next_run" not in inspect.getsource(workspace_service)
    assert "TriggerUtil.next_run" in inspect.getsource(workspace_service)


# ============================================================ Task A10：四个序列化助手下沉统一层
# 审查 M-1：`_dump_trigger_args` / `_load_trigger_args` / `_describe_trigger` / `_trigger_provided`
# 曾在工作流 / 工作台 / 训练三处**逐字复制**，且空值口径已分叉（`_load_trigger_args` 在
# workflow / workspace 返回 `""`、在 train 返回 `None`）。以下用例钉住统一后的形态。


def test_dump_args_dispatches_by_trigger():
    """`dump_args` 按类型分派：interval → JSON 串、now → NULL、cron / date → 原样。"""
    assert TriggerUtil.dump_args("interval", {"hours": 2, "minutes": 30}) == (
        '{"hours": 2, "minutes": 30}'
    )
    assert TriggerUtil.dump_args("cron", "0 9 * * mon") == "0 9 * * mon"
    assert TriggerUtil.dump_args("date", "2999-01-01 09:00:00") == "2999-01-01 09:00:00"
    # now 按契约本就没有参数（落 NULL），不是「未配置」
    assert TriggerUtil.dump_args("now", None) is None
    # 空值原样透传（未配置的行保持空，不发明值）
    assert TriggerUtil.dump_args("cron", None) is None


def test_load_args_dispatches_by_trigger():
    """`load_args` 按类型还原：interval 的 JSON 串 → 对象；cron / date 原样；now → None。"""
    assert TriggerUtil.load_args("interval", '{"hours": 2, "minutes": 30}') == {
        "hours": 2,
        "minutes": 30,
    }
    # 已是对象（dict）时原样透传，供前端组件直接用
    assert TriggerUtil.load_args("interval", {"hours": 1}) == {"hours": 1}
    assert TriggerUtil.load_args("cron", "0 9 * * mon") == "0 9 * * mon"
    assert TriggerUtil.load_args("date", "2999-01-01 09:00:00") == "2999-01-01 09:00:00"
    assert TriggerUtil.load_args("now", None) is None


@pytest.mark.parametrize("trigger", ["cron", "interval", "date", "now"])
def test_load_args_empty_value_is_none_for_all_triggers(trigger):
    """**空值口径统一为 `None`**（三处写入口一致，不再有的返回 `""`）。"""
    assert TriggerUtil.load_args(trigger, None) is None
    assert TriggerUtil.load_args(trigger, "") is None
    assert TriggerUtil.load_args(trigger, "   ") is None


def test_load_args_dirty_interval_json_is_echoed_without_raising():
    """脏 interval JSON（迁移遗留）原样回显，绝不把列表接口打成 500。"""
    assert TriggerUtil.load_args("interval", "{not json") == "{not json"
    # 合法 JSON 但不是对象（旧数组写法）同样原样回显
    assert TriggerUtil.load_args("interval", "[1, 2, 3]") == "[1, 2, 3]"
    assert TriggerUtil.load_args("interval", '"30 5 2 1 0"') == '"30 5 2 1 0"'


def test_describe_args_dispatches_by_trigger():
    """`describe_args` 按类型给中文短句；空值 → None；now 无参数也算「已配置」。"""
    assert TriggerUtil.describe_args("cron", "0 9 * * 1") == "每周一 09:00"
    assert (
        TriggerUtil.describe_args("interval", {"hours": 2, "minutes": 30}) == "每 2 小时 30 分一次"
    )
    assert TriggerUtil.describe_args("date", "2999-01-01 09:00:00") == "2999-01-01 09:00 执行一次"
    assert TriggerUtil.describe_args("now", None) == "保存后立即执行一次"


@pytest.mark.parametrize("trigger", ["cron", "interval", "date"])
def test_describe_args_empty_value_is_none(trigger):
    assert TriggerUtil.describe_args(trigger, None) is None
    assert TriggerUtil.describe_args(trigger, "  ") is None


@pytest.mark.parametrize(
    ("trigger", "args"),
    [
        ("cron", "0 0 9 L * *"),  # 遗留 Quartz 写法
        ("cron", "0 9 * * 5-1"),
        ("interval", "{not json"),
        ("interval", {"hours": 0}),  # 全 0 无法描述
        ("date", "not-a-date"),
    ],
)
def test_describe_args_dirty_data_returns_none_without_raising(trigger, args):
    """脏数据不得把列表/详情打成 500（兜底 `except Exception`，不只捕可预期异常）。"""
    assert TriggerUtil.describe_args(trigger, args) is None


def test_args_provided_semantics():
    """「请求是否提交了触发配置」：显式空串算提交；`now` 按契约视为已提供。"""
    assert TriggerUtil.args_provided("cron", None) is True
    assert TriggerUtil.args_provided(None, "0 9 * * mon") is True  # 只带旧字段
    assert TriggerUtil.args_provided("", None) is True  # 显式空串 = 清空配置
    assert TriggerUtil.args_provided(None, "") is True
    assert TriggerUtil.args_provided(None, None) is False
    # `now` 无参数：类型本身即「已提供」
    assert TriggerUtil.args_provided("now", None) is True


def test_three_services_no_longer_duplicate_trigger_helpers():
    """源码级锁定：三处写入口不得再有本地副本（统一层是唯一口径）。"""
    import inspect

    from app.plugin.module_ai.workflow import service as workflow_service
    from app.plugin.module_ai.workspace import service as workspace_service
    from app.plugin.module_train import schedule_service

    for module in (workspace_service, workflow_service, schedule_service):
        source = inspect.getsource(module)
        for helper in (
            "_dump_trigger_args",
            "_load_trigger_args",
            "_describe_trigger",
            "_trigger_provided",
        ):
            assert helper not in source, (module.__name__, helper)
        assert "TriggerUtil.dump_args" in source
        assert "TriggerUtil.load_args" in source
        assert "TriggerUtil.describe_args" in source
    assert "TriggerUtil.args_provided" in inspect.getsource(workspace_service)
    assert "TriggerUtil.args_provided" in inspect.getsource(schedule_service)
