"""数据源表导入本体支持目标域与业务标记（Task 4）。

验证点：
1. ``import_ds_table_as_ontology(ds_id, "SYS_XYZ", domain_code="fuel_business")``
   会在 ``ai_ont_object`` 写入 ``domain_code == "fuel_business"``；
2. 系统表（SYS_ 前缀）导入后 ``ai_ont_object.is_business == false``；
3. 审计字段（created_time）导入后 ``ai_ont_property.is_business == false``；
4. 业务字段（coal_amount）导入后 ``ai_ont_property.is_business == true``。

说明：
- 本体表由应用启动时建（Postgres 走 service 的 ``_ONT_TABLES_SQL``），测试库为 SQLite，
  SQLite 不支持 BIGSERIAL / ``ADD COLUMN IF NOT EXISTS``，因此这里按项目既有做法
  （参照 ``test_ontology.py``）直接用 SQLite 兼容 DDL 建表，并补上 ``is_business`` 列。
"""
import asyncio
import json
import uuid

import _ont_ddl
import pytest
from sqlalchemy import text

from app.core.database import async_db_session


def _create_ds(test_client, auth_headers, code, **overrides):
    """新建数据源，返回其 id（未带 filter_rules 时走默认规则）。"""
    payload = {"name": f"资金数据源{code}", "code": code, "type": "postgres"}
    payload.update(overrides)
    r = test_client.post(
        "/api/v1/ai/query/datasources/save",
        json=payload,
        headers=auth_headers,
    )
    assert r.status_code == 200, r.text
    return r.json()["data"]["id"]


async def _seed_schema(ds_id):
    """向 ai_query_schema 写入一张系统表 SYS_XYZ（含审计字段 + 业务字段）。"""
    async with async_db_session.begin() as db:
        await db.execute(
            text(
                "INSERT INTO ai_query_schema(datasource,table_name,columns,table_comment,"
                "status,uuid,is_deleted,created_time,updated_time) "
                "VALUES(:d,:t,:cols,'c','0',:u,false,now(),now())"
            ),
            {
                "d": f"ds:{ds_id}",
                "t": "SYS_XYZ",
                "cols": json.dumps(
                    [
                        {"name": "id", "type": "int", "comment": ""},
                        {"name": "created_time", "type": "timestamp", "comment": ""},
                        {"name": "coal_amount", "type": "numeric", "comment": ""},
                    ]
                ),
                "u": "uSYS_XYZ",
            },
        )


async def _cleanup(ds_id, code):
    async with async_db_session.begin() as db:
        await db.execute(
            text("DELETE FROM ai_query_schema WHERE datasource=:d"), {"d": f"ds:{ds_id}"}
        )
        await db.execute(
            text("DELETE FROM ai_query_datasources WHERE code=:c"), {"c": code}
        )
        await db.execute(
            text("DELETE FROM ai_ont_property WHERE object_code=:c"), {"c": "SYS_XYZ"}
        )
        await db.execute(
            text("DELETE FROM ai_ont_object WHERE code=:c"), {"c": "SYS_XYZ"}
        )


@pytest.fixture(scope="module", autouse=True)
def _ont_tables(test_client):
    """在测试库建本体元数据表（SQLite），_ont_ddl 已含 is_business 列。"""

    async def _create():
        for t in ("ai_ont_object", "ai_ont_property"):
            await _run_ddl(_ont_ddl.ONT_DDL[t])

    asyncio.run(_create())


async def _run_ddl(sql: str) -> None:
    async with async_db_session.begin() as db:
        await db.execute(text(sql))


def test_import_ds_ontology_sets_domain_and_business(test_client, auth_headers):
    """导入带目标域的系统表数据源 → 对象/属性带 domain_code 与 is_business 标记。"""
    code = f"ds_ont_domain_{uuid.uuid4().hex[:8]}"
    ds_id = _create_ds(test_client, auth_headers, code)
    assert ds_id, "应得到新建数据源的 id"

    async def _import():
        from app.plugin.module_ai.query.service import AiQueryService

        return await AiQueryService.import_ds_table_as_ontology(
            ds_id, "SYS_XYZ", domain_code="fuel_business"
        )

    asyncio.run(_seed_schema(ds_id))
    try:
        result = asyncio.run(_import())
        assert result.get("ok") is True, f"导入应成功: {result}"

        async def _assert_rows():
            async with async_db_session() as db:
                obj = (
                    await db.execute(
                        text(
                            "SELECT domain_code, is_business FROM ai_ont_object "
                            "WHERE code=:c"
                        ),
                        {"c": "SYS_XYZ"},
                    )
                ).mappings().first()
                assert obj is not None, "ai_ont_object 应含有导入对象行"
                assert obj["domain_code"] == "fuel_business", (
                    f"对象 domain_code 应为 fuel_business，实际: {obj['domain_code']}"
                )
                assert obj["is_business"] in (False, 0), (
                    f"系统表对象 is_business 应为 false，实际: {obj['is_business']}"
                )

                props = (
                    await db.execute(
                        text(
                            "SELECT code, is_business FROM ai_ont_property "
                            "WHERE object_code=:c"
                        ),
                        {"c": "SYS_XYZ"},
                    )
                ).mappings().all()
                by_code = {p["code"]: p["is_business"] for p in props}
                assert "created_time" in by_code, "应导入 created_time 属性"
                assert by_code["created_time"] in (False, 0), (
                    f"审计字段 created_time is_business 应为 false，"
                    f"实际: {by_code['created_time']}"
                )
                assert "coal_amount" in by_code, "应导入 coal_amount 属性"
                assert by_code["coal_amount"] in (True, 1), (
                    f"业务字段 coal_amount is_business 应为 true，"
                    f"实际: {by_code['coal_amount']}"
                )

        asyncio.run(_assert_rows())
    finally:
        asyncio.run(_cleanup(ds_id, code))


