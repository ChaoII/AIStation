"""Task 12：策略管理接口与权限解释接口（``/ai/query/policy/*``、``/ai/query/access/*``）。

两类用例：

- **注册与权限**（需要应用）：OpenAPI 里有 5 条新路径；4 个权限码进了
  ``AI_BUTTON_PERMS``，否则页面上按钮永远 403；
- **接口行为**（需要应用 + 数据库）：保存时真的拦截坏策略（不入库）、
  合法策略 CRUD 闭环、explain 用**库里的身份**构造主体（超管绕过 / 默认拒绝 /
  缺属性），且返回固定六个字段。
"""
from __future__ import annotations

import pytest

BASE = "/api/v1/ai/query"

#: OpenAPI 的 ``paths`` **不含** ``ROOT_PATH``（``/api/v1`` 是 mount 前缀），
#: 运行期请求才带；两种写法各自用于不同断言，别混。
POLICY_PATHS = (
    "/ai/query/policy/list",
    "/ai/query/policy/save",
    "/ai/query/policy/delete",
    "/ai/query/access/explain",
    "/ai/query/access/logs",
)


def _payload(**over) -> dict:
    """一条最小可用策略；各用例只覆盖自己关心的字段。"""
    data = {
        "name": "pytest-policy",
        "description": "",
        "enabled": True,
        "priority": 100,
        "resource_kind": "table",
        "resource_code": "pytest_policy_table",
        "effect": "allow",
        "subject_kind": "everyone",
        "subject_value": "",
        "condition": "",
        "columns": [],
        "mask_expr": "",
        "marking": "",
    }
    data.update(over)
    return data


def _save(test_client, auth_headers, **over):
    return test_client.post(
        f"{BASE}/policy/save", json=_payload(**over), headers=auth_headers
    )


def _list(test_client, auth_headers, **params):
    r = test_client.get(f"{BASE}/policy/list", params=params, headers=auth_headers)
    assert r.status_code == 200, r.text
    return r.json()["data"]


# ---------------------------------------------------------------------------
# 路由与权限注册
# ---------------------------------------------------------------------------
def test_policy_routes_registered(test_client):
    import conftest

    assert conftest.app is not None
    paths = conftest.app.openapi()["paths"]
    missing = [p for p in POLICY_PATHS if p not in paths]
    assert not missing, f"这些策略/解释接口没有注册：{missing}"


def test_policy_permissions_registered():
    """权限码必须进 ``AI_BUTTON_PERMS``：只在接口里写 Depends 不够，
    存量库重启要靠 ``_ensure_ai_menus`` 幂等补齐菜单行，否则非超管一律 403。"""
    from app.scripts.init_app import AI_BUTTON_PERMS

    codes = {code for code, _ in AI_BUTTON_PERMS}
    for action in ("query", "create", "update", "delete"):
        code = f"module_ai:query:policy:{action}"
        assert code in codes, f"{code} 未注册（非超管将无法访问策略管理）"


# ---------------------------------------------------------------------------
# 保存校验：坏策略一律 400 且不入库
# ---------------------------------------------------------------------------
BAD_POLICIES = [
    ("effect 非枚举", {"effect": "grant"}),
    ("resource_kind 非枚举", {"resource_kind": "object"}),
    ("subject_kind 非枚举", {"subject_kind": "group"}),
    ("mask 缺表达式", {"effect": "mask", "columns": ["phone"]}),
    ("allow 不该有 mask_expr", {"effect": "allow", "mask_expr": "upper(name)"}),
    ("deny 不该有 mask_expr", {"effect": "deny", "mask_expr": "upper(name)"}),
    ("condition 带分号", {"condition": "dept_id = 1; drop table t"}),
    ("deny 不支持行条件", {"effect": "deny", "condition": "dept_id = 1"}),
    ("mask 不支持行条件", {"effect": "mask", "mask_expr": "upper(name)", "condition": "dept_id = 1"}),
    ("condition 带注释", {"condition": "dept_id = 1 -- 注释"}),
    ("condition 带子查询", {"condition": "id in (select id from t)"}),
    ("condition 带未知参数", {"condition": "id = $role.x"}),
    ("condition 语法坏掉", {"condition": "dept_id = ("}),
    ("mask_expr 语法坏掉", {"effect": "mask", "columns": ["phone"], "mask_expr": "((("}),
    ("role 主体没有值", {"subject_kind": "role", "subject_value": ""}),
    ("user 主体没有值", {"subject_kind": "user", "subject_value": ""}),
    ("attr 主体没有值", {"subject_kind": "attr", "subject_value": ""}),
    ("domain 主体没有值", {"subject_kind": "domain", "subject_value": ""}),
]


