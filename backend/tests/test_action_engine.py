"""动作引擎单测：提交条件 / 规则 / 副作用（纯函数，不连库）。

对照官方 action-types 文档的语义逐条验证。
"""
from app.plugin.module_ai.ontology import action_engine as E


def _ctx(**kw):
    return E.ActorContext(**kw)


# ---------------------------------------------------------------------------
# 取值
# ---------------------------------------------------------------------------
def test_resolve_value_kinds():
    ctx = _ctx(user_id=7, user_name="张三", role_ids=[1, 2], role_codes=["管理员"])
    params = {"name": "新名字"}
    assert E.resolve_value("静态", ctx, params) == "静态"
    assert E.resolve_value({"kind": "static", "value": 5}, ctx, params) == 5
    assert E.resolve_value({"kind": "parameter", "value": "name"}, ctx, params) == "新名字"
    assert E.resolve_value({"kind": "current_user"}, ctx, params) == "7"
    assert set(E.resolve_value({"kind": "current_user_group"}, ctx, params)) == {"管理员", "1", "2"}
    assert E.resolve_value({"kind": "execution_context"}, ctx, params) == {"is_scenario": False}
    assert E.resolve_value({"kind": "none"}, ctx, params) is None
    assert E.resolve_value(None, ctx, params) is None


def test_resolve_value_object_parameter_property():
    ctx = _ctx()
    calls = []

    def resolver(p, prop):
        calls.append((p, prop))
        return "operational"

    v = E.resolve_value({"kind": "parameter", "value": "aircraft", "property": "status"},
                        ctx, {}, resolver)
    assert v == "operational"
    assert calls == [("aircraft", "status")]


# ---------------------------------------------------------------------------
# 算子
# ---------------------------------------------------------------------------
def test_single_value_operators():
    assert E._apply_operator("is", "a", "a") is True
    assert E._apply_operator("is", "a", "b") is False
    assert E._apply_operator("is_not", "a", "b") is True
    assert E._apply_operator("matches", "John Doe", r"^[A-Z]") is True
    assert E._apply_operator("matches", "john", r"^[A-Z]") is False
    assert E._apply_operator("lt", 4, 2) is False
    assert E._apply_operator("gte", 4, 2) is True
    assert E._apply_operator("gte", "abc", 2) is False  # 非数值不通过
    assert E._apply_operator("is_empty", "", None) is True
    assert E._apply_operator("is_empty", [], None) is True
    assert E._apply_operator("is_not_empty", "x", None) is True


def test_multi_value_operators():
    assert E._apply_operator("includes", ["a", "b"], "a") is True
    assert E._apply_operator("includes", ["a", "b"], "c") is False
    assert E._apply_operator("includes_any", ["a", "b"], ["c", "b"]) is True
    assert E._apply_operator("is_included_in", "a", ["a", "b"]) is True
    assert E._apply_operator("each_is", ["a", "a"], "a") is True
    assert E._apply_operator("each_is", ["a", "b"], "a") is False
    assert E._apply_operator("each_is_not", ["a", "b"], "c") is True


def test_invalid_regex_fails_closed():
    # 正则写错时不能放行
    assert E._apply_operator("matches", "x", "([") is False


# ---------------------------------------------------------------------------
# 提交条件
# ---------------------------------------------------------------------------
def test_criteria_all_must_pass_and_collect_failure_messages():
    ctx = _ctx(user_id=7, role_codes=["飞行调度员"])
    params = {"status": "operational"}
    criteria = [
        {"operator": "includes",
         "failure_message": "只有飞行调度员能执行",
         "left": {"kind": "current_user_group"}, "right": {"kind": "static", "value": "飞行调度员"}},
        {"operator": "is",
         "failure_message": "飞机必须处于运行状态",
         "left": {"kind": "parameter", "value": "status"}, "right": {"kind": "static", "value": "operational"}},
    ]
    r = E.evaluate_criteria(criteria, ctx, params)
    assert r["ok"] is True and r["failures"] == []

    # 第二条不满足 → 只有它的失败信息
    r2 = E.evaluate_criteria(criteria, ctx, {"status": "retired"})
    assert r2["ok"] is False
    assert r2["failures"] == ["飞机必须处于运行状态"]


def test_criteria_group_and_or_not():
    ctx = _ctx(user_id=1, role_codes=["规划组"])
    g_and = {"operator": "and", "failure_message": "需同时满足",
             "children": [{"operator": "is", "left": {"kind": "current_user"}, "right": {"kind": "static", "value": "1"}},
                          {"operator": "is", "left": {"kind": "current_user"}, "right": {"kind": "static", "value": "2"}}]}
    assert E.evaluate_criteria([g_and], ctx, {})["ok"] is False

    g_or = {"operator": "or", "failure_message": "需满足其一",
            "children": [{"operator": "is", "left": {"kind": "current_user"}, "right": {"kind": "static", "value": "1"}},
                         {"operator": "is", "left": {"kind": "current_user"}, "right": {"kind": "static", "value": "2"}}]}
    assert E.evaluate_criteria([g_or], ctx, {})["ok"] is True

    g_not = {"operator": "not", "children": [
        {"operator": "is", "left": {"kind": "current_user"}, "right": {"kind": "static", "value": "1"}}]}
    assert E.evaluate_criteria([g_not], ctx, {})["ok"] is False


def test_criteria_trace_for_test_run():
    ctx = _ctx(user_id=7)
    criteria = [{"operator": "is", "failure_message": "x",
                 "left": {"kind": "current_user"}, "right": {"kind": "static", "value": "7"}}]
    r = E.evaluate_criteria(criteria, ctx, {}, with_trace=True)
    assert r["trace"][0]["ok"] is True
    assert r["trace"][0]["nodes"][0]["operator"] == "is"


