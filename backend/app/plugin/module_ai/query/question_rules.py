"""问句启发式：时间区间 + 列举/全量判定（2026-11-08 从 service.py 拆出）。

三件事，都是**确定性**规则（不调模型）：
1. ``parse_time_range``：从「最近 7 天 / 本月 / 今天」解析出可注入 SQL 的天数；
2. ``is_listing_question``：列举类问题（哪些/列出/清单…）不要走单值指标模板；
3. ``wants_full_list``：要的是「每个/所有」全量时，``validate_sql`` 补的 ``LIMIT``
   要放宽到系统上限；但「前 N / 排名」出现时恰恰不能放宽（实测踩过：含"各"的
   取前 5 名被当成全量，结果 5 行被放到 1000 行）。

``service.py`` 保留原名（带下划线）的再导出，测试对
``service.is_listing_question`` / ``_wants_grouping`` 之类打桩仍生效。
"""
from __future__ import annotations

import re
from typing import Any

DAYS_RE = re.compile(r"(?:最近|近|过去)\s*(\d+)\s*(?:天|日)", re.IGNORECASE)


def parse_time_range(question: str) -> dict[str, Any]:
    """从问句中解析时间区间，返回可注入 SQL 的参数。"""
    m = DAYS_RE.search(question)
    if m:
        return {"days": int(m.group(1))}
    if re.search(r"今天|今日", question):
        return {"days": 1}
    if re.search(r"本月|这个月", question):
        return {"days": 30}
    if re.search(r"本周|这周", question):
        return {"days": 7}
    return {}


def detect_time_frame(question: str) -> str:
    """识别问句的时间语境，用于指标维度对齐。"""
    q = question.lower()
    if re.search(r"本月|这个月|当月", q):
        return "month"
    if re.search(r"今天|今日", q):
        return "today"
    if re.search(r"近7|最近7|近七|最近七|过去7", q):
        return "days"
    return ""


def metric_time_hint(m: dict) -> str:
    """从指标 key/name/描述推断其时间维度，用于对齐问句时间语境。"""
    s = f"{m.get('key', '')} {m.get('name', '')} {m.get('description', '')}".lower()
    if "month" in s or "本月" in s or "当月" in s:
        return "month"
    if "7d" in s or "最近" in s or "近7" in s or "近七" in s:
        return "days"
    if "today" in s or "今日" in s or "今天" in s:
        return "today"
    return ""


LISTING_RE = re.compile(
    r"(哪些|列出|列表|清单|明细|罗列|有哪些|分别是什么|各叫什么|的名称|的名字|叫啥|叫什么名字)"
)


def is_listing_question(question: str) -> bool:
    """列举类问题（哪些/列出/名称等）不走指标模板，强制慢路径 NL2SQL。"""
    return bool(LISTING_RE.search(question or ""))


ALL_LIST_HINTS = ("每个", "各", "所有", "全部", "分别", "每类", "每种", "列出",
                   "逐个", "清单", "都有哪些", "有哪些")


TOP_N_RE = re.compile(r"前\s*\d+|排名|排前|top\s*\d+|前几|最多前", re.IGNORECASE)


def wants_full_list(question: str) -> bool:
    q = question or ""
    if TOP_N_RE.search(q):
        return False
    return any(h in q for h in ALL_LIST_HINTS)
