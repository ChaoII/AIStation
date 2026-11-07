"""Task 6：唯一网关 QueryGuard（三态开关 + shadow）+ 策略/数据域读取。

覆盖点（全部是纯逻辑，打桩库/策略源，``PYTEST_NO_APP=1`` 可跑）：

1. **无主体拒绝**：``principal=None`` 一律 deny（reason 带 ``principal``），审计照写；
2. **legacy**：只做「无主体 + 星号 + 审计」，**绝不加载策略、绝不调用引擎**，结论来自
   调用方 ``legacy_check``（未传视为放行）；
3. **shadow**：新旧都算，**返回旧结论**，差异真的写进 ``ai_policy_shadow_diff``
   （diff_kind / sql_hash / 打码预览都要对）；
4. **enforce**：编译器接线前是**硬闸** —— 一律 deny（reason 写明原因），不加载策略、
   不调用旧判定；新引擎语义（表级默认拒绝 / 行条件 / 域注入 / 解析失败）由
   ``_new_decision`` 的直接用例覆盖；
5. **星号止血对三种模式都生效**：``select * from 敏感表`` 在 legacy 下也必须拒，
   且不能先跑旧判定（否则等于没修）；
6. **域注入**：``prepare`` 把 ``domain_codes_for_user`` 的结果填进
   ``principal.attrs["domains"]``（逗号串），域策略才命中；
7. **失败语义**：策略/敏感表清单加载失败 → deny（fail-closed）；
   shadow 差异写入失败 → 不影响旧结论（fail-open，灰度期不能拖垮线上）；
8. ``repo``：``list_policies`` 只读「启用且未删除」；``domain_codes_for_user`` 按
   ``members`` 过滤并跳过禁用/已删域。
"""

from __future__ import annotations

import asyncio

from app.plugin.module_ai.query.policy.engine import Decision, Policy


# ---------------------------------------------------------------------------
# 构造工具
# ---------------------------------------------------------------------------
def _guard():
    from app.plugin.module_ai.query.policy import guard

    return guard


def _principal(**over):
    from app.plugin.module_ai.query.policy.principal import Principal

    kw = {"user_id": 7, "is_superuser": False, "roles": ("USER",), "attrs": {}, "entry": "ask"}
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


class _Stubs:
    """记录审计与 shadow 差异的桩，测试末尾断言用。"""

    def __init__(self):
        self.audit_calls: list[dict] = []
        self.shadow_calls: list[dict] = []
        self.engine_calls: list[dict] = []


def _setup(
    monkeypatch,
    G,
    *,
    mode="legacy",
    policies=(),
    domains=(),
    sensitive=(),
    tables=("t",),
    columns=None,
    patch_tables=True,
    record_shadow=True,
) -> _Stubs:
    """把 guard 的外部依赖全部打桩（模式/策略/域/敏感表/表解析/列元数据/审计/shadow）。"""
    st = _Stubs()

    async def _mode():
        return mode

    async def _policies():
        return list(policies)

    async def _domains(user_id):
        return tuple(domains)

    async def _sensitive():
        return set(sensitive)

    async def _tables(sql):
        return set(tables)

    _columns = {"t": ["a", "dept_id"]} if columns is None else dict(columns)

    async def _table_columns(datasource, wanted=None):
        names = {str(t).lower() for t in (wanted or ()) if str(t)}
        return {
            table: list(cols)
            for table, cols in _columns.items()
            if not names or str(table).lower() in names
        }

    async def _audit(**kw):
        st.audit_calls.append(kw)

    async def _shadow(**kw):
        st.shadow_calls.append(kw)

    monkeypatch.setattr(G, "_engine_mode", _mode)
    monkeypatch.setattr(G, "list_policies", _policies)
    monkeypatch.setattr(G, "domain_codes_for_user", _domains)
    monkeypatch.setattr(G, "sensitive_tables", _sensitive)
    monkeypatch.setattr(G, "table_columns", _table_columns)
    if patch_tables:
        monkeypatch.setattr(G, "_tables_of", _tables)
    monkeypatch.setattr(G, "write_access_log", _audit)
    if record_shadow:
        monkeypatch.setattr(G, "_record_shadow_diff", _shadow)
    return st


def _run(G, *, sql="select a from t", principal=None, entry="ask", datasource="ds:4",
         dialect="postgres", legacy_check=None):
    return asyncio.run(
        G.prepare(
            sql=sql,
            principal=_principal() if principal is None else principal,
            entry=entry,
            datasource=datasource,
            dialect=dialect,
            legacy_check=legacy_check,
        )
    )


