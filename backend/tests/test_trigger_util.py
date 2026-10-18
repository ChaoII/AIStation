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
        first = scheduler_util._resolve_interval_args("30 5 2 1 0")
        second = scheduler_util._resolve_interval_args("0 0 1 0 0")
    finally:
        _logger.remove(sink_id)
        scheduler_util._legacy_interval_warned = False

    assert first == {"seconds": 30, "minutes": 5, "hours": 2, "days": 1, "weeks": 0}
    assert second == {"seconds": 0, "minutes": 0, "hours": 1, "days": 0, "weeks": 0}
    assert sum("interval" in message for message in messages) == 1


def test_resolve_interval_args_rejects_bad_input():
    """A4：既不是 JSON 对象、也不是 5 段旧字符串的输入必须报错（不静默吞掉）。"""
    scheduler_util = _scheduler_util()

    with pytest.raises(ValueError):
        scheduler_util._resolve_interval_args("0 0 1")
    with pytest.raises(ValueError):
        scheduler_util._resolve_interval_args("[1, 2, 3]")


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
