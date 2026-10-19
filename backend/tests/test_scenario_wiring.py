"""场景（Scenario）链路接线回归（2026-10-19 第四批后端部分）。

背景：后端沙箱/读时叠加/单事务合并早已写完，但**只有 instance_search 与
instance_get 接了 scenario** —— pivot/graph 在场景里仍读基线数据，
aggregate 更是「收了 scenario_code 却从头到尾没用」（静默返回基线数据，
比报错更危险）。实施依据见 docs/ontology-scenario-wiring-map.md。
"""
import asyncio
import inspect

from app.plugin.module_ai.ontology import controller as C
from app.plugin.module_ai.ontology import service as svc


def _run(coro):
    return asyncio.run(coro)


def test_instance_pivot_accepts_and_applies_scenario(monkeypatch):
    """instance_pivot 必须接受 scenario_code 并对**对侧实例**做读时叠加。

    修前：在场景里改了 A，沿关系跳到关联的 B 仍是基线数据 ——
    读时叠加语义只做了一半。
    """
    async def _scenario():
        import app.plugin.module_ai.ontology.service as S

        # 关系与元数据打桩
        async def _links(object_code=None):
            return [{"id": 7, "source_object": "piv_src", "target_object": "piv_tgt",
                     "name": "关联", "card": "many_to_one",
                     "source_field": "tgt_id", "target_field": "id"}]

        meta = {"materialized": True, "table": "piv_tbl", "key_prop": "id",
                "cols": ["id", "name"], "real_cols": {"id", "name", "tgt_id"},
                "datasource_id": 0, "name": "对侧"}

        async def _meta(code):
            return dict(meta)

        async def _can_view(code, principal):
            return True, ""

        async def _exec_on(ds, sql, params):
            class _R:
                def fetchone(self):
                    return ("v1",)

                def fetchall(self):
                    return [("v1", "基线名")]

            return _R()

        async def _overlay(scenario, code, items):
            # 叠加后给每行打上标记，便于断言真的生效
            return [{**x, "_overlay": f"{scenario}/{code}"} for x in items]

        monkeypatch.setattr(S, "list_links", _links)
        monkeypatch.setattr(S, "_instance_meta", _meta)
        monkeypatch.setattr(S, "_ensure_can_view", lambda c, p: asyncio.sleep(0, result=None))
        monkeypatch.setattr(S, "_exec_on", _exec_on)
        monkeypatch.setattr(S, "_row_to_instance",
                            lambda meta, row, cols: dict(zip(cols, row, strict=False)))
        monkeypatch.setattr(S._sec, "filter_instances",
                            lambda code, items, p: asyncio.sleep(
                                0, result={"rows": items, "dropped": 0, "hidden_columns": []}))
        monkeypatch.setattr("app.plugin.module_ai.ontology.scenario.overlay_edits", _overlay)

        r = await S.instance_pivot("piv_src", "k1", 7, limit=10, scenario_code="sc_demo")
        return r

    r = _run(_scenario())
    assert r.get("ok"), r
    assert r.get("items"), f"没有返回关联实例：{r}"
    assert all(x.get("_overlay") == "sc_demo/piv_tgt" for x in r["items"]), (
        f"pivot 没对对侧实例做场景叠加：{r['items']}")
    assert r.get("scenario_overlay") is True, f"响应未标记叠加来源：{r}"


def test_instance_graph_passes_scenario_down():
    """instance_graph 必须把 scenario 透传给 instance_get 与内部的 instance_pivot。"""
    get_src = inspect.getsource(svc.instance_graph)
    assert "scenario_code=scenario_code" in get_src, (
        "instance_graph 没把 scenario 透传给 instance_get")
    assert "piv = await instance_pivot" in get_src, "内部没走 instance_pivot"
    # pivot 调用处也要带 scenario（否则图的邻居仍是基线数据）
    assert "scenario_code=scenario_code)" in get_src, (
        "instance_graph 内部的 instance_pivot 调用没带 scenario")


def test_instance_aggregate_refuses_scenario_instead_of_lying():
    """聚合在场景下必须显式拒绝，不能静默返回基线数据。

    修前：`instance_aggregate` **收了 scenario_code 却从头到尾没用** ⇒
    在场景里看图表会显示基线数据，用户以为看到了场景结果。
    完整支持需要把场景差异下推进 SQL（像 row_filter_sql 那样），是独立工程量；
    在那之前，显式拒绝优于给错数。
    """
    r = _run(svc.instance_aggregate("whatever", group_by="name",
                                    scenario_code="sc_demo"))
    assert r.get("ok") is False, f"场景下的聚合没有被拒绝：{r}"
    assert r.get("blocked_by") == "scenario_unsupported", r
    assert "暂不支持" in str(r.get("msg", "")), r


def test_controller_endpoints_thread_scenario():
    """两个端点都要把 scenario 从请求带到 service。"""
    pivot_src = inspect.getsource(C.instance_pivot)
    assert "scenario" in pivot_src, "/instance/.../pivot 端点没暴露 scenario 参数"
    assert "scenario_code=scenario" in pivot_src, "pivot 端点没把 scenario 传给 service"

    graph_src = inspect.getsource(C.instance_graph)
    assert 'data.get("scenario"' in graph_src, "/instance/graph 端点没读取 scenario"
    assert "scenario_code=" in graph_src, "graph 端点没把 scenario 传给 service"
