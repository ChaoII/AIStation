"""Step 1（P0-1）：SQL 编译器接进执行链路。

覆盖本步新增的三块能力（``PYTEST_NO_APP=1`` 可跑）：

1. ``policy.model.table_columns``：系统库 / 自定义源的列标签 → 真实列名
   （自定义源第一项是表注释，必须剔除）；
2. ``guard._new_decision`` 的编译产物：``decision.sql`` 可直接执行、``applied`` 记
   实际改写；视图按**单层**血缘映射，映射不到就拒绝（不伪造过滤）；
3. 审计/差异只记**实际施加**的改写，纯格式差异不算 ``rewrite_only``。
"""

from __future__ import annotations

import asyncio

from app.plugin.module_ai.query.policy import guard as G
from app.plugin.module_ai.query.policy.compiler import AccessPlan
from app.plugin.module_ai.query.policy.engine import Decision, Policy
from app.plugin.module_ai.query.policy.model import table_columns


def _principal(**over):
    from app.plugin.module_ai.query.policy.principal import Principal

    kw = {
        "user_id": 7,
        "is_superuser": False,
        "roles": ("USER",),
        "attrs": {},
        "entry": "ask",
    }
    kw.update(over)
    return Principal(**kw)


def _policy(effect="allow", pid=1, **over) -> Policy:
    kw = {
        "id": pid,
        "effect": effect,
        "resource_kind": "table",
        "resource_code": "t",
        "subject_kind": "everyone",
        "subject_value": "",
        "condition": "",
        "columns": (),
        "mask_expr": "",
        "marking": "",
        "priority": 100,
        "enabled": True,
    }
    kw.update(over)
    return Policy(**kw)


# ---------------------------------------------------------------------------
# 1. 列元数据
# ---------------------------------------------------------------------------
def test_table_columns_parses_system_labels(monkeypatch):
    from app.plugin.module_ai.query.service import AiQueryService as Q

    async def _system(cls):
        return {
            "video_cameras": [
                "id(bigint)【主键】",
                "name(character varying)【名称】",
                "password(text)【敏感】",
            ]
        }

    monkeypatch.setattr(Q, "_system_schema", classmethod(_system))

    got = asyncio.run(table_columns("system", ["VIDEO_CAMERAS"]))

    assert got == {
        "video_cameras": ["id", "name", "password"]
    }, got


def test_table_columns_skips_ds_table_comment(monkeypatch):
    """``_ds_schema_map`` 第一项 ``表名(注释)`` 是表注释，不是列。"""
    from app.plugin.module_ai.query.service import AiQueryService as Q

    async def _ds(cls, datasource, strict=False):
        assert datasource == "ds:4"
        return {
            "DTXY_PMXX": ["DTXY_PMXX(煤炭品名表)", "ID(bigint)", "VARIETY(品种)"],
            "OTHER": ["NAME"],
        }

    monkeypatch.setattr(Q, "_ds_schema_map", classmethod(_ds))

    got = asyncio.run(table_columns("ds:4", ["DTXY_PMXX"]))

    assert got == {"DTXY_PMXX": ["ID", "VARIETY"]}, got


# ---------------------------------------------------------------------------
# 2. 视图合并 / 编译产物
# ---------------------------------------------------------------------------
def test_merge_plan_tightens_only():
    plan = AccessPlan(
        row_filters={},
        allowed_columns={"v": ("a", "b", "secret")},
        masked={},
        denied={},
        policy_ids=(1,),
    )
    fragment = AccessPlan(
        row_filters={"v": "dept_id = 3"},
        allowed_columns={"v": ("a", "b")},
        masked={"v": {"b": "left(b, 1)"}},
        denied={"v": frozenset({"secret"})},
        policy_ids=(2,),
    )

    merged = G._merge_plan(plan, fragment)

    assert merged.row_filters == {"v": "dept_id = 3"}, merged.row_filters
    assert merged.allowed_columns == {"v": ("a", "b")}, merged.allowed_columns
    assert merged.masked == {"v": {"b": "left(b, 1)"}}, merged.masked
    assert "secret" in merged.denied["v"], merged.denied
    assert merged.policy_ids == (1, 2), merged.policy_ids


