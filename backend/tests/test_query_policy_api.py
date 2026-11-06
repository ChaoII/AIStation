"""Task 12：策略管理接口与权限解释接口（``/ai/query/policy/*``、``/ai/query/access/*``）。

两类用例：

- **注册与权限**（需要应用）：OpenAPI 里有 5 条新路径；4 个权限码进了
  ``AI_BUTTON_PERMS``，否则页面上按钮永远 403；
- **接口行为**（需要应用 + 数据库）：保存时真的拦截坏策略（不入库）、
  合法策略 CRUD 闭环、explain 用**库里的身份**构造主体（超管绕过 / 默认拒绝 /
  缺属性），且返回固定六个字段。
"""
from __future__ import annotations

import asyncio

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
    ("mask 不支持行条件", {"effect": "mask", "columns": ["name"], "mask_expr": "upper(name)", "condition": "dept_id = 1"}),
    ("mask 缺 columns", {"effect": "mask", "mask_expr": "upper(name)"}),
    ("attr 主体带空格等号", {"subject_kind": "attr", "subject_value": "dept_id = 3"}),
    ("user 主体不是数字", {"subject_kind": "user", "subject_value": "admin"}),
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


def test_save_rejects_row_condition_until_compiler_wired(test_client, auth_headers):
    """C2：编译器未接线前，保存带 ``condition`` 的策略一律 400 且不入库。

    历史缺陷：策略 API 收下 condition、explain 显示 permit，但执行路径用的是**原 SQL**
    —— 管理员以为行过滤生效，实际明文全行。宁可显式拒绝，也不能"看起来配了"。
    """
    name = "pytest-policy-attr-blocked"
    r = _save(
        test_client,
        auth_headers,
        name=name,
        resource_code="pytest_policy_attr",
        condition="dept_id = $attr.dept_id AND owner_id = $user.id",
        columns=["dept_id", "owner_id"],
    )
    assert r.status_code == 400, r.text
    msg = r.json()["msg"]
    assert "编译器" in msg, f"拒绝文案要说明原因（编译器未接线）：{msg}"

    rows = _list(test_client, auth_headers, resource_code="pytest_policy_attr")
    assert not [row for row in rows if row["name"] == name], "被拒的策略不得入库"