# ---------------------------------------------------------------------------
# 1. 无主体
# ---------------------------------------------------------------------------
def test_missing_principal_denies(monkeypatch):
    G = _guard()
    st = _setup(monkeypatch, G, mode="enforce")

    d = asyncio.run(
        G.prepare(sql="select 1", principal=None, entry="ask", datasource="ds:4")
    )

    assert not d.permit
    assert "principal" in d.reason, d.reason
    assert st.audit_calls[-1]["decision"] == "deny"
    assert st.audit_calls[-1]["principal"] is None, "审计要如实记录没有主体，不能伪造 0"


# ---------------------------------------------------------------------------
# 2. legacy：只旧判定，绝不加载策略/引擎
# ---------------------------------------------------------------------------
def test_legacy_mode_never_calls_engine(monkeypatch):
    G = _guard()
    st = _setup(monkeypatch, G, mode="legacy", policies=(_policy(),))

    async def _boom(*a, **k):
        raise AssertionError("legacy 模式不得加载策略或调用引擎")

    monkeypatch.setattr(G, "list_policies", _boom)
    monkeypatch.setattr(G, "domain_codes_for_user", _boom)
    monkeypatch.setattr(G, "table_columns", _boom)
    monkeypatch.setattr(G, "build_plan", _boom)

    async def _legacy():
        return Decision(True, "旧判定放行")

    d = _run(G, legacy_check=_legacy)

    assert d.permit and d.reason == "旧判定放行"
    assert st.audit_calls, "放行也要写审计"
    assert st.audit_calls[-1]["decision"] == "permit"


def test_legacy_without_check_defaults_to_permit(monkeypatch):
    """``legacy_check is None`` 视为旧判定放行（T7 之前的过渡态）。"""
    G = _guard()
    _setup(monkeypatch, G, mode="legacy")

    d = _run(G)

    assert d.permit


def test_legacy_exception_propagates(monkeypatch):
    """legacy 必须与改造前行为一致：旧判定抛错照旧上抛（网关不吞）。"""
    G = _guard()
    _setup(monkeypatch, G, mode="legacy")

    async def _boom():
        raise RuntimeError("旧判定炸了")

    try:
        _run(G, legacy_check=_boom)
    except RuntimeError as e:
        assert "旧判定" in str(e)
    else:  # pragma: no cover
        raise AssertionError("legacy 模式不应吞掉旧判定的异常")


def test_legacy_exception_still_writes_deny_audit(monkeypatch):
    """判定抛异常也必须落一条 deny 审计，且**原异常原样抛出**（类型/文案不变）。

    T7 接线后 ``legacy_check`` 会跑白名单校验 / 字段级 ACL / 数据源授权，
    这些失败都是 ``CustomException``。若异常路径不写审计，拒答就完全没有痕迹
    —— 审计变成"只有放行和引擎判定才有记录"，治理上等于缺口。
    """
    from app.core.exceptions import CustomException

    G = _guard()
    st = _setup(monkeypatch, G, mode="legacy")

    async def _deny():
        raise CustomException(msg="表「hack」不在可查询白名单内")

    try:
        _run(G, legacy_check=_deny, entry="export", datasource="ds:9")
    except CustomException as e:
        assert e.msg == "表「hack」不在可查询白名单内", (
            f"原异常文案被改写了：{e.msg}")
    else:  # pragma: no cover
        raise AssertionError("判定异常必须原样抛出，不能被换成 Decision")

    assert st.audit_calls, "异常路径一条审计都没写（治理缺口）"
    call = st.audit_calls[-1]
    assert call["decision"] == "deny", call
    assert call["policy_ids"] == [], call
    assert call["rewrite"] == [], call
    assert "CustomException" in call["reason"], f"reason 没带异常类型：{call['reason']}"
    assert "hack" in call["reason"], f"reason 没带异常摘要：{call['reason']}"
    assert call["entry"] == "export" and call["datasource"] == "ds:9", call


def test_audit_failure_does_not_mask_decision_exception(monkeypatch):
    """审计本身也抛错时，抛出的必须是**原判定异常**，不是审计异常。"""
    G = _guard()
    _setup(monkeypatch, G, mode="legacy")

    async def _boom():
        raise RuntimeError("字段级权限校验失败")

    async def _audit_boom(**kw):
        raise OSError("审计库不可用")

    monkeypatch.setattr(G, "write_access_log", _audit_boom)

    try:
        _run(G, legacy_check=_boom)
    except RuntimeError as e:
        assert "字段级权限校验失败" in str(e), f"原异常被审计异常顶替了：{e}"
    except OSError as e:  # pragma: no cover
        raise AssertionError(f"审计异常掩盖了原判定异常：{e}") from e
    else:  # pragma: no cover
        raise AssertionError("异常被吞掉了")


