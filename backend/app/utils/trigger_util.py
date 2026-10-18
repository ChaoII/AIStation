"""统一触发器工具（cron 口径）。

本模块是全平台唯一的 cron 口径：**标准 5 段 crontab** `分 时 日 月 周`。
- 周字段按标准 crontab 语义：`0`/`7` = 周日，也接受 `mon…sun`（大小写不敏感）；
- 规范化后周字段统一输出星期名（`sun`/`mon`/…），避免 APScheduler「0 = 周一」的错位；
- 不支持 Quartz 专有语法（`?`/`L`/`W`/`#`）与 6/7 段（秒、年份）写法，一律明确报错。

供 AI 工作台/工作流、训练调度、系统定时任务节点与中心调度器共用。
"""

from __future__ import annotations

import re


class TriggerUtil:
    """触发器工具类（当前只实现 cron 的规范化与校验）。"""

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

    # 数值字段取值范围：(最小, 最大, 字段名)
    _FIELD_RANGES = (
        (0, 59, "分"),
        (0, 23, "时"),
        (1, 31, "日"),
        (1, 12, "月"),
    )

    # 周字段区间排序用的周序（周一=0…周日=6，与 APScheduler 一致）。
    # 区间要求「起点周序 < 终点周序」：这是 APScheduler 与 croniter 都能构造的交集，
    # 跨周区间（如 `sun-sat`、`fri-mon`）两边都无法构造，直接报错并提示改用列表写法。
    _WEEKDAY_ORDER = {
        "mon": 0,
        "tue": 1,
        "wed": 2,
        "thu": 3,
        "fri": 4,
        "sat": 5,
        "sun": 6,
    }

    _SEGMENT_REASON = "只支持 5 段标准 crontab（分 时 日 月 周）"

    # ------------------------------------------------------------------ 对外 API

    @classmethod
    def validate_cron(cls, expr: str) -> tuple[bool, str]:
        """校验 cron 表达式。

        返回 `(是否合法, 可读原因)`；合法时原因为空字符串。原因文案为中文短句，
        可直接用于接口 400 响应与前端提示。
        """
        try:
            ok, reason, _ = cls._parse_cron(expr)
        except Exception:  # noqa: BLE001 —— 校验接口不应抛错，兜底给通用原因
            return False, "cron 表达式解析失败"
        return ok, reason

    @classmethod
    def normalize_cron(cls, expr: str) -> str:
        """规范化 cron 表达式（周字段映射为星期名，输出标准 5 段）。

        与 `validate_cron` 同源：校验通过 ⇒ 本方法一定不抛错。
        表达式非法时抛 `ValueError`，异常信息即 `validate_cron` 的原因文案。
        """
        ok, reason, normalized = cls._parse_cron(expr)
        if not ok:
            raise ValueError(reason)
        return normalized

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
        """校验数值字段（分/时/日/月），支持 `*`、`a`、`a-b`、`a,b,c`、`*/n`、`a-b/n`。"""
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
            ok, reason = cls._check_range(base, low, high, label)
            if not ok:
                return False, reason, ""
            start, end = (int(part) for part in base.split("-"))
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
            ok, reason = cls._check_range(item, low, high, label)
            if not ok:
                return False, reason, ""
            return True, "", item

        if re.fullmatch(r"\d+", item):
            number = int(item)
            if low <= number <= high:
                return True, "", item
            return False, f"{label}字段取值超出范围（{low}-{high}）：{item}", ""

        return False, f"{label}字段格式非法：{item}", ""

    @classmethod
    def _check_range(cls, item: str, low: int, high: int, label: str) -> tuple[bool, str]:
        """校验 `a-b` 区间片段。"""
        matched = re.fullmatch(r"(\d+)-(\d+)", item)
        if not matched:
            return False, f"{label}字段区间格式非法：{item}"
        start, end = int(matched.group(1)), int(matched.group(2))
        if not (low <= start <= high and low <= end <= high):
            return False, f"{label}字段取值超出范围（{low}-{high}）：{item}"
        if start >= end:
            return False, f"{label}字段区间起点必须小于终点：{item}"
        return True, ""

    @classmethod
    def _parse_weekday(cls, field: str) -> tuple[bool, str, str]:
        """校验周字段并映射为星期名（不支持步长）。"""
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
        for item in field.split(","):
            if item == "*":
                values.append("*")
                continue
            if "-" in item:
                parts = item.split("-")
                if len(parts) != 2:
                    return False, f"周字段区间格式非法：{item}", ""
                start = cls._weekday_value(parts[0])
                end = cls._weekday_value(parts[1])
                if start is None or end is None:
                    return False, f"周字段取值非法：{item}（支持 0-7 或 mon…sun）", ""
                if cls._WEEKDAY_ORDER[start] >= cls._WEEKDAY_ORDER[end]:
                    return (
                        False,
                        f"周字段区间起点必须小于终点（按 周一=0…周日=6）：{item}；"
                        "跨周请改用列表写法（如 5,6,0）",
                        "",
                    )
                values.append(f"{start}-{end}")
                continue
            value = cls._weekday_value(item)
            if value is None:
                return False, f"周字段取值非法：{item}（支持 0-7 或 mon…sun）", ""
            values.append(value)
        return True, "", ",".join(values)

    @classmethod
    def _weekday_value(cls, token: str) -> str | None:
        """周字段取值 → 星期名；无法识别返回 `None`。"""
        return cls._WEEKDAY_MAP.get(token.strip().lower())