# ---------------------------------------------------------------------------
# 合法策略 CRUD 闭环
# ---------------------------------------------------------------------------
def test_save_list_filter_update_delete(test_client, auth_headers):
    r = _save(
        test_client,
        auth_headers,
        name="pytest-policy-crud",
        resource_code="pytest_policy_crud",
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

        # 更新（带 id）：改 enabled / priority
        upd = _save(
            test_client,
            auth_headers,
            id=pid,
            name="pytest-policy-crud",
            resource_code="pytest_policy_crud",
            enabled=False,
            priority=3,
        )
        assert upd.status_code == 200, upd.text
        row = next(
            x for x in _list(test_client, auth_headers, resource_code="pytest_policy_crud")
            if x["id"] == pid
        )
        assert row["enabled"] is False
        assert row["priority"] == 3
        assert row["condition"] == "", "未提供 condition 时不该凭空写入行条件"
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


def test_partial_update_keeps_unchanged_fields(test_client, auth_headers):
    """Important 1：更新**只写请求里实际传的字段**。

    历史缺陷：``PolicyUpsert`` 给 ``effect="allow"`` / ``subject_kind="everyone"`` /
    ``marking=""`` 默认值，而 UPDATE 写所有列 —— 只传 ``{id,name,resource_code}`` 就会
    把 deny 变 allow、把 role:analyst 变 everyone、顺手清掉 marking（等于关掉星号止血）。
    """
    created = _save(
        test_client,
        auth_headers,
        name="pytest-policy-partial",
        resource_code="pytest_policy_partial",
        effect="deny",
        subject_kind="role",
        subject_value="analyst",
        marking="sensitive",
        priority=42,
    )
    assert created.status_code == 200, created.text
    pid = created.json()["data"]["id"]
    try:
        # 只传 3 个字段（id / name / resource_code）
        upd = test_client.post(
            f"{BASE}/policy/save",
            json={
                "id": pid,
                "name": "pytest-policy-partial-renamed",
                "resource_code": "pytest_policy_partial",
            },
            headers=auth_headers,
        )
        assert upd.status_code == 200, upd.text

        row = next(
            x
            for x in _list(test_client, auth_headers, resource_code="pytest_policy_partial")
            if x["id"] == pid
        )
        assert row["name"] == "pytest-policy-partial-renamed"
        # 没传的字段一个都不能被"默认值"覆盖
        assert row["effect"] == "deny"
        assert row["subject_kind"] == "role"
        assert row["subject_value"] == "analyst"
        assert row["marking"] == "sensitive"
        assert row["enabled"] is True
        assert row["priority"] == 42
    finally:
        test_client.post(f"{BASE}/policy/delete", json={"ids": [pid]}, headers=auth_headers)


def test_save_rejects_mask_until_compiler_wired(test_client, auth_headers):
    """C2：编译器未接线前，保存带 ``mask_expr`` 的策略一律 400（列脱敏不生效）。"""
    name = "pytest-policy-mask-blocked"
    r = _save(
        test_client,
        auth_headers,
        name=name,
        resource_code="pytest_policy_mask_keep",
        effect="mask",
        columns=["phone"],
        mask_expr="upper(phone)",
    )
    assert r.status_code == 400, r.text
    msg = r.json()["msg"]
    assert "编译器" in msg, f"拒绝文案要说明原因（编译器未接线）：{msg}"

    rows = _list(test_client, auth_headers, resource_code="pytest_policy_mask_keep")
    assert not [row for row in rows if row["name"] == name], "被拒的 mask 策略不得入库"


def test_update_validates_merged_state(test_client, auth_headers):
    """部分更新也必须按「库里现值 + 本次改动」合并后校验。

    只传 ``effect="mask"`` 而库里没有 ``mask_expr`` → 400，且库里那条 allow 不受影响
    （不能"先写一半再报错"）。
    """
    created = _save(
        test_client,
        auth_headers,
        name="pytest-policy-merged",
        resource_code="pytest_policy_merged",
        effect="allow",
        columns=["id"],
    )
    assert created.status_code == 200, created.text
    pid = created.json()["data"]["id"]
    try:
        upd = test_client.post(
            f"{BASE}/policy/save",
            json={"id": pid, "effect": "mask"},
            headers=auth_headers,
        )
        assert upd.status_code == 400, upd.text
        assert "mask_expr" in upd.json()["msg"]

        row = next(
            x
            for x in _list(test_client, auth_headers, resource_code="pytest_policy_merged")
            if x["id"] == pid
        )
        assert row["effect"] == "allow"
    finally:
        test_client.post(f"{BASE}/policy/delete", json={"ids": [pid]}, headers=auth_headers)


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
def db_exec(test_client, db_run):
    """在**应用事件循环**里执行一条 SQL（造停用用户/角色、改状态）。"""

    def _run(sql: str, params: dict | None = None):
        from sqlalchemy import text

        from app.core.database import async_db_session

        async def _do():
            async with async_db_session.begin() as db:
                result = await db.execute(text(sql), params or {})
                return result.scalar() if result.returns_rows else None

        return db_run(_do())

    return _run


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
    assert set(data) == {
        "permit", "reason", "policy_ids", "matched", "attrs_missing", "superuser",
        "applied",
    }
    assert data["permit"] is False
    assert data["superuser"] is False
    assert "默认拒绝" in data["reason"]
    assert data["policy_ids"] == [] and data["matched"] == []
    # C2：enforce 未接线编译器，explain 明确告诉治理页「实际施加的改写」为空
    assert data["applied"] == []


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
    test_client, auth_headers, plain_user_id, db_exec
):
    deny = _save(
        test_client,
        auth_headers,
        name="pytest-policy-explain-deny",
        resource_code="pytest_explain_deny",
        effect="deny",
        subject_kind="everyone",
    )
    # 行/列策略暂时**不能经 API 保存**（C2 硬闸）—— 但存量库里可能已有这类行，
    # explain 必须照样解释它们，所以这里直接写库（模拟迁移/历史数据）。
    from datetime import datetime

    now = datetime.now().replace(microsecond=0)
    attr_id = int(
        db_exec(
            "INSERT INTO ai_policy (name, description, enabled, priority, resource_kind, "
            "resource_code, effect, subject_kind, subject_value, condition, columns, "
            "mask_expr, marking, created_time, updated_time, is_deleted) "
            "VALUES (:n, '', true, 100, 'table', :c, 'allow', 'everyone', '', :cond, "
            ":cols, '', '', :now, :now, false) RETURNING id",
            {
                "n": "pytest-policy-explain-attr",
                "c": "pytest_explain_attr",
                # 该用户 dept_id 为空 → 缺属性 → allow 不适用 → 拒绝
                "cond": "dept_id = $attr.dept_id",
                "cols": '["dept_id"]',
                "now": now,
            },
        )
    )
    ids = [deny.json()["data"]["id"], attr_id]
    try:
        d = test_client.get(
            f"{BASE}/access/explain",
            params={"user_id": plain_user_id, "table": "pytest_explain_deny"},
            headers=auth_headers,
        ).json()["data"]
        assert d["permit"] is False
        assert ids[0] in d["policy_ids"]
        assert any(m["id"] == ids[0] and m["effect"] == "deny" for m in d["matched"])
        assert d["applied"] == []

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
        assert a["applied"] == [], "编译器未接线时不得声称已施加列/行改写"
    finally:
        test_client.post(
            f"{BASE}/policy/delete", json={"ids": ids}, headers=auth_headers
        )


