"""场景的纯函数与叠加逻辑单测。

对照官方 ontology/overview-ontology-scenario：
· 场景 = 沙箱式的编辑叠加，不影响主本体
· 读场景 = 基线 + 差异
· 限额与寿命都取官方数字
"""
import asyncio
from datetime import datetime
from decimal import Decimal

import pytest

from app.plugin.module_ai.ontology import scenario as S


# ---------------------------------------------------------------------------
# 安全序列化
# ---------------------------------------------------------------------------
def test_json_safe_handles_datetime_and_decimal():
    s = S._j({"t": datetime(2026, 10, 9, 12, 0, 0), "d": Decimal("1.5"), "b": b"x"})
    assert "2026-10-09 12:00:00" in s
    assert "1.5" in s
    assert "x" in s


def test_json_safe_keeps_chinese():
    assert "改名" in S._j({"name": "改名"})


# ---------------------------------------------------------------------------
# 官方常量
# ---------------------------------------------------------------------------
def test_official_limits_are_used():
    # 官方：30,000 edits / 50 actions / 31 天
    assert S.MAX_EDITS == 30000
    assert S.MAX_ACTIONS == 50
    assert S.DEFAULT_TTL_DAYS == 31
    assert S.MAX_LOAD_OBJECTS == 10000


def test_status_and_edit_labels_cover_all_values():
    for s in S.ONT_SCENARIO_STATUS:
        assert s in S.ONT_SCENARIO_STATUS_LABEL, s
    for k in S.ONT_EDIT_KINDS:
        assert k in S.ONT_EDIT_LABEL, k
    # 官方：模型结果不会被合并 —— 这个种类必须存在且说明里写明
    assert "model_result" in S.ONT_EDIT_KINDS
    assert "不合并" in S.ONT_EDIT_LABEL["model_result"]


def test_now_format():
    s = S._now()
    assert len(s) == 19 and s[4] == "-" and s[13] == ":"


# ---------------------------------------------------------------------------
# 读叠加（把 list_edits 打桩，专测叠加算法）
# ---------------------------------------------------------------------------
def _patch_edits(monkeypatch, edits):
    async def fake(code):
        return edits

    monkeypatch.setattr(S, "list_edits", fake)


def _edit(key, kind, before=None, after=None, action_code=""):
    return {"object_key": key, "kind": kind, "before": before or {}, "after": after or {},
            "object_code": "cams", "action_code": action_code,
            "kind_label": S.ONT_EDIT_LABEL.get(kind, kind)}


def test_overlay_modify(monkeypatch):
    _patch_edits(monkeypatch, [_edit("1", "modify", {"name": "old"}, {"name": "new"})])
    items = [{"key": "1", "props": {"name": "old", "brand": "H"}},
             {"key": "2", "props": {"name": "other"}}]
    out = asyncio.run(S.overlay_edits("sc", "cams", items))
    by = {i["key"]: i for i in out}
    assert by["1"]["props"]["name"] == "new"
    assert by["1"]["props"]["brand"] == "H"      # 未改的字段保留
    assert by["1"]["scenario_edited"] is True
    assert by["2"]["props"]["name"] == "other"   # 未编辑的对象原样


def test_overlay_delete(monkeypatch):
    _patch_edits(monkeypatch, [_edit("1", "delete")])
    items = [{"key": "1", "props": {}}, {"key": "2", "props": {}}]
    out = asyncio.run(S.overlay_edits("sc", "cams", items))
    assert [i["key"] for i in out] == ["2"]


def test_overlay_create(monkeypatch):
    _patch_edits(monkeypatch, [_edit("9", "create", {}, {"name": "新建的"})])
    out = asyncio.run(S.overlay_edits("sc", "cams", [{"key": "1", "props": {}}]))
    keys = {i["key"] for i in out}
    assert keys == {"1", "9"}
    created = next(i for i in out if i["key"] == "9")
    assert created["scenario_created"] is True
    assert created["props"]["name"] == "新建的"


def test_overlay_create_then_delete_is_hidden(monkeypatch):
    _patch_edits(monkeypatch, [_edit("9", "create", {}, {"name": "x"}),
                               _edit("9", "delete")])
    out = asyncio.run(S.overlay_edits("sc", "cams", []))
    assert out == []