def test_no_criteria_means_pass():
    assert E.evaluate_criteria(None, _ctx(), {})["ok"] is True
    assert E.evaluate_criteria([], _ctx(), {})["ok"] is True


def test_execution_context_scenario():
    # 我们没有场景，is_scenario 恒为 false；条件应如实不通过
    ctx = _ctx(is_scenario=False)
    c = {"operator": "is", "failure_message": "仅场景内可用",
         "left": {"kind": "execution_context", "value": "is_scenario"},
         "right": {"kind": "static", "value": True}}
    assert E.evaluate_criteria([c], ctx, {})["ok"] is False
    ctx2 = _ctx(is_scenario=True)
    assert E.evaluate_criteria([c], ctx2, {})["ok"] is True


# ---------------------------------------------------------------------------
# 规则
# ---------------------------------------------------------------------------
def test_plan_rules_sources():
    ctx = _ctx(user_id=7, user_name="张三")
    params = {"new_name": "东门-1号"}
    rules = [
        {"type": "modify_object", "assignments": [
            {"property": "name", "source": "parameter", "value": "new_name"},
            {"property": "updated_by", "source": "current_user"},
            {"property": "updated_at", "source": "current_time"},
            {"property": "kind", "source": "static", "value": "camera"},
        ]},
    ]
    r = E.plan_rules(rules, ctx, params)
    assert r["errors"] == []
    a = r["edits"][0]["assignments"]
    assert a["name"] == "东门-1号"
    assert a["updated_by"] == "张三"
    assert a["kind"] == "camera"
    assert a["updated_at"]


def test_plan_rules_warns_on_missing_param():
    r = E.plan_rules([{"type": "modify_object",
                       "assignments": [{"property": "name", "source": "parameter",
                                        "value": "not_provided"}]}], _ctx(), {})
    assert r["errors"] == []
    assert r["edits"][0]["assignments"] == {}
    assert any("not_provided" in w for w in r["warnings"])


def test_plan_rules_object_parameter_property():
    rules = [{"type": "modify_object", "assignments": [
        {"property": "status", "source": "object_parameter_property",
         "parameter": "aircraft", "object_property": "status"}]}]
    r = E.plan_rules(rules, _ctx(), {"aircraft": "A1"}, lambda p, prop: "operational")
    assert r["edits"][0]["assignments"]["status"] == "operational"


def test_plan_rules_rejects_unknown_type():
    r = E.plan_rules([{"type": "teleport_object"}], _ctx(), {})
    assert r["errors"] and "teleport_object" in r["errors"][0]


def test_validate_rules_official_limit_create_twice():
    errs = E.validate_rules([{"type": "create_object"}, {"type": "create_object"}], set())
    assert any("创建两次" in e for e in errs)


def test_validate_rules_undefined_parameter():
    errs = E.validate_rules(
        [{"type": "modify_object", "assignments": [
            {"property": "n", "source": "parameter", "value": "ghost"}]}], {"real"})
    assert any("ghost" in e for e in errs)


# ---------------------------------------------------------------------------
# 副作用
# ---------------------------------------------------------------------------
def test_plan_side_effects_notification_and_webhook():
    ctx = _ctx(user_id=7, user_name="张三")
    params = {"new_name": "东门-1号"}
    p = E.plan_side_effects([
        {"type": "notification", "title": "改名 {{new_name}}", "content": "由 {{当前用户}} 执行",
         "recipients": [1, 2]},
        {"type": "webhook", "url": "https://example.com/hook", "method": "post",
         "body": {"name": "{{new_name}}"}, "timing": "before", "blocking": True},
    ], ctx, params)
    assert p["errors"] == []
    n = p["effects"][0]
    assert n["title"] == "改名 东门-1号"
    assert n["content"] == "由 张三 执行"
    assert n["recipients"] == [1, 2]
    w = p["effects"][1]
    assert w["method"] == "POST" and w["timing"] == "before" and w["blocking"] is True
    assert w["body"] == {"name": "东门-1号"}


def test_plan_side_effects_validates_url_and_method():
    p = E.plan_side_effects([{"type": "webhook", "url": "ftp://x"}], _ctx(), {})
    assert p["errors"] and "http" in p["errors"][0]
    p2 = E.plan_side_effects([{"type": "webhook", "url": "https://a.com", "method": "DELETE"}], _ctx(), {})
    assert p2["errors"] and "DELETE" in p2["errors"][0]


def test_validate_side_effects_requires_recipients():
    errs = E.validate_side_effects([{"type": "notification", "title": "x"}])
    assert any("收件人" in e for e in errs)


# ---------------------------------------------------------------------------
# 编辑期校验
# ---------------------------------------------------------------------------
def test_validate_criteria_catches_bad_config():
    errs = E.validate_criteria(
        [{"operator": "equals", "left": {"kind": "parameter", "value": "ghost"},
          "right": {"kind": "static", "value": 1}}], {"real"})
    joined = "；".join(errs)
    assert "运算符不支持" in joined
    assert "ghost" in joined


def test_validate_criteria_nested_group():
    errs = E.validate_criteria([{"operator": "and", "children": [
        {"operator": "is", "left": {"kind": "current_user"}, "right": {"kind": "static", "value": "1"}}]}], set())
    assert errs == []
    errs2 = E.validate_criteria([{"operator": "and", "children": []}], set())
    assert any("没有子条件" in e for e in errs2)


def test_interp_templates():
    ctx = _ctx(user_id=7, user_name="张三")
    s = E._interp("{{a}}/{{当前用户}}/{{b}}", {"a": "1", "b": "2"}, ctx)
    assert s == "1/张三/2"
    # 未提供的参数替换成空串
    assert E._interp("x{{missing}}y", {}, ctx) == "xy"