def test_explain_disabled_user_is_denied(test_client, auth_headers, db_exec):
    """Important 2：停用账号即便有 allow 策略也必须 deny，且 reason 写明原因。

    真实链路里停用用户连登录都过不去（``get_current_user`` 抛 401）；解释接口如果
    还给 permit，治理页就会告诉管理员"这个人还能看"，与线上行为相反。
    """
    from datetime import datetime

    from app.utils.common_util import uuid4_str

    now = datetime.now().replace(microsecond=0)
    uid = int(
        db_exec(
            "INSERT INTO sys_user (tenant_id, username, password, name, is_superuser, "
            "status, uuid, created_time, updated_time, is_deleted) "
            "VALUES (1, :u, 'x', :n, false, '1', :uuid, :now, :now, false) "
            "RETURNING id",
            {
                "u": f"pytest-disabled-{uuid4_str()[:8]}",
                "n": "停用用户（策略解释）",
                "uuid": uuid4_str(),
                "now": now,
            },
        )
    )
    saved = _save(
        test_client,
        auth_headers,
        name="pytest-policy-disabled-user",
        resource_code="pytest_explain_disabled_user",
        effect="allow",
        subject_kind="everyone",
    )
    pid = saved.json()["data"]["id"]
    try:
        data = test_client.get(
            f"{BASE}/access/explain",
            params={"user_id": uid, "table": "pytest_explain_disabled_user"},
            headers=auth_headers,
        ).json()["data"]
        assert data["permit"] is False
        assert "停用" in data["reason"]
        assert data["matched"] == []
    finally:
        test_client.post(f"{BASE}/policy/delete", json={"ids": [pid]}, headers=auth_headers)
        db_exec("DELETE FROM sys_user WHERE id=:u", {"u": uid})


