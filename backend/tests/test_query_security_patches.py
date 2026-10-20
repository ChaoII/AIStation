"""问数侧安全三补丁回归（2026-10-19 本体审查后修复）。

1. 报表执行绕过本体权限 —— 用全局表白名单，且不做行/列策略改写
2. 指标结果缓存跨用户共享 —— 缓存 key 不含 user，A 用户按自己权限算出的
   结果会在 TTL 内被 B 拿到
3. 字段级 ACL 只在流式路径生效且 fail-open —— 非流式慢路径根本没调，
   且唯一调用点包着 `except: pass`（出错就放行）

注意：`_run()` 是模块级的 ``asyncio.run`` 助手；**不要**在 async 函数内部再调它
（会撞 "cannot be called from a running event loop"），async 函数里直接 ``await``。
"""
import asyncio

import pytest


def _run(coro):
    return asyncio.run(coro)


def _auth(uid: int = 42):
    """造一个最小的 auth 替身（run_report / _execute_one 只用到 auth.user.id）。"""
    return type("A", (), {"user": type("U", (), {"id": uid})()})()


# ===========================================================================
# 1) 报表必须按用户收窄白名单，并做本体行/列策略改写
# ===========================================================================
def test_run_report_uses_per_user_allowed_tables(monkeypatch):
    """报表（系统库）必须用**按用户收窄**的白名单，不是全局白名单。

    修前：``validate_sql(sql, await _system_allowed())`` —— 数据域/ABAC 完全不生效，
    任何能触发报表的人都能查到全局白名单里的所有表。
    """
    async def _scenario():
        import app.plugin.module_ai.query.service as S
        from app.core.exceptions import CustomException
        from app.plugin.module_ai.query import report as R

        async def _get(rid):
            return {"id": rid, "key": "R_X", "name": "X", "datasource": "system",
                    "sql_template": "SELECT COUNT(*) AS n FROM video_cameras"}

        async def _global_allowed():
            return {"video_cameras", "ai_ont_object"}   # 全局白名单含 video_cameras

        async def _per_user_allowed(auth):
            return {"ai_ont_object"}                    # 该用户被数据域收窄

        async def _secure(sql, auth):
            return {"sql": sql, "deny": False, "rewritten": [], "msg": ""}

        async def _exec(sql):
            raise AssertionError("越权表不该被执行")

        monkeypatch.setattr(R, "get_report", _get)
        monkeypatch.setattr(S, "_system_allowed", _global_allowed)
        monkeypatch.setattr(S.AiQueryService, "_allowed_for_user",
                            staticmethod(_per_user_allowed))
        monkeypatch.setattr(S, "_secure_ont_sql", _secure)
        monkeypatch.setattr(S, "_execute_sql", _exec)

        with pytest.raises(CustomException) as ei:
            await R.run_report(1, {}, auth=_auth())
        return str(ei.value)

    msg = _run(_scenario())
    assert "不在可查询白名单" in msg, f"报表没按用户收窄白名单（越权可查）：{msg}"


def test_run_report_applies_ontology_row_column_rewrite(monkeypatch):
    """报表（系统库）必须过本体行/列策略改写，与问数主链路口径一致。"""
    async def _scenario():
        import app.plugin.module_ai.query.service as S
        from app.plugin.module_ai.query import report as R

        captured = {}

        async def _get(rid):
            return {"id": rid, "key": "R_X", "name": "X", "datasource": "system",
                    "sql_template": "SELECT id FROM video_cameras"}

        async def _per_user_allowed(auth):
            return {"video_cameras"}

        async def _secure(sql, auth):
            captured["called"] = True
            return {"sql": "SELECT id FROM video_cameras /*secured*/",
                    "deny": False, "rewritten": ["video_cameras"], "msg": ""}

        async def _exec(sql):
            captured["exec_sql"] = sql
            return {"columns": ["id"], "rows": [[1]], "took_ms": 1}

        async def _no_acl_violation(sql, uid):
            # P0-3 后报表也走字段级 ACL（与 ask 共用 `_execute_one` 收口）；
            # 这里放行，避免本用例依赖字段资产/本体属性的数据库元数据。
            return []

        monkeypatch.setattr(R, "get_report", _get)
        monkeypatch.setattr(S.AiQueryService, "_allowed_for_user",
                            staticmethod(_per_user_allowed))
        monkeypatch.setattr(S.AiQueryService, "_ont_sql_violations",
                            staticmethod(_no_acl_violation))
        monkeypatch.setattr(S, "_secure_ont_sql", _secure)
        monkeypatch.setattr(S, "_execute_sql", _exec)

        out = await R.run_report(1, {}, auth=_auth())
        return captured, out

    captured, out = _run(_scenario())
    assert captured.get("called"), "报表没过本体行/列策略改写"
    assert "secured" in captured.get("exec_sql", ""), (
        f"执行的不是改写后的 SQL：{captured.get('exec_sql')}")
    assert out["rows"] == [[1]]


# ===========================================================================
# 2) 指标结果缓存 key 必须含 user
# ===========================================================================
def test_metric_cache_key_includes_user():
    """指标缓存 key 必须含 user_id：不同用户不得命中彼此的结果。

    修前：``_cache_key(metric, params)`` 只含 {ds, key, params} ⇒
    A 按自己权限算出的结果，30~120 秒内会被 B 直接拿到（越权读）。
    """
    from app.plugin.module_ai.query.service import AiQueryService as Q

    metric = {"datasource": "system", "key": "m_count"}
    params = {"a": 1}
    try:
        k1 = Q._cache_key(metric, params, user_id=1)
        k2 = Q._cache_key(metric, params, user_id=2)
    except TypeError:
        pytest.fail("_cache_key 还不接受 user_id —— 指标缓存仍跨用户共享")
    assert k1 != k2, f"不同用户的缓存 key 相同（越权读）：{k1}"
    assert Q._cache_key(metric, params, user_id=1) == k1, "同一用户 key 必须稳定"


