"""Alembic 迁移的跨方言兼容层（PostgreSQL / SQLite / MySQL）。

背景：历史迁移脚本按 PostgreSQL 方言编写，使用了 ``postgresql.JSONB``、
``postgresql.ENUM``、``DO $$ ... $$``、``ALTER TYPE``、``ADD COLUMN IF NOT EXISTS``
等 PG 专属语法。项目在 ``setting.py`` 中声明支持 SQLite/MySQL，但迁移链并不能
在所有方言上原样重放（历史遗留，改动成本极高）。

本模块按「最小侵入、不改变 PG 语义」的原则，把**可安全降级**的类型渲染统一到
非 PG 方言：

- ``JSONB`` 在 SQLite/MySQL 上渲染为 ``JSON``（两种方言均有原生 JSON 类型）。

其余 PG 专属语句（``DO`` 块、``ALTER TYPE``、``IF NOT EXISTS`` 补列等）无法自动
降级，迁移脚本需通过 :func:`is_postgres` 等判断显式分支；具体支持矩阵见
``docs/superpowers/runbooks/alembic-migration.md``。
"""
from typing import Any

from alembic.ddl.base import ColumnComment
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles


def dialect_name(bind: Any) -> str:
    """返回连接的方言名（如 ``postgresql`` / ``sqlite`` / ``mysql``）。"""
    dialect = getattr(bind, "dialect", None)
    if dialect is None:
        raise ValueError("无法从 bind 获取方言，请传入 Connection/Bind")
    return dialect.name


def is_postgres(bind: Any) -> bool:
    """当前连接是否为 PostgreSQL。"""
    return dialect_name(bind) == "postgresql"


def is_sqlite(bind: Any) -> bool:
    """当前连接是否为 SQLite。"""
    return dialect_name(bind) == "sqlite"


@compiles(JSONB, "sqlite")
def _compile_jsonb_sqlite(element: JSONB, compiler: Any, **kw: Any) -> str:
    """SQLite 无 JSONB 类型，降级为 JSON。"""
    return "JSON"


@compiles(JSONB, "mysql")
def _compile_jsonb_mysql(element: JSONB, compiler: Any, **kw: Any) -> str:
    """MySQL 无 JSONB 类型，降级为 JSON。"""
    return "JSON"


@compiles(ColumnComment, "sqlite")
def _compile_column_comment_sqlite(element: Any, compiler: Any, **kw: Any) -> str:
    """SQLite 不支持列注释；渲染为无副作用的空操作语句。"""
    return "SELECT 1"


def portable_add_column(
    table: str,
    column_name: str,
    column_type: Any,
    *,
    schema: str | None = None,
) -> None:
    """跨方言「补列」：SQLite 先探测列是否存在再添加，其余方言用 ``IF NOT EXISTS``。

    参数:
    - table (str): 表名。
    - column_name (str): 列名。
    - column_type (Any): SQLAlchemy 类型或可渲染的类型字符串。
    - schema (str | None): 模式名，默认 None。
    """
    import sqlalchemy as sa
    from alembic import op

    bind = op.get_bind()
    if is_postgres(bind):
        # PostgreSQL 原生支持 ADD COLUMN IF NOT EXISTS（幂等）
        op.execute(f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {column_name} {column_type}")
        return

    # SQLite / MySQL 不支持 ADD COLUMN IF NOT EXISTS：先探测列是否存在
    insp = sa.inspect(bind)
    if not insp.has_table(table, schema=schema):
        return
    existing = {col["name"] for col in insp.get_columns(table, schema=schema)}
    if column_name in existing:
        return
    op.execute(f"ALTER TABLE {table} ADD COLUMN {column_name} {column_type}")


def portable_drop_column(
    table: str,
    column_name: str,
    *,
    schema: str | None = None,
) -> None:
    """跨方言「删列」：SQLite 先探测删除，PostgreSQL 用 ``IF EXISTS``。

    参数:
    - table (str): 表名。
    - column_name (str): 列名。
    - schema (str | None): 模式名，默认 None。
    """
    import sqlalchemy as sa
    from alembic import op

    bind = op.get_bind()
    insp = sa.inspect(bind)
    if not insp.has_table(table, schema=schema):
        return
    existing = {col["name"] for col in insp.get_columns(table, schema=schema)}
    if column_name not in existing:
        return
    if is_postgres(bind):
        op.execute(f"ALTER TABLE {table} DROP COLUMN IF EXISTS {column_name}")
        return
    # SQLite(≥3.35) / MySQL：不支持 DROP COLUMN IF EXISTS，已探测存在性
    op.execute(f"ALTER TABLE {table} DROP COLUMN {column_name}")