# ---------------------------------------------------------------------------
# 3. shadow：返回旧结论 + 真的写差异
# ---------------------------------------------------------------------------
def test_shadow_mode_returns_legacy_decision_but_records_diff(monkeypatch):
    G = _guard()
    st = _setup(monkeypatch, G, mode="shadow", policies=())  # 新引擎无策略 → 拒

    async def _legacy():
        return Decision(True, "旧判定放行")

    d = _run(G, legacy_check=_legacy)

    assert d.permit, "shadow 模式下结论必须来自旧判定"
    assert d.reason == "旧判定放行"
    assert st.shadow_calls, "shadow 模式新旧结论不同，必须写差异"
    call = st.shadow_calls[-1]
    assert call["legacy"].permit and not call["new"].permit
    assert st.audit_calls[-1]["decision"] == "permit", "审计记的是生效结论"


def test_shadow_diff_row_is_written_with_kind(monkeypatch):
    """差异行真的 INSERT 到 ``ai_policy_shadow_diff``（参数逐项校验）。"""
    G = _guard()
    sink: dict = {}
    _setup(monkeypatch, G, mode="shadow", policies=(), record_shadow=False)
    monkeypatch.setattr(G, "async_db_session_fresh", _fresh(sink))

    sql = "select a from t where phone='13800138000'"

    async def _legacy():
        return Decision(True, "旧判定放行")

    d = _run(G, sql=sql, legacy_check=_legacy, entry="report", datasource="ds:9")

    assert d.permit
    assert "ai_policy_shadow_diff" in sink["sql"], sink["sql"]
    p = sink["params"]
    assert p["legacy"] == "permit" and p["new"] == "deny"
    assert p["kind"] == "legacy_permit_new_deny"
    assert p["uid"] == 7
    assert p["entry"] == "report"
    assert len(p["h"]) == 64
    assert "13800138000" not in p["prev"], "差异表也不能存明文 PII"


def test_shadow_no_diff_when_decisions_agree(monkeypatch):
    G = _guard()
    st = _setup(
        monkeypatch,
        G,
        mode="shadow",
        policies=(_policy(),),  # everyone allow t → 新引擎也放行
    )

    async def _legacy():
        return Decision(True, "旧判定放行")

    d = _run(G, legacy_check=_legacy)

    assert d.permit
    assert not st.shadow_calls, "结论相同不该写差异（否则表会被噪声灌满）"


def test_shadow_records_legacy_deny_new_permit(monkeypatch):
    G = _guard()
    st = _setup(monkeypatch, G, mode="shadow", policies=(_policy(),))
    sink: dict = {}
    monkeypatch.setattr(G, "_record_shadow_diff", _capture_kind(st))
    monkeypatch.setattr(G, "async_db_session_fresh", _fresh(sink))

    async def _legacy():
        return Decision(False, "旧判定拒绝")

    d = _run(G, legacy_check=_legacy)

    assert not d.permit, "shadow 返回旧结论（拒绝）"
    assert st.shadow_calls[-1]["legacy"].permit is False
    assert st.shadow_calls[-1]["new"].permit is True
    # 直接验证写入的 kind（用桩接管记录、真实写函数的 kind 由 _diff_kind 决定）
    assert G._diff_kind(legacy_decision=Decision(False), new_decision=Decision(True)) == (
        "legacy_deny_new_permit"
    )


def test_shadow_write_failure_does_not_break_query(monkeypatch):
    """灰度期差异写不进去也不能影响线上查询（返回旧结论）。"""
    G = _guard()
    _setup(monkeypatch, G, mode="shadow", policies=(), record_shadow=False)

    class _Boom:
        def __call__(self):
            raise RuntimeError("db down")

    monkeypatch.setattr(G, "async_db_session_fresh", _Boom())

    async def _legacy():
        return Decision(True, "旧判定放行")

    d = _run(G, legacy_check=_legacy)

    assert d.permit, "shadow 写差异失败必须 fail-open（不能把查询搞挂）"


def test_shadow_records_rewrite_only_for_row_filter(monkeypatch):
    """双放行但新引擎多出 `dept_id = 3` 这类行过滤 → rewrite_only，且 rewrite 列有内容。

    这是 T9 之后"用户的行被静默藏掉"最该被抓到的变更；此前 `_new_decision` 丢弃
    `d.sql`，diff 条数恒为 0。
    """
    G = _guard()
    sink: dict = {}
    _setup(
        monkeypatch,
        G,
        mode="shadow",
        policies=(_policy(condition="dept_id = 3"),),
        record_shadow=False,
    )
    monkeypatch.setattr(G, "async_db_session_fresh", _fresh(sink))

    async def _legacy():
        return Decision(True, "旧判定放行")

    d = _run(G, legacy_check=_legacy)

    assert d.permit, "shadow 仍返回旧结论"
    p = sink["params"]
    assert p["kind"] == "rewrite_only", p
    assert p["legacy"] == "permit" and p["new"] == "permit"
    assert '"row"' in p["rw"] and "dept_id = 3" in p["rw"], p["rw"]