# ===========================================================================
# 3) 字段级 ACL 必须在共同执行出口生效，且 fail-closed
# ===========================================================================
def test_execute_one_denies_on_column_acl_violation(monkeypatch):
    """``_execute_one``（ask 与 ask_stream 的共同出口）必须跑字段级 ACL。"""
    async def _scenario():
        import app.plugin.module_ai.query.service as S
        from app.core.exceptions import CustomException
        from app.plugin.module_ai.query.service import AiQueryService as Q

        async def _violations(sql, uid):
            return ["video_cameras.password"]

        async def _secure(sql, auth):
            return {"sql": sql, "deny": False, "rewritten": [], "msg": ""}

        async def _exec(sql):
            raise AssertionError("不该执行到这一步（越权字段已放行）")

        monkeypatch.setattr(Q, "_ont_sql_violations", staticmethod(_violations))
        monkeypatch.setattr(S, "_secure_ont_sql", _secure)
        monkeypatch.setattr(S, "_execute_sql", _exec)

        with pytest.raises(CustomException) as ei:
            await Q._execute_one("SELECT password FROM video_cameras", "system", _auth())
        return str(ei.value)

    msg = _run(_scenario())
    assert "字段级权限" in msg, msg


def test_execute_one_fails_closed_when_acl_check_errors(monkeypatch):
    """字段级 ACL 检查自身出错时必须 **fail-closed**（拒绝），不能放行。

    修前：唯一调用点包着 ``except Exception: pass`` ⇒ 检查一炸就等于没做，
    受限字段被原样查出来。
    """
    async def _scenario():
        import app.plugin.module_ai.query.service as S
        from app.core.exceptions import CustomException
        from app.plugin.module_ai.query.service import AiQueryService as Q

        async def _violations(sql, uid):
            raise RuntimeError("元数据查询失败")

        async def _secure(sql, auth):
            return {"sql": sql, "deny": False, "rewritten": [], "msg": ""}

        async def _exec(sql):
            raise AssertionError("检查失败时不该放行执行")

        monkeypatch.setattr(Q, "_ont_sql_violations", staticmethod(_violations))
        monkeypatch.setattr(S, "_secure_ont_sql", _secure)
        monkeypatch.setattr(S, "_execute_sql", _exec)

        with pytest.raises(CustomException) as ei:
            await Q._execute_one("SELECT id FROM video_cameras", "system", _auth())
        return str(ei.value)

    msg = _run(_scenario())
    assert "权限" in msg, f"检查失败时没有拒绝（fail-open）：{msg}"


def test_execute_one_passes_when_no_violation(monkeypatch):
    """无违规时不应被误伤（超管/公开字段照常执行）。"""
    async def _scenario():
        import app.plugin.module_ai.query.service as S
        from app.plugin.module_ai.query.service import AiQueryService as Q

        async def _violations(sql, uid):
            return []   # 超管：无违规

        async def _secure(sql, auth):
            return {"sql": sql, "deny": False, "rewritten": [], "msg": ""}

        async def _exec(sql):
            return {"columns": ["id"], "rows": [[1]], "took_ms": 1}

        monkeypatch.setattr(Q, "_ont_sql_violations", staticmethod(_violations))
        monkeypatch.setattr(S, "_secure_ont_sql", _secure)
        monkeypatch.setattr(S, "_execute_sql", _exec)

        return await Q._execute_one("SELECT id FROM video_cameras", "system", _auth(1))

    out = _run(_scenario())
    assert out["rows"] == [[1]], out


# ===========================================================================
# 4) 敏感字段放行规则必须命中**当前用户**
# ===========================================================================
def test_can_see_sensitive_is_scoped_to_user_roles(monkeypatch):
    """``sensitive_ok`` 放行规则必须按 attribute/value 命中当前用户。

    修前：``_can_see_sensitive`` 只判断"存在**任一**启用且 sensitive_ok 的规则"，
    完全不看它是否针对当前用户 ⇒ dev 库里一条 ``role=ADMIN`` 的放行规则，
    让**所有用户**都能看敏感字段，字段级 ACL 形同虚设（被短路）。
    """
    async def _scenario():
        from app.plugin.module_ai.query.service import AiQueryService as Q

        rule = {"id": 1, "name": "仅管理员可看敏感字段", "attribute": "role",
                "value": "ADMIN", "allowed_tables": [], "sensitive_ok": True,
                "enabled": True}

        async def _rules():
            return [rule]

        async def _roles(uid: int) -> set[str]:
            return {"ADMIN"} if uid == 3 else {"GUEST"}

        monkeypatch.setattr(Q, "list_access_rules", staticmethod(_rules))
        monkeypatch.setattr(Q, "_user_role_codes_by_id", staticmethod(_roles))

        # 2：非超管且无 ADMIN 角色；3：非超管但有 ADMIN 角色
        return await Q._can_see_sensitive(2), await Q._can_see_sensitive(3)

    guest, admin = _run(_scenario())
    assert guest is False, (
        "非 ADMIN 用户被一条 role=ADMIN 的放行规则放行了 —— 字段级 ACL 被短路")
    assert admin is True, "有 ADMIN 角色的用户应被放行"
