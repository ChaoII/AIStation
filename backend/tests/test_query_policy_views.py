"""Task 10：视图权限按血缘**三级降级**（纯逻辑，不读库、不接线）。

设计稿：``docs/superpowers/specs/2026-11-06-query-permission-model-design.md`` §5.4。

血缘覆盖率不足以支撑"映射不了就全拒"（实测 ds:4 表级 66.5%、列级仅 11.3%），
所以按三级降级，**每一级都必须说实话**：

1. ``column``：血缘给到了「基表.列」→ 行条件/列 deny/mask **精确**套到视图列上；
2. ``table``：只给到基表 → 只套**表级** allow/deny；**绝不加行条件**（加了也证明不了
   视图暴露了条件列，"假装过滤"比拒答更危险）；
3. ``none``：完全映射不到（血缘缺失 / 只有推断失败的占位条目）→ 没有受保护的基表就放行
   （审计可见），有就拒绝。

``tier`` 的语义是**血缘映射能到达的粒度**（能力），不是"最终是否拒绝"：
一张列级映射的视图也可能因为审批不过而拒绝（例如条件列没被视图暴露），此时 ``tier``
仍是 ``column``，方便运维区分"映射不到"和"映射到了但条件不满足"。

``lineage`` 的条目格式（``dict[视图, list[str]]``）：

- ``"表"`` —— 只映射到表（tier=table）；
- ``"表.列"`` —— 视图暴露该基表的同名列（tier=column）；
- ``"表.*"`` —— 该基表所有同名列都暴露（列清单不可枚举，星号保留）；
- ``"unknown"`` / ``"?"`` / ``""`` —— 血缘推断失败的占位（**不是**真实表名）；
- 带 schema 的 ``public.表`` 按表处理，``public.表.列`` 按列处理。

返回的 ``AccessPlan`` 是**补充片段**（只含从基表推导出的限制），调用方把它叠加到
"视图自身"的计划条目上；``tier == "none"`` 且放行时片段为空（不改变调用方判定）。

全部用例 ``PYTEST_NO_APP=1`` 可跑（不需要应用与数据库）。
"""

from __future__ import annotations

import itertools

from app.plugin.module_ai.query.policy.compiler import DENIED_ALL, AccessPlan, rewrite
from app.plugin.module_ai.query.policy.engine import Policy
from app.plugin.module_ai.query.policy.views import resolve_view_policies

_ids = itertools.count(1)


# ---------------------------------------------------------------------------
# 构造辅助
# ---------------------------------------------------------------------------
def pol(
    effect: str,
    table: str,
    *,
    columns=(),
    condition: str = "",
    mask_expr: str = "",
    marking: str = "",
    subject_kind: str = "everyone",
    subject_value: str = "",
    priority: int = 100,
    enabled: bool = True,
    kind: str = "table",
) -> Policy:
    return Policy(
        id=next(_ids),
        effect=effect,
        resource_kind=kind,
        resource_code=table,
        subject_kind=subject_kind,
        subject_value=subject_value,
        condition=condition,
        columns=(columns,) if isinstance(columns, str) else tuple(columns),
        mask_expr=mask_expr,
        marking=marking,
        priority=priority,
        enabled=enabled,
    )


def merge(fragment: AccessPlan, view: str) -> AccessPlan:
    """把片段叠加到"视图自身无限制"的计划上（等价于接线时的合并）。"""
    return AccessPlan(
        row_filters=dict(fragment.row_filters),
        allowed_columns=dict(fragment.allowed_columns) or {view: None},
        masked=dict(fragment.masked),
        denied=dict(fragment.denied),
        policy_ids=fragment.policy_ids,
        deny_reason=fragment.deny_reason,
    )


#: 一条行条件（dept_id）、一条列 deny（phone）、一条列 mask（amount）。
POLS = [
    pol("allow", "fuel_price", condition="dept_id = 3"),
    pol("deny", "fuel_price", columns=("phone",)),
    pol("mask", "fuel_price", columns=("amount",), mask_expr="round(amount, 2)"),
]


