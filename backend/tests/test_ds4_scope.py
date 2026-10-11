"""ds:4 表范围：自定义数据源的检索/prompt 只应看到**已纳入资产目录的业务表**。

实测问题：`_ds_schema_map` 读全部同步表（311 张，含 92 张 SYS_*/_BAK 技术表），
系统表混进检索与 prompt —— 用户明确要求"选关键业务表、不要把系统表全加进去"。

测试用**独立假数据源 id**，不依赖真实 ds:4 数据。
"""
import asyncio

FAKE_DS = 987654


async def _seed():
    """造一个假数据源：3 张表同步过，其中 2 张已纳入资产目录。"""
    from sqlalchemy import text

    from app.core.database import async_db_session

    async with async_db_session.begin() as db:
        for t, inc in (("FUEL_BIZ_TABLE", True), ("SYS_TECH_TABLE", False),
                       ("FUEL_BAK_TABLE_BAK", True)):
            await db.execute(
                text(
                    "INSERT INTO ai_query_schema(datasource,table_name,columns,table_comment,"
                    "status,uuid,is_deleted,created_time,updated_time) "
                    "VALUES(:d,:t,'[]','c','0',:u,false,now(),now())"
                ),
                {"d": f"ds:{FAKE_DS}", "t": t, "u": f"u{t}"},
            )
        for t, inc in (("FUEL_BIZ_TABLE", True), ("SYS_TECH_TABLE", False),
                       ("FUEL_BAK_TABLE_BAK", True)):
            await db.execute(
                text(
                    "INSERT INTO ai_query_assets(table_name,included,description,status,uuid,"
                    "object_enabled,is_deleted,created_time,updated_time) "
                    "VALUES(:t,:i,'','0',:u,true,false,now(),now())"
                ),
                {"t": t, "i": inc, "u": f"a{t}"},
            )


async def _cleanup():
    from sqlalchemy import text

    from app.core.database import async_db_session

    async with async_db_session.begin() as db:
        await db.execute(
            text("DELETE FROM ai_query_schema WHERE datasource=:d"), {"d": f"ds:{FAKE_DS}"}
        )
        await db.execute(
            text("DELETE FROM ai_query_assets WHERE table_name LIKE 'FUEL_BIZ%' "
                 "OR table_name LIKE 'SYS_TECH%' OR table_name LIKE 'FUEL_BAK%'")
        )


def test_included_only_filters_out_non_business_tables():
    async def _run():
        from app.plugin.module_ai.query.service import list_ds_schema

        await _cleanup()
        await _seed()
        try:
            all_rows = await list_ds_schema(FAKE_DS)
            assert {r["table"] for r in all_rows} == {
                "FUEL_BIZ_TABLE", "SYS_TECH_TABLE", "FUEL_BAK_TABLE_BAK"
            }, "未过滤时应返回全部同步表"

            inc = await list_ds_schema(FAKE_DS, included_only=True)
            names = {r["table"] for r in inc}
            assert names == {"FUEL_BIZ_TABLE", "FUEL_BAK_TABLE_BAK"}, (
                f"只应返回已纳入的表（系统表必须被排除），实际: {names}"
            )
        finally:
            await _cleanup()

    asyncio.run(_run())


def test_ds_schema_map_respects_included_scope():
    async def _run():
        from app.plugin.module_ai.query.service import AiQueryService

        await _cleanup()
        await _seed()
        try:
            m = await AiQueryService._ds_schema_map(f"ds:{FAKE_DS}")
            assert "FUEL_BIZ_TABLE" in m, f"业务表应在检索范围内: {list(m)}"
            assert "SYS_TECH_TABLE" not in m, (
                f"系统表不应进检索范围: {list(m)}"
            )
        finally:
            await _cleanup()
            from app.plugin.module_ai.query import service as svc

            svc._DS_SCHEMA_CACHE.clear()

    asyncio.run(_run())
