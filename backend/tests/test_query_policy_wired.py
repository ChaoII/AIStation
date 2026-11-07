"""Task 7：``_execute_one`` 接入唯一收口 ``QueryGuard.prepare``。

本文件锁定四件事（全部纯逻辑，``PYTEST_NO_APP=1`` 可跑）：

1. **唯一收口真的接上了**：系统库取数必经 ``guard.prepare``，且 ``entry`` /
   ``datasource`` / ``sql`` / ``principal`` 原样透传（默认 ``entry="ask"``）；
2. **legacy 行为不变**：``legacy_check`` 就是改造前的旧校验组合
   （``validate_sql`` + ``_ont_sql_violations``），异常/文案/顺序与改造前一致，
   且同一请求里字段级 ACL **只算一遍**（复用 ``legacy_check`` 的结果）；
3. **编译结果按需执行**：``decision.sql`` 非空（enforce 编译产出）时用它执行；
   为空（legacy/shadow）仍执行原 SQL。字段级 ACL 在 guard 之后仍是一层独立检查
   （enforce 的引擎判定不能替代列级 ACL）；
4. **开关可打开**：``policy_engine`` 有默认键（legacy），``POLICY_ENGINE`` 环境变量
   可覆盖（addendum 第 1 条）；审计不记录「没施加的改写」（addendum 第 2 条）。
"""

import asyncio
from types import SimpleNamespace

import pytest

from app.plugin.module_ai.query.policy.engine import Decision

SQL = "SELECT name FROM video_cameras"
TABLE = "video_cameras"


def _run(coro):
    return asyncio.run(coro)


def _auth(uid: int = 42, superuser: bool = False):
    """最小 auth 替身（与既有 ACL 用例同口径：`_execute_one` 只用 user.id/superuser）。"""
    return SimpleNamespace(
        user=SimpleNamespace(id=uid, is_superuser=superuser))


class _Recorder:
    """记录 stubs 调用情况。"""

    def __init__(self):
        self.prepare_kwargs: dict = {}
        self.prepare_calls: int = 0
        self.principal_entries: list[str] = []
        self.validate_calls: list[tuple[str, set]] = []
        self.allowed_calls: int = 0
        self.violation_calls: list[tuple[str, int | None]] = []
        self.executed: list[str] = []


def _patch_env(
    monkeypatch,
    *,
    decision: Decision | None = None,
    violations=(),
    raise_on_violations: Exception | None = None,
    allowed=(TABLE,),
    call_legacy: bool = False,
    secure_sql: str | None = None,
    validate_raises: Exception | None = None,
) -> _Recorder:
    """把 ``_execute_one`` 的外部依赖全部打桩（DB/执行层/守卫）。

    ``call_legacy=True`` 时 prepare 桩照 guard ``legacy`` 模式的做法**真的调用**
    ``legacy_check`` —— 用来验证旧校验组合与异常语义；否则直接返回 ``decision``。
    """
    import app.plugin.module_ai.query.service as S
    from app.plugin.module_ai.query.policy import guard
    from app.plugin.module_ai.query.policy import principal as P
    from app.plugin.module_ai.query.service import AiQueryService as Q

    rec = _Recorder()

    async def _allowed_for_user(auth):
        rec.allowed_calls += 1
        return set(allowed)

    async def _ont_violations(sql, uid):
        rec.violation_calls.append((sql, uid))
        if raise_on_violations is not None:
            raise raise_on_violations
        return list(violations)

    def _validate(sql, allowed_tables, question=""):
        rec.validate_calls.append((sql, set(allowed_tables)))
        if validate_raises is not None:
            raise validate_raises
        return sql

    async def _secure(sql, auth):
        return {"sql": secure_sql if secure_sql is not None else sql,
                "deny": False, "rewritten": [], "msg": ""}

    async def _exec(sql):
        rec.executed.append(sql)
        return {"columns": ["name"], "rows": [["cam-1"]], "took_ms": 1}

    async def _dialect(cls, datasource):
        return "postgres"

    async def _prepare(**kw):
        rec.prepare_calls += 1
        rec.prepare_kwargs = dict(kw)
        if call_legacy:
            return await kw["legacy_check"]()
        return decision if decision is not None else Decision(True, "ok")

    async def _load_principal(auth, entry="ask"):
        rec.principal_entries.append(entry)
        return SimpleNamespace(user_id=42, is_superuser=False, roles=(), attrs={},
                               entry=entry)

    monkeypatch.setattr(Q, "_allowed_for_user", staticmethod(_allowed_for_user))
    monkeypatch.setattr(Q, "_ont_sql_violations", staticmethod(_ont_violations))
    monkeypatch.setattr(Q, "_sql_dialect", classmethod(_dialect))
    monkeypatch.setattr(S, "validate_sql", _validate)
    monkeypatch.setattr(S, "_secure_ont_sql", _secure)
    monkeypatch.setattr(S, "_execute_sql", _exec)
    monkeypatch.setattr(guard, "prepare", _prepare)
    monkeypatch.setattr(P, "load_principal", _load_principal)
    return rec