def _run_new(G, *, sql="select a from t", principal=None, dialect="postgres",
             datasource="system"):
    """直接跑新引擎判定（``_new_decision``）—— 现在包含 SQL 编译。"""
    return asyncio.run(
        G._new_decision(
            sql=sql,
            principal=_principal() if principal is None else principal,
            dialect=dialect,
            datasource=datasource,
        )
    )


# ---------------------------------------------------------------------------
# 4. enforce：编译器接线后**真的执行改写**（不再是硬闸）
# ---------------------------------------------------------------------------
def test_enforce_mode_applies_compiled_sql(monkeypatch):
    """enforce：策略条件 → 可执行 SQL（含 WHERE），applied 记录实际改写。"""
    G = _guard()
    st = _setup(
        monkeypatch,
        G,
        mode="enforce",
        policies=(_policy(condition="dept_id = 3"),),
        columns={"t": ["a", "dept_id"]},
    )

    async def _legacy():  # pragma: no cover - enforce 不跑旧判定
        raise AssertionError("enforce 不该调用旧判定")

    d = _run(G, sql="select a from t", legacy_check=_legacy)

    assert d.permit, d.reason
    assert "where" in (d.sql or "").lower(), d.sql
    assert "dept_id = 3" in (d.sql or ""), d.sql
    assert d.applied and d.applied[0].get("row") == "dept_id = 3", d.applied
    # 审计必须记**实际施加**的改写（不再是空数组）
    call = st.audit_calls[-1]
    assert call["decision"] == "permit", call
    assert call["rewrite"] and call["rewrite"][0].get("row") == "dept_id = 3", call
    assert 1 in call["policy_ids"], call


def test_enforce_mode_denies_when_table_not_allowed(monkeypatch):
    """enforce 默认拒绝：没有 allow 的表 → deny（不是硬闸，是引擎语义）。"""
    G = _guard()
    st = _setup(monkeypatch, G, mode="enforce", policies=())

    d = _run(G)

    assert not d.permit
    assert "t" in d.reason, d.reason
    assert st.audit_calls[-1]["decision"] == "deny"
    assert st.audit_calls[-1]["rewrite"] == []


def test_enforce_mode_failure_is_denied_not_raised(monkeypatch):
    """enforce 判定链路异常 → deny（不抛、不降级放行）。"""
    G = _guard()
    st = _setup(monkeypatch, G, mode="enforce", policies=(_policy(),))

    async def _boom(datasource, tables=None):
        raise RuntimeError("元数据查询失败")

    monkeypatch.setattr(G, "table_columns", _boom)

    d = _run(G)

    assert not d.permit
    assert "fail-closed" in d.reason, d.reason
    assert st.audit_calls[-1]["decision"] == "deny"


def test_enforce_gate_still_runs_star_stop(monkeypatch):
    """enforce 不能把星号止血的顺序搞乱：敏感表 ``select *`` 的 reason 仍是星号原因。"""
    G = _guard()
    _setup(
        monkeypatch,
        G,
        mode="enforce",
        sensitive=("fuel_price",),
        tables=("fuel_price",),
    )

    d = _run(G, sql="select * from fuel_price")

    assert not d.permit
    assert "星号" in d.reason, d.reason


# 4.1 新引擎语义（直接调 ``_new_decision``，现在包含 SQL 编译）
def test_new_decision_denies_table_without_allow(monkeypatch):
    G = _guard()
    _setup(monkeypatch, G, mode="enforce", policies=())

    d = _run_new(G)

    assert not d.permit
    assert "t" in d.reason, "拒绝原因要带表名，否则用户/管理员看不出是哪张表"


def test_new_decision_deny_reason_has_table_and_policy_ids(monkeypatch):
    G = _guard()
    deny = _policy(effect="deny", subject_kind="user", subject_value="7", pid=31)
    _setup(monkeypatch, G, mode="enforce", policies=(deny,))

    d = _run_new(G)

    assert not d.permit
    assert "t" in d.reason and "31" in d.reason, d.reason
    assert 31 in d.policy_ids


