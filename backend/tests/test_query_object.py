"""对象查询 IR：解析 / 越界裁剪 / 形态限制 / 提示词（纯逻辑，可 PYTEST_NO_APP=1 快测）。

设计：docs/superpowers/specs/2026-10-14-semantic-query-layer-design.md
"""


def _allowed():
    return {
        "video_cameras": {
            "name": "摄像机表",
            "fields": {
                "id": {"name": "ID", "type": "string", "options": []},
                "name": {"name": "名称", "type": "string", "options": []},
                "status": {"name": "状态", "type": "enum", "options": ["ONLINE", "OFFLINE"]},
                "region": {"name": "区域", "type": "string", "options": []},
            },
            "links": {"摄像机_告警记录": {"id": 3, "source": "video_cameras",
                                     "target": "video_alarm_records", "card": "one_to_many"}},
        },
    }


def test_parse_ir_accepts_valid_and_fenced():
    from app.plugin.module_ai.query.object_query import parse_ir

    ir = parse_ir('{"object":"video_cameras","group_by":[{"field":"region"}]}')
    assert ir and ir.object == "video_cameras"
    assert ir.group_by[0]["field"] == "region"

    fenced = parse_ir('```json\n{"object":"video_cameras","limit":10}\n```')
    assert fenced and fenced.object == "video_cameras"
    assert fenced.limit == 10


def test_parse_ir_returns_none_on_garbage():
    from app.plugin.module_ai.query.object_query import parse_ir

    assert parse_ir("") is None
    assert parse_ir("没有 JSON 的一段话") is None
    assert parse_ir('{"object":"x"') is None          # 截断（外层没闭合）
    assert parse_ir("[1,2,3]") is None                 # 不是对象


def test_validate_ir_rejects_object_outside_allowlist():
    from app.plugin.module_ai.query.object_query import parse_ir, validate_ir

    ir = parse_ir('{"object":"secret_table","filters":[{"field":"id","op":"eq","value":1}]}')
    cleaned, reasons = validate_ir(ir, _allowed())
    assert cleaned is None                             # 对象越界 → 整条作废
    assert any("不在可查询范围" in r for r in reasons)


def test_validate_ir_trims_bad_fields_and_ops_but_keeps_rest():
    from app.plugin.module_ai.query.object_query import parse_ir, validate_ir

    ir = parse_ir(
        '{"object":"video_cameras",'
        '"filters":[{"field":"region","op":"eq","value":"华南"},'
        '{"field":"nosuchcol","op":"eq","value":1},'
        '{"field":"status","op":"badop","value":"ONLINE"}],'
        '"group_by":[{"field":"region","alias":"区域"}],'
        '"aggregations":[{"fn":"count","field":"","alias":"数量"}]}'
    )
    cleaned, reasons = validate_ir(ir, _allowed())
    assert cleaned is not None
    assert [f["field"] for f in cleaned.filters] == ["region"]     # 越界字段/算子被剔除
    assert cleaned.group_by[0]["field"] == "region"
    assert cleaned.aggregations[0]["fn"] == "count"
    assert any("nosuchcol" in r for r in reasons)
    assert any("badop" in r for r in reasons)


def test_validate_ir_rejects_unsupported_shapes():
    """P0：多分组/多指标/多跳 一律不支持 → 降级（不返回半截结果）。"""
    from app.plugin.module_ai.query.object_query import parse_ir, validate_ir

    multi_group = parse_ir(
        '{"object":"video_cameras","group_by":[{"field":"region"},{"field":"status"}]}')
    assert validate_ir(multi_group, _allowed())[0] is None

    multi_agg = parse_ir(
        '{"object":"video_cameras","aggregations":[{"fn":"count"},{"fn":"min","field":"id"}]}')
    assert validate_ir(multi_agg, _allowed())[0] is None

    multi_hop = parse_ir(
        '{"object":"video_cameras","object_key":"1",'
        '"traverse":[{"link":"摄像机_告警记录"},{"link":"摄像机_告警记录"}]}')
    assert validate_ir(multi_hop, _allowed())[0] is None

    traverse_no_key = parse_ir(
        '{"object":"video_cameras","traverse":[{"link":"摄像机_告警记录"}]}')
    assert validate_ir(traverse_no_key, _allowed())[0] is None