# ---------------------------------------------------------------------------
# 一级：列可映射 → 精确套用行 / 列策略
# ---------------------------------------------------------------------------
def test_column_level_mapping_applies_row_filter():
    plan, tier = resolve_view_policies(
        "v_price",
        {"v_price": ["fuel_price.price", "fuel_price.dept_id", "fuel_price.amount"]},
        POLS,
    )

    assert tier == "column"
    assert "dept_id" in plan.row_filters["v_price"]
    # 列白名单 = 血缘声明暴露的列（星号展开的来源）
    assert plan.allowed_columns["v_price"] == ("price", "dept_id", "amount")
    assert plan.masked["v_price"]["amount"] == "round(amount, 2)"
    # phone 没被视图暴露 → 不必 deny；deny 表里也不能凭空多出一列
    assert not (plan.denied.get("v_price") or frozenset())


def test_column_level_fragment_is_executable_after_merge():
    """端到端：合并后的计划能真正改写 SQL（行过滤下推 + 掩码替换）。"""
    plan, tier = resolve_view_policies(
        "v_price", {"v_price": ["fuel_price.price", "fuel_price.dept_id"]}, POLS
    )
    assert tier == "column"

    d = rewrite("select * from v_price", merge(plan, "v_price"))

    assert d.permit, d.reason
    assert "dept_id = 3" in d.sql
    assert "phone" not in d.sql
    # 外层投影已按血缘暴露的列展开（包装里的 SELECT * 是编译中间态）
    assert "*" not in d.sql.lower().split("from")[0]


def test_exposed_deny_column_is_rejected_on_view():
    """基表 deny 列**被视图暴露**时，视图上的这一列也必须不可读。"""
    pols = [pol("allow", "fuel_price"), pol("deny", "fuel_price", columns=("phone",))]
    plan, tier = resolve_view_policies(
        "v_phone", {"v_phone": ["fuel_price.phone", "fuel_price.price"]}, pols
    )

    assert tier == "column"
    assert "phone" in (plan.denied["v_phone"] or frozenset())
    assert "phone" not in (plan.allowed_columns["v_phone"] or ())

    merged = merge(plan, "v_phone")
    # 星号按白名单展开 → 不含 phone（安全），但显式引用必须拒绝
    starred = rewrite("select * from v_phone", merged)
    assert starred.permit, starred.reason
    assert "phone" not in starred.sql.lower().split("from")[0]
    assert not rewrite("select phone from v_phone", merged).permit


def test_condition_column_not_exposed_is_denied_not_faked():
    """行条件引用的列没被视图暴露 → 拒绝，绝不"假装加了行过滤"。"""
    plan, tier = resolve_view_policies(
        "v_narrow", {"v_narrow": ["fuel_price.price"]}, POLS
    )

    # 映射能力到了列级（审计要能区分"映射不到"）
    assert tier == "column"
    assert plan.row_filters == {}, "不能把视图没暴露的列写进行条件"
    assert DENIED_ALL in plan.denied["v_narrow"]


def test_qualified_condition_column_is_denied():
    """行条件带基表限定（``fuel_price.dept_id``）无法安全挪到视图 → 拒绝。"""
    pols = [pol("allow", "fuel_price", condition="fuel_price.dept_id = 3")]
    plan, tier = resolve_view_policies(
        "v_price", {"v_price": ["fuel_price.dept_id"]}, pols
    )

    assert tier == "column"
    assert plan.row_filters == {}
    assert DENIED_ALL in plan.denied["v_price"]


def test_mask_referencing_unexposed_column_is_denied():
    """掩码表达式引用了视图没暴露的列 → 不能生成非法 SQL，拒绝该视图。"""
    pols = [
        pol("allow", "fuel_price"),
        pol("mask", "fuel_price", columns=("amount",), mask_expr="round(phone, 2)"),
    ]
    plan, tier = resolve_view_policies(
        "v_price", {"v_price": ["fuel_price.amount"]}, pols
    )

    assert tier == "column"
    assert DENIED_ALL in plan.denied["v_price"]


# ---------------------------------------------------------------------------
# 二级：只映射到表 → 只套表级 allow/deny（不加行条件）
# ---------------------------------------------------------------------------
def test_table_only_mapping_keeps_table_deny():
    pols = [pol("deny", "fuel_price")]
    plan, tier = resolve_view_policies("v2", {"v2": ["fuel_price"]}, pols)

    assert tier == "table"
    assert plan.row_filters == {}
    assert DENIED_ALL in plan.denied["v2"]
    assert not rewrite("select * from v2", plan).permit


