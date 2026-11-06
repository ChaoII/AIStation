"""权限策略三张表：``ai_policy`` / ``ai_query_access_log`` / ``ai_policy_shadow_diff``。

设计稿：``docs/superpowers/specs/2026-11-06-query-permission-model-design.md`` §4。

三条约定（与 ``service._ensure_query_tables`` 保持一致，别各写一套）：

1. DDL 照 **PostgreSQL** 写，执行前一律过 ``_ddl_for_dialect``（SQLite 测试库要翻译
   ``BIGSERIAL`` / ``JSONB`` / ``DEFAULT now()``，否则建表静默失败、表现为「表不存在」）；
2. 逐条执行 + ``CREATE TABLE IF NOT EXISTS``，**幂等**，可在每次启动时重复调用；
3. 单条失败只记降级（``_degrade``）不抛异常 —— 建表是附加能力，不能拖垮启动。

⚠️ 与 ``service`` 的循环引用：本模块的函数在**调用时**才导入 ``service``
（``service._ensure_query_tables`` 末尾会反过来调本模块的 ``ensure_policy_tables``）。
"""
from __future__ import annotations

from sqlalchemy import select, text

from app.core.database import async_db_session

#: 策略表 DDL（PG 方言，执行前按当前库方言翻译）。
#:
#: 一条 SQL 一张表：逐条独立执行，某张表失败不会连带后面全部失败。
POLICY_TABLES_SQL: list[str] = [
    # 统一策略表：表级 allow/deny、列级 allow/deny/mask、行级 allow 共用。
    # 语义（设计稿 §3.2）：deny > mask > allow；表级默认拒绝；列的限制只来自显式
    # deny/mask（`columns` 为空的 allow 表示整表可读，不是"列级默认拒绝"）。
    (
        "CREATE TABLE IF NOT EXISTS ai_policy ("
        "id BIGSERIAL PRIMARY KEY, "
        "name VARCHAR(120) NOT NULL, "
        "description VARCHAR(255) DEFAULT '', "
        "enabled BOOLEAN NOT NULL DEFAULT true, "
        "priority INTEGER NOT NULL DEFAULT 100, "
        # table | view | object | datasource
        "resource_kind VARCHAR(16) NOT NULL, "
        # 表名 / 视图名 / 对象码
        "resource_code VARCHAR(160) NOT NULL, "
        # allow | deny | mask
        "effect VARCHAR(8) NOT NULL, "
        # everyone | role | user | attr | domain
        "subject_kind VARCHAR(16) NOT NULL, "
        # 角色码 / 用户 id / 属性表达式 / 数据域 code
        "subject_value VARCHAR(160) DEFAULT '', "
        # 行级表达式（仅 allow 使用）
        "condition TEXT DEFAULT '', "
        # 列清单；空 = 整表
        "columns JSONB DEFAULT '[]', "
        # 掩码表达式（仅 mask 使用）
        "mask_expr TEXT DEFAULT '', "
        # 标记名（用于下游传播，如 sensitive / PHI）
        "marking VARCHAR(60) DEFAULT '', "
        "created_time TIMESTAMP DEFAULT now(), "
        "updated_time TIMESTAMP DEFAULT now(), "
        "is_deleted BOOLEAN DEFAULT false)"
    ),
    # 审计表：每次判定（放行也写）落一条，供 explain 与治理看板回溯。
    # 只存 sql_hash + 截断的 sql_preview（2KB、敏感字面量打码），不存全量 SQL。
    (
        "CREATE TABLE IF NOT EXISTS ai_query_access_log ("
        "id BIGSERIAL PRIMARY KEY, "
        "user_id INTEGER, "
        # ask|agent|app|workflow|cron|report|metric|object|export|eval
        "entry VARCHAR(32), "
        "datasource VARCHAR(120), "
        "sql_hash CHAR(64), "
        "sql_preview TEXT, "
        # permit | deny
        "decision VARCHAR(8), "
        "reason VARCHAR(255), "
        "policy_ids JSONB DEFAULT '[]', "
        # 实际施加的改写（行/列/掩码）
        "rewrite JSONB DEFAULT '[]', "
        "elapsed_ms INTEGER, "
        "created_time TIMESTAMP DEFAULT now())"
    ),
    # shadow 差异表：灰度期「旧逻辑决策 vs 新引擎决策」的逐条差异。
    (
        "CREATE TABLE IF NOT EXISTS ai_policy_shadow_diff ("
        "id BIGSERIAL PRIMARY KEY, "
        "sql_hash CHAR(64), "
        "user_id INTEGER, "
        "entry VARCHAR(32), "
        # permit | deny
        "legacy_decision VARCHAR(8), "
        "new_decision VARCHAR(8), "
        # legacy_permit_new_deny | legacy_deny_new_permit | rewrite_only
        "diff_kind VARCHAR(32), "
        "policy_ids JSONB DEFAULT '[]', "
        "sql_preview TEXT, "
        # 新引擎要新增的改写（行过滤 / 掩码）：rewrite_only 差异靠它解释"藏了哪些行"
        "rewrite JSONB DEFAULT '[]', "
        "created_time TIMESTAMP DEFAULT now())"
    ),
]

