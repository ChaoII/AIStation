"""两段式分解生成：多步判定 / 计划解析 / 计划渲染（纯逻辑）。"""


def test_is_multistep_only_for_multi_step_questions():
    from app.plugin.module_ai.query.plan import is_multistep

    assert is_multistep("每个设备下上限最高的两个测点") is True
    assert is_multistep("按煤种类型统计记录数并排名") is True
    assert is_multistep("各煤种类型的记录占比是多少") is True
    assert is_multistep("今天一共产生了多少条告警") is False
    assert is_multistep("系统里有多少个用户") is False


def test_parse_plan_extracts_structured_fields():
    from app.plugin.module_ai.query.plan import parse_plan

    text = (
        '{"tables":["CMMS_POINT","CMMS_FACILITY"],"joins":["p.FACILITYID=f.ID"],'
        '"group_by":["p.FACILITYID"],"window":["ROW_NUMBER() OVER (PARTITION BY p.FACILITYID '
        'ORDER BY p.UPPERLIMIT DESC)"],"filters":["rn<=2"],"outputs":["设备名称","测点名称"],'
        '"order_limit":"ORDER BY 设备名称"}'
    )
    p = parse_plan(text)
    assert p and p["tables"] == ["CMMS_POINT", "CMMS_FACILITY"]
    assert p["group_by"] == ["p.FACILITYID"]
    assert "ORDER BY" in p["order_limit"]


def test_parse_plan_tolerates_fenced_and_truncated_output():
    from app.plugin.module_ai.query.plan import parse_plan

    fenced = '```json\n{"tables":["A_T"],"group_by":["A_T.ID"]}\n```'
    assert parse_plan(fenced)["tables"] == ["A_T"]
    # 截断：外层没闭合 → 解析失败 → None（调用方降级）
    assert parse_plan('{"tables":["A_T"') is None
    # 没有表 → 视为无效
    assert parse_plan('{"group_by":["x"]}') is None
    assert parse_plan("随便一段没有 JSON 的话") is None


def test_format_plan_renders_readable_lines():
    from app.plugin.module_ai.query.plan import format_plan

    out = format_plan({"tables": ["T"], "group_by": ["T.ID"], "joins": [], "window": []})
    assert "用到的表" in out and "T" in out
    assert "分组键" in out
    assert "联表条件" not in out          # 空项不渲染


def test_sql_prompt_includes_plan_and_context():
    from app.plugin.module_ai.query.plan import sql_prompt

    out = sql_prompt("问题", {"tables": ["T"]}, "【可用表】T(a,b)")
    assert "【可用表】" in out
    assert "执行计划" in out
    assert "只返回一条 SELECT" in out
