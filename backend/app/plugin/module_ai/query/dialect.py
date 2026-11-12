"""问数「多方言」提示词层（G6）。

设计依据：`docs/superpowers/specs/2026-10-14-semantic-query-layer-design.md` §3.9 G6。

为什么要它：慢路径 `_nl2sql` / `ask_stream` 的 system_prompt 里硬编码了
「你是 PostgreSQL 数据库查询助手…日期用 CURRENT_DATE / date_trunc」。当数据源是
自定义 MySQL / SQLite 时，这套 PostgreSQL 专用语法会诱导模型生成**不兼容**的 SQL
（如 MySQL 里用 `date_trunc` / `||`），导致执行直接报错。

本模块只做**提示词级方言适配**（给模型正确的语法约束），**不做** AST 级 transpile
（WrenAI 式 sqlglot 方言转换，明确在 P2 范围外）。纯逻辑、无 IO，可 `PYTEST_NO_APP=1`
快测。
"""
from __future__ import annotations

from typing import Any

#: 核心安全约束（**唯一真源**）：不可关闭、不可改文案，只读展示在「生成规则」面板里。
#: 放在本模块（纯逻辑、无 IO）而不是 ``prompt_rules``，是为了让 `PYTEST_NO_APP=1`
#: 的快测也能导入；拼接方式必须与历史实现逐字一致（``"".join``，无分隔符）。
CORE_RULES: tuple[str, ...] = (
    "必须写 FROM 子句并只使用给定的表/字段。",
    "只返回一条 SQL，不要多余解释，不要使用 DELETE/UPDATE/INSERT/DDL。",
)

#: 各方言的语法提示。`rules` 会在 prompt 里以「必须使用 X 语法（…）」出现，
#: 直接约束模型在该数据源下写出兼容 SQL。
DIALECTS: dict[str, dict[str, Any]] = {
    "postgres": {
        "name": "PostgreSQL",
        "rules": [
            "日期用 CURRENT_DATE / date_trunc / INTERVAL，别用 CURDATE / NOW(3)",
            "字符串拼接用 ||",
            "分页用 LIMIT n OFFSET m",
            "标识符大小写敏感时用双引号",
        ],
    },
    "mysql": {
        "name": "MySQL",
        "rules": [
            "日期用 CURDATE() / DATE_FORMAT / DATE_SUB，不要用 PostgreSQL 的日期函数",
            "字符串拼接用 CONCAT()",
            "分页用 LIMIT n OFFSET m",
            "标识符用反引号 ` 包裹",
        ],
    },
    "sqlite": {
        "name": "SQLite",
        "rules": [
            "日期用 date('now') / strftime",
            "字符串拼接用 ||",
            "分页用 LIMIT n OFFSET m",
            "按需用 strftime 或 substr 截断日期",
        ],
    },
}

#: 默认回退方言：未知类型 / 模板化数据源（file/api）都退回 PostgreSQL。
#: semantics：宁可给通用 PG 语法，也不要给错误方言。
_DEFAULT = "postgres"

#: 模板化数据源（不是关系型库，SQL 只是模板占位）——提示用标准 SQL。
_TEMPLATED_TYPES = {"file", "api"}


def resolve_dialect(datasource_type: str) -> dict:
    """按数据源类型返回方言配置；未知类型回退 PostgreSQL（不报错）。

    ``datasource_type`` 取值来自 ``AiQueryDatasourceModel.type``（postgres/mysql/
    sqlite/file/api）。file/api 是模板化数据源，无真实方言，回退 PG 并附提示。
    """
    t = (datasource_type or "").strip().lower()
    if t in _TEMPLATED_TYPES:
        return DIALECTS[_DEFAULT]
    return DIALECTS.get(t, DIALECTS[_DEFAULT])


def dialect_name(dialect: dict | None) -> str:
    """取方言显示名（供 prompt 与调试用）。"""
    return (dialect or DIALECTS[_DEFAULT]).get("name") or "PostgreSQL"


def dialect_syntax_sentence(dialect: dict | None) -> str:
    """拼出「必须使用 X 语法（规则1；规则2…）」句。"""
    d = dialect or DIALECTS[_DEFAULT]
    name = d.get("name") or "PostgreSQL"
    rules = "；".join(d.get("rules") or [])
    return f"必须使用 {name} 语法（{rules}）"


def is_templated_type(datasource_type: str) -> bool:
    """判断是否为模板化数据源（file/api），用于给「请用标准 SQL」提示。"""
    return (datasource_type or "").strip().lower() in _TEMPLATED_TYPES