# ===========================================================================
# ① 收口真的接上了：prepare 被调用，参数原样透传
# ===========================================================================
def test_execute_one_calls_guard_with_principal_and_entry(monkeypatch):
    """系统库执行必经 ``guard.prepare``，entry/数据源/SQL/主体都透传。"""
    rec = _patch_env(monkeypatch)

    from app.plugin.module_ai.query.service import AiQueryService as Q

    out = _run(Q._execute_one(SQL, "system", _auth(), entry="report"))

    assert rec.prepare_calls == 1, "系统库取数没有经过 guard.prepare（唯一收口没接上）"
    kw = rec.prepare_kwargs
    assert kw["sql"] == SQL, kw
    assert kw["datasource"] == "system", kw
    assert kw["entry"] == "report", f"entry 没透传：{kw.get('entry')!r}"
    assert kw["principal"] is not None, "principal 没装载"
    assert kw["principal"].user_id == 42, kw["principal"]
    assert rec.principal_entries == ["report"], (
        f"load_principal 没拿到调用方的 entry：{rec.principal_entries}")
    assert rec.executed == [SQL], f"放行后应执行原 SQL：{rec.executed}"
    assert out["rows"] == [["cam-1"]], out


def test_execute_one_defaults_entry_to_ask(monkeypatch):
    """不传 entry 时默认 ``ask``（既有调用点零改动即符合口径）。"""
    rec = _patch_env(monkeypatch)

    from app.plugin.module_ai.query.service import AiQueryService as Q

    _run(Q._execute_one(SQL, "system", _auth()))

    assert rec.prepare_kwargs["entry"] == "ask", rec.prepare_kwargs
    assert rec.principal_entries == ["ask"], rec.principal_entries


def test_report_and_metric_pass_their_own_entry(monkeypatch):
    """报表/指标两条复用路径必须各自传 ``report`` / ``metric``（审计能区分入口）。"""
    import app.plugin.module_ai.query.report as R
    import app.plugin.module_ai.query.service as S
    from app.plugin.module_ai.query.service import AiQueryService as Q

    seen: list[tuple[str, str]] = []

    async def _one(cls, sql, datasource, auth, *args, **kwargs):
        seen.append((kwargs.get("entry"), sql))
        return {"columns": ["c"], "rows": [[1]], "took_ms": 1, "sql": sql}

    async def _get_report(rid):
        return {"id": rid, "key": "R_E", "name": "入口用例", "datasource": "system",
                "sql_template": f"SELECT name FROM {TABLE}", "params": []}

    async def _allowed(auth):
        return {TABLE}

    def _validate(sql, allowed_tables, question=""):
        return sql

    monkeypatch.setattr(Q, "_execute_one", classmethod(_one))
    monkeypatch.setattr(Q, "_allowed_for_user", staticmethod(_allowed))
    monkeypatch.setattr(S, "validate_sql", _validate)
    monkeypatch.setattr(R, "get_report", _get_report)

    _run(R.run_report(1, {}, auth=_auth()))
    _run(S._execute_metric(
        {"key": "m_e", "name": "入口用例", "datasource": "system",
         "sql_template": f"SELECT name FROM {TABLE}"}, {}, _auth()))

    assert [e for e, _ in seen] == ["report", "metric"], (
        f"报表/指标的 entry 没按入口区分：{seen}")


