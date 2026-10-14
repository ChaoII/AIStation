"""S1-T3：实例层按 datasource_id 跨库查询。"""
import asyncio


def test_instance_meta_reads_datasource_id(monkeypatch):
    async def _go():
        from app.plugin.module_ai.ontology import service as ont

        async def _fake_exec(sql, params=None):
            class _R:
                def fetchone(self):
                    return ("demo_ds_obj", "演示", "id", "name", "DEMO_TABLE", False, 4)

            return _R()

        async def _fake_cols(table, datasource_id=None):
            return {"id", "name"}

        async def _fake_props(code):
            return [
                {"code": "id", "name": "ID", "prop_type": "number", "options": []},
                {"code": "name", "name": "名", "prop_type": "string", "options": []},
            ]

        monkeypatch.setattr(ont, "_exec", _fake_exec)
        monkeypatch.setattr(ont, "_table_columns", _fake_cols)
        monkeypatch.setattr(ont, "list_properties", _fake_props)
        return await ont._instance_meta("demo_ds_obj")

    meta = asyncio.run(_go())
    assert meta["datasource_id"] == 4
    assert meta["materialized"] is True


def test_instance_aggregate_without_group_by(monkeypatch):
    """无分组聚合：SELECT 只产出 1 列，不能取 r[1]（曾 IndexError）。"""
    async def _go():
        from app.plugin.module_ai.ontology import service as ont

        async def _fake_meta(code):
            return {"code": code, "name": "入厂煤批次", "table": "T", "key_prop": "ID",
                    "name_prop": "", "edits_enabled": False, "datasource_id": 4,
                    "props": [], "cols": [], "real_cols": {"ID"}, "materialized": True}

        async def _fake_exec_on(ds_id, sql, params=None):
            class _R:
                def fetchall(self):
                    return [(277,)]

            return _R()

        class _P:
            is_superuser = True

        from app.plugin.module_ai.ontology import security as sec

        async def _fake_rfs(code, principal, cols, quote='"'):
            return {"ok": True, "where": "", "mode": "none"}

        async def _fake_vp(code, principal):
            return None

        monkeypatch.setattr(ont, "_instance_meta", _fake_meta)
        monkeypatch.setattr(ont, "_exec_on", _fake_exec_on)
        monkeypatch.setattr(sec, "row_filter_sql", _fake_rfs)
        monkeypatch.setattr(sec, "visible_properties", _fake_vp)
        return await ont.instance_aggregate("coal_batch", group_by="",
                                            aggs=[{"fn": "count"}], principal=_P())

    r = asyncio.run(_go())
    assert r["ok"] is True
    assert r["series"] == [{"label": "合计", "value": 277}]
    assert r["rows"] == [["合计", 277]]


def test_instance_search_passes_datasource_id(monkeypatch):
    """datasource_id 非空时，实例查询必须走 _exec_on（而不是系统库 _exec）。"""
    seen = {}

    async def _go():
        from app.plugin.module_ai.ontology import service as ont

        async def _fake_meta(code):
            return {
                "code": code, "name": "演示", "table": "DEMO_TABLE", "key_prop": "id",
                "name_prop": "name", "edits_enabled": False, "datasource_id": 4,
                "props": [{"code": "id", "name": "ID", "prop_type": "number", "options": []}],
                "cols": ["id"], "real_cols": {"id", "name"}, "materialized": True,
            }

        async def _fake_exec_on(ds_id, sql, params=None):
            seen["ds_id"] = ds_id

            class _R:
                def fetchall(self):
                    return []

                def fetchone(self):
                    return (0,)

                def scalar(self):
                    return 0

            return _R()

        monkeypatch.setattr(ont, "_instance_meta", _fake_meta)
        monkeypatch.setattr(ont, "_exec_on", _fake_exec_on)
        return await ont.instance_search("demo_ds_obj", limit=10)

    r = asyncio.run(_go())
    assert seen.get("ds_id") == 4
    assert r["ok"] is True
