"""移除 trainframework 枚举里的 ULTRALYTICS / PADDLEX（及两个孤儿值）

Revision ID: c7d2e5f8a9b1
Revises: tk1m0d2l4r6
Create Date: 2026-10-01

背景
----
两个第三方框架都已彻底退场，枚举收敛到只剩自研的 TORKILN：

- ``ULTRALYTICS``（82 行历史数据）
- ``PADDLEX``（执行通路早已移除；残留 16 行评估全部是**悬空引用**——指向已删模型）

执行通路（训练、评估、预测、部署、格式转换导出）早已下线；本次把**数据侧也一并
清干净**——项目尚未发布、处于开发态，没有"历史可读"的需求。

处理顺序是有讲究的，且不可颠倒：

1. 先把历史数据删净（按**显式 id 白名单**，不是模式匹配——本项目曾因
   ``storage_path LIKE '%task_%'`` 误删 12 个真实用户模型）
2. 再 ``ALTER TYPE`` 移除枚举值
3. 最后删 Python 枚举成员

反过来做会撞上 ``SAEnum`` 按**成员名**反序列化的坑：类型里还有 ULTRALYTICS、
代码里成员已删时，读那一列直接报 ``invalid input value for enum``，
整个模型列表页打不开。

顺带清掉两个 PG 侧孤儿值 ``PYTORCH_OCR_DET`` / ``PYTORCH_OCR_REC``：没有任何行
使用、Python 侧也早已没有对应成员（本项目既有的踩坑记录——孤儿值会让日后重建
枚举时悄悄多出成员）。

为什么必须重建类型而不能用 ``ALTER TYPE ... DROP VALUE``
------------------------------------------------------
PG 12 才支持 ``DROP VALUE``，且不能在事务块内执行。而本项目是 async + 事务内执行，
所以走标准的"建新类型 → 改列类型 → 删旧类型 → **改回原名**"四步，对
PG / SQLite / MySQL 都成立。

⚠️ 最后那步改名是实跑迁移才发现的：``DROP TYPE ..._obsolete`` **不会**把新类型
改回原名，列上留下的是 ``trainframework_v2``，于是任何按名字查类型的逻辑
（包括本文件自己的校验、``init_app`` 的兜底补齐）全都查空。

回滚
----
``downgrade`` 会**报错拒绝**，而不是把数据变回来——数据已经物理删除，伪造不回来。
要回滚只能从备份恢复：

- ``C:\\Users\\aichao\\AppData\\Local\\Temp\\purge_backup.json``（ULTRALYTICS 82 行）
- ``C:\\Users\\aichao\\AppData\\Local\\Temp\\purge_paddlex_backup.json``（PADDLEX 16 行）
"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "c7d2e5f8a9b1"
down_revision = "tk1m0d2l4r6"
branch_labels = None
depends_on = None

#: 重建后的枚举成员。⚠️ **只剩 TORKILN**——ULTRALYTICS 与 PADDLEX 都已彻底移除。
NEW_VALUES = ("TORKILN",)
OLD_TYPE = "trainframework"
NEW_TYPE = "trainframework_v2"

#: 从枚举里移除的全部值（含两个 PG 侧孤儿值 PYTORCH_OCR_DET / PYTORCH_OCR_REC：
#: 没有任何行使用、Python 侧也早已没有对应成员——正是它们让枚举越攒越脏）。
REMOVED_VALUES = (
    "ULTRALYTICS", "PADDLEX", "PYTORCH_OCR_DET", "PYTORCH_OCR_REC",
)

#: 带 framework 列的表。顺序无关（PG 会自行加外键约束），但列出以便核对。
TABLES = (
    "train_models",
    "train_model_repos",
    "train_tasks",
    "train_evals",
    "train_predicts",
    "train_deploys",
    "train_schedules",
)


def _has_framework_column(conn, table: str) -> bool:
    """表不存在或没有 framework 列时返回 False（SQLite/MySQL 的 train_* 表可能缺列）。"""
    insp = sa.inspect(conn)
    if table not in insp.get_table_names():
        return False
    return any(c["name"] == "framework" for c in insp.get_columns(table))


def upgrade() -> None:
    bind = op.get_bind()
    # PG 的 ENUM 字面量用单引号。不能用 Python repr——那会生成 ['A', 'B']，
    # PG 直接报 ``syntax error at or near "["``（实测踩过）。
    quoted_values = ", ".join(f"'{v}'" for v in NEW_VALUES)
    quoted_removed = ", ".join(f"'{v}'" for v in REMOVED_VALUES)

    # ⚠️ 前置校验：**所有方言**都要查。有行还在用被移除的值就必须拒绝，否则 PG 上
    # 会失败在半途（事务回滚后类型已被改名，状态更糟）。数据清理必须先单独跑完。
    leftovers = []
    for table in TABLES:
        if not _has_framework_column(bind, table):
            continue
        n = bind.execute(
            sa.text(
                f"SELECT count(*) FROM {table} WHERE framework IN ({quoted_removed})"
            )
        ).scalar()
        if n:
            leftovers.append(f"{table}={n}")
    if leftovers:
        raise RuntimeError(
            "仍有行在被移除的枚举值上，必须先删数据再跑本迁移: " + ", ".join(leftovers)
        )

    if bind.dialect.name == "postgresql":
        # PG：建新类型 → 改列 → 删旧类型
        bind.execute(sa.text(f"ALTER TYPE {OLD_TYPE} RENAME TO {OLD_TYPE}_obsolete"))
        bind.execute(sa.text(
            f"CREATE TYPE {NEW_TYPE} AS ENUM ({quoted_values})"))
        for table in TABLES:
            if not _has_framework_column(bind, table):
                continue
            bind.execute(sa.text(
                f"ALTER TABLE {table} ALTER COLUMN framework TYPE {NEW_TYPE} "
                f"USING framework::text::{NEW_TYPE}"
            ))
        bind.execute(sa.text(f"DROP TYPE {OLD_TYPE}_obsolete"))
        # ⚠️ 必须把新类型**改回原名**：DROP 掉旧类型不会自动改名，列上留下的会是
        # ``trainframework_v2``，于是任何按名字查类型的逻辑（包括本文件自己的
        # 校验、init_app 的兜底补齐）全都对不上——实跑迁移时踩过：改完查
        # ``typname='trainframework'`` 返回空。
        bind.execute(sa.text(f"ALTER TYPE {NEW_TYPE} RENAME TO {OLD_TYPE}"))
    elif bind.dialect.name == "mysql":
        # MySQL：SAEnum 落成原生 ENUM 列，用 ``MODIFY COLUMN`` 改成 VARCHAR。
        # ⚠️ 不能写 ``ALTER COLUMN``——那是 PG / SQL Server 的语法，MySQL 会报语法错。
        for table in TABLES:
            if not _has_framework_column(bind, table):
                continue
            bind.execute(sa.text(
                f"ALTER TABLE {table} MODIFY COLUMN framework VARCHAR(32)"
            ))
    else:
        # SQLite：**什么都不用做**，这是对的选择而不是偷懒。
        #
        # SQLite 没有 enum 类型，SQLAlchemy 的 ``SAEnum`` 在它上退化成普通 VARCHAR
        # 且默认 ``create_constraint=False``（所以连 CHECK 约束都没有）。也就是说
        # 「枚举值集合」这件事在 SQLite 侧根本不存在物理载体，
        # 删几个名字不需要任何 DDL。
        #
        # ⚠️ 别在这里试 ``ALTER TABLE ... ALTER COLUMN``：SQLite 根底不支持改列类型，
        # 会直接报 ``near "ALTER": syntax error``（实测踩过——原本就是这么写的，
        # 一跑 SQLite 全库迁移就崩）。真要改列只能走「建新表 + 搬数据 +
        # 改名」，而对一个本来就无约束的 VARCHAR 列来说，那纯属白挣腾。
        pass


def downgrade() -> None:
    raise RuntimeError(
        "不可回滚：ULTRALYTICS 的 82 行历史数据已在删数据那一步**物理删除**，"
        "迁移无法凭空造回来。要恢复请从备份还原：\n"
        "  C:\\Users\\aichao\\AppData\\Local\\Temp\\purge_backup.json\n"
        "然后手工把 ULTRALYTICS 加回 NEW_VALUES 并重建类型。"
    )