# ===========================================================================
# ② legacy 行为不变：旧校验组合就是 validate_sql + _ont_sql_violations
# ===========================================================================
def test_legacy_check_combines_whitelist_and_field_acl(monkeypatch):
    """``legacy_check`` = 白名单校验 + 字段级 ACL（两者都被调用）。"""
    rec = _patch_env(monkeypatch, call_legacy=True)

    from app.plugin.module_ai.query.service import AiQueryService as Q

    _run(Q._execute_one(SQL, "system", _auth()))

    assert rec.validate_calls == [(SQL, {TABLE})], (
        f"legacy_check 没跑 validate_sql（旧白名单校验丢失）：{rec.validate_calls}")
    assert rec.violation_calls == [(SQL, 42)], (
        f"legacy_check 没跑字段级 ACL：{rec.violation_calls}")
    assert rec.executed == [SQL], f"无违规时应正常执行：{rec.executed}"


def test_legacy_check_denies_field_acl_violation_with_old_message(monkeypatch):
    """字段级 ACL 命中 → 拒绝，文案与改造前一致（前端/评测依赖这句话）。"""
    rec = _patch_env(
        monkeypatch, call_legacy=True, violations=["video_cameras.password"])

    from app.core.exceptions import CustomException
    from app.plugin.module_ai.query.service import AiQueryService as Q

    with pytest.raises(CustomException) as ei:
        _run(Q._execute_one(SQL, "system", _auth()))
    msg = ei.value.msg
    assert "字段级权限" in msg, f"越权字段被放行了（旧行为变了）：{msg}"
    assert "video_cameras.password" in msg, msg
    assert rec.executed == [], f"越权字段的 SQL 被执行了：{rec.executed}"


def test_field_acl_computed_once_per_request(monkeypatch):
    """同一请求里字段级 ACL 只算一遍（legacy_check 的结果被复用，不重复查元数据）。"""
    rec = _patch_env(monkeypatch, call_legacy=True)

    from app.plugin.module_ai.query.service import AiQueryService as Q

    _run(Q._execute_one(SQL, "system", _auth()))

    assert len(rec.violation_calls) == 1, (
        f"字段级 ACL 被算了 {len(rec.violation_calls)} 遍（每次问数多一轮元数据查询）："
        f"{rec.violation_calls}")


def test_legacy_check_keeps_fail_closed_on_acl_error(monkeypatch):
    """ACL 自身出错 → fail-closed，文案沿用「字段级权限校验失败，已拒绝执行」。"""
    rec = _patch_env(
        monkeypatch, call_legacy=True,
        raise_on_violations=RuntimeError("元数据查询失败"))

    from app.core.exceptions import CustomException
    from app.plugin.module_ai.query.service import AiQueryService as Q

    with pytest.raises(CustomException) as ei:
        _run(Q._execute_one(SQL, "system", _auth()))
    assert "拒绝执行" in ei.value.msg, f"ACL 出错时放行了（fail-open）：{ei.value.msg}"
    assert rec.executed == [], f"ACL 出错时仍执行了 SQL：{rec.executed}"


def test_legacy_check_propagates_validate_sql_error(monkeypatch):
    """白名单校验失败照旧上抛原异常（guard 不能把它吞成一条笼统的 deny）。"""
    from app.core.exceptions import CustomException
    from app.plugin.module_ai.query.service import AiQueryService as Q

    rec = _patch_env(
        monkeypatch, call_legacy=True,
        validate_raises=CustomException(msg="表「hack」不在可查询白名单内"))

    with pytest.raises(CustomException) as ei:
        _run(Q._execute_one(SQL, "system", _auth()))
    assert "不在可查询白名单内" in ei.value.msg, ei.value.msg
    assert rec.executed == [], rec.executed