def time_rules(dialect: dict | None, time_cfg: dict | None = None) -> str:
    """时间口径的**确定性**写法（随方言变化，口径可配）。

    为什么必须写进提示词：模型对「上个月」极易写成
    ``>= date_trunc('month', CURRENT_DATE)``（那是**本月**），
    数据一旦跨月就会答错且不报错（实测 2026-11 问「上个月」返回 0 行）。

    为什么可配（2026-11-12 原则「语义不写死」）：周从周几开始、月份按自然月还是
    滚动 30 天，是**业务口径**，各厂不同。默认 = 周一起 + 自然月，由数据源
    `filter_rules.time`（`week_start` / `month_mode`）覆盖。
    """
    name = ((dialect or DIALECTS[_DEFAULT]).get("name") or "PostgreSQL").strip()
    cfg = time_cfg or {}
    week_start = str(cfg.get("week_start") or "monday").strip().lower()
    month_mode = str(cfg.get("month_mode") or "natural").strip().lower()
    if week_start not in ("monday", "sunday"):
        week_start = "monday"
    if month_mode not in ("natural", "rolling30"):
        month_mode = "natural"
    if name == "MySQL":
        week = (
            ">= DATE_SUB(CURDATE(), INTERVAL WEEKDAY(CURDATE()) DAY)"
            if week_start == "monday"
            else ">= DATE_SUB(CURDATE(), INTERVAL DAYOFWEEK(CURDATE()) - 1 DAY)"
        )
        month = (
            ">= DATE_FORMAT(CURDATE(), '%Y-%m-01')" if month_mode == "natural"
            else ">= DATE_SUB(CURDATE(), INTERVAL 30 DAY)"
        )
        last_month = (
            ">= DATE_FORMAT(DATE_SUB(CURDATE(), INTERVAL 1 MONTH), '%Y-%m-01')"
            " AND < DATE_FORMAT(CURDATE(), '%Y-%m-01')"
            if month_mode == "natural"
            else "> DATE_SUB(CURDATE(), INTERVAL 60 DAY)"
            " AND <= DATE_SUB(CURDATE(), INTERVAL 30 DAY)"
        )
        body = (
            "- 今天：>= CURDATE()\n"
            f"- 本周：{week}\n"
            f"- 本月：{month}\n"
            f"- 上个月：{last_month}\n"
            "- 今年：>= DATE_FORMAT(CURDATE(), '%Y-01-01')\n"
            "- 去年：>= DATE_FORMAT(DATE_SUB(CURDATE(), INTERVAL 1 YEAR), '%Y-01-01')"
            " AND < DATE_FORMAT(CURDATE(), '%Y-01-01')\n"
            "- 最近N天：>= DATE_SUB(CURDATE(), INTERVAL N DAY)\n"
        )
    elif name == "SQLite":
        week = (
            ">= date('now','weekday 1','-7 days')"
            if week_start == "monday"
            else ">= date('now','weekday 0','-7 days')"
        )
        month = (
            ">= date('now','start of month')" if month_mode == "natural"
            else ">= date('now','-30 day')"
        )
        last_month = (
            ">= date('now','-1 month','start of month') AND < date('now','start of month')"
            if month_mode == "natural"
            else "> date('now','-60 day') AND <= date('now','-30 day')"
        )
        body = (
            "- 今天：>= date('now')\n"
            f"- 本周：{week}\n"
            f"- 本月：{month}\n"
            f"- 上个月：{last_month}\n"
            "- 今年：>= date('now','start of year')\n"
            "- 去年：>= date('now','-1 year','start of year')"
            " AND < date('now','start of year')\n"
            "- 最近N天：>= date('now','-N day')\n"
        )
    else:
        week = (
            ">= date_trunc('week', CURRENT_DATE)"
            if week_start == "monday"
            else ">= date_trunc('week', CURRENT_DATE + INTERVAL '1 day') - INTERVAL '1 day'"
        )
        month = (
            ">= date_trunc('month', CURRENT_DATE)" if month_mode == "natural"
            else ">= CURRENT_DATE - 30"
        )
        last_month = (
            ">= date_trunc('month', CURRENT_DATE - INTERVAL '1 month')"
            " AND < date_trunc('month', CURRENT_DATE)"
            if month_mode == "natural"
            else "> CURRENT_DATE - 60 AND <= CURRENT_DATE - 30"
        )
        body = (
            "- 今天：>= CURRENT_DATE\n"
            f"- 本周：{week}\n"
            f"- 本月：{month}\n"
            f"- 上个月：{last_month}\n"
            "- 今年：>= date_trunc('year', CURRENT_DATE)\n"
            "- 去年：>= date_trunc('year', CURRENT_DATE - INTERVAL '1 year')"
            " AND < date_trunc('year', CURRENT_DATE)\n"
            "- 最近N天：>= CURRENT_DATE - N\n"
        )
    return (
        "时间口径（按此逐字使用，不要自创；「上个月」**不是** >= 本月1日）：\n" + body
    )


def build_system_prompt(dialect: dict | None, rules: list[str], schema_ctx: str,
                        extra: str = "", time_cfg: dict | None = None) -> str:
    """组装慢路径的 system_prompt（按方言参数化）。

    参数与 `_nl2sql` / `ask_stream` 里原有的硬编码拼装**逐字兼容**，只是把
    「你是 PostgreSQL 数据库查询助手…」换成按方言生成。

    - ``dialect``：``resolve_dialect`` 的结果。
    - ``rules``：问数的通用规则列表（实体名 / 枚举 / 占比 / 别名等，现已存在）。
    - ``schema_ctx``：schema 上下文（已存在，原样拼接）。
    - ``extra``：追加约束（如「全量不截断」），原样拼接。
    """
    d = dialect or DIALECTS[_DEFAULT]
    header = (
        f"你是 {d.get('name') or 'PostgreSQL'} 数据库查询助手。根据用户问题生成只读 SELECT 查询。"
        f"{dialect_syntax_sentence(d)}。"
    )
    return (
        header
        + "".join(CORE_RULES) + "\n注意："
        + "".join(rules) + time_rules(d, time_cfg) + "\n" + (extra or "") + (schema_ctx or "")
    )


def templated_note(datasource_type: str) -> str:
    """模板化数据源（file/api）时追加的说明，否则返回空串。"""
    if not is_templated_type(datasource_type):
        return ""
    return "（该数据源为模板化/接口数据，请用标准 SQL：避免方言特性，用通用写法。）\n"


__all__ = [
    "DIALECTS", "resolve_dialect", "dialect_name", "dialect_syntax_sentence",
    "is_templated_type", "build_system_prompt", "templated_note", "time_rules",
]