def test_explain_ignores_disabled_role(test_client, auth_headers, db_exec):
    """Important 2：停用角色不能给主体加分。

    ``_user_role_codes_by_id`` 只滤 ``is_deleted``；``AuthPermission`` 只认
    ``role.status == "0"``。解释接口必须按后者的口径过滤，否则停用角色仍显示 permit。
    """
    from datetime import datetime

    from app.utils.common_util import uuid4_str

    now = datetime.now().replace(microsecond=0)
    uid = int(
        db_exec(
            "INSERT INTO sys_user (tenant_id, username, password, name, is_superuser, "
            "status, uuid, created_time, updated_time, is_deleted) "
            "VALUES (1, :u, 'x', :n, false, '0', :uuid, :now, :now, false) "
            "RETURNING id",
            {
                "u": f"pytest-role-user-{uuid4_str()[:8]}",
                "n": "角色停用测试用户",
                "uuid": uuid4_str(),
                "now": now,
            },
        )
    )
    role_code = f"pytest_role_{uuid4_str()[:6]}"
    rid = int(
        db_exec(
            'INSERT INTO sys_role (name, code, "order", data_scope, uuid, status, '
            "created_time, updated_time, is_deleted) "
            "VALUES (:n, :c, 999, 4, :uuid, '1', :now, :now, false) RETURNING id",
            {
                "n": "停用角色（策略解释）",
                "c": role_code,
                "uuid": uuid4_str(),
                "now": now,
            },
        )
    )
    db_exec(
        "INSERT INTO sys_user_roles (user_id, role_id) VALUES (:u, :r)",
        {"u": uid, "r": rid},
    )
    saved = _save(
        test_client,
        auth_headers,
        name="pytest-policy-disabled-role",
        resource_code="pytest_explain_disabled_role",
        effect="allow",
        subject_kind="role",
        subject_value=role_code,
    )
    pid = saved.json()["data"]["id"]

    def _explain() -> dict:
        return test_client.get(
            f"{BASE}/access/explain",
            params={"user_id": uid, "table": "pytest_explain_disabled_role"},
            headers=auth_headers,
        ).json()["data"]

    try:
        denied = _explain()
        assert denied["permit"] is False, f"停用角色不应放行：{denied}"
        assert denied["matched"] == []

        # 对照：角色启停用后同一条策略生效（证明上面的 deny 是"角色被过滤"造成的）
        db_exec("UPDATE sys_role SET status='0' WHERE id=:r", {"r": rid})
        allowed = _explain()
        assert allowed["permit"] is True, allowed
        assert any(m["subject_kind"] == "role" for m in allowed["matched"])
    finally:
        test_client.post(f"{BASE}/policy/delete", json={"ids": [pid]}, headers=auth_headers)
        db_exec("DELETE FROM sys_user_roles WHERE user_id=:u", {"u": uid})
        db_exec("DELETE FROM sys_role WHERE id=:r", {"r": rid})
        db_exec("DELETE FROM sys_user WHERE id=:u", {"u": uid})


def _fake_auth(*codes: str):
    """只有指定权限码的登录主体（用于权限分档的单测，不需要应用）。"""
    from types import SimpleNamespace

    return SimpleNamespace(
        check_data_scope=True,
        user=SimpleNamespace(
            id=9,
            name="权限单元测试",
            is_superuser=False,
            roles=[
                SimpleNamespace(
                    status="0",
                    menus=[SimpleNamespace(permission=c, status="0") for c in codes],
                )
            ],
        ),
    )


def test_permission_split_create_and_update_are_exclusive():
    """只有 create 不能 update，只有 update 不能 create。"""
    from app.core.exceptions import CustomException
    from app.plugin.module_ai.query.policy_api import _require_perm

    create_only = _fake_auth("module_ai:query:policy:create")
    asyncio.run(_require_perm(create_only, "module_ai:query:policy:create"))
    with pytest.raises(CustomException):
        asyncio.run(_require_perm(create_only, "module_ai:query:policy:update"))

    update_only = _fake_auth("module_ai:query:policy:update")
    asyncio.run(_require_perm(update_only, "module_ai:query:policy:update"))
    with pytest.raises(CustomException):
        asyncio.run(_require_perm(update_only, "module_ai:query:policy:create"))


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