def test_table_only_mapping_with_row_condition_is_denied():
    """只映射到表 + 基表有行策略 → 不能加行条件，只能拒绝（本轮核心）。"""
    plan, tier = resolve_view_policies("v2", {"v2": ["fuel_price"]}, POLS)

    assert tier == "table"
    assert plan.row_filters == {}, "表级映射下不允许出现行条件"
    assert DENIED_ALL in plan.denied["v2"]


def test_table_only_mapping_with_plain_allow_adds_nothing():
    """基表只有无条件 allow（迁移期的 legacy 兜底）→ 无需改写，视图照常可查。"""
    pols = [pol("allow", "fuel_price")]
    plan, tier = resolve_view_policies("v2", {"v2": ["fuel_price"]}, pols)

    assert tier == "table"
    assert plan.row_filters == {}
    assert not plan.masked
    assert not plan.denied
    assert plan.allowed_columns == {}


def test_table_only_mapping_with_marking_is_denied():
    """基表带标记（sensitive）但映射不到列 → 无法证明视图没暴露标记列 → 拒绝。"""
    pols = [pol("allow", "fuel_price", marking="sensitive")]
    plan, tier = resolve_view_policies("v2", {"v2": ["fuel_price"]}, pols)

    assert tier == "table"
    assert DENIED_ALL in plan.denied["v2"]


def test_table_only_mapping_with_column_deny_is_denied():
    """基表有列 deny/mask 但映射不到列 → 视图可能换名暴露该列 → 拒绝。"""
    pols = [pol("allow", "fuel_price"), pol("deny", "fuel_price", columns=("phone",))]
    plan, tier = resolve_view_policies("v2", {"v2": ["fuel_price"]}, pols)

    assert tier == "table"
    assert plan.row_filters == {}
    assert DENIED_ALL in plan.denied["v2"]


# ---------------------------------------------------------------------------
# 三级：完全不可映射
# ---------------------------------------------------------------------------
def test_unmapped_view_with_protected_base_is_denied():
    """血缘只给出推断失败的占位（"unknown"）→ 无法证明视图不依赖受保护表 → 拒绝。"""
    plan, tier = resolve_view_policies("v3", {"v3": ["unknown"]}, POLS)

    assert tier == "none"
    assert DENIED_ALL in plan.denied["v3"]
    assert not rewrite("select * from v3", plan).permit


def test_unmapped_view_with_unresolvable_entry_is_denied():
    """``".dept_id"`` 这类条目解析不出基表 → 同上，按不可映射处理。"""
    plan, tier = resolve_view_policies("v3", {"v3": [".dept_id"]}, POLS)

    assert tier == "none"
    assert DENIED_ALL in plan.denied["v3"]


# ---------------------------------------------------------------------------
# 直传 lineage.py 的真实输出（``upstream`` 是 list[dict]）
# ---------------------------------------------------------------------------
def test_lineage_dict_entry_with_protected_base_is_denied():
    """``{"table": "fuel_price"}`` 必须归一成表级映射，不能当字符串解析失败而放行。"""
    lineage = {"v_d": [{"table": "fuel_price", "kind": "view", "confidence": 0.9}]}

    plan, tier = resolve_view_policies("v_d", lineage, POLS)

    assert tier == "table"
    assert plan.row_filters == {}
    assert DENIED_ALL in plan.denied["v_d"]
    assert "行条件" in plan.deny_reason


def test_lineage_dict_entry_with_unprotected_base_is_permitted():
    """dict 条目指向没有策略的表 → 没有可施加的映射，放行。"""
    lineage = {"v_d": [{"table": "unknown_table", "kind": "view"}]}

    plan, tier = resolve_view_policies("v_d", lineage, POLS)

    assert tier == "none"
    assert not plan.denied
    assert plan.row_filters == {}


def test_lineage_malformed_dict_entry_is_denied_with_policy_ids():
    """dict 缺 ``table`` / 非字符串 → 不可解析；拒绝时 policy_ids 要能定位策略。"""
    lineage = {"v_d": [{"kind": "view"}]}

    plan, tier = resolve_view_policies("v_d", lineage, POLS)

    assert tier == "none"
    assert DENIED_ALL in plan.denied["v_d"]
    assert plan.policy_ids, "不可解析的整视图拒绝也要带策略 id（审计可追）"


