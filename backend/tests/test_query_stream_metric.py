"""S2-T5：流式问数接入指标快路径。"""
import asyncio
from types import SimpleNamespace


def test_stream_hits_metric_fast_path(monkeypatch):
    from app.plugin.module_ai.query import service as S

    async def _go():
        async def _seed():
            return None

        async def _sess(sid, title, auth):
            return {"id": 1}

        async def _ctx(oc, ok, auth):
            return ""

        async def _rewrite(q, sid, ds):
            return q

        async def _cfg():
            return {"object_query_enabled": "false"}

        async def _metrics(ds=None):
            return [{"key": "batch_count", "name": "批次量", "agg": "count",
                     "datasource": "system", "sql_template": "SELECT 1 AS 数值",
                     "params": [], "cache_ttl": 0, "enabled": True}]

        async def _terms(ds=None):
            return []

        async def _exec_metric(metric, params, auth=None):
            return {"sql": "SELECT 1", "columns": ["数值"], "rows": [[1]], "took_ms": 1}

        async def _save(*a, **k):
            return {"summary": "s"}

        monkeypatch.setattr(S.AiQueryService, "ensure_system_seed",
                            classmethod(lambda cls: _seed()))
        monkeypatch.setattr(S.AiQueryService, "get_or_create_session",
                            classmethod(lambda cls, sid, t, a: _sess(sid, t, a)))
        monkeypatch.setattr(S.AiQueryService, "_object_context_block",
                            classmethod(lambda cls, oc, ok, a: _ctx(oc, ok, a)))
        monkeypatch.setattr(S.AiQueryService, "_maybe_rewrite",
                            classmethod(lambda cls, q, sid, ds: _rewrite(q, sid, ds)))
        monkeypatch.setattr(S.AiQueryService, "_cfg", classmethod(lambda cls: _cfg()))
        monkeypatch.setattr(S.AiQueryService, "list_metrics",
                            classmethod(lambda cls, ds=None: _metrics(ds)))
        monkeypatch.setattr(S.AiQueryService, "list_terms",
                            classmethod(lambda cls, ds=None: _terms(ds)))
        monkeypatch.setattr(S.AiQueryService, "_save_message",
                            classmethod(lambda cls, *a, **k: _save(*a, **k)))
        monkeypatch.setattr(S.AiQueryService, "_summarize",
                            classmethod(lambda cls, m, r: "s"))
        monkeypatch.setattr(S, "_execute_metric", _exec_metric)
        monkeypatch.setattr(S, "_match_metric", lambda q, m, t, c=None: m[0] if m else None)
        monkeypatch.setattr(S, "_is_listing_question", lambda q: False)
        monkeypatch.setattr(S, "_wants_grouping", lambda q: False)

        auth = SimpleNamespace(user=SimpleNamespace(id=1, is_superuser=True))
        return [ev async for ev in S.AiQueryService.ask_stream("批次量", auth, session_id=1)]

    evs = asyncio.run(_go())
    paths = [e.get("path") for e in evs if e.get("type") in ("result", "done")]
    assert "fast" in paths, evs
    assert evs[-1].get("type") == "done"
