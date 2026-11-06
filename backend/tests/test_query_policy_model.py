"""问数权限模型（Task 1）：策略/审计/shadow 三张表的 DDL 常量与幂等建表。

覆盖三件事：

1. ``POLICY_TABLES_SQL`` 真的包含三张表、每张都带 ``CREATE TABLE IF NOT EXISTS``（幂等）；
2. ``ensure_policy_tables()`` 能真的把表建出来，且连跑两次不报错；
3. ``sensitive_tables()`` 只取 ``sensitive=true`` 且未软删的表名，统一小写去重。

前两条的「建表」用例：常量与纯逻辑部分用 ``PYTEST_NO_APP=1`` 就能跑；
真正落库的用例走应用会话（需要应用，``PYTEST_NO_APP=1`` 时自动 skip）。
"""
from __future__ import annotations


def test_policy_tables_cover_three_tables():
    """三张表都在，且都是幂等建表语句（重复执行不能炸）。"""
    from app.plugin.module_ai.query.policy.model import POLICY_TABLES_SQL

    joined = "\n".join(POLICY_TABLES_SQL).lower()
    assert "ai_policy" in joined
    assert "ai_query_access_log" in joined
    assert "ai_policy_shadow_diff" in joined
    assert "create table if not exists" in joined
    # 一条 SQL 一张表：逐条执行时单条失败不牵连其它表
    assert len(POLICY_TABLES_SQL) == 3


def test_policy_tables_columns_match_design():
    """关键列必须齐（设计稿 §4），否则后续判定引擎/审计写入会缺字段。"""
    from app.plugin.module_ai.query.policy.model import POLICY_TABLES_SQL

    joined = "\n".join(POLICY_TABLES_SQL).lower()
    for col in (
        # ai_policy：表/列/行三级策略共用一张表
        "resource_kind",
        "resource_code",
        "effect",
        "subject_kind",
        "subject_value",
        "condition",
        "columns",
        "mask_expr",
        "marking",
        "priority",
        "enabled",
        "is_deleted",
        # 审计表
        "sql_hash",
        "sql_preview",
        "decision",
        "reason",
        "policy_ids",
        "rewrite",
        "elapsed_ms",
        # shadow 差异表
        "legacy_decision",
        "new_decision",
        "diff_kind",
    ):
        assert col in joined, f"缺少列：{col}"


def test_shadow_diff_ddl_has_rewrite_column():
    """shadow 差异表要带 ``rewrite`` 列（rewrite_only 差异的解释全靠它）。"""
    from app.plugin.module_ai.query.policy.model import POLICY_ALTER_COLS, POLICY_TABLES_SQL

    ddl = next(s for s in POLICY_TABLES_SQL if "ai_policy_shadow_diff" in s).lower()
    assert "rewrite" in ddl and "jsonb default '[]'" in ddl, ddl
    assert ("ai_policy_shadow_diff", "rewrite", "JSONB DEFAULT '[]'") in POLICY_ALTER_COLS


def test_ensure_policy_tables_creates_tables(test_client, db_run):
    """幂等建表：应用库上连跑两次都必须成功，且三张表真的存在。"""
    from sqlalchemy import inspect

    from app.core.database import async_db_session
    from app.plugin.module_ai.query import service as S
    from app.plugin.module_ai.query.policy.model import ensure_policy_tables

    async def _go():
        await ensure_policy_tables()
        await ensure_policy_tables()  # 幂等：第二次不能报错
        async with async_db_session() as db:
            conn = await db.connection()
            return await conn.run_sync(lambda c: set(inspect(c).get_table_names()))

    S.reset_degraded()
    names = db_run(_go())
    for t in ("ai_policy", "ai_query_access_log", "ai_policy_shadow_diff"):
        assert t in names, f"{t} 没建出来"
    st = S.degraded_status()
    assert not any(r["area"] == "policy_tables" for r in st["areas"]), st


def test_ensure_policy_tables_adds_missing_rewrite_column(test_client, db_run):
    """存量库补列：老表没有 ``rewrite`` 时必须幂等 ALTER 出来（连跑两次不报错）。"""
    from sqlalchemy import inspect, text

    from app.core.database import async_db_session
    from app.plugin.module_ai.query import service as S
    from app.plugin.module_ai.query.policy.model import ensure_policy_tables

    old_ddl = (
        "CREATE TABLE ai_policy_shadow_diff ("
        "id BIGSERIAL PRIMARY KEY, sql_hash CHAR(64), user_id INTEGER, entry VARCHAR(32), "
        "legacy_decision VARCHAR(8), new_decision VARCHAR(8), diff_kind VARCHAR(32), "
        "policy_ids JSONB DEFAULT '[]', sql_preview TEXT, "
        "created_time TIMESTAMP DEFAULT now())"
    )

    async def _go():
        async with async_db_session.begin() as db:
            await db.execute(text("DROP TABLE IF EXISTS ai_policy_shadow_diff"))
            await db.execute(text(S._ddl_for_dialect(old_ddl)))
        await ensure_policy_tables()
        await ensure_policy_tables()  # 幂等：第二次不能重复 ADD COLUMN 报错
        async with async_db_session() as db:
            conn = await db.connection()
            return await conn.run_sync(
                lambda c: [
                    col["name"]
                    for col in inspect(c).get_columns("ai_policy_shadow_diff")
                ]
            )

    S.reset_degraded()
    cols = db_run(_go())
    assert "rewrite" in cols, f"存量库没补上 rewrite 列：{cols}"
    st = S.degraded_status()
    assert not any(r["area"] == "policy_table_columns" for r in st["areas"]), st


def test_sensitive_tables_lowercased_and_deduped(test_client, db_run):
    """敏感表清单：只取 sensitive=true 且未软删，表名小写去重。"""
    from sqlalchemy import delete

    from app.core.database import async_db_session
    from app.plugin.module_ai.query.model import AiQueryAssetColumnModel
    from app.plugin.module_ai.query.policy.model import sensitive_tables

    like = "t_policy_sens_%"

    async def _go():
        try:
            async with async_db_session.begin() as db:
                await db.execute(delete(AiQueryAssetColumnModel).where(
                    AiQueryAssetColumnModel.table_name.like(like)))
                for table, sensitive, deleted in (
                    ("T_Policy_Sens_A", True, False),
                    ("t_policy_sens_a", True, False),   # 同表大小写重复 → 去重
                    ("t_policy_sens_b", False, False),  # 非敏感 → 不出现
                    ("t_policy_sens_c", True, True),    # 已软删 → 不出现
                ):
                    db.add(AiQueryAssetColumnModel(
                        table_name=table,
                        column_name="id",
                        sensitive=sensitive,
                        included=True,
                        is_deleted=deleted,
                    ))
                await db.flush()
            return await sensitive_tables()
        finally:
            async with async_db_session.begin() as db:
                await db.execute(delete(AiQueryAssetColumnModel).where(
                    AiQueryAssetColumnModel.table_name.like(like)))

    got = db_run(_go())
    mine = {t for t in got if t.startswith("t_policy_sens_")}
    # 大小写不同的同一张表只出现一次（小写），非敏感/已软删的都不出现
    assert mine == {"t_policy_sens_a"}, mine
    assert all(t == t.lower() for t in got), "表名必须统一小写"
