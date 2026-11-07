"""上下文投影（需要应用/ORM）：自定义源分支不能因漏导入而 NameError。"""
import asyncio

from app.plugin.module_ai.query.policy.principal import Principal as _Principal


def P():
    return _Principal(user_id=7, is_superuser=False, roles=("USER",), attrs={}, entry="ask")




def test_custom_ds_branch_accepts_principal(monkeypatch):
    """回归：自定义源分支曾漏导入 _build_scope → 所有 ds:* 慢路径 NameError（实测踩过）。"""
    import asyncio as _a

    from app.plugin.module_ai.query import service as svc

    monkeypatch.setattr(svc.AiQueryService, "_cfg", classmethod(lambda cls: _a.sleep(0, result={})))
    monkeypatch.setattr(svc.AiQueryService, "_concept_context",
                        classmethod(lambda cls: _a.sleep(0, result="")))
    monkeypatch.setattr(svc.AiQueryService, "_semantic_tables",
                        classmethod(lambda cls, *a, **k: _a.sleep(0, result=["T"])))
    monkeypatch.setattr(svc.AiQueryService, "_ds_schema_map",
                        classmethod(lambda cls, ds, **k: _a.sleep(0, result={"T": ["a", "b"]})))
    monkeypatch.setattr(svc.AiQueryService, "_prune_columns",
                        classmethod(lambda cls, q, cols: (list(cols), len(cols))))
    monkeypatch.setattr("app.plugin.module_ai.query.policy.repo.list_policies",
                        lambda: _a.sleep(0, result=[]))

    svc._BYPASS_CACHE.set(True)
    ctx = _a.run(svc.AiQueryService._build_schema_context("q", "ds:9", [], [], principal=P()))
    assert "T" in ctx
    svc._BYPASS_CACHE.set(False)
