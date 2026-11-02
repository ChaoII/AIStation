"""**建表/手写 SQL 的运行时方言适配**（PG 写、SQLite 跑）。

与 ``dialect.py`` 的区别（别搞混）：

- ``dialect.py``：**被查询的目标数据源**是什么方言（MySQL/PG/SQLite），
  用来给模型写「语法提示」和拼 SQL。
- 本模块：**我们自己的库**（元数据/影子表/评测表）在跑谁，用来把
  照 PG 写的手写 DDL / UPDATE 翻译成能跑的写法。

为什么需要它
------------
本模块的手写 SQL 都是照 PostgreSQL 写的（``BIGSERIAL`` / ``JSONB`` /
``DEFAULT now()`` / ``::interval``），而单元测试跑在 SQLite 上。SQLite 对这些
写法不是"能跑但慢"，而是**直接语法错**；偏偏调用点又都是 best-effort
（``except: pass``）——于是表现为「表根本没建出来 / 兜底根本没生效，但没人知道」。

实测踩过两次（同一类坑）：

1. ``service._QUERY_TABLES_SQL``（问数影子表）→
   ``test_ai_eval.py::test_security_audit`` 单跑报 ``no such table: ai_access_rule``，
   只有同文件别的用例先建过表才能过（顺序依赖假绿）。
2. ``eval_runner.reconcile_stale_runs``（启动对账）→ 启动日志一行
   ``[ai-eval] 启动对账失败（忽略）: unrecognized token: ":"``，
   意味着「僵尸 running 自动清理」**从来没生效过**，界面上孤儿运行一直显示运行中。

约定
----
凡是**手写**的 DDL / 含方言语法的 SQL，一律过这里；ORM 模型的建表由 SQLAlchemy 处理。
"""
from __future__ import annotations

from app.config.setting import settings


def is_postgres() -> bool:
    """当前是否 PostgreSQL（生产主路径）。"""
    return settings.DATABASE_TYPE == "postgres"


def is_sqlite() -> bool:
    """当前是否 SQLite（单元测试库）。"""
    return settings.DATABASE_TYPE == "sqlite"


def ddl_for_dialect(sql: str) -> str:
    """把 PG 方言 DDL 翻译成当前数据库方言（**只有 SQLite 需要**）。

    - ``BIGSERIAL PRIMARY KEY`` → ``INTEGER PRIMARY KEY AUTOINCREMENT``：
      SQLite 里 ``BIGSERIAL`` 只是个普通类型名（不是 rowid 别名），不换的话
      id **不会自增、全是 NULL**（``ORDER BY id DESC`` 因此失去意义）。
    - ``DEFAULT now()`` → ``DEFAULT CURRENT_TIMESTAMP``：SQLite 的 DEFAULT
      只接受常量 / CURRENT_*，``now()`` 直接 ``near "(": syntax error``。
    - ``JSONB`` → ``JSON``：SQLite 会把未知类型名当 NUMERIC 亲和，落成 JSON 更贴近本意。

    非 SQLite 原样返回（PostgreSQL 行为**一字不变**）。
    """
    if not is_sqlite():
        return sql
    return (
        sql.replace("BIGSERIAL PRIMARY KEY", "INTEGER PRIMARY KEY AUTOINCREMENT")
        .replace("DEFAULT now()", "DEFAULT CURRENT_TIMESTAMP")
        .replace("JSONB", "JSON")
    )


def json_empty() -> str:
    """JSON 空对象的 SQL 字面量。

    PG 里 ``COALESCE(jsonb列, '{}'::jsonb)`` 是惯用写法（显式类型更稳）；
    其它方言不认 ``::``，用纯文本 ``'{}'``（SQLite 上就是字符串拼接）。
    """
    return "'{}'::jsonb" if is_postgres() else "'{}'"


def cast_text(expr: str) -> str:
    """把表达式转成文本（**方言无关**的 ``::text`` 替代）。

    - PG / SQLite：``CAST(expr AS TEXT)``
    - MySQL：``CAST(expr AS CHAR)``（MySQL 的 CAST 不接受 TEXT）

    用处：主键可能是 int/bigint，而写入侧拿到的是字符串 key，
    需要「两边都转文本」再比较；直接写 ``"id"::text`` 只有 PG 认，
    SQLite 会报 ``near "::": syntax error``，整个写回动作失败。
    """
    if settings.DATABASE_TYPE == "mysql":
        return f"CAST({expr} AS CHAR)"
    return f"CAST({expr} AS TEXT)"


def cast_int(expr: str) -> str:
    """把表达式转成整数（**方言无关**的 ``::int`` 替代）。

    - PG / SQLite：``CAST(expr AS INTEGER)``
    - MySQL：``CAST(expr AS SIGNED)``（MySQL 的 CAST 不接受 INTEGER）
    """
    if settings.DATABASE_TYPE == "mysql":
        return f"CAST({expr} AS SIGNED)"
    return f"CAST({expr} AS INTEGER)"


def stale_where(column: str, minutes_param: str = "m") -> tuple[str, str]:
    """构造「某时间列早于 N 分钟前」的比较表达式。

    返回 ``(sql 片段, 参数名)``：

    - PG：``<col> < now() - (:m || ' minutes')::interval`` → 参数名 ``m``，
      传分钟数字符串；
    - 其它（SQLite）：``<col> < :cutoff`` → 参数名 ``cutoff``，
      值用 :func:`cutoff_text` 算好。

    ``::interval`` 是 PG 专有语法，SQLite 会把 ``::`` 当参数前缀报
    ``unrecognized token: ":"`` —— 这正是启动对账静默失效的原因。
    """
    if is_postgres():
        return f"{column} < now() - (:{minutes_param} || ' minutes')::interval", minutes_param
    return f"{column} < :cutoff", "cutoff"


def cutoff_text(minutes: int) -> str:
    """N 分钟前的本地时间文本（``%Y-%m-%d %H:%M:%S``）。

    与 SQLite 侧 ``now()``（测试库注册的等价函数）格式一致，字典序比较即可。
    """
    from datetime import datetime, timedelta

    return (datetime.now() - timedelta(minutes=minutes)).strftime("%Y-%m-%d %H:%M:%S")