def test_new_decision_superuser_bypasses_without_loading_policies(monkeypatch):
    G = _guard()
    _setup(monkeypatch, G, mode="enforce", policies=())

    async def _boom(*a, **k):
        raise AssertionError("超管绕过时不必加载策略")

    monkeypatch.setattr(G, "list_policies", _boom)

    d = _run_new(G, principal=_principal(is_superuser=True))

    assert d.permit and "superuser" in d.reason


def test_new_decision_no_tables_but_parsable_is_permitted(monkeypatch):
    """``select 1`` 这类不涉及表的查询没有可泄漏对象，不该被表级默认拒绝误伤。"""
    G = _guard()
    _setup(monkeypatch, G, mode="enforce", policies=(), tables=())

    d = _run_new(G, sql="select 1")

    assert d.permit, d.reason


def test_new_decision_unparsable_sql_denies(monkeypatch):
    G = _guard()
    _setup(monkeypatch, G, mode="enforce", policies=(), tables=())

    d = _run_new(G, sql="select from where (((")

    assert not d.permit
    assert "解析" in d.reason, d.reason


# ---------------------------------------------------------------------------
# 4.1 引擎意外异常：``_new_decision`` 函数契约直接抛；enforce 在编排层转 deny
# ---------------------------------------------------------------------------
def test_new_decision_engine_error_propagates(monkeypatch):
    """编译/计划构建异常时 ``_new_decision`` 原样上抛（fail-closed 由 ``prepare`` 落地）。"""
    import pytest

    G = _guard()
    _setup(
        monkeypatch,
        G,
        mode="enforce",
        policies=(_policy(),),
        columns={"t": ["a"]},
    )

    def _boom(*a, **k):
        raise ValueError("引擎炸了")

    monkeypatch.setattr(G, "build_plan", _boom)

    with pytest.raises(ValueError, match="引擎炸了"):
        _run_new(G)


def test_shadow_engine_error_returns_legacy_without_diff(monkeypatch):
    """shadow 下引擎异常不能把旧逻辑本来放行的查询打成失败。"""
    G = _guard()
    st = _setup(monkeypatch, G, mode="shadow", policies=(_policy(),))

    def _boom(*a, **k):
        raise ValueError("引擎炸了")

    monkeypatch.setattr(G, "build_plan", _boom)

    async def _legacy():
        return Decision(True, "旧判定放行")

    d = _run(G, legacy_check=_legacy)

    assert d.permit and d.reason == "旧判定放行"
    assert not st.shadow_calls, "引擎异常不是业务差异，不能写进差异表"


# ---------------------------------------------------------------------------
# 4.2 编译结果随 Decision 带出（行过滤下推 + applied 记录实际改写）
# ---------------------------------------------------------------------------
def test_new_decision_carries_row_condition(monkeypatch):
    G = _guard()
    _setup(
        monkeypatch,
        G,
        mode="enforce",
        policies=(_policy(condition="dept_id = 3"),),
        columns={"t": ["a", "dept_id"]},
    )

    d = _run_new(G)

    assert d.permit
    assert "where" in d.sql.lower(), d.sql
    assert "dept_id = 3" in d.sql, "编译后的 SQL 必须含行过滤条件"
    assert d.applied and d.applied[0].get("row") == "dept_id = 3", d.applied


def test_new_decision_unions_row_conditions(monkeypatch):
    G = _guard()
    _setup(
        monkeypatch,
        G,
        mode="enforce",
        policies=(
            _policy(condition="dept_id = 3", pid=1),
            _policy(condition="dept_id = 4", pid=2),
        ),
        columns={"t": ["a", "dept_id"]},
    )

    d = _run_new(G)

    assert "(dept_id = 3) OR (dept_id = 4)" in d.sql, d.sql
    assert len(d.applied) == 1 and "OR" in d.applied[0]["row"], d.applied


def test_new_decision_unconditional_allow_absorbs_conditions(monkeypatch):
    G = _guard()
    _setup(
        monkeypatch,
        G,
        mode="enforce",
        policies=(_policy(condition="dept_id = 3", pid=1), _policy(pid=2)),
        columns={"t": ["a", "dept_id"]},
    )

    d = _run_new(G)

    assert d.permit
    assert "where" not in d.sql.lower(), d.sql
    assert d.applied == (), "无条件授权吸收条件（union_condition 语义）"