def test_view_without_lineage_is_permitted_with_empty_fragment():
    """完全没有血缘记录 → 空片段（不改变调用方判定），tier 记 none 供审计。"""
    plan, tier = resolve_view_policies("v4", {}, POLS)

    assert tier == "none"
    assert plan.row_filters == {}
    assert plan.allowed_columns == {}
    assert plan.masked == {}
    assert not plan.denied


def test_unmapped_view_without_any_policy_is_permitted():
    """没有血缘、也没有任何策略 → 没有可泄漏的对象，放行。"""
    plan, tier = resolve_view_policies("v3", {"v3": ["unknown"]}, [])

    assert tier == "none"
    assert not plan.denied


# ---------------------------------------------------------------------------
# 边界：多基表 / 名称归一 / 禁用策略
# ---------------------------------------------------------------------------
def test_multiple_bases_with_different_row_conditions_are_denied():
    """两张基表各带行条件：一份视图条件表达不了两张表的过滤 → 拒绝。"""
    pols = [
        pol("allow", "fuel_price", condition="dept_id = 3"),
        pol("allow", "coal_price", condition="mine_id = 7"),
    ]
    lineage = {
        "v_join": ["fuel_price.dept_id", "coal_price.mine_id", "coal_price.price"],
    }

    plan, tier = resolve_view_policies("v_join", lineage, pols)

    assert tier == "column"
    assert DENIED_ALL in plan.denied["v_join"]


def test_mixed_granularity_with_row_condition_is_denied():
    """混合粒度（一张到列、一张只到表）+ 行条件 → 拒绝：三值里没有 mixed。"""
    pols = [
        pol("allow", "fuel_price", condition="dept_id = 3"),
        pol("allow", "coal_price"),
    ]
    lineage = {"v_mix": ["fuel_price.dept_id", "coal_price"]}

    plan, tier = resolve_view_policies("v_mix", lineage, pols)

    assert tier == "table"
    assert plan.row_filters == {}, "tier=table 时不允许出现行条件"
    assert DENIED_ALL in plan.denied["v_mix"]
    assert "混合粒度" in plan.deny_reason

    # 拒绝原因要能透传到编译器（审计/explain 用）
    decision = rewrite("select dept_id from v_mix", merge(plan, "v_mix"))
    assert not decision.permit
    assert "混合粒度" in decision.reason


def test_wildcard_mapping_with_column_deny_is_denied():
    """``表.*`` 只声明"整表列都暴露"，列级 deny 无法精确落地 → 拒绝。"""
    pols = [pol("allow", "fuel_price"), pol("deny", "fuel_price", columns=("phone",))]
    plan, tier = resolve_view_policies("v_w", {"v_w": ["fuel_price.*"]}, pols)

    assert tier == "column"
    assert DENIED_ALL in plan.denied["v_w"]


def test_cross_base_deny_wins_over_mask_without_contradiction():
    """同一视图列被 A 基表 deny、B 基表 mask：deny 优先，不产生 mask/allowed 自相矛盾。"""
    pols = [
        pol("allow", "fuel_price"),
        pol("deny", "fuel_price", columns=("phone",)),
        pol("allow", "coal_price"),
        pol("mask", "coal_price", columns=("phone",), mask_expr="'***'"),
    ]
    lineage = {
        "v_c": [
            "fuel_price.phone",
            "fuel_price.price",
            "coal_price.phone",
            "coal_price.price",
        ]
    }

    plan, tier = resolve_view_policies("v_c", lineage, pols)

    assert tier == "column"
    assert "phone" in (plan.denied["v_c"] or frozenset())
    assert not (plan.masked.get("v_c") or {}).get("phone"), "deny 列不应再配掩码"
    assert "phone" not in (plan.allowed_columns["v_c"] or ())
    assert plan.allowed_columns["v_c"] == ("price",)


def test_case_and_schema_are_normalized():
    """视图名/表名大小写与 schema 前缀都不敏感（编译器口径一致）。"""
    plan, tier = resolve_view_policies(
        "PUBLIC.V_Price", {"public.v_price": ["FUEL_PRICE.DEPT_ID"]}, POLS
    )

    assert tier == "column"
    assert "dept_id" in plan.row_filters["v_price"]


def test_disabled_policies_are_ignored():
    """禁用策略不参与映射（否则停用后视图还被拒）。"""
    pols = [pol("deny", "fuel_price", enabled=False)]
    plan, tier = resolve_view_policies("v5", {"v5": ["fuel_price"]}, pols)

    assert tier == "none"
    assert not plan.denied
