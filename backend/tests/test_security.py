"""对象权限的纯函数单测：策略表达式求值 + 主体 + 可见列计算。

对照官方 object-permissioning：
· 单元格级安全 = 行级（对象安全策略）+ 列级（属性安全策略）
· 行策略里可用用户属性，如 ``user.userAttribute('care_center') == care_center``
"""
import pytest

from app.plugin.module_ai.ontology import security as S


def _p(**kw):
    base = {"user_id": 7, "username": "zhang", "name": "张三", "is_superuser": False,
            "role_codes": ["ANALYST"], "role_ids": [3], "dept_id": 12, "dept_code": "华东"}
    base.update(kw)
    return S.Principal(**base)


# ---------------------------------------------------------------------------
# 主体
# ---------------------------------------------------------------------------
def test_principal_has_role_accepts_code_or_id():
    p = _p()
    assert p.has_role("ANALYST") is True
    assert p.has_role("3") is True          # 角色 ID 也算
    assert p.has_role("ADMIN") is False
    assert p.has_role("ADMIN", "ANALYST") is True   # 命中其一即可
    assert p.has_role() is False


def test_principal_attribute_lookup():
    p = _p(attributes={"region": "east", "level": 2})
    assert p.attr("id") == 7
    assert p.attr("name") == "张三"
    assert p.attr("dept") == 12
    assert p.attr("dept_id") == 12
    assert p.attr("dept_code") == "华东"
    assert p.attr("superuser") is False
    assert p.attr("roles") == ["ANALYST"]
    assert p.attr("region") == "east"
    assert p.attr("nope") is None


def test_anonymous_principal_has_nothing():
    assert S.ANONYMOUS.anonymous is True
    assert S.ANONYMOUS.has_role("ADMIN") is False
    assert S.ANONYMOUS.attr("dept") is None


# ---------------------------------------------------------------------------
# 策略表达式：变量提取
# ---------------------------------------------------------------------------
def test_policy_vars_excludes_user_and_builtins():
    assert S.policy_vars("dept_id == user.attribute('dept')") == ["dept_id"]
    assert S.policy_vars("region == user.attribute('region') and len(name) > 0") == ["name", "region"]
    assert S.policy_vars("user.role('ADMIN')") == []
    assert S.policy_vars("((bad") == []


# ---------------------------------------------------------------------------
# 策略表达式：求值
# ---------------------------------------------------------------------------
def test_eval_simple_equality():
    p = _p(dept_id=12)
    assert S.eval_policy("dept_id == user.attribute('dept')", {"dept_id": 12}, p) is True
    assert S.eval_policy("dept_id == user.attribute('dept')", {"dept_id": 99}, p) is False


def test_eval_role_check():
    p = _p(role_codes=["ADMIN"])
    assert S.eval_policy("user.role('ADMIN')", {}, p) is True
    assert S.eval_policy("user.role('NOPE')", {}, p) is False


def test_eval_boolean_and_comparison():
    p = _p(dept_id=3)
    props = {"dept_id": 3, "level": 5, "owner": "张三"}
    assert S.eval_policy("dept_id == user.attribute('dept') and level >= 3", props, p) is True
    assert S.eval_policy("level > 10 or owner == user.name", props, p) is True
    assert S.eval_policy("not (level > 10)", props, p) is True
    assert S.eval_policy("level != 5", props, p) is False


def test_eval_in_operator():
    p = _p(attributes={"regions": ["east", "north"]})
    assert S.eval_policy("region in user.attribute('regions')", {"region": "east"}, p) is True
    assert S.eval_policy("region in user.attribute('regions')", {"region": "west"}, p) is False
    assert S.eval_policy("region not in user.attribute('regions')", {"region": "west"}, p) is True


def test_eval_in_with_none_rhs_is_false_not_crash():
    """用户没有该属性时 ``in`` 右边是 None —— 必须判 False 而不是抛异常。"""
    p = _p(attributes={})
    assert S.eval_policy("region in user.attribute('regions')", {"region": "east"}, p) is False


def test_eval_missing_property_is_none_not_error():
    """对象没这一列时按 None 处理，避免一条策略让整表不可见。"""
    p = _p()
    assert S.eval_policy("ghost == 1", {}, p) is False
    assert S.eval_policy("ghost is None" if False else "not (ghost == 1)", {}, p) is True


def test_eval_builtins():
    p = _p()
    assert S.eval_policy("len(name) > 2", {"name": "abc"}, p) is True
    assert S.eval_policy("lower(name) == 'abc'", {"name": "ABC"}, p) is True
    assert S.eval_policy("contains(name, 'cam')", {"name": "my_cam"}, p) is True
    assert S.eval_policy("any([a, b])", {"a": False, "b": True}, p) is True


def test_eval_rejects_dangerous_access():
    p = _p()
    # 只允许 user 命名空间上的属性
    with pytest.raises(S.PolicyError):
        S.eval_policy("user.password == 'x'", {}, p)
    with pytest.raises(S.PolicyError):
        S.eval_policy("__import__('os')", {}, p)
    with pytest.raises(S.PolicyError):
        S.eval_policy("a.b", {"a": {"b": 1}}, p)
    with pytest.raises(S.PolicyError):
        S.eval_policy("user.__class__", {}, p)
    with pytest.raises(S.PolicyError):
        S.eval_policy("user.eval('1')", {}, p)


def test_eval_syntax_error_message():
    p = _p()
    with pytest.raises(S.PolicyError) as e:
        S.eval_policy("((bad", {}, p)
    assert "语法" in str(e.value)


# ---------------------------------------------------------------------------
# 列级掩码
# ---------------------------------------------------------------------------
def test_mask_props_removes_hidden_columns():
    props = {"name": "c1", "password": "x", "brand": "H"}
    assert S.mask_props(props, {"name", "brand"}) == {"name": "c1", "brand": "H"}
    assert S.mask_props(props, set()) == {}
    assert S.mask_props({}, {"name"}) == {}


def test_role_match_semantics():
    p = _p()
    # 空列表 = 不限制
    assert S._role_match([], p) is True
    assert S._role_match(["ANALYST"], p) is True
    assert S._role_match(["ADMIN"], p) is False
    # 超管总是通过
    assert S._role_match(["ADMIN"], _p(is_superuser=True)) is True


# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------
def test_labels_cover_all_enum_values():
    for k in S.ONT_RESOURCE_KINDS:
        assert k in S.ONT_RESOURCE_LABEL, k
    for e in S.ONT_POLICY_EFFECTS:
        assert e in ("allow", "deny")


def test_policy_user_namespace_is_closed():
    p = _p()
    u = S._PolicyUser(p)
    assert u.id == 7
    assert u.dept == 12
    assert u.superuser is False
    assert u.role("ANALYST") is True
    assert u.attribute("dept_code") == "华东"
    # 白名单之外不可达
    assert "password" not in S._USER_ATTRS
    assert "eval" not in S._USER_ATTRS
