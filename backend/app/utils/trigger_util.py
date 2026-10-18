"""统一触发器工具（全平台唯一口径）。

本模块是四种触发类型（`cron` / `interval` / `date` / `now`）的**唯一实现**，
规范化、校验、中文描述、APScheduler 触发器构造与「下次运行时间」都收敛于此。

**cron 口径**：**标准 5 段 crontab** `分 时 日 月 周`。
- 周字段按标准 crontab 语义：`0`/`7` = 周日，也接受 `mon…sun`（大小写不敏感）；
- 规范化后周字段统一输出**星期名列表**（区间展开为显式列表，如 `1-5` → `mon,tue,wed,thu,fri`）：
  两套下游库（APScheduler 的 `mon=0…sun=6` 与 croniter 的 `sun=0…sat=6`）对名称区间的解释相反，
  只有展开成显式列表才能消除这种口径不一致；
- 不支持 Quartz 专有语法（`?`/`L`/`W`/`#`）与 6/7 段（秒、年份）写法，一律明确报错；
- 通配与列表混写（`*,mon`、`1,*`）归一为 `*`；
- 触发器构造（`to_cron_trigger`）、中文描述（`describe_cron`）与「下次运行时间」（`next_run`）
  同源复用规范化结果，时区固定 `Asia/Shanghai`。

**分派层**（`normalize` / `validate` / `describe` / `to_trigger` / `next_run` / `preview` /
`needs_review`）按 `trigger` 分派：
- `interval`：参数为 JSON `{"weeks":0,"days":0,"hours":2,"minutes":30,"seconds":0}`（**全 0 判非法**）；
- `date`：参数为 `"YYYY-MM-DD HH:mm:ss"`（**过去时间判非法**）；
- `now`：参数为 `null`，构造 `DateTrigger(now + 2s)` 的一次性作业。

**唯一校验入口是 `validate`**：`normalize` / `describe` / `to_trigger` 只做解析级检查
（非法输入抛 `ValueError`，未知 `trigger` 抛 `CustomException`）；`validate` 额外做
cron 的**可调度性检查**（永不触发的日/月组合、日与周同时为非 `*`）并返回可读原因。
其中「日」字段为 `*` / `*/1` / `1-31` 视为**覆盖全集**（等价「不限制日」），不算「日与周同时指定」。

**面向接口的两个入口**：
- `preview(trigger, args) -> dict`：一次产出「是否合法 / 可读原因 / 人话描述 / 下次运行时间」，
  四个入口的 `POST .../trigger/preview` 直接回显，前端**不自算**（避免第二套口径）；
- `needs_review(trigger, args) -> bool`：列表行是否需要人工确认（迁移跳过 / 新校验不通过）。

供 AI 工作台/工作流、训练调度、系统定时任务节点与中心调度器共用。
"""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timedelta, tzinfo
from zoneinfo import ZoneInfo

from apscheduler.triggers.base import BaseTrigger
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.date import DateTrigger
from apscheduler.triggers.interval import IntervalTrigger

from app.core.exceptions import CustomException

logger = logging.getLogger(__name__)


