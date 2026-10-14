"""S1-T2：`_exec_on` 按 datasource_id 选择执行引擎。"""
import asyncio


def test_exec_on_system_when_no_ds():
    async def _go():
        from app.plugin.module_ai.ontology import service as ont

        r = await ont._exec_on(None, "SELECT 1 AS x")
        assert r.scalar() == 1
        assert r.fetchall()[0][0] == 1

    asyncio.run(_go())


def test_exec_on_uses_datasource_engine_and_disposes(monkeypatch):
    calls = {"disposed": False}

    class _FakeConn:
        async def execute(self, *a, **k):
            class _R:
                def fetchall(self):
                    return [(42,)]

            return _R()

    class _FakeEngine:
        def connect(self):
            return self

        async def __aenter__(self):
            return _FakeConn()

        async def __aexit__(self, *a):
            return False

        async def dispose(self):
            calls["disposed"] = True

    async def _go():
        from app.plugin.module_ai.ontology import service as ont
        from app.plugin.module_ai.query import executor as qe
        from app.plugin.module_ai.query import service as qs

        class _DS:  # 假数据源
            type, host, port, database, username, password = "postgres", "h", 1, "d", "u", "p"

        async def _fake_load(ds_id):
            return _DS()

        monkeypatch.setattr(qs, "_load_ds", _fake_load)
        monkeypatch.setattr(qe, "build_engine", lambda cfg: _FakeEngine())

        r = await ont._exec_on(4, "SELECT 42")
        assert r.scalar() == 42
        assert calls["disposed"] is True

    asyncio.run(_go())