def test_validate_ir_rejects_empty_and_clamps_limit():
    from app.plugin.module_ai.query.object_query import parse_ir, validate_ir

    empty = parse_ir('{"object":"video_cameras"}')
    assert validate_ir(empty, _allowed())[0] is None        # 没有任何条件

    big = parse_ir('{"object":"video_cameras","limit":99999,'
                   '"filters":[{"field":"region","op":"eq","value":"x"}]}')
    cleaned, _ = validate_ir(big, _allowed())
    assert cleaned is not None and cleaned.limit == 500     # 夹到上限


def test_validate_ir_accepts_aggregation_count_without_field():
    from app.plugin.module_ai.query.object_query import parse_ir, validate_ir

    ir = parse_ir('{"object":"video_cameras","group_by":[{"field":"region","alias":"区域"}],'
                  '"aggregations":[{"fn":"count","field":"*","alias":"数量"}]}')
    cleaned, _ = validate_ir(ir, _allowed())
    assert cleaned is not None
    assert cleaned.aggregations[0]["field"] == ""


def test_render_ir_prompt_only_contains_allowlisted_names():
    from app.plugin.module_ai.query.object_query import render_ir_prompt

    p = render_ir_prompt("按区域统计摄像机数量", _allowed())
    assert "video_cameras" in p and "region" in p, p
    assert "不存在的表" not in p
    assert "只返回 JSON" in p


def test_build_allowed_shape():
    from app.plugin.module_ai.query.object_query import build_allowed

    out = build_allowed(
        [{"code": "c1", "name": "对象一"}],
        {"c1": [{"code": "f1", "name": "字段一", "prop_type": "string", "options": ["A"]}]},
        {"c1": [{"id": 9, "name": "关系一", "source_object": "c1", "target_object": "c2"}]},
    )
    assert set(out) == {"c1"}
    assert out["c1"]["fields"]["f1"]["options"] == ["A"]
    assert out["c1"]["links"]["关系一"]["id"] == 9


def test_validate_ir_accepts_chinese_display_names():
    """实测回归：模型会回填中文名（「摄像机表」）而不是编码 → 必须宽容解析。"""
    from app.plugin.module_ai.query.object_query import parse_ir, validate_ir

    ir = parse_ir(
        '{"object":"摄像机表",'
        '"group_by":[{"field":"区域","alias":"区域"}],'
        '"aggregations":[{"fn":"count","field":"","alias":"数量"}]}'
    )
    cleaned, reasons = validate_ir(ir, _allowed())
    assert cleaned is not None, reasons
    assert cleaned.object == "video_cameras"            # 中文名 → 编码
    assert cleaned.group_by[0]["field"] == "region"     # 中文名 → 编码
    assert cleaned.aggregations[0]["fn"] == "count"


def test_render_ir_prompt_puts_code_before_display_name():
    """编码必须排在中文名之前（否则模型倾向回填中文名）。"""
    from app.plugin.module_ai.query.object_query import render_ir_prompt

    p = render_ir_prompt("随便问问", _allowed())
    assert p.index("video_cameras") < p.index("摄像机表")
    assert "不要填中文名" in p


def test_object_exec_hides_credential_columns(monkeypatch):
    """单对象详情不得把 password/token 带进答案（答案会落进会话历史）。"""
    import asyncio

    from app.plugin.module_ai.ontology import service as ont
    from app.plugin.module_ai.query import object_exec
    from app.plugin.module_ai.query.object_query import ObjectQueryIR

    async def _meta(code):
        return {"code": code, "table": "video_cameras", "key_prop": "id", "name_prop": "name",
                "edits_enabled": False, "props": [],
                "cols": ["id", "name", "password", "access_token", "status"],
                "materialized": True}

    async def _get(code, key, principal=None, scenario_code=""):
        return {"ok": True, "props": {"id": 1, "name": "c1", "password": "s3cret",
                                      "access_token": "tok", "status": "ONLINE"}}

    monkeypatch.setattr(ont, "_instance_meta", _meta)
    monkeypatch.setattr(ont, "instance_get", _get)

    res = asyncio.run(object_exec.execute_ir(
        ObjectQueryIR(object="video_cameras", object_key="1"), None))
    assert res["ok"] is True
    assert "password" not in res["columns"]
    assert "access_token" not in res["columns"]
    assert "status" in res["columns"]
    assert "隐藏敏感字段" in (res.get("note") or "")

