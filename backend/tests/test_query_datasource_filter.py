"""数据源 filter_rules 配置字段（model/schema/service + 默认规则落库）。

覆盖点：
1. 新建数据源（不传 filter_rules）→ 取回应为 DEFAULT_FILTER_RULES。
2. 新建数据源（传自定义 filter_rules）→ 取回应为自定义值，不被默认覆盖。
"""
import uuid

from app.plugin.module_ai.query.filtering import DEFAULT_FILTER_RULES


def _save_ds(test_client, auth_headers, code, **overrides):
    payload = {
        "name": f"测试筛选规则{code}",
        "code": code,
        "type": "postgres",
    }
    payload.update(overrides)
    r = test_client.post(
        "/api/v1/ai/query/datasources/save", json=payload, headers=auth_headers
    )
    assert r.status_code == 200, r.text
    return r.json()["data"]


def _find_ds(test_client, auth_headers, code):
    lst = test_client.get(
        "/api/v1/ai/query/datasources/list", headers=auth_headers
    ).json()["data"]
    for d in lst:
        if d["code"] == code:
            return d
    raise AssertionError(f"列表未找到数据源 {code}")


def test_new_datasource_without_filter_rules_defaults(test_client, auth_headers):
    """不传 filter_rules 时，取回应等于默认规则。"""
    code = f"ds_test_filter_{uuid.uuid4().hex[:8]}"
    _save_ds(test_client, auth_headers, code)
    ds = _find_ds(test_client, auth_headers, code)
    assert ds["filter_rules"] == DEFAULT_FILTER_RULES, (
        f"未传 filter_rules 应落默认规则，实际: {ds.get('filter_rules')}"
    )


def test_datasource_with_custom_filter_rules_preserved(test_client, auth_headers):
    """传自定义 filter_rules 时，取回应为自定义值（不被默认覆盖）。"""
    code = f"ds_test_filter_custom_{uuid.uuid4().hex[:8]}"
    custom = {
        "enabled": False,
        "system_table": {"prefixes": ["X_"], "keywords": [], "exact": [], "regex": ""},
        "audit_fields": ["custom_audit"],
    }
    _save_ds(test_client, auth_headers, code, filter_rules=custom)
    ds = _find_ds(test_client, auth_headers, code)
    assert ds["filter_rules"] == custom, (
        f"自定义 filter_rules 不应被默认覆盖，实际: {ds.get('filter_rules')}"
    )


def test_update_without_filter_rules_preserves_existing(test_client, auth_headers):
    """同 code 再次保存但不传 filter_rules 时，应保留已保存的自定义配置（不被默认覆盖）。"""
    code = f"ds_test_filter_update_{uuid.uuid4().hex[:8]}"
    custom = {"enabled": False}
    _save_ds(test_client, auth_headers, code, filter_rules=custom)
    # 第二次保存同一 code，不传 filter_rules
    _save_ds(test_client, auth_headers, code)
    ds = _find_ds(test_client, auth_headers, code)
    assert ds["filter_rules"] == custom, (
        f"更新时不传 filter_rules 应保留既有配置，实际: {ds.get('filter_rules')}"
    )