def test_import_ds_ontology_endpoint_passes_domain_code(test_client, auth_headers):
    """走 POST /ontology/import-from-ds 接口：body 传 domain_code → 对象写入该域（Task 5）。"""
    code = f"ds_ont_ep_domain_{uuid.uuid4().hex[:8]}"
    ds_id = _create_ds(test_client, auth_headers, code)
    assert ds_id, "应得到新建数据源的 id"

    asyncio.run(_seed_schema(ds_id))
    try:
        # 通过控制器端点导入，body 携带 domain_code
        r = test_client.post(
            "/api/v1/ai/query/ontology/import-from-ds",
            json={"datasource_id": ds_id, "table": "SYS_XYZ", "domain_code": "fuel_business"},
            headers=auth_headers,
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body.get("data", {}).get("ok") is True, f"接口导入应成功: {body}"

        async def _assert_domain():
            async with async_db_session() as db:
                obj = (
                    await db.execute(
                        text(
                            "SELECT domain_code FROM ai_ont_object WHERE code=:c"
                        ),
                        {"c": "SYS_XYZ"},
                    )
                ).mappings().first()
                assert obj is not None, "ai_ont_object 应含有导入对象行"
                assert obj["domain_code"] == "fuel_business", (
                    f"通过接口导入的对象 domain_code 应为 fuel_business，"
                    f"实际: {obj['domain_code']}"
                )

        asyncio.run(_assert_domain())
    finally:
        asyncio.run(_cleanup(ds_id, code))


def test_import_uses_datasource_filter_rules_for_is_business(test_client, auth_headers):
    """导入 is_business 判定应沿用数据源自定义 filter_rules（与集成页打标口径一致，Task 8）。

    自定义规则：
    - ``system_table.prefixes=["TMP_"]``（不再把 ``SYS_`` 当系统表）；
    - ``audit_fields=["creationtime"]``（只把大写审计列 CREATIONTIME 标为审计）。

    因此导入后：对象 ``SYS_XYZ`` 视为业务（缺省规则下应为系统表）；属性
    ``created_time`` 视为业务（缺省规则下是审计字段）、``CREATIONTIME`` 视为审计、
    ``coal_amount`` 视为业务。差异足以证明规则被透传到导入路径。
    """
    code = f"ds_ont_rules_{uuid.uuid4().hex[:8]}"
    custom_rules = {
        "enabled": True,
        "system_table": {"prefixes": ["TMP_"], "keywords": [], "exact": [], "regex": ""},
        "audit_fields": ["creationtime"],
    }
    ds_id = _create_ds(test_client, auth_headers, code, filter_rules=custom_rules)
    assert ds_id, "应得到新建数据源的 id"

    async def _seed():
        # 写入含大写审计列 CREATIONTIME 的表结构
        async with async_db_session.begin() as db:
            await db.execute(
                text(
                    "INSERT INTO ai_query_schema(datasource,table_name,columns,table_comment,"
                    "status,uuid,is_deleted,created_time,updated_time) "
                    "VALUES(:d,:t,:cols,'c','0',:u,false,now(),now())"
                ),
                {
                    "d": f"ds:{ds_id}",
                    "t": "SYS_XYZ",
                    "cols": json.dumps(
                        [
                            {"name": "id", "type": "int", "comment": ""},
                            {"name": "created_time", "type": "timestamp", "comment": ""},
                            {"name": "coal_amount", "type": "numeric", "comment": ""},
                            {"name": "CREATIONTIME", "type": "timestamp", "comment": ""},
                        ]
                    ),
                    "u": "uSYS_XYZ_rules",
                },
            )

    asyncio.run(_seed())
    try:
        async def _import():
            from app.plugin.module_ai.query.service import AiQueryService

            return await AiQueryService.import_ds_table_as_ontology(ds_id, "SYS_XYZ")

        result = asyncio.run(_import())
        assert result.get("ok") is True, f"导入应成功: {result}"

        async def _assert_rows():
            async with async_db_session() as db:
                obj = (
                    await db.execute(
                        text("SELECT is_business FROM ai_ont_object WHERE code=:c"),
                        {"c": "SYS_XYZ"},
                    )
                ).mappings().first()
                assert obj is not None, "ai_ont_object 应含有导入对象行"
                # 自定义规则不再把 SYS_ 当系统表 → 对象应视为业务（与缺省规则相反）
                assert obj["is_business"] in (True, 1), (
                    f"自定义规则下对象 is_business 应为 true，实际: {obj['is_business']}"
                )

                props = (
                    await db.execute(
                        text(
                            "SELECT code, is_business FROM ai_ont_property "
                            "WHERE object_code=:c"
                        ),
                        {"c": "SYS_XYZ"},
                    )
                ).mappings().all()
                by_code = {p["code"]: p["is_business"] for p in props}
                # 缺省规则下 created_time 是审计字段；自定义规则不含它 → 业务
                assert by_code["created_time"] in (True, 1), (
                    f"自定义规则下 created_time 应为业务，实际: {by_code['created_time']}"
                )
                # 自定义规则把大写 CREATIONTIME 标为审计 → 非业务（大小写不敏感）
                assert by_code["CREATIONTIME"] in (False, 0), (
                    f"自定义规则下 CREATIONTIME 应为审计，"
                    f"实际: {by_code['CREATIONTIME']}"
                )
                assert by_code["coal_amount"] in (True, 1), (
                    f"业务字段 coal_amount is_business 应为 true，"
                    f"实际: {by_code['coal_amount']}"
                )

        asyncio.run(_assert_rows())
    finally:
        asyncio.run(_cleanup(ds_id, code))
