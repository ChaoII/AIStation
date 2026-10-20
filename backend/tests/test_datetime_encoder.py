"""响应层时间格式化回归：isoformat 快路径必须与 strftime 输出**逐字一致**。

背景：本机 `strftime` 单次 31.5µs（WSL 上 1.3µs），而 `isoformat` 0.54µs；
一个 user/list 请求格式化约 495 个时间字段，白烧约 24ms。
"""

from datetime import date, datetime, time

from app.common.constant import DATE_DISPLAY_FMT, DATETIME_DISPLAY_FMT, TIME_DISPLAY_FMT
from app.common.response import _JSON_DATETIME_CUSTOM_ENCODER as ENC


def test_datetime_format_matches_strftime() -> None:
    cases = [
        datetime(2026, 10, 20, 12, 5, 27),
        datetime(2026, 1, 1, 0, 0, 0),
        datetime(1999, 12, 31, 23, 59, 59, 999999),
        datetime.now(),
    ]
    for d in cases:
        assert ENC[datetime](d) == d.strftime(DATETIME_DISPLAY_FMT), d


def test_date_and_time_format_match() -> None:
    for d in [date(2026, 10, 20), date(2000, 2, 29), date.today()]:
        assert ENC[date](d) == d.strftime(DATE_DISPLAY_FMT), d
    for t in [time(0, 0, 0), time(23, 59, 59), time(12, 5, 27, 123456)]:
        assert ENC[time](t) == t.strftime(TIME_DISPLAY_FMT), t


def test_extreme_year_falls_back_to_strftime() -> None:
    """年份 <1000 时 strftime 不补零，必须走兜底分支才与旧输出一致。"""
    d = datetime(999, 1, 2, 3, 4, 5)
    assert ENC[datetime](d) == d.strftime(DATETIME_DISPLAY_FMT)
