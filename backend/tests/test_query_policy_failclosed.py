"""Step 1 复审回归：编译器接线的 fail-closed（C1/C2/C3 + I1/I4）。

每条用例都是**真断言**（拒绝/放行 + SQL 内容/调用次数），不靠"没抛异常"通过。
``PYTEST_NO_APP=1`` 可跑（全部打桩外部 IO）。
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from app.plugin.module_ai.query.policy import guard as G
from app.plugin.module_ai.query.policy.engine import Decision, Policy


# ---------------------------------------------------------------------------
# 工具
# ---------------------------------------------------------------------------
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
        "resource_code": "T",
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


class _Deps:
    """guard 的外部 IO 桩（策略/域/列元数据/血缘/审计）。"""

    def __init__(self, *, policies, columns=None, lineage=None, sensitive=()):
        self.policies = list(policies)
        self.columns = dict(columns or {})
        self.lineage = lineage if lineage is not None else {}
        self.lineage_calls: list[tuple[str, str, bool]] = []
        self.sensitive = set(sensitive)
        self.audit_calls: list[dict] = []


def _patch_guard(monkeypatch, *, mode="enforce", deps: _Deps, lineage_raises=False,
                 tables=None):
    async def _mode():
        return mode

    async def _policies():
        return list(deps.policies)

    async def _domains(user_id):
        return ()

    async def _table_columns(datasource, wanted=None, strict=False):
        return {k: list(v) for k, v in deps.columns.items()}

    async def _lineage(datasource, table, strict=False):
        deps.lineage_calls.append((datasource, table, bool(strict)))
        if lineage_raises:
            raise RuntimeError("ai_query_lineage 读取失败")
        return deps.lineage

    async def _audit(**kw):
        deps.audit_calls.append(kw)

    monkeypatch.setattr(G, "_engine_mode", _mode)
    monkeypatch.setattr(G, "list_policies", _policies)
    monkeypatch.setattr(G, "domain_codes_for_user", _domains)
    monkeypatch.setattr(G, "table_columns", _table_columns)
    monkeypatch.setattr(G, "write_access_log", _audit)
    if tables is not None:
        async def _tables(sql, dialect="postgres"):
            return set(tables)
        monkeypatch.setattr(G, "_tables_of", _tables)

    from app.plugin.module_ai.query import lineage as L

    monkeypatch.setattr(L, "lineage_for_table", _lineage)
    return deps


def _new(sql, *, dialect="postgres", datasource="ds:2", principal=None):
    return asyncio.run(
        G._new_decision(
            sql=sql,
            principal=_principal() if principal is None else principal,
            dialect=dialect,
            datasource=datasource,
        )
    )


# ===========================================================================
# C1：取不到表不能跳过 rewrite
# ===========================================================================
def test_mysql_backtick_table_with_column_deny_is_denied(monkeypatch):
    """MySQL 反引号取表（dialect=mysql）→ 列 deny 必须真的拒。"""
    deps = _Deps(
        policies=[
            _policy(pid=1, resource_code="T", columns=("id",)),
            _policy(pid=2, effect="deny", resource_code="T", columns=("secret",)),
        ],
        columns={"T": ["id", "secret"]},
    )
    _patch_guard(monkeypatch, deps=deps)  # 不 patch _tables_of：走真实方言解析

    d = _new("select `T`.`secret` from `T`", dialect="mysql")

    assert not d.permit, (
        "MySQL 反引号查询没取到表 → 跳过了列 deny（fail-open）："
        f"{d.reason!r} / sql={d.sql!r}"
    )
    assert "secret" in d.reason.lower(), d.reason


@pytest.mark.parametrize(
    "sql",
    [
        "vacuum",
        "call myproc()",
        "select 1; delete from T",
        "do $$ begin delete from T; end $$",
    ],
)
def test_enforce_rejects_non_select_and_multi_statement(monkeypatch, sql):
    deps = _Deps(policies=[_policy(pid=1, resource_code="T")])
    _patch_guard(monkeypatch, deps=deps, tables=set())

    d = _new(sql)

    assert not d.permit, f"非 SELECT / 多语句被放行：{sql!r} -> {d.reason!r}"
    assert d.sql == "", "拒绝时不能带可执行 SQL"


def test_select_without_table_still_compiles(monkeypatch):
    deps = _Deps(policies=[])
    _patch_guard(monkeypatch, deps=deps, tables=set())

    d = _new("select 1")

    assert d.permit, d.reason
    assert d.sql, "select 1 也必须走 rewrite 产出可执行 SQL"


def test_enforce_permit_without_compiled_sql_is_denied(monkeypatch):
    """C1.3：enforce 放行但没有编译 SQL → deny（显式超管除外）。"""
    deps = _Deps(policies=[_policy(pid=1, resource_code="T")])
    _patch_guard(monkeypatch, deps=deps, tables={"T"})

    async def _empty_sql(**kw):
        return Decision(True, "stub：没有编译 SQL", sql="")

    monkeypatch.setattr(G, "_new_decision", _empty_sql)

    d = asyncio.run(
        G.prepare(
            sql="select a from T",
            principal=_principal(),
            entry="ask",
            datasource="ds:2",
            dialect="mysql",
        )
    )
    assert not d.permit, "enforce 下 permit + 空 SQL 必须 deny（否则执行原 SQL 绕过策略）"

    d_super = asyncio.run(
        G.prepare(
            sql="select a from T",
            principal=_principal(is_superuser=True),
            entry="ask",
            datasource="ds:2",
            dialect="mysql",
        )
    )
    assert d_super.permit, "显式超管旁路应保留"


# ===========================================================================
# C2：视图大小写 / 血缘失败
# ===========================================================================
def test_uppercase_view_gets_base_table_restriction(monkeypatch):
    """``FROM "V"`` 与 ``FROM "v"`` 同口径：基表行条件必须落到视图上（或拒绝）。"""
    deps = _Deps(
        policies=[
            _policy(pid=1, resource_code="v", resource_kind="table"),
            _policy(pid=2, resource_code="T", condition="dept_id = 3"),
        ],
        columns={"v": ["a", "dept_id"], "T": ["a", "dept_id"]},
        lineage={"upstream": [{"table": "T", "kind": "view"}]},
    )
    _patch_guard(monkeypatch, deps=deps, tables={"V"})

    d = _new('select a from "V"', datasource="ds:4")

    assert not d.permit, (
        "大写视图静默跳过了基表行条件（permit 且 applied 为空就是 fail-open）："
        f"{d.reason!r} applied={d.applied!r}"
    )
    assert "视图" in d.reason or "唯一" in d.reason, d.reason


def test_lineage_read_failure_denies(monkeypatch):
    """血缘读取失败 → deny（不能和"没有血缘"混为一谈）。"""
    deps = _Deps(
        policies=[_policy(pid=1, resource_code="V")],
        columns={"V": ["a"]},
    )
    _patch_guard(
        monkeypatch, deps=deps, tables={"V"}, lineage_raises=True
    )

    d = asyncio.run(
        G.prepare(
            sql='select a from "V"',
            principal=_principal(),
            entry="ask",
            datasource="ds:4",
            dialect="postgres",
        )
    )

    assert not d.permit
    assert "fail-closed" in d.reason or "血缘" in d.reason, d.reason


# ===========================================================================
# C3：无列元数据 + 列级限制 → deny
# ===========================================================================
@pytest.mark.parametrize("effect", ["deny", "mask"])
@pytest.mark.parametrize("metadata", [{}, {"T": ["id"]}])
def test_no_or_partial_metadata_with_column_restriction_denies(
    monkeypatch, effect, metadata
):
    extra = {"columns": ("secret",), "mask_expr": "left(secret, 3)" if effect == "mask" else ""}
    deps = _Deps(
        policies=[
            _policy(pid=1, resource_code="T"),
            _policy(pid=2, effect=effect, resource_code="T", **extra),
        ],
        columns=metadata,
    )
    _patch_guard(monkeypatch, deps=deps, tables={"T"})

    d = _new("select secret from T")

    assert not d.permit, (
        f"列元数据={metadata!r} 且存在 {effect} 策略时仍放行（fail-open）："
        f"{d.reason!r} / sql={d.sql!r}"
    )


def test_no_metadata_without_column_restriction_is_permitted(monkeypatch):
    deps = _Deps(
        policies=[_policy(pid=1, resource_code="T")],
        columns={},
    )
    _patch_guard(monkeypatch, deps=deps, tables={"T"})

    d = _new("select a from T")

    assert d.permit, d.reason
    assert d.sql, d.sql


def test_marking_without_metadata_denies(monkeypatch):
    deps = _Deps(
        policies=[_policy(pid=1, resource_code="T", marking="sensitive")],
        columns={},
    )
    _patch_guard(monkeypatch, deps=deps, tables={"T"})

    d = _new("select a from T")

    assert not d.permit, d.reason


def test_ds_schema_failure_raises_in_strict_mode(monkeypatch):
    from app.plugin.module_ai.query.service import AiQueryService as Q
    from app.plugin.module_ai.query.policy.model import table_columns

    async def _boom(cls, datasource, strict=False):
        raise RuntimeError("读取数据源表结构失败")

    monkeypatch.setattr(Q, "_ds_schema_map", classmethod(_boom))

    with pytest.raises(RuntimeError, match="表结构"):
        asyncio.run(table_columns("ds:4", ["T"], strict=True))


# ===========================================================================
# I1：enforce 必须补 LIMIT（validate_sql）
# ===========================================================================
def test_execute_one_adds_limit_in_enforce(monkeypatch):
    import app.plugin.module_ai.query.service as S
    from app.plugin.module_ai.query.policy import guard
    from app.plugin.module_ai.query.policy import principal as P
    from app.plugin.module_ai.query.service import AiQueryService as Q

    executed: list[str] = []

    async def _secure(sql, auth):
        return {"sql": sql, "deny": False, "rewritten": [], "msg": ""}

    async def _exec(sql):
        executed.append(sql)
        return {"columns": ["a"], "rows": [[1]], "took_ms": 1}

    async def _prepare(**kw):
        return Decision(True, "ok", sql="SELECT a FROM t")

    async def _load_principal(auth, entry="ask"):
        return SimpleNamespace(
            user_id=42, is_superuser=False, roles=(), attrs={}, entry=entry
        )

    async def _allowed(auth):
        return {"t"}

    async def _acl(sql, uid):
        return []

    async def _dialect(cls, datasource):
        return "postgres"

    monkeypatch.setattr(S, "_secure_ont_sql", _secure)
    monkeypatch.setattr(S, "_execute_sql", _exec)
    monkeypatch.setattr(S, "_default_sensitive_return_cols", lambda sql: [])
    monkeypatch.setattr(guard, "prepare", _prepare)
    monkeypatch.setattr(P, "load_principal", _load_principal)
    monkeypatch.setattr(Q, "_allowed_for_user", staticmethod(_allowed))
    monkeypatch.setattr(Q, "_ont_sql_violations", staticmethod(_acl))
    monkeypatch.setattr(Q, "_sql_dialect", classmethod(_dialect))

    auth = SimpleNamespace(user=SimpleNamespace(id=42, is_superuser=False))
    asyncio.run(Q._execute_one("SELECT a FROM t", "system", auth))

    assert executed, "没有执行任何 SQL"
    assert "limit" in executed[0].lower(), (
        f"enforce 执行 SQL 没补 LIMIT（validate_sql 丢了）：{executed[0]}"
    )


# ===========================================================================
# I3：legacy 自定义源不多查方言
# ===========================================================================
def _patch_execute_one_custom(monkeypatch, *, mode, dialect_calls):
    import app.plugin.module_ai.query.service as S
    from app.plugin.module_ai.query.policy import guard
    from app.plugin.module_ai.query.policy import principal as P
    from app.plugin.module_ai.query.service import AiQueryService as Q

    captured: dict = {}

    async def _engine_mode():
        return mode

    async def _dialect(cls, datasource):
        dialect_calls.append(datasource)
        return "mysql"

    async def _prepare(**kw):
        captured.update(kw)
        return Decision(True, "ok")

    async def _load_principal(auth, entry="ask"):
        return SimpleNamespace(
            user_id=42, is_superuser=False, roles=(), attrs={}, entry=entry
        )

    async def _ds_access(ds_id, auth):
        return None

    async def _custom(ds_id, sql, auth):
        return {"columns": ["ID"], "rows": [[1]], "took_ms": 1}

    monkeypatch.setattr(guard, "_engine_mode", _engine_mode)
    monkeypatch.setattr(guard, "prepare", _prepare)
    monkeypatch.setattr(P, "load_principal", _load_principal)
    monkeypatch.setattr(Q, "_sql_dialect", classmethod(_dialect))
    monkeypatch.setattr(S, "_assert_ds_access", _ds_access)
    monkeypatch.setattr(S, "_execute_custom_ds_sql", _custom)

    auth = SimpleNamespace(user=SimpleNamespace(id=42, is_superuser=False))
    asyncio.run(Q._execute_one("SELECT ID FROM T", "ds:7", auth))
    return captured


def test_legacy_custom_ds_uses_real_dialect_for_star_stop(monkeypatch):
    """legacy 也必须用真实方言做星号止血：MySQL 反引号 ``count(*)`` 不能被误杀。"""
    import app.plugin.module_ai.query.service as S
    from app.plugin.module_ai.query.policy import guard
    from app.plugin.module_ai.query.policy import principal as P
    from app.plugin.module_ai.query.service import AiQueryService as Q

    dialect_calls: list[str] = []
    executed: list[str] = []

    async def _engine_mode():
        return "legacy"

    async def _dialect(cls, datasource):
        dialect_calls.append(datasource)
        return "mysql"

    async def _load_principal(auth, entry="ask"):
        return SimpleNamespace(
            user_id=42, is_superuser=False, roles=(), attrs={}, entry=entry
        )

    async def _ds_access(ds_id, auth):
        return None

    async def _custom(ds_id, sql, auth):
        executed.append(sql)
        return {"columns": ["cnt"], "rows": [[1]], "took_ms": 1}

    async def _sensitive():
        return {"ai_models"}  # 非空才会真的去解析 SQL

    async def _audit(**kw):
        return None

    monkeypatch.setattr(guard, "_engine_mode", _engine_mode)
    monkeypatch.setattr(guard, "sensitive_tables", _sensitive)
    monkeypatch.setattr(guard, "write_access_log", _audit)
    monkeypatch.setattr(P, "load_principal", _load_principal)
    monkeypatch.setattr(Q, "_sql_dialect", classmethod(_dialect))
    monkeypatch.setattr(S, "_assert_ds_access", _ds_access)
    monkeypatch.setattr(S, "_execute_custom_ds_sql", _custom)

    auth = SimpleNamespace(user=SimpleNamespace(id=42, is_superuser=False))
    out = asyncio.run(Q._execute_one("select count(*) from `t`", "ds:7", auth))

    assert dialect_calls == ["ds:7"], (
        f"legacy 也必须解析真实方言（否则 postgres 解析 MySQL 反引号会误杀）：{dialect_calls}"
    )
    assert executed and out["rows"] == [[1]], "合法 MySQL count(*) 被星号止血误杀"


@pytest.mark.parametrize(
    "sql",
    [
        "select count(*) from `t`",
        "select count(*) from `t` # comment",
        "select count(*) from `t` force index (idx_a)",
        "select straight_join count(*) from `t`",
    ],
)
def test_mysql_syntax_star_stop_tolerated_with_mysql_dialect(sql):
    """MySQL 专有语法只有用 mysql 方言读才不误判（legacy 也必须传对方言）。"""
    from app.plugin.module_ai.query.policy.star import unexpanded_star

    assert unexpanded_star(sql, {"ai_models"}, "mysql") is None, sql
    assert unexpanded_star(sql, {"ai_models"}, "postgres") == "*", sql


def test_enforce_custom_ds_resolves_dialect(monkeypatch):
    calls: list[str] = []
    captured = _patch_execute_one_custom(
        monkeypatch, mode="enforce", dialect_calls=calls
    )

    assert calls == ["ds:7"], f"enforce 必须按真实方言编译：{calls}"
    assert captured["dialect"] == "mysql", captured


# ===========================================================================
# 收尾回归：CTE 查询 / 血缘表启动建表
# ===========================================================================
def test_validate_sql_accepts_cte():
    from app.plugin.module_ai.query.service import validate_sql

    out = validate_sql("WITH x AS (SELECT 1) SELECT * FROM x", set())

    assert "with" in out.lower() and "limit" in out.lower(), out


def test_validate_sql_rejects_cte_with_delete():
    from app.core.exceptions import CustomException
    from app.plugin.module_ai.query.service import validate_sql

    with pytest.raises(CustomException):
        validate_sql("WITH x AS (DELETE FROM t RETURNING id) SELECT * FROM x", set())


def test_ensure_query_tables_invokes_lineage_ensure(monkeypatch):
    """启动期必须幂等创建 `ai_query_lineage`（否则 enforce 全拒 / shadow 零差异）。"""
    from app.plugin.module_ai.query import lineage as L
    from app.plugin.module_ai.query import service as S
    from app.plugin.module_ai.query.policy import model as PM

    called: list[int] = []

    async def _ensure():
        called.append(1)

    async def _policy():
        return None

    monkeypatch.setattr(S, "_QUERY_TABLES_SQL", ())
    monkeypatch.setattr(S, "_QUERY_ALTER_COLS", ())
    monkeypatch.setattr(PM, "ensure_policy_tables", _policy)
    monkeypatch.setattr(L, "ensure_lineage_table", _ensure)

    asyncio.run(S._ensure_query_tables())

    assert called, "_ensure_query_tables 没有调用 ensure_lineage_table"


def test_lineage_table_created_at_startup(test_client, db_run):
    """启动确保函数跑完后，库里真的有 `ai_query_lineage`。"""
    from sqlalchemy import inspect as sa_inspect

    from app.core.database import async_db_session
    from app.plugin.module_ai.query import service as S

    db_run(S._ensure_query_tables())

    async def _has() -> bool:
        async with async_db_session() as db:
            names = await db.run_sync(
                lambda s: set(sa_inspect(s.connection()).get_table_names())
            )
        return "ai_query_lineage" in names

    assert db_run(_has()) is True



# ===========================================================================
# I4：编译器输入 = 本体安全改写后的 SQL，输出直接执行（只 secure 一次）
# ===========================================================================
def test_execute_one_compiles_secured_sql_and_executes_directly(monkeypatch):
    import app.plugin.module_ai.query.service as S
    from app.plugin.module_ai.query.policy import guard
    from app.plugin.module_ai.query.policy import principal as P
    from app.plugin.module_ai.query.service import AiQueryService as Q

    secured_sql = "SELECT a FROM t WHERE ont_dept_id = 3"
    compiled_sql = (
        "SELECT a FROM (SELECT * FROM t WHERE ont_dept_id = 3 AND policy_dept = 7) AS t"
    )
    secure_calls: list[str] = []
    executed: list[str] = []
    prepared: dict = {}

    async def _secure(sql, auth):
        secure_calls.append(sql)
        return {"sql": secured_sql, "deny": False, "rewritten": [], "msg": ""}

    async def _exec(sql):
        executed.append(sql)
        return {"columns": ["a"], "rows": [[1]], "took_ms": 1}

    async def _prepare(**kw):
        prepared.update(kw)
        return Decision(True, "ok", sql=compiled_sql)

    async def _load_principal(auth, entry="ask"):
        return SimpleNamespace(
            user_id=42, is_superuser=False, roles=(), attrs={}, entry=entry
        )

    async def _allowed(auth):
        return {"t"}

    async def _acl(sql, uid):
        return []

    async def _dialect(cls, datasource):
        return "postgres"

    monkeypatch.setattr(S, "_secure_ont_sql", _secure)
    monkeypatch.setattr(S, "_execute_sql", _exec)
    monkeypatch.setattr(S, "_default_sensitive_return_cols", lambda sql: [])
    monkeypatch.setattr(guard, "prepare", _prepare)
    monkeypatch.setattr(P, "load_principal", _load_principal)
    monkeypatch.setattr(Q, "_allowed_for_user", staticmethod(_allowed))
    monkeypatch.setattr(Q, "_ont_sql_violations", staticmethod(_acl))
    monkeypatch.setattr(Q, "_sql_dialect", classmethod(_dialect))

    auth = SimpleNamespace(user=SimpleNamespace(id=42, is_superuser=False))
    asyncio.run(Q._execute_one("SELECT a FROM t", "system", auth))

    assert secure_calls == ["SELECT a FROM t"], (
        f"本体安全改写必须只跑一次，且输入是原 SQL：{secure_calls}"
    )
    assert prepared["sql"] == "SELECT a FROM t", prepared
    assert prepared["compile_sql"] == secured_sql, (
        f"编译器输入必须是本体安全改写后的 SQL：{prepared.get('compile_sql')!r}"
    )
    assert executed and "ont_dept_id" in executed[0] and "policy_dept" in executed[0], (
        f"执行 SQL 必须同时含本体过滤与策略过滤：{executed}"
    )


def test_compiler_preserves_ontology_filter(monkeypatch):
    """编译 secured SQL：本体行过滤与策略行过滤同时存在（不被覆盖）。"""
    deps = _Deps(
        policies=[_policy(pid=1, resource_code="T", condition="POLICY_FLAG = 1")],
        columns={"T": ["A", "ONT_FLAG", "POLICY_FLAG"]},
    )
    _patch_guard(monkeypatch, deps=deps, tables={"T"})

    d = _new('SELECT "A" FROM "T" WHERE "ONT_FLAG" = 1')

    assert d.permit, d.reason
    assert "ONT_FLAG" in d.sql, d.sql
    assert "POLICY_FLAG" in d.sql, d.sql