@pytest.mark.parametrize("label,over", BAD_POLICIES, ids=[x[0] for x in BAD_POLICIES])
def test_save_rejects_bad_policy(test_client, auth_headers, label, over):
    name = f"pytest-bad-{abs(hash(label)) % 10000}"
    r = _save(test_client, auth_headers, name=name, **over)
    assert r.status_code == 400, f"{label} 本该被拒绝：{r.status_code} {r.text}"
    body = r.json()
    assert body["success"] is False
    assert body["msg"], "拒绝必须带原因"

    # 真的没进库（不是"返回 400 但已经写进去了"）
    rows = _list(test_client, auth_headers, resource_code="pytest_policy_table")
    assert not [row for row in rows if row["name"] == name], f"{label} 的坏策略被写进了库"


def test_save_accepts_condition_with_attr_placeholders(test_client, auth_headers):
    """``$attr.*`` / ``$user.id`` 是合法写法：保存时按"占位符可绑定"校验，
    不能因为"运行期才知道具体值"就把正确的策略拒掉。"""
    r = _save(
        test_client,
        auth_headers,
        name="pytest-policy-attr-ok",
        resource_code="pytest_policy_attr",
        condition="dept_id = $attr.dept_id AND owner_id = $user.id",
        columns=["dept_id", "owner_id"],
    )
    assert r.status_code == 200, r.text
    pid = r.json()["data"]["id"]
    try:
        row = next(
            x for x in _list(test_client, auth_headers, resource_code="pytest_policy_attr")
            if x["id"] == pid
        )
        assert "$attr.dept_id" in row["condition"]
        assert row["columns"] == ["dept_id", "owner_id"]
    finally:
        test_client.post(
            f"{BASE}/policy/delete", json={"ids": [pid]}, headers=auth_headers
        )


# ---------------------------------------------------------------------------
# 合法策略 CRUD 闭环
# ---------------------------------------------------------------------------
def test_save_list_filter_update_delete(test_client, auth_headers):
    r = _save(
        test_client,
        auth_headers,
        name="pytest-policy-crud",
        resource_code="pytest_policy_crud",
        condition="dept_id = 1",
        columns=["dept_id", "id"],
        priority=7,
    )
    assert r.status_code == 200, r.text
    pid = r.json()["data"]["id"]

    try:
        rows = _list(
            test_client, auth_headers, resource_kind="table", resource_code="pytest_policy_crud"
        )
        assert [row["id"] for row in rows] == [pid]
        row = rows[0]
        assert row["effect"] == "allow"
        assert row["subject_kind"] == "everyone"
        assert row["enabled"] is True
        assert row["priority"] == 7
        assert row["columns"] == ["dept_id", "id"]

        # 过滤器真的生效（不同 resource_code 查不到）
        assert _list(test_client, auth_headers, resource_code="pytest_policy_other") == []

        # 更新（带 id）：改 enabled / priority / 条件
        upd = _save(
            test_client,
            auth_headers,
            id=pid,
            name="pytest-policy-crud",
            resource_code="pytest_policy_crud",
            enabled=False,
            priority=3,
            condition="dept_id = 2",
        )
        assert upd.status_code == 200, upd.text
        row = next(
            x for x in _list(test_client, auth_headers, resource_code="pytest_policy_crud")
            if x["id"] == pid
        )
        assert row["enabled"] is False
        assert row["priority"] == 3
        assert row["condition"] == "dept_id = 2"
    finally:
        d = test_client.post(
            f"{BASE}/policy/delete", json={"ids": [pid]}, headers=auth_headers
        )
        assert d.status_code == 200, d.text

    # 软删后管理列表看不到
    assert not [
        x for x in _list(test_client, auth_headers, resource_code="pytest_policy_crud")
        if x["id"] == pid
    ]


def test_delete_unknown_id_is_idempotent(test_client, auth_headers):
    """删一个不存在的 id 不该 500（前端批量删/重复点很常见）。"""
    r = test_client.post(
        f"{BASE}/policy/delete", json={"ids": [99999999]}, headers=auth_headers
    )
    assert r.status_code == 200, r.text
    assert r.json()["data"]["deleted"] == 0


def test_update_unknown_id_rejected(test_client, auth_headers):
    r = _save(test_client, auth_headers, id=99999999, name="pytest-ghost")
    assert r.status_code == 400, r.text


