"""启动期 Alembic 版本戳检测与补写（审计 I1）。

背景：``create_all`` 建出来的库没有 ``alembic_version`` 记录。部署时直接
``alembic upgrade head`` 会从 base 迁移重放 ``create_table``，对已存在的表抛
``DuplicateTable`` 而中断。

本模块提供**保守**的自动处理：

- 空库（无业务表）→ 交由 ``create_all``/迁移创建，不写戳；
- 已有 ``alembic_version`` 记录 → 不干预；
- 表存在但无记录，且库结构**与当前模型完全一致**（即由当前版本 ``create_all``
  建出）→ 补写 ``head``，使后续 ``upgrade head`` 成为安全空操作；
- 表存在但无记录，且缺表/缺列（旧版 ``create_all`` 或半迁移库）→ **拒绝**写戳，
  打印明确操作指引，避免把落后 schema 误标为 head 而跳过后续迁移。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from sqlalchemy import Engine, inspect, text
from sqlalchemy.engine import Connection

from app.config.path_conf import ALEMBIC_VERSION_DIR

ALEMBIC_VERSION_TABLE = "alembic_version"

LEGACY_HINT = (
    "检测到既有无戳库的 schema 落后于当前模型，已拒绝自动写入 alembic_version。"
    "请先备份数据库，再用 `alembic revision --autogenerate` 生成补齐脚本或手工补列后重试；"
    "切勿直接 `alembic stamp head`，否则会跳过缺失的迁移。"
)


class StampState(str, Enum):
    """版本戳检测结果。"""

    NO_TABLES = "no_tables"  # 空库：由 create_all/迁移创建
    ALREADY_STAMPED = "stamped"  # 已有 alembic_version 记录
    SCHEMA_MATCHES_HEAD = "schema_matches_head"  # create_all 建的当前 schema
    LEGACY_MISMATCH = "legacy_mismatch"  # 表在但 schema 落后：拒绝打戳


@dataclass
class StampDecision:
    """检测/补写结论。

    属性:
    - state (StampState): 状态。
    - revision (str | None): 已存在或新写入的版本号。
    - missing (list[str]): 缺失的表/列描述（仅 LEGACY_MISMATCH 有意义）。
    - message (str): 可读说明/操作指引。
    """

    state: StampState
    revision: str | None = None
    missing: list[str] = field(default_factory=list)
    message: str = ""


def get_head_revision() -> str:
    """返回 Alembic 迁移链当前 head 版本号。

    返回:
    - str: head revision id。

    异常:
    - RuntimeError: 迁移目录中不存在 head 时抛出。
    """
    from alembic.config import Config
    from alembic.script import ScriptDirectory

    cfg = Config()
    cfg.set_main_option("script_location", str(ALEMBIC_VERSION_DIR.parent))
    head = ScriptDirectory.from_config(cfg).get_current_head()
    if not head:
        raise RuntimeError("Alembic 未找到 head 版本，请检查迁移目录")
    return head


def get_model_schema() -> dict[str, set[str]]:
    """返回当前 ORM 模型的全量表/列集合（确保所有模型已导入）。

    返回:
    - dict[str, set[str]]: ``{表名: {列名, ...}}``。
    """
    from app.core.base_model import MappedBase
    from app.utils.import_util import ImportUtil

    ImportUtil.find_models(MappedBase)
    return {
        table.name: {col.name for col in table.columns}
        for table in MappedBase.metadata.sorted_tables
    }


def _missing_schema(
    insp: Any, table_names: set[str], expected: dict[str, set[str]]
) -> list[str]:
    """逐表比对期望列集合，返回缺失描述（表缺失/列缺失）。"""
    missing: list[str] = []
    for table, columns in expected.items():
        if table not in table_names:
            missing.append(f"{table} (整表缺失)")
            continue
        existing = {col["name"] for col in insp.get_columns(table)}
        gap = sorted(set(columns) - existing)
        if gap:
            missing.append(f"{table}: {gap}")
    return missing


def evaluate(
    connection: Connection, expected: dict[str, set[str]] | None = None
) -> StampDecision:
    """在给定连接上判定是否需要补写 ``alembic_version``（不产生任何写入）。

    参数:
    - connection (Connection): 同步数据库连接。
    - expected (dict[str, set[str]] | None): 期望的表/列集合，默认取当前模型。

    返回:
    - StampDecision: 判定结果。
    """
    insp = inspect(connection)
    table_names = set(insp.get_table_names())

    # 已有版本记录则一律不干预（即使业务表为空）
    if ALEMBIC_VERSION_TABLE in table_names:
        row = connection.execute(
            text(f"SELECT version_num FROM {ALEMBIC_VERSION_TABLE} LIMIT 1")
        ).fetchone()
        if row and row[0]:
            return StampDecision(
                StampState.ALREADY_STAMPED,
                revision=str(row[0]),
                message="alembic_version 已存在，跳过",
            )

    app_tables = table_names - {ALEMBIC_VERSION_TABLE}
    if not app_tables:
        return StampDecision(StampState.NO_TABLES, message="空库：交由 create_all/迁移创建")

    expected = expected if expected is not None else get_model_schema()
    missing = _missing_schema(insp, table_names, expected)
    if missing:
        return StampDecision(
            StampState.LEGACY_MISMATCH,
            missing=missing,
            message=LEGACY_HINT,
        )
    return StampDecision(
        StampState.SCHEMA_MATCHES_HEAD,
        message="库结构与当前模型一致，可安全补写 head",
    )


def _write_alembic_version(connection: Connection, revision: str) -> None:
    """写入（或覆盖）``alembic_version`` 记录。"""
    connection.execute(
        text(
            f"CREATE TABLE IF NOT EXISTS {ALEMBIC_VERSION_TABLE} ("
            "version_num VARCHAR(32) NOT NULL, "
            "CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num))"
        )
    )
    connection.execute(text(f"DELETE FROM {ALEMBIC_VERSION_TABLE}"))
    connection.execute(
        text(f"INSERT INTO {ALEMBIC_VERSION_TABLE} (version_num) VALUES (:v)"),
        {"v": revision},
    )


def _stamp_in_connection(
    connection: Connection, head: str, expected: dict[str, set[str]] | None
) -> StampDecision:
    """在事务内判定并在 schema 一致时补写 head。"""
    decision = evaluate(connection, expected=expected)
    if decision.state is StampState.SCHEMA_MATCHES_HEAD:
        _write_alembic_version(connection, head)
        decision.revision = head
    return decision


def apply_stamp(
    engine: Engine,
    expected: dict[str, set[str]] | None = None,
    head: str | None = None,
) -> StampDecision:
    """同步入口：检测并（必要时）补写版本戳。

    参数:
    - engine (Engine): 同步引擎。
    - expected (dict[str, set[str]] | None): 期望表/列集合，默认取当前模型。
    - head (str | None): 目标版本号，默认取迁移链 head。

    返回:
    - StampDecision: 判定结果（SCHEMA_MATCHES_HEAD 时会写入）。
    """
    head = head or get_head_revision()
    with engine.begin() as conn:
        return _stamp_in_connection(conn, head, expected)


async def ensure_schema_stamp(async_engine: Any) -> StampDecision:
    """异步入口：供应用启动期调用（内部 ``run_sync`` 复用同步逻辑）。

    参数:
    - async_engine (Any): SQLAlchemy AsyncEngine。

    返回:
    - StampDecision: 判定结果。
    """
    head = get_head_revision()
    async with async_engine.begin() as conn:
        return await conn.run_sync(_stamp_in_connection, head, None)