def test_view_mapping_does_not_fake_row_filter(monkeypatch):
    """基表只有表级血缘却带行条件 → 视图拒绝（绝不能"看起来过滤了"）。"""
    from app.plugin.module_ai.query import lineage as L

    view_policy = _policy(pid=10, resource_kind="view", resource_code="v")
    base_policy = _policy(pid=11, resource_code="t", condition="dept_id = 3")

    async def _policies():
        return [view_policy, base_policy]

    async def _domains(user_id):
        return ()

    async def _columns(datasource, tables=None, strict=False):
        return {"v": ["a", "dept_id"], "t": ["a", "dept_id"]}

    async def _tables(sql, dialect="postgres"):
        return {"v"}

    async def _lineage(datasource, table, strict=False):
        assert table == "V"
        return {"upstream": [{"table": "t", "kind": "view"}]}

    monkeypatch.setattr(G, "list_policies", _policies)
    monkeypatch.setattr(G, "domain_codes_for_user", _domains)
    monkeypatch.setattr(G, "table_columns", _columns)
    monkeypatch.setattr(G, "_tables_of", _tables)
    monkeypatch.setattr(L, "lineage_for_table", _lineage)

    d = asyncio.run(
        G._new_decision(
            sql="select a from v",
            principal=_principal(),
            dialect="postgres",
            datasource="ds:4",
        )
    )

    assert not d.permit
    assert "视图只映射到表" in d.reason, d.reason


def test_view_mapping_does_not_fake_column_restriction(monkeypatch):
    """基表有列级 deny、血缘只到表 → 视图拒绝（不能假装列限制没暴露）。"""
    from app.plugin.module_ai.query import lineage as L

    view_policy = _policy(pid=10, resource_kind="view", resource_code="v")
    base_allow = _policy(pid=11, resource_code="t")
    base_deny = _policy(
        pid=12, effect="deny", resource_code="t", columns=("secret",)
    )

    async def _policies():
        return [view_policy, base_allow, base_deny]

    async def _domains(user_id):
        return ()

    async def _columns(datasource, tables=None, strict=False):
        return {"v": ["a", "secret"], "t": ["a", "secret"]}

    async def _tables(sql, dialect="postgres"):
        return {"v"}

    async def _lineage(datasource, table, strict=False):
        return {"upstream": [{"table": "t", "kind": "view"}]}

    monkeypatch.setattr(G, "list_policies", _policies)
    monkeypatch.setattr(G, "domain_codes_for_user", _domains)
    monkeypatch.setattr(G, "table_columns", _columns)
    monkeypatch.setattr(G, "_tables_of", _tables)
    monkeypatch.setattr(L, "lineage_for_table", _lineage)

    d = asyncio.run(
        G._new_decision(
            sql="select a from v",
            principal=_principal(),
            dialect="postgres",
            datasource="ds:4",
        )
    )

    assert not d.permit, d.sql
    assert "列级限制" in d.reason, d.reason


# ---------------------------------------------------------------------------
# 3. 审计 / shadow 差异只记实际改写
# ---------------------------------------------------------------------------
def test_diff_kind_ignores_format_only_change():
    legacy = Decision(True, "旧判定放行")
    new = Decision(True, "编译完成", sql="SELECT a FROM t", applied=())

    assert G._diff_kind(legacy_decision=legacy, new_decision=new) is None


def test_diff_kind_records_actual_rewrite():
    legacy = Decision(True, "旧判定放行")
    new = Decision(
        True,
        "编译完成",
        sql="SELECT a FROM (SELECT * FROM t WHERE dept_id = 3) AS t",
        applied=({"row": "dept_id = 3", "table": "t"},),
    )

    assert G._diff_kind(legacy_decision=legacy, new_decision=new) == "rewrite_only"


def test_audit_rewrite_is_empty_for_legacy(monkeypatch):
    """legacy 执行原 SQL：即使旧判定带 applied，也不能写成"已施加"。"""
    captured: dict = {}

    async def _mode():
        return "legacy"

    async def _audit(**kw):
        captured.update(kw)

    async def _legacy():
        return Decision(True, "legacy 放行", applied=({"row": "dept_id = 3"},))

    monkeypatch.setattr(G, "_engine_mode", _mode)
    monkeypatch.setattr(G, "write_access_log", _audit)

    d = asyncio.run(
        G.prepare(
            sql="select a from t",
            principal=_principal(),
            entry="ask",
            datasource="system",
            legacy_check=_legacy,
        )
    )

    assert d.permit
    assert captured["rewrite"] == [], captured["rewrite"]