def test_overlay_no_edits_passthrough(monkeypatch):
    _patch_edits(monkeypatch, [])
    items = [{"key": "1", "props": {"a": 1}}]
    assert asyncio.run(S.overlay_edits("sc", "cams", items)) == items


def test_overlay_instance_modify_and_delete(monkeypatch):
    _patch_edits(monkeypatch, [_edit("1", "modify", {}, {"name": "new"})])
    assert asyncio.run(S.overlay_instance("sc", "cams", "1", {"name": "old"}))["name"] == "new"
    _patch_edits(monkeypatch, [_edit("1", "delete")])
    assert asyncio.run(S.overlay_instance("sc", "cams", "1", {"name": "old"})) == {}


# ---------------------------------------------------------------------------
# 差异合并算法（多次编辑叠加成净变化）
# ---------------------------------------------------------------------------
def test_diff_merges_multiple_edits(monkeypatch):
    async def fake_list(code):
        return [_edit("1", "modify", {"name": "base"}, {"name": "step1"}),
                _edit("1", "modify", {"name": "step1"}, {"name": "step2"})]

    async def fake_exec(sql, params=None):
        class R:
            def fetchone(self):
                return (1,)
        return R()

    monkeypatch.setattr(S, "list_edits", fake_list)
    monkeypatch.setattr(S._svc, "_exec", fake_exec)
    d = asyncio.run(S.scenario_diff("sc"))
    assert d["ok"] is True
    assert d["objects_changed"] == 1
    ch = d["changes"][0]
    # before 取第一次的基线，after 取最后一次
    assert ch["changed"]["name"] == {"before": "base", "after": "step2"}


def test_diff_separates_model_results(monkeypatch):
    async def fake_list(code):
        return [_edit("1", "modify", {"a": 1}, {"a": 2}),
                _edit("1", "model_result", {}, {"a": 9})]

    async def fake_exec(sql, params=None):
        class R:
            def fetchone(self):
                return (1,)
        return R()

    monkeypatch.setattr(S, "list_edits", fake_list)
    monkeypatch.setattr(S._svc, "_exec", fake_exec)
    d = asyncio.run(S.scenario_diff("sc"))
    # 模型结果不进入 changes，单独列出（官方：不会合并）
    assert len(d["changes"]) == 1
    assert len(d["model_results"]) == 1
    assert d["changes"][0]["changed"]["a"]["after"] == 2


def test_diff_missing_scenario(monkeypatch):
    async def fake_exec(sql, params=None):
        class R:
            def fetchone(self):
                return None
        return R()

    monkeypatch.setattr(S._svc, "_exec", fake_exec)
    d = asyncio.run(S.scenario_diff("nope"))
    assert d["ok"] is False


# ---------------------------------------------------------------------------
# 唯一编码
# ---------------------------------------------------------------------------
def test_unique_code_from_ascii_and_chinese(monkeypatch):
    async def fake_exec(sql, params=None):
        class R:
            def fetchone(self):
                return None
        return R()

    monkeypatch.setattr(S._svc, "_exec", fake_exec)
    a = asyncio.run(S._unique_code("Plan A"))
    b = asyncio.run(S._unique_code("方案甲"))
    assert a == "sc_plan_a"
    assert b.startswith("sc_")


def test_unique_code_appends_suffix_on_conflict(monkeypatch):
    calls = {"n": 0}

    async def fake_exec(sql, params=None):
        calls["n"] += 1

        class R:
            def fetchone(self):
                return (1,) if calls["n"] == 1 else None
        return R()

    monkeypatch.setattr(S._svc, "_exec", fake_exec)
    code = asyncio.run(S._unique_code("Plan A"))
    assert code == "sc_plan_a_2"


def test_compare_requires_two():
    r = asyncio.run(S.compare_scenarios(["only_one"]))
    assert r["ok"] is False
    assert "2" in r["msg"]


@pytest.mark.parametrize("kind", S.ONT_EDIT_KINDS)
def test_edit_labels_are_chinese(kind):
    assert S.ONT_EDIT_LABEL[kind]