# ===========================================================================
# ③ guard 拒绝 / P1 不改写
# ===========================================================================
def test_guard_deny_raises_with_reason_and_skips_execution(monkeypatch):
    """guard 拒绝 → 抛 CustomException(reason)，一条数据 SQL 都不执行。"""
    rec = _patch_env(monkeypatch, decision=Decision(False, "表 video_cameras 拒绝：deny"))

    from app.core.exceptions import CustomException
    from app.plugin.module_ai.query.service import AiQueryService as Q

    with pytest.raises(CustomException) as ei:
        _run(Q._execute_one(SQL, "system", _auth()))
    assert "video_cameras" in ei.value.msg and "拒绝" in ei.value.msg, ei.value.msg
    assert rec.executed == [], f"被拒的 SQL 仍被执行：{rec.executed}"


def test_decision_sql_is_used_when_present(monkeypatch):
    """enforce 的编译结果必须用于执行（行过滤/掩码才真正生效）。

    legacy / shadow 的 ``decision.sql`` 为空 → 执行原 SQL；只有编译器产出非空
    ``decision.sql`` 时才替换执行语句。
    """
    compiled = 'SELECT name FROM (SELECT * FROM video_cameras WHERE dept_id = 3) AS x'
    rec = _patch_env(
        monkeypatch,
        decision=Decision(True, "ok", sql=compiled),
    )

    from app.plugin.module_ai.query.service import AiQueryService as Q

    _run(Q._execute_one(SQL, "system", _auth()))

    assert rec.executed == [compiled], (
        f"执行用的不是编译后的 SQL（行/列策略不会生效）：{rec.executed}")


def test_field_acl_still_runs_when_guard_engine_decides(monkeypatch):
    """guard 没走 legacy_check（enforce 只做表级）时，列级 ACL 仍要独立生效。"""
    rec = _patch_env(
        monkeypatch,  # 不调用 legacy_check：模拟 enforce 由引擎给结论
        decision=Decision(True, "新引擎放行"),
        violations=["video_cameras.password"],
    )

    from app.core.exceptions import CustomException
    from app.plugin.module_ai.query.service import AiQueryService as Q

    with pytest.raises(CustomException) as ei:
        _run(Q._execute_one(SQL, "system", _auth()))
    assert "字段级权限" in ei.value.msg, (
        f"切到新引擎后列级 ACL 丢失了（越权字段可读）：{ei.value.msg}")
    assert rec.executed == [], rec.executed


def test_custom_datasource_also_goes_through_guard(monkeypatch):
    """自定义数据源同样经过唯一收口（旧判定换成数据源授权校验）。

    ds:* 是真实主链路（冒烟就是 ds:4）。若在这里提前 return，星号止血/主体校验/审计
    全部绕过；字段级 ACL 与系统表白名单不适用外部库，故不进它的 legacy_check。
    """
    rec = _patch_env(monkeypatch, call_legacy=True)

    import app.plugin.module_ai.query.service as S
    from app.plugin.module_ai.query.service import AiQueryService as Q

    ds_checks: list[tuple[int, object]] = []

    async def _assert_ds(ds_id, auth):
        ds_checks.append((ds_id, auth))

    async def _custom(ds_id, sql, auth):
        rec.executed.append(f"ds:{ds_id}")
        return {"columns": ["ID"], "rows": [[1]], "took_ms": 1}

    monkeypatch.setattr(S, "_assert_ds_access", _assert_ds)
    monkeypatch.setattr(S, "_execute_custom_ds_sql", _custom)

    out = _run(Q._execute_one("SELECT ID FROM t", "ds:7", _auth(), entry="report"))

    assert rec.prepare_calls == 1, "自定义数据源绕过了唯一收口"
    assert rec.prepare_kwargs["datasource"] == "ds:7", rec.prepare_kwargs
    assert rec.prepare_kwargs["entry"] == "report", rec.prepare_kwargs
    assert rec.prepare_kwargs["principal"] is not None
    assert [d for d, _ in ds_checks] == [7], f"旧判定没跑数据源授权校验：{ds_checks}"
    assert rec.validate_calls == [], (
        f"系统表白名单不该用于外部库（会误杀）：{rec.validate_calls}")
    assert rec.executed == ["ds:7"], rec.executed
    assert out["rows"] == [[1]], out


