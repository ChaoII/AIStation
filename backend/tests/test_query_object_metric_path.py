"""S2-T4：对象查询路径串联指标并放开自定义数据源。"""
import asyncio
from types import SimpleNamespace


def test_object_query_path_attempts_custom_ds(monkeypatch):
    """自定义数据源不再被无条件 return None：应把 datasource 透传给对象白名单构建。"""
    async def _go():
        from app.plugin.module_ai.query import service as S

        seen = {}

        async def _fake_cfg():
            return {}

        async def _fake_allowed(question, auth, max_objects=8, datasource="system"):
            seen["datasource"] = datasource
            return {}

        monkeypatch.setattr(S.AiQueryService, "_cfg", classmethod(lambda cls: _fake_cfg()))
        monkeypatch.setattr(
            S.AiQueryService, "_allowed_objects_for_query",
            classmethod(lambda cls, q, a, max_objects=8, datasource="system":
                        _fake_allowed(q, a, max_objects, datasource)))
        auth = SimpleNamespace(user=SimpleNamespace(id=1, is_superuser=True))
        ans = await S.AiQueryService._object_query_path("各煤种批次量", 1, "ds:4", auth)
        return ans, seen

    ans, seen = asyncio.run(_go())
    assert ans is None
    assert seen.get("datasource") == "ds:4"


def test_allowed_objects_for_query_accepts_datasource():
    """签名必须接受 datasource 形参（否则自定义源调用直接 TypeError）。"""
    import inspect

    from app.plugin.module_ai.query import service as S

    sig = inspect.signature(S.AiQueryService._allowed_objects_for_query)
    assert "datasource" in sig.parameters
