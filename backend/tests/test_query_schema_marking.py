"""表/字段打标与枚举元数据（Task 3）。

覆盖点：
1. ``GET /datasources/{id}/schema``（即 ``list_ds_schema``）返回每表 ``is_system``、
   每列 ``is_audit``（按该数据源 filter_rules 现算）。
2. 系统表（SYS_*） ``is_system=true``，业务表（video_cameras） ``is_system=false``。
3. 审计字段（created_time） ``is_audit=true``，业务字段（coal_amount） ``is_audit=false``。
4. 字段资产保存 ``enum`` 后，``list_asset_columns`` 输出 ``is_audit`` 与 ``enum``。

实现说明：为免去连接真实数据库 introspect 的负担，采用 brief 允许的
「直接向 ai_query_schema 插一行（含 columns JSONB）」方式造数据，再真正走
``list_ds_schema`` / ``list_asset_columns`` 的返回逻辑。
"""
import asyncio
import json
import uuid

from sqlalchemy import text

from app.core.database import async_db_session


def _create_ds(test_client, auth_headers, code):
    """新建数据源，返回其 id（不传 filter_rules，落默认规则）。"""
    r = test_client.post(
        "/api/v1/ai/query/datasources/save",
        json={"name": f"打标测试{code}", "code": code, "type": "postgres"},
        headers=auth_headers,
    )
    assert r.status_code == 200, r.text
    return r.json()["data"]["id"]


async def _seed_schema(ds_id):
    """向 ai_query_schema 写入：一张系统表 + 一张业务表（含字段）。"""
    async with async_db_session.begin() as db:
        for t, cols in (
            (
                "SYS_XYZ",
                [
                    {"name": "id", "type": "int", "comment": ""},
                    {"name": "created_time", "type": "timestamp", "comment": ""},
                ],
            ),
            (
                "video_cameras",
                [
                    {"name": "id", "type": "int", "comment": ""},
                    {"name": "coal_amount", "type": "numeric", "comment": ""},
                ],
            ),
        ):
            await db.execute(
                text(
                    "INSERT INTO ai_query_schema(datasource,table_name,columns,table_comment,"
                    "status,uuid,is_deleted,created_time,updated_time) "
                    "VALUES(:d,:t,:cols,'c','0',:u,false,now(),now())"
                ),
                {"d": f"ds:{ds_id}", "t": t, "cols": json.dumps(cols), "u": f"u{t}"},
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
            text("DELETE FROM ai_query_asset_columns WHERE table_name=:t"),
            {"t": "video_cameras"},
        )


def test_ds_schema_marks_system_and_audit(test_client, auth_headers):
    """list_ds_schema 按 filter_rules 对表/字段打 is_system / is_audit。"""
    code = f"ds_mark_{uuid.uuid4().hex[:8]}"
    ds_id = _create_ds(test_client, auth_headers, code)
    assert ds_id, "应返回新建数据源 id"
    asyncio.run(_seed_schema(ds_id))
    try:
        r = test_client.get(
            f"/api/v1/ai/query/datasources/{ds_id}/schema", headers=auth_headers
        )
        assert r.status_code == 200, r.text
        rows = r.json()["data"]
        by_table = {x["table"]: x for x in rows}

        sys_tbl = by_table["SYS_XYZ"]
        assert sys_tbl["is_system"] is True, (
            f"SYS_ 前缀应判为系统表，实际: {sys_tbl.get('is_system')}"
        )
        audit_col = next(c for c in sys_tbl["columns"] if c["name"] == "created_time")
        assert audit_col["is_audit"] is True, (
            f"created_time 应判为审计字段，实际: {audit_col.get('is_audit')}"
        )

        biz_tbl = by_table["video_cameras"]
        assert biz_tbl["is_system"] is False, (
            f"业务表不应判为系统表，实际: {biz_tbl.get('is_system')}"
        )
        biz_col = next(c for c in biz_tbl["columns"] if c["name"] == "coal_amount")
        assert biz_col["is_audit"] is False, (
            f"业务字段不应判为审计字段，实际: {biz_col.get('is_audit')}"
        )
    finally:
        asyncio.run(_cleanup(ds_id, code))


def test_asset_column_outputs_audit_and_enum(test_client, auth_headers):
    """list_asset_columns 输出 is_audit（现算）与 enum（保存后可回读）。"""
    code = f"ds_mark_enum_{uuid.uuid4().hex[:8]}"
    ds_id = _create_ds(test_client, auth_headers, code)
    asyncio.run(_seed_schema(ds_id))
    try:
        # 保存一个带枚举的业务字段
        sr = test_client.post(
            "/api/v1/ai/query/assets/column/save",
            json={
                "table_name": "video_cameras",
                "column_name": "coal_amount",
                "description": "燃煤量",
                "included": True,
                "enum": ["低硫", "高硫"],
            },
            headers=auth_headers,
        )
        assert sr.status_code == 200, sr.text

        r = test_client.get(
            "/api/v1/ai/query/assets/video_cameras/columns", headers=auth_headers
        )
        assert r.status_code == 200, r.text
        cols = r.json()["data"]
        coal = next(c for c in cols if c["column_name"] == "coal_amount")
        assert coal["is_audit"] is False, (
            f"业务字段 is_audit 应为 false，实际: {coal.get('is_audit')}"
        )
        assert coal["enum"] == ["低硫", "高硫"], (
            f"保存的 enum 应回读，实际: {coal.get('enum')}"
        )

        # 未维护元数据的真实审计字段也应输出 is_audit=true
        colr = test_client.get(
            "/api/v1/ai/query/assets/SYS_XYZ/columns", headers=auth_headers
        )
        assert colr.status_code == 200, colr.text
        scols = colr.json()["data"]
        ct = next(c for c in scols if c["column_name"] == "created_time")
        assert ct["is_audit"] is True, (
            f"created_time 真实字段应 is_audit=true，实际: {ct.get('is_audit')}"
        )
    finally:
        asyncio.run(_cleanup(ds_id, code))