# ---------------------------------------------------------------------------
# explain：用库里的身份，不信任入参
# ---------------------------------------------------------------------------
@pytest.fixture(scope="module")
def plain_user_id(test_client, db_run):
    """造一个**非超管、无角色**的用户：explain 必须按默认拒绝回答。"""

    def _run(sql: str, params: dict):
        from sqlalchemy import text

        from app.core.database import async_db_session

        async def _do():
            async with async_db_session.begin() as db:
                result = await db.execute(text(sql), params)
                return result.scalar() if result.returns_rows else None

        return db_run(_do())

    from datetime import datetime

    from app.utils.common_util import uuid4_str

    uid = _run(
        "INSERT INTO sys_user (tenant_id, username, password, name, is_superuser, "
        "status, uuid, created_time, updated_time, is_deleted) "
        "VALUES (1, :u, 'x', :n, false, '0', :uuid, :now, :now, false) "
        "RETURNING id",
        {
            "u": f"pytest-policy-{uuid4_str()[:8]}",
            "n": "策略解释测试用户",
            "uuid": uuid4_str(),
            "now": datetime.now().replace(microsecond=0),
        },
    )
    yield int(uid)
    _run("DELETE FROM sys_user WHERE id=:u", {"u": uid})


def test_explain_default_deny_for_plain_user(test_client, auth_headers, plain_user_id):
    r = test_client.get(
        f"{BASE}/access/explain",
        params={"user_id": plain_user_id, "table": "pytest_explain_none"},
        headers=auth_headers,
    )
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert set(data) == {"permit", "reason", "policy_ids", "matched", "attrs_missing", "superuser"}
    assert data["permit"] is False
    assert data["superuser"] is False
    assert "默认拒绝" in data["reason"]
    assert data["policy_ids"] == [] and data["matched"] == []


def test_explain_superuser_bypass_comes_from_db(test_client, auth_headers):
    """``is_superuser`` 只能来自库（入参没有这个字段），reason 必须是原文
    ``superuser bypass``（治理页面/审计文案直接展示）。"""
    r = test_client.get(
        f"{BASE}/access/explain",
        params={"user_id": 1, "table": "pytest_explain_none"},
        headers=auth_headers,
    )
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert data["permit"] is True
    assert data["superuser"] is True
    assert data["reason"] == "superuser bypass"


def test_explain_reports_deny_policy_and_missing_attr(
    test_client, auth_headers, plain_user_id
):
    deny = _save(
        test_client,
        auth_headers,
        name="pytest-policy-explain-deny",
        resource_code="pytest_explain_deny",
        effect="deny",
        subject_kind="everyone",
    )
    attr = _save(
        test_client,
        auth_headers,
        name="pytest-policy-explain-attr",
        resource_code="pytest_explain_attr",
        effect="allow",
        subject_kind="everyone",
        # 该用户 dept_id 为空 → 缺属性 → allow 不适用 → 拒绝
        condition="dept_id = $attr.dept_id",
        columns=["dept_id"],
    )
    ids = [deny.json()["data"]["id"], attr.json()["data"]["id"]]
    try:
        d = test_client.get(
            f"{BASE}/access/explain",
            params={"user_id": plain_user_id, "table": "pytest_explain_deny"},
            headers=auth_headers,
        ).json()["data"]
        assert d["permit"] is False
        assert ids[0] in d["policy_ids"]
        assert any(m["id"] == ids[0] and m["effect"] == "deny" for m in d["matched"])

        a = test_client.get(
            f"{BASE}/access/explain",
            params={
                "user_id": plain_user_id,
                "table": "pytest_explain_attr",
                "column": "dept_id",
            },
            headers=auth_headers,
        ).json()["data"]
        assert a["permit"] is False
        assert "dept_id" in a["attrs_missing"]
        assert ids[1] in a["policy_ids"]
    finally:
        test_client.post(
            f"{BASE}/policy/delete", json={"ids": ids}, headers=auth_headers
        )


def test_explain_unknown_user_is_denied(test_client, auth_headers):
    """库里没有这个人 → 不伪造主体，直接拒绝（fail-closed）。"""
    r = test_client.get(
        f"{BASE}/access/explain",
        params={"user_id": 99999999, "table": "anything"},
        headers=auth_headers,
    )
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert data["permit"] is False
    assert data["matched"] == []
    assert "主体" in data["reason"]


# ---------------------------------------------------------------------------
# 审计回溯
# ---------------------------------------------------------------------------
def test_access_logs_returns_recent_rows(test_client, auth_headers):
    r = test_client.get(f"{BASE}/access/logs", params={"limit": 5}, headers=auth_headers)
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert isinstance(data, list)
    assert len(data) <= 5