# ---------------------------------------------------------------------------
# 5. 星号止血：三种模式都生效
# ---------------------------------------------------------------------------
def test_star_denial_applies_to_all_modes(monkeypatch):
    for mode in ("legacy", "shadow", "enforce"):
        G = _guard()
        _setup(
            monkeypatch,
            G,
            mode=mode,
            policies=(_policy(resource_code="fuel_price"),),
            sensitive=("fuel_price",),
            tables=("fuel_price",),
        )
        called: list[int] = []

        async def _legacy(called=called):
            called.append(1)
            return Decision(True, "旧判定放行")

        d = _run(G, sql="select * from fuel_price", legacy_check=_legacy)

        assert not d.permit, f"{mode} 模式下敏感表星号必须拒绝"
        assert "fuel_price" in d.reason, d.reason
        assert not called, f"{mode} 模式下星号必须在旧判定之前拒（否则 P0 等于没做）"


def test_plain_star_denied_when_any_joined_table_is_sensitive(monkeypatch):
    G = _guard()
    _setup(
        monkeypatch,
        G,
        mode="legacy",
        policies=(_policy(resource_code="fuel_price"), _policy(pid=2)),
        sensitive=("fuel_price",),
        tables=("fuel_price", "t"),
    )

    d = _run(G, sql="select * from t join fuel_price on t.id = fuel_price.id")

    assert not d.permit and "fuel_price" in d.reason


def test_count_star_is_not_blocked(monkeypatch):
    G = _guard()
    _setup(
        monkeypatch,
        G,
        mode="legacy",
        policies=(_policy(resource_code="fuel_price"),),
        sensitive=("fuel_price",),
        tables=("fuel_price",),
    )

    d = _run(G, sql="select count(*) from fuel_price")

    assert d.permit, "count(*) 不取列，不能拦"


def test_sensitive_tables_load_failure_denies(monkeypatch):
    G = _guard()
    _setup(monkeypatch, G, mode="legacy")

    async def _boom():
        raise RuntimeError("db down")

    monkeypatch.setattr(G, "sensitive_tables", _boom)

    d = _run(G, sql="select * from t")

    assert not d.permit
    assert "fail-closed" in d.reason, d.reason


def test_star_denial_writes_audit(monkeypatch):
    """星号拒绝路径同样要落审计（P0 被拦的查询必须可回溯）。"""
    G = _guard()
    st = _setup(
        monkeypatch,
        G,
        mode="legacy",
        sensitive=("fuel_price",),
        tables=("fuel_price",),
    )
    sql = "select * from fuel_price"

    d = _run(G, sql=sql)

    assert not d.permit
    assert st.audit_calls, "星号拒绝也要写审计"
    call = st.audit_calls[-1]
    assert call["decision"] == "deny"
    assert "fuel_price" in call["reason"]
    assert call["sql"] == sql


# ---------------------------------------------------------------------------
# 6. 域注入
# ---------------------------------------------------------------------------
def test_domains_injected_into_principal_attrs(monkeypatch):
    G = _guard()
    domain_allow = _policy(
        subject_kind="domain", subject_value="hr", resource_code="t", pid=11
    )
    _setup(
        monkeypatch,
        G,
        mode="enforce",
        policies=(domain_allow,),
        domains=("hr", "finance"),
    )

    seen: list[dict] = []
    real = G.build_plan

    def _spy(policies, principal, tables):
        seen.append(dict(principal.attrs))
        return real(policies, principal, tables)

    monkeypatch.setattr(G, "build_plan", _spy)

    d = _run_new(G)

    assert d.permit, "域策略命中靠 attrs['domains'] 注入，没注入就永远不命中"
    assert seen and seen[0].get("domains") == "hr,finance", seen


def test_domains_override_caller_supplied_attrs(monkeypatch):
    """域成员以库为准，调用方塞进来的 ``domains`` 不能当真（防伪造）。"""
    G = _guard()
    domain_allow = _policy(subject_kind="domain", subject_value="finance")
    _setup(monkeypatch, G, mode="enforce", policies=(domain_allow,), domains=("hr",))

    d = _run_new(G, principal=_principal(attrs={"domains": "finance"}))

    assert not d.permit, "库里的域成员是 hr，伪造 finance 不应命中"


# ---------------------------------------------------------------------------
# 7. 策略加载失败 → fail-closed
# ---------------------------------------------------------------------------
def test_policy_load_failure_denies(monkeypatch):
    import pytest

    G = _guard()
    _setup(monkeypatch, G, mode="enforce")

    async def _boom():
        raise RuntimeError("ai_policy 查询失败")

    monkeypatch.setattr(G, "list_policies", _boom)

    with pytest.raises(G._PolicyLoadError) as ei:
        _run_new(G)

    assert "fail-closed" in str(ei.value) and "策略" in str(ei.value)


def test_domain_load_failure_denies(monkeypatch):
    import pytest

    G = _guard()
    _setup(monkeypatch, G, mode="enforce", policies=(_policy(),))

    async def _boom(user_id):
        raise RuntimeError("ai_data_domain 查询失败")

    monkeypatch.setattr(G, "domain_codes_for_user", _boom)

    with pytest.raises(G._PolicyLoadError):
        _run_new(G)


