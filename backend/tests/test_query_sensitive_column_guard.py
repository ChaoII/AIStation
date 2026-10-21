"""问数「内置默认敏感列名单」硬拦（P1-12 方案 b）。

目标：加一块**内置默认敏感列名单**（password/passwd/pwd/secret/token/api_key/...）
作为配置显式标记（``ai_query_asset_columns.sensitive`` / 本体属性 ``sensitive``）
之外的**底板**：凡查询的**返回结果列**命中名单（大小写不敏感，含常见变体）即
**默认拦截、永不返回**。

边界（必须守住）：
- 只拦「返回结果/列」，**不拦 WHERE/JOIN 里的引用**（否则会伤到正常过滤）；
- 与配置标记两层叠加，互不冲突；
- fail-closed：名单命中 → 拒绝（不进入返回结果），绝不静默放行。

本文件是纯逻辑测试（执行层打桩），可用
``PYTEST_NO_APP=1 pytest tests/test_query_sensitive_column_guard.py`` 快速跑。
"""
import asyncio

import pytest


def _run(coro):
    return asyncio.run(coro)


def _auth(uid: int = 42, superuser: bool = False):
    """最小 auth 替身（`_execute_one` 只用 auth.user.id / is_superuser）。"""
    return type("A", (), {"user": type("U", (), {
        "id": uid, "is_superuser": superuser})()})()


TABLE = "video_cameras"


def _patch(monkeypatch, executed: list):
    """打桩：本体改写放行 + 字段级 ACL（**配置标记**）放行 + 执行层。

    ``executed`` 收集真正进入执行层的 SQL —— 内置名单拦截生效时它必须保持为空。
    这里把「配置显式标记」的 ACL（``_ont_sql_violations``）打桩为空，专门隔离并
    测**内置默认名单**这一层。
    """
    import app.plugin.module_ai.query.service as S
    from app.plugin.module_ai.query.service import AiQueryService as Q

    async def _no_violation(sql, uid):
        return []          # 无配置标记 —— 隔离出「内置名单」这一层

    async def _secure(sql, auth):
        return {"sql": sql, "deny": False, "rewritten": [], "msg": ""}

    async def _exec(sql):
        executed.append(sql)
        return {"columns": ["id", "created_time"], "rows": [[1, "2026-01-01"]],
                "took_ms": 1}

    monkeypatch.setattr(Q, "_ont_sql_violations", staticmethod(_no_violation))
    monkeypatch.setattr(S, "_secure_ont_sql", _secure)
    monkeypatch.setattr(S, "_execute_sql", _exec)


# ===========================================================================
# ① 敏感列在 SELECT 返回列中 → 必须被拦（永不返回）
# ===========================================================================
def test_return_password_column_is_blocked(monkeypatch):
    """`SELECT password FROM ...` → 内置名单拦截，不执行任何数据 SQL。"""
    executed: list = []
    _patch(monkeypatch, executed)

    from app.core.exceptions import CustomException
    from app.plugin.module_ai.query.service import AiQueryService as Q

    with pytest.raises(CustomException) as ei:
        _run(Q._execute_one(f"SELECT password FROM {TABLE}", "system", _auth()))
    msg = str(ei.value)
    assert "敏感" in msg, f"返回 password 没被内置名单拦截：{msg}"
    assert "password" in msg, msg
    assert executed == [], f"敏感列查询被执行了：{executed}"


# ===========================================================================
# ② 大小写 / 下划线变体同样被拦
# ===========================================================================
@pytest.mark.parametrize("col", [
    "PASSWORD",          # 大小写不敏感
    "passwd",
    "user_passwd",       # 下划线变体
    "api_token",         # 复合变体
    "access_token",
    "api_key",
    "refresh_token",
    "private_key",
    "encrypt_key",
    "auth_secret",
    "credential",
    "secret",
    "salt",
])
def test_sensitive_variants_are_blocked(monkeypatch, col):
    """`SELECT <变体> FROM ...` → 一律被内置名单拦截。"""
    executed: list = []
    _patch(monkeypatch, executed)

    from app.core.exceptions import CustomException
    from app.plugin.module_ai.query.service import AiQueryService as Q

    with pytest.raises(CustomException) as ei:
        _run(Q._execute_one(f"SELECT {col} FROM {TABLE}", "system", _auth()))
    msg = str(ei.value)
    assert "敏感" in msg, f"变体 {col!r} 没被拦截：{msg}"
    assert col.lower() in msg.lower(), msg
    assert executed == [], f"变体 {col!r} 查询被执行了：{executed}"


# ===========================================================================
# ③ 正向：非敏感列仍能正常返回（别把功能修死）
# ===========================================================================
def test_non_sensitive_columns_still_return(monkeypatch):
    """`SELECT id, created_time FROM ...` → 正常执行并返回，返回结构不变。"""
    executed: list = []
    _patch(monkeypatch, executed)

    from app.plugin.module_ai.query.service import AiQueryService as Q

    out = _run(Q._execute_one(
        f"SELECT id, created_time FROM {TABLE}", "system", _auth()))
    assert out["rows"] == [[1, "2026-01-01"]], out
    assert out["columns"] == ["id", "created_time"], out
    assert len(executed) == 1, f"正常查询没有被执行：{executed}"