class TriggerUtil:
    """触发器工具类（cron 的规范化、校验、构造、描述与下次运行时间）。"""

    #: 统一时区：全平台一律 `Asia/Shanghai`，避免「同表达式不同机器不同触发时刻」
    TIMEZONE = "Asia/Shanghai"

    #: 支持的触发类型（顺序即 UI 展示顺序）
    TRIGGERS = ("cron", "interval", "date", "now")

    #: interval 参数字段（顺序即描述拼装顺序）
    _INTERVAL_FIELDS = ("weeks", "days", "hours", "minutes", "seconds")

    #: interval 字段 → 中文单位（`describe` 用）
    _INTERVAL_LABELS = {
        "weeks": "周",
        "days": "天",
        "hours": "小时",
        "minutes": "分",
        "seconds": "秒",
    }

    #: date 参数与预览输出的统一时间格式
    _DATETIME_FORMAT = "%Y-%m-%d %H:%M:%S"

    #: date 参数可接受的格式（秒可省略）
    _DATE_FORMATS = (_DATETIME_FORMAT, "%Y-%m-%d %H:%M")

    #: `now` 的延迟秒数：先让保存接口返回，再触发一次性作业
    _NOW_DELAY_SECONDS = 2

    #: cron 可调度性检查窗口（天）：4 年 + 1 天，覆盖闰年 2/29（如 2028-02-29）
    _SCHEDULABLE_WINDOW_DAYS = 365 * 4 + 1

    _UNKNOWN_TRIGGER_HINT = "支持 cron / interval / date / now"

    # 周字段映射表：标准 crontab（0/7=周日）→ 调度器可读的星期名
    _WEEKDAY_MAP = {
        "0": "sun",
        "7": "sun",
        "sun": "sun",
        "1": "mon",
        "mon": "mon",
        "2": "tue",
        "tue": "tue",
        "3": "wed",
        "wed": "wed",
        "4": "thu",
        "thu": "thu",
        "5": "fri",
        "fri": "fri",
        "6": "sat",
        "sat": "sat",
    }

    # 周字段的标准数字序：0=周日…6=周六；`7` 亦指周日（区间比较按**原始数字** 0..7 处理）
    _WEEKDAY_NUMBER = {"sun": 0, "mon": 1, "tue": 2, "wed": 3, "thu": 4, "fri": 5, "sat": 6}
    # 数字 → 名称（下标 7 亦为周日，展开时靠去重收敛为一次）
    _WEEKDAY_BY_NUMBER = ("sun", "mon", "tue", "wed", "thu", "fri", "sat", "sun")

    # 数值字段取值范围：(最小, 最大, 字段名)
    _FIELD_RANGES = (
        (0, 59, "分"),
        (0, 23, "时"),
        (1, 31, "日"),
        (1, 12, "月"),
    )

    _SEGMENT_REASON = "只支持 5 段标准 crontab（分 时 日 月 周）"

    #: 「日」字段中语义等价于「不限制日」的写法（生成式 UI 常写 `1-31`）：
    #: 只有**真正受限**的日字段（如 `1`、`15`、`1-15`）才构成「日与周同时指定」。
    _FULL_DAY_FIELDS = ("*", "*/1", "1-31")

    #: 「校验通过却没有下次运行时间」的分类型可读提示
    #: （cron 永不触发 ≠ date 已过期，预览不得笼统写「表达式非法」）
    _NO_NEXT_RUN_REASON = {
        "cron": "该表达式在可预见的未来不会触发（请检查「日」与「月」的组合，如 6 月 31 日）",
        "date": "该单次执行时间已过（如需立即执行请选择「立即执行」）",
        "interval": "间隔时长无效，没有下次运行时间",
        "now": "「立即执行」只在保存后触发一次，没有下次运行时间",
    }

    #: 星期名 → 中文标签（`describe_cron` 用）
    _WEEKDAY_LABEL = {
        "sun": "周日",
        "mon": "周一",
        "tue": "周二",
        "wed": "周三",
        "thu": "周四",
        "fri": "周五",
        "sat": "周六",
    }

    # ------------------------------------------------------------------ 对外 API

    @classmethod
    def validate_cron(cls, expr: str) -> tuple[bool, str]:
        """校验 cron 表达式。

        返回 `(是否合法, 可读原因)`；合法时原因为空字符串。原因文案为中文短句，
        可直接用于接口 400 响应与前端提示。
        """
        try:
            ok, reason, _ = cls._parse_cron(expr)
        except ValueError:
            # 只兜底解析层可预期的数值转换错误；其它异常照常抛出，不掩盖真实 bug
            logger.exception("cron 表达式解析异常：%r", expr)
            return False, "cron 表达式解析失败"
        return ok, reason

    @classmethod
    def normalize_cron(cls, expr: str) -> str:
        """规范化 cron 表达式（周字段映射为星期名列表，区间展开；输出标准 5 段）。

        与 `validate_cron` 同源：校验通过 ⇒ 本方法一定不抛错。
        表达式非法时抛 `ValueError`，异常信息即 `validate_cron` 的原因文案。
        """
        ok, reason, normalized = cls._parse_cron(expr)
        if not ok:
            raise ValueError(reason)
        return normalized

    @classmethod
    def to_cron_trigger(cls, expr: str) -> CronTrigger:
        """构造 APScheduler 的 `CronTrigger`（时区固定 `Asia/Shanghai`）。

        输入先经 `normalize_cron` 规范化（周字段已是标准 crontab 语义的星期名列表），
        因此「校验通过 ⇒ 一定能构造成功」（同源约束）。
        表达式非法时抛 `ValueError`。
        """
        minute, hour, day, month, day_of_week = cls.normalize_cron(expr).split()
        return CronTrigger(
            minute=minute,
            hour=hour,
            day=day,
            month=month,
            day_of_week=day_of_week,
            timezone=cls.TIMEZONE,
        )

    @classmethod
    def describe_cron(cls, expr: str) -> str:
        """把 cron 表达式描述成中文短句（如「每周一 09:00」「每天 09:00」「每小时第 15 分」）。

        表达式非法时抛 `ValueError`（与 `normalize_cron` 同源）。
        """
        minute, hour, day, month, day_of_week = cls.normalize_cron(expr).split()
        period = cls._describe_period(day, month, day_of_week)

        if hour == "*" and minute == "*":
            return "每分钟" if period == "每天" else f"{period}每分钟"

        hour_step = cls._field_step(hour)
        if hour_step is not None:
            if minute == "0":
                text = f"每 {hour_step} 小时整点"
            elif minute == "*":
                text = f"每 {hour_step} 小时每分钟"
            else:
                text = f"每 {hour_step} 小时第 {cls._join_values(minute)} 分"
            return text if period == "每天" else f"{period}{text}"

        minute_step = cls._field_step(minute)
        if minute_step is not None:
            text = f"每 {minute_step} 分钟"
            if hour == "*":
                return text if period == "每天" else f"{period}{text}"
            text = f"{cls._join_values(hour)} 点的每 {minute_step} 分钟"
            return text if period == "每天" else f"{period} {text}"

        if hour == "*":
            text = "每小时整点" if minute == "0" else f"每小时第 {cls._join_values(minute)} 分"
            return text if period == "每天" else f"{period}{text}"

        if minute == "*":
            text = f"{cls._join_values(hour)} 点的每分钟"
            return text if period == "每天" else f"{period} {text}"

        if cls._is_number_list(minute) and cls._is_number_list(hour):
            return f"{period} {cls._describe_time(minute, hour)}"

        # 兜底：区间等无法写成 `HH:MM` 的写法，按原样字段描述（不猜语义）
        return f"{period} {cls._join_values(hour)} 点的第 {cls._join_values(minute)} 分"

    # ------------------------------------------------------------------ 分派层（四种触发类型）

    @classmethod
    def normalize(cls, trigger: str, args) -> tuple[str, object]:
        """按 `trigger` 规范化参数，返回 `(trigger, 规范化后的参数)`。

        - `cron` → 5 段规范化字符串（周字段为星期名列表）；
        - `interval` → 补齐缺省字段后的 dict（`{"weeks":0,...,"seconds":0}`）；
        - `date` → `"YYYY-MM-DD HH:mm:ss"` 字符串；
        - `now` → `None`。

        只做**解析级**规范化（不校验可调度性/过去时间，那是 `validate` 的职责）；
        参数非法抛 `ValueError`，`trigger` 未知抛 `CustomException`。
        """
        if trigger == "cron":
            return "cron", cls.normalize_cron(args)
        if trigger == "interval":
            return "interval", cls._parse_interval_args(args)
        if trigger == "date":
            return "date", cls._parse_date_args(args).strftime(cls._DATE_FORMATS[0])
        if trigger == "now":
            return "now", None
        raise cls._unknown_trigger(trigger)

    @classmethod
    def validate(cls, trigger: str, args) -> tuple[bool, str]:
        """**唯一对外校验入口**：返回 `(是否合法, 可读原因)`（合法时原因为空串）。

        分派到各类型的校验规则：
        - `cron`：语法校验（同 `validate_cron`）+ 两条收紧——
          「日」与「周」不得同时为非 `*`（APScheduler 取 AND、croniter 取 OR，语义不一致；
          日字段为 `*` / `*/1` / `1-31` 时视为**覆盖全集**，不算同时指定）、
          可调度性检查（4 年窗口内找不到下次触发即非法，如 6 月 31 日）；
        - `interval`：字段非负整数，且**至少一项大于 0**（全 0 会被 APScheduler 视为 1 秒，
          产生每秒触发的无效作业）；
        - `date`：格式合法且**不能是过去时间**（要立即执行请用 `now`）；
        - `now`：恒合法（无参数）。

        未知 `trigger` 返回 `(False, 原因)` 而**不抛异常**，便于接口 400 直接回显。
        """
        if trigger == "cron":
            ok, reason = cls.validate_cron(args)
            if not ok:
                return False, reason
            return cls._check_cron_schedulable(args)
        if trigger == "interval":
            try:
                data = cls._parse_interval_args(args)
            except ValueError as exc:
                return False, str(exc)
            if cls._interval_total_seconds(data) <= 0:
                return False, "间隔时长至少需要一项大于 0（全 0 会产生无效作业）"
            return True, ""
        if trigger == "date":
            try:
                run_at = cls._parse_date_args(args)
            except ValueError as exc:
                return False, str(exc)
            timezone = ZoneInfo(cls.TIMEZONE)
            if run_at.replace(tzinfo=timezone) <= datetime.now(timezone):
                return False, "单次执行时间不能是过去时间（如需立即执行请选择「立即执行」）"
            return True, ""
        if trigger == "now":
            return True, ""
        return False, f"未知的触发类型：{trigger}（{cls._UNKNOWN_TRIGGER_HINT}）"

    @classmethod
    def describe(cls, trigger: str, args) -> str:
        """按 `trigger` 输出中文短句（如「每 2 小时 30 分一次」「2026-10-20 09:00 执行一次」）。

        参数非法抛 `ValueError`，`trigger` 未知抛 `CustomException`。
        """
        if trigger == "cron":
            return cls.describe_cron(args)
        if trigger == "interval":
            data = cls._parse_interval_args(args)
            if cls._interval_total_seconds(data) <= 0:
                raise ValueError("间隔时长至少需要一项大于 0（全 0 会产生无效作业）")
            parts = [
                f"{data[field]} {cls._INTERVAL_LABELS[field]}"
                for field in cls._INTERVAL_FIELDS
                if data[field]
            ]
            return f"每 {' '.join(parts)}一次"
        if trigger == "date":
            run_at = cls._parse_date_args(args)
            return f"{run_at.strftime('%Y-%m-%d %H:%M')} 执行一次"
        if trigger == "now":
            return "保存后立即执行一次"
        raise cls._unknown_trigger(trigger)

    @classmethod
    def to_trigger(cls, trigger: str, args) -> BaseTrigger:
        """按 `trigger` 构造 APScheduler 触发器（时区固定 `Asia/Shanghai`）。

        - `cron` → `CronTrigger`；`interval` → `IntervalTrigger`；
        - `date` / `now` → `DateTrigger`（`now` 为 `now + 2s`）。

        参数非法抛 `ValueError`，`trigger` 未知抛 `CustomException`。
        """
        if trigger == "cron":
            return cls.to_cron_trigger(args)
        if trigger == "interval":
            data = cls._parse_interval_args(args)
            if cls._interval_total_seconds(data) <= 0:
                raise ValueError("间隔时长至少需要一项大于 0（全 0 会产生无效作业）")
            return cls._to_interval_trigger(data)
        if trigger == "date":
            return DateTrigger(run_date=cls._parse_date_args(args), timezone=cls.TIMEZONE)
        if trigger == "now":
            run_date = datetime.now(ZoneInfo(cls.TIMEZONE)) + timedelta(
                seconds=cls._NOW_DELAY_SECONDS
            )
            return DateTrigger(run_date=run_date, timezone=cls.TIMEZONE)
        raise cls._unknown_trigger(trigger)

    @classmethod
    def next_run(cls, trigger: str, args, base: datetime | None = None) -> datetime | None:
        """统一的「下次运行时间」（列表与预览共用），四种触发类型都支持。

        - `trigger="cron"`：`args` 为 5 段 cron 表达式，返回带 `Asia/Shanghai` 时区的时刻；
        - `trigger="interval"`：以基准时刻为起点，返回「起点 + 一个间隔」（与 APScheduler
          `IntervalTrigger` 的默认起点约定一致）；
        - `trigger="date"` / `"now"`：一次性触发器，基准时刻之后才有下次触发，否则 `None`；
        - `base` 为参照时刻（缺省为当前时间）；**朴素时间按 `Asia/Shanghai` 解释**，
          保证同一输入在不同机器时区下结果一致；
        - **永不触发的日/月组合（如 `0 9 31 6 *`、`0 9 30 2 *`）返回 `None`**
          （APScheduler 内部构造非法日期会抛错；契约是「没有下次触发」，由调用方决定如何提示）；
        - `trigger` 未知抛 `CustomException`，参数非法抛 `ValueError`。
        """
        if trigger == "interval":
            data = cls._parse_interval_args(args)
            interval_seconds = cls._interval_total_seconds(data)
            if interval_seconds <= 0:
                raise ValueError("间隔时长至少需要一项大于 0（全 0 会产生无效作业）")
            timezone = ZoneInfo(cls.TIMEZONE)
            now = cls._resolve_base(timezone, base)
            # APScheduler 的起点约定是「起点 + 一个间隔」：显式锚定到基准时刻，
            # 否则 start_date 会在构造时被设为「真实当前时间 + 间隔」，预览结果随机器时间漂移
            trigger_obj = cls._to_interval_trigger(
                data, start_date=now + timedelta(seconds=interval_seconds)
            )
        else:
            trigger_obj = cls.to_trigger(trigger, args)
            timezone = cls._trigger_timezone(trigger_obj)
            now = cls._resolve_base(timezone, base)

        try:
            next_fire = trigger_obj.get_next_fire_time(None, now)
        except (ValueError, OSError):
            # 日/月组合永不发生（如 6 月 31 日）：APScheduler 内部会一路推进到 3001 年并抛错。
            # 按 `datetime | None` 契约返回 None，不把「表达式不触发」升级成 500。
            logger.debug("%s 触发器无有效下次触发时间：%r", trigger, args)
            return None

        if next_fire is not None and next_fire < now:
            # DateTrigger 的 `get_next_fire_time` 不与 now 比较、直接返回 run_date（APScheduler 3.11），
            # 过去的一次性时刻按「没有下次触发」处理（契约 datetime | None，供预览显示「永不触发」）
            return None
        return next_fire

    @classmethod
    def preview(cls, trigger: str, args) -> dict:
        """触发预览：一次调用产出「是否合法 / 可读原因 / 人话描述 / 下次运行时间」。

        四个入口的 `POST .../trigger/preview` 都直接回显本方法的结果——描述与下次运行时间
        **一律由后端产出**，前端不自算（否则又会冒出第二套口径）。

        返回 `{"valid": bool, "reason": str, "describe": str, "next_run": str | None}`：
        - 合法：`valid=True`、`reason=""`、`describe` 为人话短句、
          `next_run` 为 `"YYYY-MM-DD HH:mm:ss"`（`Asia/Shanghai` 墙钟时间，可直接展示）；
        - 非法：`valid=False`、`reason` 为可读原因、`next_run=None`；
          `describe` **尽力而为**（能解析出描述就给，解析不了为空串）。

        三处统一适配（A3 审查遗留）：
        - `next_run is None` 的两种语义**分别提示** —— cron 永不触发（日/月组合不存在）
          与 date 已过期（过去时间）文案不同，不笼统写「表达式非法」；
        - `validate` 返回元组、`describe` / `next_run` 抛异常的**双形态在本方法内收敛**，
          调用方（接口层）只面对返回值一种形态，无需 try/except；
        - 任何脏数据都收敛成 `valid=False` + `reason`，不把预览变成 500。
        """
        ok, reason = cls.validate(trigger, args)
        if not ok:
            return {
                "valid": False,
                "reason": reason,
                "describe": cls._safe_describe(trigger, args),
                "next_run": None,
            }

        try:
            describe = cls.describe(trigger, args)
            next_fire = cls.next_run(trigger, args)
        except (ValueError, CustomException) as exc:
            # validate 已通过却在描述/构造阶段失败：属边界数据，收敛为「非法 + 原因」而不是 500
            logger.warning("触发预览失败（validate 已通过）：%r %r → %s", trigger, args, exc)
            return {"valid": False, "reason": str(exc), "describe": "", "next_run": None}

        if next_fire is None:
            # 校验通过却算不出下次运行：按类型给出可读原因（cron 永不触发 ≠ date 已过期）
            return {
                "valid": False,
                "reason": cls._NO_NEXT_RUN_REASON.get(trigger, "该触发配置没有下次运行时间"),
                "describe": describe,
                "next_run": None,
            }

        return {
            "valid": True,
            "reason": "",
            "describe": describe,
            "next_run": next_fire.strftime(cls._DATETIME_FORMAT),
        }

    @classmethod
    def needs_review(cls, trigger: str | None, args) -> bool:
        """列表行是否需要人工确认（供各模块列表接口逐行标注 `needs_review`）。

        两类（都必须显式提示，否则会以「有任务但调度不上」静默停摆）：

        ① **迁移跳过 / 未配置**：`trigger_args` 为空 —— 迁移时无法等值转换的行会被跳过
           （旧 6 段秒位非 0、7 段带年、解析失败），列表里的空值同样意味着「调度不上」。
           `now` 是唯一例外：它按契约**本就没有参数**，不算被跳过；
        ② **有表达式但按新校验不通过**：遗留 Quartz 写法（`0 0 9 L * *`）、永不触发的
           日/月组合（`0 9 31 6 *`）等 —— 这类行「看起来有调度」，必须人工确认后改写。

        任何解析异常都按「需人工确认」处理：列表接口不得因单行脏数据 500。
        """
        name = "" if trigger is None else str(trigger).strip()
        name = name or "cron"
        if name == "now":
            return False
        if args is None or (isinstance(args, str) and not args.strip()):
            return True
        try:
            ok, _ = cls.validate(name, args)
        except Exception:  # noqa: BLE001 - 单行脏数据不得让整个列表接口 500
            logger.exception("触发参数校验异常，按「需人工确认」处理：%r %r", trigger, args)
            return True
        return not ok

    @classmethod
    def _safe_describe(cls, trigger: str, args) -> str:
        """尽力给出人话描述（供非法输入的预览回显）：解析不了返回空串，绝不抛异常。"""
        try:
            return cls.describe(trigger, args)
        except (ValueError, CustomException):
            return ""

    # ------------------------------------------------------------------ 分派层内部实现

    @classmethod
    def _resolve_base(cls, timezone: tzinfo, base: datetime | None) -> datetime:
        """把参照时刻归一为带时区的时刻；朴素时间按该时区解释（跨机器结果一致）。"""
        if base is None:
            return datetime.now(timezone)
        if base.tzinfo is None:
            return base.replace(tzinfo=timezone)
        return base

    @classmethod
    def _to_interval_trigger(
        cls, data: dict[str, int], start_date: datetime | None = None
    ) -> IntervalTrigger:
        """构造 `IntervalTrigger`（`start_date` 缺省由 APScheduler 取「当前时间 + 间隔」）。"""
        return IntervalTrigger(timezone=cls.TIMEZONE, start_date=start_date, **data)

    @classmethod
    def _unknown_trigger(cls, trigger: str) -> CustomException:
        """未知触发类型的统一异常（400，原因可直接回显给前端）。"""
        return CustomException(
            msg=f"未知的触发类型：{trigger}（{cls._UNKNOWN_TRIGGER_HINT}）",
            code=400,
            status_code=400,
        )

    @classmethod
    def _day_covers_all(cls, day: str) -> bool:
        """「日」字段是否覆盖全月（`*` / `*/1` / `1-31`），即语义上「不限制日」。

        这三种写法文本不同但语义相同（`1-31` 是生成式 UI 常见的「任意日」写法）：
        若按文本判定「日/周同时指定」，`0 9 1-31 * mon`、`0 9 */1 * mon` 会被误判非法，
        且提示里给出的「改写建议」与输入自相矛盾（A3 审查遗留）。
        只有**真正受限**的日字段（如 `1`、`15`、`1-15`）才触发该规则。
        """
        return day in cls._FULL_DAY_FIELDS

    @classmethod
    def _check_cron_schedulable(cls, expr: str) -> tuple[bool, str]:
        """cron 的可调度性检查（`validate("cron", ...)` 专用，`validate_cron` 不做）。"""
        minute, hour, day, month, day_of_week = cls.normalize_cron(expr).split()

        if not cls._day_covers_all(day) and day_of_week != "*":
            # APScheduler 对「日」「周」取 AND，Vixie cron / croniter 取 OR（实测 `0 9 1 * mon` 两边不同）
            # → 实现间语义不一致，判非法并引导只指定其一
            return (
                False,
                "「日」与「周」不能同时指定（只指定其一）："
                f"要按日请写 {minute} {hour} {day} {month} *，"
                f"要按周请写 {minute} {hour} * {month} {day_of_week}",
            )

        if cls._has_next_fire(expr):
            return True, ""
        return False, "该日/月组合永远不会触发（如 6 月 31 日）"

    @classmethod
    def _has_next_fire(cls, expr: str) -> bool:
        """有限窗口（4 年）内是否存在下次触发；永不触发的组合返回 `False`。"""
        trigger = cls.to_cron_trigger(expr)
        now = datetime.now(trigger.timezone)
        horizon = now + timedelta(days=cls._SCHEDULABLE_WINDOW_DAYS)
        try:
            next_fire = trigger.get_next_fire_time(None, now)
        except (ValueError, OSError):
            # 6 月 31 日之类的组合：APScheduler 一路推进到 3001 年并抛错
            return False
        return next_fire is not None and next_fire <= horizon

    @classmethod
    def _parse_interval_args(cls, args) -> dict[str, int]:
        """解析 interval 参数并补齐缺省字段（不校验是否全 0）。

        接受 dict 或 JSON 字符串（兼容 TEXT 列里的旧字符串）；字段必须是非负整数。
        """
        data = cls._as_mapping(args, "间隔参数")
        result: dict[str, int] = {}
        for field in cls._INTERVAL_FIELDS:
            raw = data.get(field, 0)
            if raw is None:
                raw = 0
            if isinstance(raw, bool) or not isinstance(raw, (int, float, str)):
                raise ValueError(f"间隔参数 {field} 必须是数字：{raw!r}")
            if isinstance(raw, float) and not raw.is_integer():
                raise ValueError(f"间隔参数 {field} 必须是整数：{raw!r}")
            try:
                value = int(raw)
            except ValueError:
                raise ValueError(f"间隔参数 {field} 必须是数字：{raw!r}") from None
            if value < 0:
                raise ValueError(f"间隔参数 {field} 不能为负数：{value}")
            result[field] = value
        return result

    @classmethod
    def _as_mapping(cls, args, label: str) -> dict:
        """把参数归一为 dict（`None` → `{}`；JSON 字符串 → `dict`）。"""
        if args is None:
            return {}
        if isinstance(args, dict):
            return dict(args)
        if isinstance(args, str):
            text = args.strip()
            if not text:
                return {}
            try:
                parsed = json.loads(text)
            except ValueError:
                raise ValueError(f"{label}必须是 JSON 对象：{text[:80]}") from None
            if not isinstance(parsed, dict):
                raise ValueError(f"{label}必须是 JSON 对象：{text[:80]}")
            return parsed
        raise ValueError(f"{label}必须是 JSON 对象：{args!r}")

    @classmethod
    def _parse_date_args(cls, args) -> datetime:
        """解析 date 参数为**朴素** `datetime`（时区由 `DateTrigger`/调用方按 Asia/Shanghai 附加）。"""
        if isinstance(args, datetime):
            if args.tzinfo is not None:
                args = args.astimezone(ZoneInfo(cls.TIMEZONE))
            return args.replace(tzinfo=None)

        text = "" if args is None else str(args).strip().replace("T", " ")
        if not text:
            raise ValueError("单次执行时间不能为空")
        for date_format in cls._DATE_FORMATS:
            try:
                return datetime.strptime(text, date_format)
            except ValueError:
                continue
        raise ValueError(f"单次执行时间格式非法（应为 YYYY-MM-DD HH:mm:ss）：{text}")

    @classmethod
    def _interval_total_seconds(cls, data: dict[str, int]) -> int:
        """间隔时长的总秒数（用于「全 0 判非法」）。"""
        return (
            data["weeks"] * 604800
            + data["days"] * 86400
            + data["hours"] * 3600
            + data["minutes"] * 60
            + data["seconds"]
        )

    @staticmethod
    def _trigger_timezone(trigger_obj: BaseTrigger) -> tzinfo:
        """取触发器的时区：优先 `.timezone`，`DateTrigger` 无该属性则取 `run_date.tzinfo`。"""
        timezone = getattr(trigger_obj, "timezone", None)
        if timezone is not None:
            return timezone
        run_date = getattr(trigger_obj, "run_date", None)
        if run_date is not None and run_date.tzinfo is not None:
            return run_date.tzinfo
        return ZoneInfo(TriggerUtil.TIMEZONE)

    # ------------------------------------------------------------------ 描述内部实现

    @classmethod
    def _describe_period(cls, day: str, month: str, day_of_week: str) -> str:
        """描述「周期」（每天 / 每周一、周三 / 每月 1 日 / 每年 3 月 15 日）。"""
        if cls._day_covers_all(day):
            # 「覆盖全集」的日字段（`*` / `*/1` / `1-31`）等价于 `*`：按周描述才与实际触发一致
            # （`0 9 1-31 * mon` 实际按周触发，写成「每月 1-31 日」会误导用户）
            day = "*"
        month_step = cls._field_step(month)
        if month_step is not None:
            if day == "*":
                return f"每 {month_step} 月"
            return f"每 {month_step} 月的{cls._describe_day(day)}"
        if month != "*":
            if day == "*":
                return f"每年 {cls._join_values(month)} 月"
            return f"每年 {cls._join_values(month)} 月 {cls._describe_day(day)}"
        day_step = cls._field_step(day)
        if day_step is not None:
            return f"每 {day_step} 日"
        if day != "*":
            return f"每月 {cls._describe_day(day)}"
        if day_of_week != "*":
            labels = "、".join(cls._WEEKDAY_LABEL[name] for name in day_of_week.split(","))
            return f"每{labels}"
        return "每天"

    @classmethod
    def _describe_day(cls, day: str) -> str:
        """日字段的中文（`1` → `1 日`；`1-15` 原样保留区间）。"""
        return f"{cls._join_values(day)} 日"

    @staticmethod
    def _field_step(field: str) -> int | None:
        """字段为 `*/n` 时返回步长 `n`，否则返回 `None`。"""
        matched = re.fullmatch(r"\*/(\d+)", field)
        return int(matched.group(1)) if matched else None

    @staticmethod
    def _is_number_list(field: str) -> bool:
        """字段是否为纯数字列表（`9`、`1,15`），即能安全写成 `HH:MM`。"""
        return all(part.isdigit() for part in field.split(","))

    @staticmethod
    def _join_values(field: str) -> str:
        """规范化字段的逗号列表换成中文顿号（`1,15` → `1、15`）。"""
        return field.replace(",", "、")

    @staticmethod
    def _describe_time(minute: str, hour: str) -> str:
        """描述 `HH:MM` 时刻（时/分为列表时取叉积，如 `09:00、09:30、18:00、18:30`）。"""
        combos = [
            f"{int(hour_value):02d}:{int(minute_value):02d}"
            for hour_value in hour.split(",")
            for minute_value in minute.split(",")
        ]
        return "、".join(combos)

    # ------------------------------------------------------------------ 内部解析

    @classmethod
    def _parse_cron(cls, expr: str) -> tuple[bool, str, str]:
        """解析并校验 cron 表达式，返回 `(是否合法, 原因, 规范化结果)`。"""
        text = "" if expr is None else str(expr).strip()
        if not text:
            return False, "cron 表达式不能为空", ""

        fields = text.split()
        count = len(fields)
        if count == 7:
            return False, f"{cls._SEGMENT_REASON}；7 段（带年份）写法不受支持", ""
        if count == 6:
            # 秒位必须为 0（且整体仍不受支持，见下方「6 段一律拒绝」）
            if not cls._is_zero(fields[0]):
                return (
                    False,
                    "6 段表达式带秒位不受支持（秒位非 0）；秒级需求请改用 interval 间隔触发",
                    "",
                )
            core = fields[1:]
        elif count == 5:
            core = fields
        else:
            return False, cls._SEGMENT_REASON, ""

        normalized: list[str] = []
        for index, field in enumerate(core):
            if index == 4:
                ok, reason, value = cls._parse_weekday(field)
            else:
                low, high, label = cls._FIELD_RANGES[index]
                ok, reason, value = cls._parse_number_field(field, low, high, label)
            if not ok:
                # 6 段形式（如 Quartz 的 `0 0 9 L * *`）也先给出字段级专属原因
                return False, reason, ""
            normalized.append(value)

        if count == 6:
            # 秒位为 0 也不接受：唯一合法形式是 5 段，不做静默去秒改写
            return False, f"{cls._SEGMENT_REASON}；6 段写法请省略秒位", ""

        return True, "", " ".join(normalized)

    @classmethod
    def _is_zero(cls, token: str) -> bool:
        """判断是否为全 0 数字（`0` / `00`）。"""
        return bool(token) and token.strip("0") == ""

    @classmethod
    def _parse_number_field(
        cls, field: str, low: int, high: int, label: str
    ) -> tuple[bool, str, str]:
        """校验数值字段（分/时/日/月），支持 `*`、`a`、`a-b`、`a,b,c`、`*/n`、`a-b/n`。

        通配与列表混写（`*,5`、`1,*`）归一为 `*`。
        """
        if "?" in field:
            return False, f"{label}字段不支持 ?（Quartz 专有语法，请用 * 表示不限制）", ""
        if "#" in field:
            return False, f"{label}字段不支持 #（Quartz 专有语法，如 1#2）", ""
        if "L" in field.upper():
            return False, f"{label}字段不支持 L（Quartz 专有语法）", ""
        if "W" in field.upper():
            return False, f"{label}字段不支持 W（Quartz 专有语法，如 15W）", ""

        values: list[str] = []
        for item in field.split(","):
            ok, reason, value = cls._parse_number_item(item, low, high, label)
            if not ok:
                return False, reason, ""
            values.append(value)
        if "*" in values:
            # 通配与列表混写（`*,5`）归一为 `*`：`*` 已包含其余取值（规格 §4.1）
            return True, "", "*"
        return True, "", ",".join(values)

    @classmethod
    def _parse_number_item(
        cls, item: str, low: int, high: int, label: str
    ) -> tuple[bool, str, str]:
        """校验数值字段的单个片段（逗号分隔后的一项）。"""
        if item == "*":
            return True, "", "*"

        matched = re.fullmatch(r"(\*|\d+|\d+-\d+)/(\d+)", item)
        if matched:
            base, step = matched.group(1), int(matched.group(2))
            if base == "*":
                # APScheduler：*/n 的 n 不得超过该字段的极差（分 59 / 时 23 / 日 30 / 月 11）
                span = high - low
                if step < 1 or step > span:
                    return False, f"{label}字段步长非法（*/n 的 n 应在 1-{span} 之间）：{item}", ""
                return True, "", f"*/{step}"
            if "-" not in base:
                # 单值带步长（`1/2`）无标准 crontab 语义，不发明含义
                return False, f"{label}字段步长写法非法（仅支持 */n 与 a-b/n）：{item}", ""
            ok, reason, _ = cls._check_range(base, low, high, label)
            if not ok:
                return False, reason, ""
            start, end = (int(part) for part in base.split("-"))
            if start == end:
                return False, f"{label}字段等值区间无需步长（请直接写 {start}）：{item}", ""
            if step < 1 or step > end - start:
                return (
                    False,
                    f"{label}字段步长非法（a-b/n 的 n 不应超过区间跨度 {end - start}）：{item}",
                    "",
                )
            return True, "", f"{base}/{step}"

        if "/" in item:
            return False, f"{label}字段步长写法非法（仅支持 */n 与 a-b/n）：{item}", ""

        if "-" in item:
            ok, reason, canonical = cls._check_range(item, low, high, label)
            if not ok:
                return False, reason, ""
            return True, "", canonical

        if re.fullmatch(r"\d+", item):
            number = int(item)
            if low <= number <= high:
                return True, "", item
            return False, f"{label}字段取值超出范围（{low}-{high}）：{item}", ""

        return False, f"{label}字段格式非法：{item}", ""

    @classmethod
    def _check_range(cls, item: str, low: int, high: int, label: str) -> tuple[bool, str, str]:
        """校验 `a-b` 区间片段。

        返回 `(是否合法, 原因, 规范化片段)`：等值区间（`5-5`）等价单值，规范化为 `5`；
        `start > end`（跨周/倒序）判非法。
        """
        matched = re.fullmatch(r"(\d+)-(\d+)", item)
        if not matched:
            return False, f"{label}字段区间格式非法：{item}", ""
        start, end = int(matched.group(1)), int(matched.group(2))
        if not (low <= start <= high and low <= end <= high):
            return False, f"{label}字段取值超出范围（{low}-{high}）：{item}", ""
        if start > end:
            return False, f"{label}字段区间起点不能大于终点：{item}", ""
        return True, "", str(start) if start == end else item

    @classmethod
    def _parse_weekday(cls, field: str) -> tuple[bool, str, str]:
        """校验周字段并映射为星期名列表（不支持步长；区间展开为显式列表）。

        通配与列表混写（`*,mon`）归一为 `*`。
        """
        if "?" in field:
            return False, "周字段不支持 ?（Quartz 专有语法，请用 * 表示每天）", ""
        if "#" in field:
            return False, "周字段不支持 #（Quartz 专有语法，如 1#2）", ""
        if "L" in field.upper():
            return False, "周字段不支持 L（Quartz 专有语法）", ""
        if "/" in field:
            # 注意：`wed` 含 w，因此周字段不做 W 通配检查，只按取值白名单判定
            return False, "周字段不支持步长（*/2、mon/2 一律非法）", ""

        values: list[str] = []

        def _append(name: str) -> None:
            # 去重（`0` 与 `7` 都指周日；区间展开与列表项统一处理）
            if name not in values:
                values.append(name)

        for item in field.split(","):
            if item == "*":
                _append("*")
                continue
            if "-" in item:
                parts = item.split("-")
                if len(parts) != 2:
                    return False, f"周字段区间格式非法：{item}", ""
                start = cls._weekday_value(parts[0])
                end = cls._weekday_value(parts[1])
                start_number = cls._weekday_number(parts[0])
                end_number = cls._weekday_number(parts[1])
                if None in (start, end, start_number, end_number):
                    return False, f"周字段取值非法：{item}（支持 0-7 或 mon…sun）", ""
                # 跨周判断用**原始数字** 0..7 比较（`7` 不折成 `0`）：`5-7` 合法（fri,sat,sun）
                if start_number > end_number:
                    # 不发明"环绕"语义，只提示两个端点的列表写法
                    return (
                        False,
                        f"周字段跨周区间不受支持（起点必须在终点之前，按 0=周日…7=周日）：{item}；"
                        f"请改用列表写法（如 {start},{end}）",
                        "",
                    )
                for number in range(start_number, end_number + 1):
                    _append(cls._WEEKDAY_BY_NUMBER[number])
                continue
            value = cls._weekday_value(item)
            if value is None:
                return False, f"周字段取值非法：{item}（支持 0-7 或 mon…sun）", ""
            _append(value)
        if "*" in values:
            # 通配与列表混写（`*,mon`）归一为 `*`：`*` 已包含其余取值（规格 §4.1）
            return True, "", "*"
        return True, "", ",".join(values)

    @classmethod
    def _weekday_value(cls, token: str) -> str | None:
        """周字段取值 → 星期名；无法识别返回 `None`。"""
        return cls._WEEKDAY_MAP.get(token.strip().lower())

    @classmethod
    def _weekday_number(cls, token: str) -> int | None:
        """周字段取值 → 原始数字（`7` 保持为 `7`，不折成 `0`）；无法识别返回 `None`。"""
        text = token.strip().lower()
        if text.isdigit():
            number = int(text)
            return number if 0 <= number <= 7 else None
        return cls._WEEKDAY_NUMBER.get(text)