def test_shadow_skips_diff_when_new_engine_unavailable(monkeypatch):
    """库坏了 → 新判定做不出来：不写差异（假差异会污染灰度报告），旧结论照旧生效。"""
    G = _guard()
    st = _setup(monkeypatch, G, mode="shadow", policies=())

    async def _boom():
        raise RuntimeError("ai_policy 查询失败")

    monkeypatch.setattr(G, "list_policies", _boom)

    async def _legacy():
        return Decision(True, "旧判定放行")

    d = _run(G, legacy_check=_legacy)

    assert d.permit and d.reason == "旧判定放行"
    assert not st.shadow_calls, "新引擎不可用时不能把加载失败记成业务差异"


def test_mode_read_failure_denies(monkeypatch):
    G = _guard()
    _setup(monkeypatch, G)

    async def _boom():
        raise RuntimeError("settings 读不到")

    monkeypatch.setattr(G, "_engine_mode", _boom)

    d = _run(G)

    assert not d.permit
    assert "开关" in d.reason or "fail-closed" in d.reason, d.reason


# ---------------------------------------------------------------------------
# 8. 开关解析（纯函数）
# ---------------------------------------------------------------------------
def test_mode_from_cfg():
    G = _guard()

    assert G._mode_from_cfg(None) == "legacy"
    assert G._mode_from_cfg({}) == "legacy", "缺失默认 legacy（不改配置层）"
    assert G._mode_from_cfg({"policy_engine": ""}) == "legacy"
    assert G._mode_from_cfg({"policy_engine": "shadow"}) == "shadow"
    assert G._mode_from_cfg({"policy_engine": " ENFORCE "}) == "enforce"
    assert G._mode_from_cfg({"policy_engine": "legacy"}) == "legacy"
    assert G._mode_from_cfg({"policy_engine": "nonsense"}) == "legacy", "未知值回退 legacy"


# ---------------------------------------------------------------------------
# 9. 审计参数
# ---------------------------------------------------------------------------
def test_audit_records_decision_and_metadata(monkeypatch):
    G = _guard()
    # shadow：生效结论是「旧判定放行」，审计必须按**生效结论**记 permit
    st = _setup(monkeypatch, G, mode="shadow", policies=(_policy(pid=5),))

    async def _legacy():
        return Decision(True, "旧判定放行")

    _run(G, sql="select a from t", entry="export", datasource="ds:7",
         legacy_check=_legacy)

    call = st.audit_calls[-1]
    assert call["entry"] == "export"
    assert call["datasource"] == "ds:7"
    assert call["sql"] == "select a from t"
    assert call["decision"] == "permit"
    # shadow 下生效结论来自旧判定：它不产 policy_ids，审计里不该出现新引擎的 5
    assert call["policy_ids"] == [], call
    assert isinstance(call["rewrite"], list)
    assert isinstance(call["elapsed_ms"], int) and call["elapsed_ms"] >= 0


def test_guard_does_not_catch_audit_errors(monkeypatch):
    """锁定「guard 自己**不** try/except 审计」：fail-open 由 ``audit.write_access_log`` 保证。

    用一个会抛的桩替身：异常必须原样冒出来（说明 guard 没吞）——生产里真实现不会抛，
    异常已在 T3 内部转成 warning。若哪天有人给 guard 包了 try/except，这条用例会红。
    """
    G = _guard()
    _setup(monkeypatch, G, mode="legacy")

    async def _boom(**kw):
        raise RuntimeError("审计设施炸了")

    monkeypatch.setattr(G, "write_access_log", _boom)

    try:
        _run(G)
    except RuntimeError as e:
        assert "审计设施" in str(e)
    else:  # pragma: no cover
        raise AssertionError("guard 不该包 try/except 审计（会掩盖真实问题）")


# ---------------------------------------------------------------------------
# 10. repo：策略读取
# ---------------------------------------------------------------------------
class _FakeResult:
    def __init__(self, rows):
        self._rows = rows

    def fetchall(self):
        return self._rows


class _FakeSession:
    """够 ``async with async_db_session() as db: db.execute(...)`` 用。"""

    def __init__(self, sink: dict, rows):
        self.sink = sink
        self.rows = rows

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def execute(self, stmt, params=None):
        self.sink["sql"] = str(stmt)
        self.sink["params"] = params
        return _FakeResult(self.rows)


def _repo_session(monkeypatch, repo, sink: dict, rows):
    monkeypatch.setattr(repo, "async_db_session", lambda: _FakeSession(sink, rows))


