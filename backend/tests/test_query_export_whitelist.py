"""问数数据资产三入口（导出/浏览/质量规则）的白名单与标识符校验回归（P0-1）。

修前：``export_asset`` / ``object_browse`` / ``dq_rules_run`` 把路径/查询参数
**直接拼进 SELECT**（``f'SELECT * FROM "{table_name}" LIMIT …'``），完全绕过
问数主链路的两道既有护栏：

  1. ``_allowed_for_user(auth)`` —— 按用户（数据域/ABAC）收窄的可查表白名单；
  2. ``validate_sql`` —— 只读/单语句/白名单校验（正则层 ``\\bfrom\\s+([A-Za-z_]…)``
     对 ``FROM "x"`` 这种**带引号**的表名不匹配，所以单纯套它也不够，
     必须先做「合法标识符」校验再拼 SQL）。

后果：任何持有 ``module_ai:query:ask`` 权限的人都能 ``export sys_user`` 拿到
密码哈希；表名含 ``"`` 即可闭合引号注入任意 SQL（psycopg2 允许多语句）。

修后：三入口统一先过「合法标识符 + 按用户白名单」校验（fail-closed，校验失败
抛 CustomException），且校验发生在**任何 SQL 拼接/执行**之前。

本文件是纯逻辑测试（monkeypatch 掉白名单与数据库），可用
``PYTEST_NO_APP=1 pytest tests/test_query_export_whitelist.py`` 快速跑。
"""
import asyncio

import pytest


def _run(coro):
    return asyncio.run(coro)


def _auth(uid: int = 42):
    """最小 auth 替身（``_allowed_for_user`` 被 monkeypatch，不会走真实权限链）。"""
    return type("A", (), {"user": type("U", (), {"id": uid, "is_superuser": False})()})()


#: 白名单外的表名（典型：被数据域/ABAC 收窄的用户不该看到 sys_user）
OUT_TABLE = "sys_user"

#: 注入串：闭合引号 + 多语句 DROP（psycopg2 允许多语句执行）
INJECT = 'x"; DROP TABLE ai_query_settings; --'


async def _restricted_allowed(auth):
    """模拟被数据域收窄的用户：只允许查 ai_models。"""
    return {"ai_models"}


def _no_db(*_a, **_k):
    raise AssertionError("未过白名单校验就碰了数据库（校验没在拼 SQL 前生效）")


def _patch(monkeypatch):
    import app.plugin.module_ai.query.service as S

    monkeypatch.setattr(S.AiQueryService, "_allowed_for_user",
                        staticmethod(_restricted_allowed))
    monkeypatch.setattr(S, "async_db_session", _no_db)


# ===========================================================================
# export_asset：数据集导出
# ===========================================================================
def test_export_asset_rejects_non_whitelist_table(monkeypatch):
    """白名单外表必须被拒绝（fail-closed 抛错），且不碰数据库。"""
    _patch(monkeypatch)
    from app.core.exceptions import CustomException
    from app.plugin.module_ai.query.service import AiQueryService as Q

    with pytest.raises(CustomException) as ei:
        _run(Q.export_asset(OUT_TABLE, _auth(), limit=10))
    assert "白名单" in str(ei.value), (
        f"白名单外表 {OUT_TABLE} 没被拒绝（可导出任意表，越权读）：{ei.value}")


def test_export_asset_rejects_injection_table_name(monkeypatch):
    """表名注入串（闭合引号 + 多语句）必须被标识符校验直接拒绝。"""
    _patch(monkeypatch)
    from app.core.exceptions import CustomException
    from app.plugin.module_ai.query.service import AiQueryService as Q

    with pytest.raises(CustomException) as ei:
        _run(Q.export_asset(INJECT, _auth(), limit=10))
    assert "非法表名" in str(ei.value), (
        f"注入表名没被拒绝（SQL 注入）：{ei.value}")


# ===========================================================================
# object_browse：对象数据浏览器
# ===========================================================================
def test_object_browse_rejects_non_whitelist_table(monkeypatch):
    """白名单外表必须被拒绝（fail-closed 抛错），且不碰数据库。"""
    _patch(monkeypatch)
    from app.core.exceptions import CustomException
    from app.plugin.module_ai.query.service import AiQueryService as Q

    with pytest.raises(CustomException) as ei:
        _run(Q.object_browse(OUT_TABLE, _auth(), page=1, page_size=20))
    assert "白名单" in str(ei.value), (
        f"白名单外表 {OUT_TABLE} 没被拒绝（可浏览任意表，越权读）：{ei.value}")


def test_object_browse_rejects_injection_table_name(monkeypatch):
    """表名注入串（闭合引号 + 多语句）必须被标识符校验直接拒绝。"""
    _patch(monkeypatch)
    from app.core.exceptions import CustomException
    from app.plugin.module_ai.query.service import AiQueryService as Q

    with pytest.raises(CustomException) as ei:
        _run(Q.object_browse(INJECT, _auth(), page=1, page_size=20))
    assert "非法表名" in str(ei.value), (
        f"注入表名没被拒绝（SQL 注入）：{ei.value}")


# ===========================================================================
# dq_rules_run：数据质量规则引擎
# ===========================================================================
def test_dq_rules_run_rejects_non_whitelist_table(monkeypatch):
    """白名单外表必须被拒绝（fail-closed 抛错），且不碰数据库。"""
    _patch(monkeypatch)
    from app.core.exceptions import CustomException
    from app.plugin.module_ai.query.service import AiQueryService as Q

    with pytest.raises(CustomException) as ei:
        _run(Q.dq_rules_run(OUT_TABLE, "username", "not_null", _auth()))
    assert "白名单" in str(ei.value), (
        f"白名单外表 {OUT_TABLE} 没被拒绝（可探测任意表数据）：{ei.value}")


def test_dq_rules_run_rejects_injection_table_name(monkeypatch):
    """表名注入串（闭合引号 + 多语句）必须被标识符校验直接拒绝。"""
    _patch(monkeypatch)
    from app.core.exceptions import CustomException
    from app.plugin.module_ai.query.service import AiQueryService as Q

    with pytest.raises(CustomException) as ei:
        _run(Q.dq_rules_run(INJECT, "username", "not_null", _auth()))
    assert "非法表名" in str(ei.value), (
        f"注入表名没被拒绝（SQL 注入）：{ei.value}")


def test_dq_rules_run_rejects_injection_column_name(monkeypatch):
    """列名同样被拼进 SELECT（``WHERE "{column}" IS NOT NULL``），也必须校验。"""
    _patch(monkeypatch)
    from app.core.exceptions import CustomException
    from app.plugin.module_ai.query.service import AiQueryService as Q

    with pytest.raises(CustomException) as ei:
        _run(Q.dq_rules_run("ai_models", INJECT, "not_null", _auth()))
    assert "非法列名" in str(ei.value), (
        f"注入列名没被拒绝（SQL 注入）：{ei.value}")


# ===========================================================================
# 正向对照：合法白名单表不应被误伤（走到校验函数这一层即算通过）
# ===========================================================================
def test_require_queryable_table_passes_whitelisted_table(monkeypatch):
    """白名单内的合法表名应原样放行（校验函数不误伤正常功能）。"""
    _patch(monkeypatch)
    from app.plugin.module_ai.query.service import AiQueryService as Q

    out = _run(Q._require_queryable_table("ai_models", _auth()))
    assert out == "ai_models"
