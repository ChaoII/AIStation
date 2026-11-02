"""静默降级计数：让"坏了但还在跑"的能力可见。

这条链路有近 30 处 ``except: pass``。容错本身是对的（附加统计失败不该让整页 500），
但失败不留痕迹 —— 实测三次事故都是"界面正常、数字全空"，只能靠翻日志发现：
影子表没建出来、启动对账没生效、资产血缘恒为 0。
"""


def test_degrade_counts_and_keeps_last_error():
    from app.plugin.module_ai.query.service import (
        _degrade,
        degraded_status,
        reset_degraded,
    )

    reset_degraded()
    _degrade("demo_area", ValueError("boom"))
    _degrade("demo_area", RuntimeError("second"))
    st = degraded_status()
    assert st["total"] == 2
    row = next(r for r in st["areas"] if r["area"] == "demo_area")
    assert row["count"] == 2
    assert "second" in row["error"], row
    reset_degraded()
    assert degraded_status()["total"] == 0


def test_shadow_table_failure_is_counted(test_client, monkeypatch, db_run):
    """建表失败必须被计数（这正是「表根本没建出来」那类事故）。"""
    from app.plugin.module_ai.query import service as S

    S.reset_degraded()
    monkeypatch.setattr(S, "_QUERY_TABLES_SQL", ("CREATE TABLE bad syntax here (",))
    db_run(S._ensure_query_tables())
    st = S.degraded_status()
    assert any(r["area"] == "shadow_tables" for r in st["areas"]), st
    monkeypatch.undo()


def test_degraded_endpoint_shape(test_client, auth_headers):
    """运维入口：GET /ai/query/system/degraded 返回计数与最后一次错误。"""
    from app.plugin.module_ai.query import service as S

    S.reset_degraded()
    S._degrade("endpoint_probe", ValueError("from test"))
    r = test_client.get("/ai/query/system/degraded", headers=auth_headers)
    assert r.status_code == 200, r.text
    body = r.json()
    data = body.get("data") or {}
    assert "areas" in data and "total" in data
    assert any(a.get("area") == "endpoint_probe" for a in data["areas"]), data
