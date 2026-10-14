"""S4-T1：自动建模 API（缓存失效 + kind 分派）。"""
import asyncio
from types import SimpleNamespace


def _auth():
    return SimpleNamespace(user=SimpleNamespace(id=1, is_superuser=True))


def test_generate_modeling_metrics_invalidates_cache(monkeypatch):
    async def _go():
        from app.plugin.module_ai.query import modeling as M
        from app.plugin.module_ai.query import service as S

        async def _fake_gen(datasource, auth, max_objects=12, dry=False, offset=0):
            return {"parsed": 2, "verified": 1, "saved": 1, "rejected": 1, "reasons": []}

        monkeypatch.setattr(M, "generate_metrics", _fake_gen)
        S._SETTINGS_CACHE = {"x": 1}
        out = await S.AiQueryService.generate_modeling("metrics", "ds:4", _auth())
        return out, S._SETTINGS_CACHE

    out, cache = asyncio.run(_go())
    assert out["saved"] == 1
    assert cache is None          # 生成后必须失效缓存，前端才能看到新指标


def test_generate_modeling_annotate_dispatch(monkeypatch):
    async def _go():
        from app.plugin.module_ai.query import modeling as M
        from app.plugin.module_ai.query import service as S

        seen = {}

        async def _fake_ann(datasource, auth, max_objects=12, offset=0):
            seen["datasource"] = datasource
            return {"parsed": 3, "saved": 3}

        monkeypatch.setattr(M, "generate_annotations", _fake_ann)
        return await S.AiQueryService.generate_modeling("annotate", "ds:4", _auth()), seen

    out, seen = asyncio.run(_go())
    assert out["saved"] == 3 and seen["datasource"] == "ds:4"
