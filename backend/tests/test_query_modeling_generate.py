"""S3-T3：指标生成-验证-落库管线（mock LLM）。"""
import asyncio
from types import SimpleNamespace


def test_generate_metrics_mock_llm_and_save(monkeypatch):
    async def _go():
        from app.plugin.module_ai.query import modeling as M
        from app.plugin.module_ai.query import service as S

        async def _fake_collect(datasource, max_objects):
            return [{"code": "coal_batch", "name": "入厂煤批次", "table": "T",
                     "fields": [{"code": "FUELKINDNAME", "name": "煤种", "type": "string"}]}]

        async def _fake_llm(prompt, **k):
            return ('[{"key":"coal_batch_count","name":"入厂批次数","object_code":"coal_batch",'
                    '"property_code":"","agg_fn":"count","bound_dimensions":[]}]')

        async def _fake_verify(metric):
            return {"ok": True, "rows": [["x", 3]]}

        saved = {}

        async def _fake_upsert(data, auth):
            saved["key"] = data.key
            saved["object_code"] = data.object_code
            return {"key": data.key}

        monkeypatch.setattr(M, "collect_objects", _fake_collect)
        monkeypatch.setattr(M, "model_llm", _fake_llm)
        monkeypatch.setattr(M, "verify_metric", _fake_verify)
        monkeypatch.setattr(S.AiQueryService, "upsert_metric", _fake_upsert)

        auth = SimpleNamespace(user=SimpleNamespace(id=1, is_superuser=True))
        return await M.generate_metrics("ds:4", auth, max_objects=5), saved

    out, saved = asyncio.run(_go())
    assert out["saved"] == 1
    assert saved.get("key") == "coal_batch_count"
    assert saved.get("object_code") == "coal_batch"


def test_generate_metrics_rejects_unverified(monkeypatch):
    async def _go():
        from app.plugin.module_ai.query import modeling as M
        from app.plugin.module_ai.query import service as S

        async def _fake_collect(datasource, max_objects):
            return [{"code": "coal_batch", "name": "x", "table": "T", "fields": []}]

        async def _fake_llm(prompt, **k):
            return '[{"key":"k1","object_code":"coal_batch","agg_fn":"count"}]'

        async def _fake_verify(metric):
            return {"ok": False, "reason": "空结果"}

        called = {"upsert": 0}

        async def _fake_upsert(data, auth):
            called["upsert"] += 1
            return {"key": data.key}

        monkeypatch.setattr(M, "collect_objects", _fake_collect)
        monkeypatch.setattr(M, "model_llm", _fake_llm)
        monkeypatch.setattr(M, "verify_metric", _fake_verify)
        monkeypatch.setattr(S.AiQueryService, "upsert_metric", _fake_upsert)

        auth = SimpleNamespace(user=SimpleNamespace(id=1, is_superuser=True))
        return await M.generate_metrics("ds:4", auth, max_objects=5), called

    out, called = asyncio.run(_go())
    assert out["saved"] == 0 and out["rejected"] == 1
    assert called["upsert"] == 0