def test_repo_list_policies_reads_enabled_and_not_deleted(monkeypatch):
    from app.plugin.module_ai.query.policy import repo

    sink: dict = {}
    rows = [
        # id,effect,resource_kind,resource_code,subject_kind,subject_value,
        # condition,columns,mask_expr,marking,priority,enabled
        (1, "allow", "table", "t", "everyone", "", "", '["phone"]', "", "", 100, True),
        (2, "mask", "view", "v", "role", "USER", "", ["name"], "LEFT(name,1)", "sensitive", 50, True),
    ]
    _repo_session(monkeypatch, repo, sink, rows)

    got = asyncio.run(repo.list_policies())

    assert "ai_policy" in sink["sql"]
    assert "enabled" in sink["sql"] and "is_deleted" in sink["sql"], sink["sql"]
    assert [p.id for p in got] == [1, 2]
    assert got[0].columns == ("phone",), "jsonb 读回字符串要解析成元组"
    assert got[1].columns == ("name",) and got[1].mask_expr == "LEFT(name,1)"
    assert got[1].subject_kind == "role" and got[1].resource_kind == "view"
    assert got[0].enabled is True


def test_repo_list_policies_failure_propagates(monkeypatch):
    """repo 不吞异常：fail-closed 由 guard 统一处理（不要两套语义）。"""
    from app.plugin.module_ai.query.policy import repo

    class _Boom:
        def __call__(self):
            raise RuntimeError("db down")

    monkeypatch.setattr(repo, "async_db_session", _Boom())

    try:
        asyncio.run(repo.list_policies())
    except RuntimeError as e:
        assert "db down" in str(e)
    else:  # pragma: no cover
        raise AssertionError("加载失败必须上抛，由 guard 转成 deny")


def test_repo_domain_codes_for_user_filters_members(monkeypatch):
    from app.plugin.module_ai.query.policy import repo

    sink: dict = {}
    rows = [
        ("hr", [7, 9]),
        ("finance", '["7"]'),
        ("sales", [8]),
        ("", [7]),  # 空 code 丢掉
    ]
    _repo_session(monkeypatch, repo, sink, rows)

    got = asyncio.run(repo.domain_codes_for_user(7))

    assert got == ("finance", "hr"), got
    assert "ai_data_domain" in sink["sql"]
    assert "enabled" in sink["sql"] and "is_deleted" in sink["sql"], sink["sql"]


def test_repo_domain_codes_skips_query_without_user(monkeypatch):
    from app.plugin.module_ai.query.policy import repo

    class _Boom:
        def __call__(self):
            raise AssertionError("没有 user_id 不该查库")

    monkeypatch.setattr(repo, "async_db_session", _Boom())

    assert asyncio.run(repo.domain_codes_for_user(None)) == ()
    assert asyncio.run(repo.domain_codes_for_user(0)) == ()


# ---------------------------------------------------------------------------
# 11. 真实表解析（不打桩 _tables_of，走 service._sql_query_scope）
# ---------------------------------------------------------------------------
def test_real_table_scope_denies_table_without_allow(monkeypatch):
    G = _guard()
    _setup(
        monkeypatch,
        G,
        mode="enforce",
        policies=(_policy(resource_code="t"),),
        patch_tables=False,
    )

    d = _run_new(G, sql="select a from public.fuel_price")

    assert not d.permit, "fuel_price 没有 allow，表级默认拒绝"
    assert "fuel_price" in d.reason, d.reason


# ---------------------------------------------------------------------------
# shadow 写入用到的桩工厂
# ---------------------------------------------------------------------------
class _FakeTx:
    def __init__(self, db):
        self.db = db

    async def __aenter__(self):
        return self.db

    async def __aexit__(self, *exc):
        return False


class _FakeWriteDB:
    def __init__(self, sink: dict):
        self.sink = sink

    async def execute(self, stmt, params=None):
        self.sink["sql"] = str(stmt)
        self.sink["params"] = params
        return None


class _FakeWriteSession:
    """够 ``async with <fresh>() as db: async with db.begin(): db.execute(...)`` 用。"""

    def __init__(self, sink: dict):
        self.sink = sink
        self.db = _FakeWriteDB(sink)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    def begin(self):
        return _FakeTx(self.db)

    async def execute(self, stmt, params=None):
        return await self.db.execute(stmt, params)


def _fresh(sink: dict):
    return lambda: _FakeWriteSession(sink)


def _capture_kind(st: _Stubs):
    """在 ``_record_shadow_diff`` 外面套一层，记录调用后交给真实实现（或不写库）。"""

    async def _shadow(**kw):
        st.shadow_calls.append(kw)

    return _shadow