def test_custom_datasource_uses_compiled_sql(monkeypatch):
    """自定义数据源同样执行 ``decision.sql``（ds:* 不能绕过行/列策略）。"""
    compiled = 'SELECT "ID" FROM (SELECT * FROM "T" WHERE "ID" > 1) AS "T"'
    _patch_env(monkeypatch, decision=Decision(True, "ok", sql=compiled))

    import app.plugin.module_ai.query.service as S
    from app.plugin.module_ai.query.service import AiQueryService as Q

    seen: list[str] = []

    async def _assert_ds(ds_id, auth):
        return None

    async def _custom(ds_id, sql, auth):
        seen.append(sql)
        return {"columns": ["ID"], "rows": [[2]], "took_ms": 1}

    monkeypatch.setattr(S, "_assert_ds_access", _assert_ds)
    monkeypatch.setattr(S, "_execute_custom_ds_sql", _custom)

    out = _run(Q._execute_one("SELECT ID FROM T", "ds:7", _auth()))

    assert seen == [compiled], f"自定义数据源没用编译后的 SQL：{seen}"
    assert out["rows"] == [[2]], out


def test_custom_datasource_denied_when_access_check_fails(monkeypatch):
    """无数据源权限 → 旧判定照旧上抛，且一条外部 SQL 都不执行。"""
    rec = _patch_env(monkeypatch, call_legacy=True)

    import app.plugin.module_ai.query.service as S
    from app.core.exceptions import CustomException
    from app.plugin.module_ai.query.service import AiQueryService as Q

    async def _assert_ds(ds_id, auth):
        raise CustomException(msg="您无权限访问该数据源")

    async def _custom(ds_id, sql, auth):  # pragma: no cover - 不该被调用
        rec.executed.append(f"ds:{ds_id}")
        return {}

    monkeypatch.setattr(S, "_assert_ds_access", _assert_ds)
    monkeypatch.setattr(S, "_execute_custom_ds_sql", _custom)

    with pytest.raises(CustomException) as ei:
        _run(Q._execute_one("SELECT ID FROM t", "ds:7", _auth()))
    assert "无权限访问该数据源" in ei.value.msg, ei.value.msg
    assert rec.executed == [], f"无权限的数据源仍被执行：{rec.executed}"


def test_execute_one_without_auth_is_denied(monkeypatch):
    """``auth=None`` 必须 deny（P0 验收：无主体不得落库 permit）。

    guard 层已有用例；这里锁的是**接线后**的端到端行为：`_execute_one` 真的会被
    无身份调用（内部/定时），不能因为"没传 auth"就退化成放行。
    """
    import app.plugin.module_ai.query.service as S
    from app.core.exceptions import CustomException
    from app.plugin.module_ai.query.policy import guard
    from app.plugin.module_ai.query.service import AiQueryService as Q

    executed: list[str] = []
    audited: list[dict] = []

    async def _secure(sql, auth):
        return {"sql": sql, "deny": False, "rewritten": [], "msg": ""}

    async def _exec(sql):  # pragma: no cover - 不该被调用
        executed.append(sql)
        return {"columns": ["name"], "rows": [["x"]], "took_ms": 1}

    async def _audit(**kw):
        audited.append(kw)

    monkeypatch.setattr(S, "_secure_ont_sql", _secure)
    monkeypatch.setattr(S, "_execute_sql", _exec)
    monkeypatch.setattr(guard, "write_access_log", _audit)

    with pytest.raises(CustomException) as ei:
        _run(Q._execute_one(SQL, "system", None))

    assert "missing principal" in ei.value.msg, ei.value.msg
    assert executed == [], f"无主体时仍执行了 SQL：{executed}"
    assert audited and audited[-1]["decision"] == "deny", (
        f"无主体拒绝没有落审计：{audited}")


