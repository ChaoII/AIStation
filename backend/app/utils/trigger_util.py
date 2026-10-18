"""统一触发器工具（cron 口径）。

本模块是全平台唯一的 cron 口径：**标准 5 段 crontab** `分 时 日 月 周`。
- 周字段按标准 crontab 语义：`0`/`7` = 周日，也接受 `mon…sun`（大小写不敏感）；
- 规范化后周字段统一输出**星期名列表**（区间展开为显式列表，如 `1-5` → `mon,tue,wed,thu,fri`）：
  两套下游库（APScheduler 的 `mon=0…sun=6` 与 croniter 的 `sun=0…sat=6`）对名称区间的解释相反，
  只有展开成显式列表才能消除这种口径不一致；
- 不支持 Quartz 专有语法（`?`/`L`/`W`/`#`）与 6/7 段（秒、年份）写法，一律明确报错；
- 通配与列表混写（`*,mon`、`1,*`）归一为 `*`；
- 触发器构造（`to_cron_trigger`）、中文描述（`describe_cron`）与「下次运行时间」（`next_run`）
  同源复用规范化结果，时区固定 `Asia/Shanghai`。

供 AI 工作台/工作流、训练调度、系统定时任务节点与中心调度器共用。
"""

from __future__ import annotations

import logging
import re
from datetime import datetime

from apscheduler.triggers.cron import CronTrigger

logger = logging.getLogger(__name__)


class TriggerUtil:
    """触发器工具类（cron 的规范化、校验、构造、描述与下次运行时间）。"""

    #: 统一时区：全平台一律 `Asia/Shanghai`，避免「同表达式不同机器不同触发时刻」
    TIMEZONE = "Asia/Shanghai"

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
    def next_run(cls, trigger: str, args, base: datetime | None = None) -> datetime | None:
        """统一的「下次运行时间」（列表与预览共用）。

        - `trigger="cron"`：`args` 为 5 段 cron 表达式，返回带 `Asia/Shanghai` 时区的时刻；
        - `base` 为参照时刻（缺省为当前时间）；**朴素时间按 `Asia/Shanghai` 解释**，
          保证同一输入在不同机器时区下结果一致；
        - **永不触发的日/月组合（如 `0 9 31 6 *`、`0 9 30 2 *`）返回 `None`**
          （APScheduler 内部构造非法日期会抛错；契约是「没有下次触发」，由调用方决定如何提示）；
        - 其它触发类型（interval / date / now）由后续任务扩展，此处显式抛 `NotImplementedError`
          （不静默返回 `None`，以免掩盖「类型未实现」）。
        """
        if trigger != "cron":
            raise NotImplementedError(f"next_run 暂不支持触发器类型：{trigger}")

        cron_trigger = cls.to_cron_trigger(args)
        if base is None:
            now = datetime.now(cron_trigger.timezone)
        elif base.tzinfo is None:
            now = base.replace(tzinfo=cron_trigger.timezone)
        else:
            now = base
        try:
            return cron_trigger.get_next_fire_time(None, now)
        except (ValueError, OSError):
            # 日/月组合永不发生（如 6 月 31 日）：APScheduler 内部会一路推进到 3001 年并抛错。
            # 按 `datetime | None` 契约返回 None，不把「表达式不触发」升级成 500。
            logger.debug("cron 表达式无有效下次触发时间：%r", args)
            return None

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

    # ------------------------------------------------------------------ 描述内部实现

    @classmethod
    def _describe_period(cls, day: str, month: str, day_of_week: str) -> str:
        """描述「周期」（每天 / 每周一、周三 / 每月 1 日 / 每年 3 月 15 日）。"""
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