# ===========================================================================
# ④ 正向：敏感列只用于 WHERE 条件（不是返回列）→ 功能仍正常（别过度拦截）
# ===========================================================================
def test_sensitive_column_in_where_only_is_allowed(monkeypatch):
    """敏感列**只在过滤条件**引用、不作为返回列 → 不应被拦截。

    这验证「只拦返回结果/列、不拦 WHERE/JOIN 使用」的边界。
    """
    executed: list = []
    _patch(monkeypatch, executed)

    from app.plugin.module_ai.query.service import AiQueryService as Q

    out = _run(Q._execute_one(
        f"SELECT id FROM {TABLE} WHERE password = 'x'", "system", _auth()))
    assert out["rows"] == [[1, "2026-01-01"]], out
    assert executed == [f"SELECT id FROM {TABLE} WHERE password = 'x'"], (
        f"WHERE 里的敏感列不该被拦：{executed}")


# ===========================================================================
# ⑤ fail-closed 且对超管同样生效（底板：永不返回）
# ===========================================================================
def test_sensitive_block_applies_to_superuser(monkeypatch):
    """内置名单是**底板**：即使超管（is_superuser）也不能返回明文敏感列。"""
    executed: list = []
    _patch(monkeypatch, executed)

    from app.core.exceptions import CustomException
    from app.plugin.module_ai.query.service import AiQueryService as Q

    with pytest.raises(CustomException) as ei:
        _run(Q._execute_one(f"SELECT token FROM {TABLE}", "system", _auth(superuser=True)))
    assert "敏感" in str(ei.value), str(ei.value)
    assert executed == [], executed


# ===========================================================================
# ⑥ 结构约束：五条路径共用 `_execute_one` → 内置名单只需写在这一处
# ===========================================================================
def test_default_guard_lives_in_execute_one_choke(monkeypatch):
    """报表 / 指标必须经过 `_execute_one`，因此内置名单只收口在 `_execute_one` 即覆盖全部。"""
    import app.plugin.module_ai.query.service as S
    from app.plugin.module_ai.query.service import AiQueryService as Q

    async def _secure(sql, auth):
        return {"sql": sql, "deny": False, "rewritten": [], "msg": ""}

    async def _exec(sql):
        raise AssertionError("敏感列不该被放行到执行层")

    async def _no_violation(sql, uid):
        return []

    async def _allowed(auth):
        return set()

    def _validate(sql, allowed):
        # 打桩 `validate_sql`：run_report / _execute_metric 在进 `_execute_one` 之前
        # 会各自跑 `_allowed_for_user` + `validate_sql`（真实查库），此处一并桩掉，
        # 让测试能走到 `_execute_one` 收口。注意 validate_sql 是**同步**调用（无 await），
        # 桩必须用同步函数，否则返回 coroutine 会原样污染后续 sql。
        return sql

    monkeypatch.setattr(Q, "_ont_sql_violations", staticmethod(_no_violation))
    monkeypatch.setattr(Q, "_allowed_for_user", staticmethod(_allowed))
    monkeypatch.setattr(S, "_secure_ont_sql", _secure)
    monkeypatch.setattr(S, "_execute_sql", _exec)
    monkeypatch.setattr(S, "validate_sql", _validate)

    # 报表：模板 SELECT 敏感列
    from app.plugin.module_ai.query import report as R
    from app.plugin.module_ai.query.report import run_report
    from app.plugin.module_ai.query.service import _execute_metric

    async def _get(rid):
        return {"id": rid, "key": "R_X", "name": "X", "datasource": "system",
                "sql_template": f"SELECT password FROM {TABLE}", "params": []}

    monkeypatch.setattr(R, "get_report", _get)

    from app.core.exceptions import CustomException

    with pytest.raises(CustomException):
        _run(run_report(1, {}, auth=_auth()))
    # 指标：模板 SELECT 敏感列
    with pytest.raises(CustomException):
        _run(_execute_metric(
            {"key": "m_pwd", "name": "密码", "datasource": "system",
             "sql_template": f"SELECT password FROM {TABLE}"}, {}, _auth()))


# ===========================================================================
# ⑦ 直接单元测试：_default_sensitive_return_cols 只扫投影、不扫 WHERE
# ===========================================================================
def test_default_sensitive_return_cols_ignores_where():
    from app.plugin.module_ai.query.service import _default_sensitive_return_cols

    # 返回列命中 → 报出列名
    assert _default_sensitive_return_cols(
        "SELECT password FROM video_cameras") == ["password"]
    assert _default_sensitive_return_cols(
        "SELECT u.PASSWD FROM users u") == ["PASSWD"]
    assert _default_sensitive_return_cols(
        "SELECT MAX(api_token) FROM users") == ["api_token"]
    # 别名同名也拦（结果列名即敏感名）
    assert _default_sensitive_return_cols(
        "SELECT id AS password FROM users") == ["password"]
    # WHERE 里的敏感列不报
    assert _default_sensitive_return_cols(
        "SELECT id FROM video_cameras WHERE password = 'x'") == []
    # 非敏感列不报
    assert _default_sensitive_return_cols(
        "SELECT id, created_time FROM video_cameras") == []
    # 空 SQL 不报
    assert _default_sensitive_return_cols("") == []