#: 存量库补列（``CREATE TABLE IF NOT EXISTS`` 不会给已存在的表加新列）。
#:
#: 照 ``service._QUERY_ALTER_COLS`` 的做法：运行时先 ``inspect`` 有没有该列，
#: 没有才 ``ALTER TABLE ... ADD COLUMN``，**幂等**，每次启动跑一遍。
#: 只用于新增的**可空/带默认值**列（老行不需要回填）。
POLICY_ALTER_COLS: tuple[tuple[str, str, str], ...] = (
    ("ai_policy_shadow_diff", "rewrite", "JSONB DEFAULT '[]'"),
)


async def ensure_policy_tables() -> None:
    """确保三张策略表存在（幂等、best-effort），并给存量库补新增列。

    复刻 ``service._ensure_query_tables`` 的做法：逐条方言翻译 + 独立事务提交；
    单条失败记一次降级（``policy_tables``），不向上抛 —— 应用启动不能被建表拖垮。

    第二步是**存量库补列**（``POLICY_ALTER_COLS``）：``CREATE TABLE IF NOT EXISTS``
    对已存在的表是空操作，新加的 ``ai_policy_shadow_diff.rewrite`` 必须靠
    ``inspect`` + ``ALTER TABLE ADD COLUMN`` 补上，否则 shadow 写差异会因"列不存在"
    整条失败（而且它是 fail-open 的，表现为**差异表悄悄没数据**）。
    """
    from .. import service

    for sql in POLICY_TABLES_SQL:
        try:
            async with async_db_session.begin() as db:
                await db.execute(text(service._ddl_for_dialect(sql)))
        except Exception as e:  # noqa: BLE001
            service._degrade("policy_tables", e)

    for table, col, ddl in POLICY_ALTER_COLS:
        try:
            async with async_db_session.begin() as db:
                from sqlalchemy import inspect as sa_inspect

                cols = await db.run_sync(
                    lambda s, _t=table: {
                        c["name"] for c in sa_inspect(s.connection()).get_columns(_t)
                    }
                )
                if col not in cols:
                    await db.execute(
                        text(
                            service._ddl_for_dialect(
                                f"ALTER TABLE {table} ADD COLUMN {col} {ddl}"
                            )
                        )
                    )
        except Exception as e:  # noqa: BLE001 - 补列失败只降级，不拖垮启动
            service._degrade("policy_table_columns", e)


async def sensitive_tables() -> set[str]:
    """``ai_query_asset_columns`` 里 ``sensitive=true`` 的表名集合（小写去重）。

    用途：``SELECT *`` / ``t.*`` 的止血判定（敏感表上的星号一律拒绝，P0），
    以及迁移时把 ``sensitive`` 列标记转成 ``deny`` 列策略 + ``marking=sensitive``。
    已软删的字段行不计入；表名统一小写（SQL 里的表名大小写不敏感）。
    """
    from ..model import AiQueryAssetColumnModel

    async with async_db_session() as db:
        rows = (
            await db.execute(
                select(AiQueryAssetColumnModel.table_name)
                .where(
                    AiQueryAssetColumnModel.sensitive.is_(True),
                    AiQueryAssetColumnModel.is_deleted.is_(False),
                )
                .distinct()
            )
        ).all()
    return {str(r[0]).strip().lower() for r in rows if r[0]}