def test_datasource_none_normalizes_to_system(monkeypatch):
    """``datasource=None`` 按系统库处理（guard 收到的必须是 ``system``，不是 None）。"""
    rec = _patch_env(monkeypatch)

    from app.plugin.module_ai.query.service import AiQueryService as Q

    _run(Q._execute_one(SQL, None, _auth()))

    assert rec.prepare_kwargs["datasource"] == "system", (
        f"datasource 没归一成 system：{rec.prepare_kwargs.get('datasource')!r}")
    assert rec.executed == [SQL], rec.executed


# ===========================================================================
# ④ 开关可打开（addendum 第 1 条）
# ===========================================================================
def test_policy_engine_has_default_key(monkeypatch):
    """``policy_engine`` 必须在默认值表里（新库/空设置表上也读得到 ``legacy``）。

    行为断言，不做源码字符串匹配：把 ``async_db_session`` 换成"设置表为空"的假会话，
    让 ``get_settings()`` 走**真实**默认值路径，再断言 ``_cfg()`` 里有这个键。
    """
    from contextlib import asynccontextmanager

    import app.plugin.module_ai.query.service as S
    from app.plugin.module_ai.query.service import AiQueryService as Q

    class _EmptyResult:
        def scalars(self):
            return self

        def all(self):
            return []

    class _FakeDB:
        async def execute(self, *args, **kwargs):  # noqa: ANN002, ANN003
            return _EmptyResult()

    @asynccontextmanager
    async def _fake_session():
        yield _FakeDB()

    monkeypatch.setattr(S, "async_db_session", _fake_session)
    monkeypatch.setattr(S, "_SETTINGS_CACHE", None)
    monkeypatch.delenv("POLICY_ENGINE", raising=False)

    cfg = _run(Q._cfg())
    assert cfg.get("policy_engine") == "legacy", (
        f"默认值表里没有 policy_engine（设置页看不到、线上也切不动）：{cfg.get('policy_engine')!r}")


def test_policy_engine_env_override(monkeypatch):
    """``POLICY_ENGINE`` 环境变量能实时覆盖 ``_cfg()['policy_engine']``（不用清缓存）。"""
    import app.plugin.module_ai.query.service as S
    from app.plugin.module_ai.query.service import AiQueryService as Q

    monkeypatch.setattr(S, "_SETTINGS_CACHE", {"policy_engine": "legacy"})
    monkeypatch.delenv("POLICY_ENGINE", raising=False)
    assert _run(Q._cfg())["policy_engine"] == "legacy"

    monkeypatch.setenv("POLICY_ENGINE", "shadow")
    assert _run(Q._cfg())["policy_engine"] == "shadow", (
        "改环境变量后 _cfg()['policy_engine'] 没变成 shadow")

    # 任务内覆盖（评测消融）比环境变量更具体：必须赢
    with S.config_override({"policy_engine": "enforce"}):
        assert _run(Q._cfg())["policy_engine"] == "enforce", (
            "config_override 被环境变量盖掉了（消融实验会跑在错的开关下）")


# ===========================================================================
# ⑤ 审计不记录「没施加的改写」（addendum 第 2 条）
# ===========================================================================
def test_guard_audit_does_not_record_planned_rewrite(monkeypatch):
    """P1 不执行改写：审计的 rewrite 必须是 ``[]``（计划中的行过滤只进 shadow 差异表）。"""
    from app.plugin.module_ai.query.policy import guard
    from app.plugin.module_ai.query.policy.principal import Principal

    captured: dict = {}

    async def _mode():
        return "legacy"

    async def _audit(**kw):
        captured.update(kw)

    async def _legacy():
        return Decision(True, "legacy 放行", applied=({"row": "dept_id = 3"},))

    monkeypatch.setattr(guard, "_engine_mode", _mode)
    monkeypatch.setattr(guard, "write_access_log", _audit)

    decision = _run(guard.prepare(
        sql="select name from video_cameras",
        principal=Principal(user_id=7, is_superuser=False, roles=(), attrs={},
                            entry="ask"),
        entry="ask",
        datasource="system",
        legacy_check=_legacy,
    ))

    assert decision.permit, decision
    assert list(decision.applied), "桩应带一条「计划中的改写」"
    assert captured["rewrite"] == [], (
        f"审计把计划中的改写记成了已施加：{captured['rewrite']}")
