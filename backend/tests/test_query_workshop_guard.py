"""Workshop（无代码应用）保存/预览/表单提交的来源表列校验回归（P0-2）。

修前：``upsert_workshop_app`` 把用户提交的 ``object_table`` / ``columns`` 原样落库，
``workshop_preview`` 再原样拼进 ``SELECT {cols} FROM "{table}"``（白名单外只补一句
``WHERE is_deleted=false``），等于**任意表读取**：

  - ``object_table`` 不校验 → 白名单外表（如 ``sys_user``，含密码哈希）可整表导出；
  - ``columns`` 不校验 → 传注入串即可闭合引号拼出任意 SQL（psycopg2 允许多语句）；
  - ``workshop_submit`` 的 INSERT 同样信任库里的配置，历史行可绕过保存期校验。

修后：三个入口统一先过 P0-1 引入的两道护栏——``_require_queryable_table``
（合法标识符 + **按用户收窄**的可查白名单）与 ``_require_ident``（逐列标识符），
校验失败抛 CustomException（fail-closed），且发生在**任何数据 SQL 拼接/执行**之前
（测试里配置读取之后的任何 execute 都判失败，即「没拦住就查数据」）。

本文件是纯逻辑测试（白名单与数据库均打桩），可用
``PYTEST_NO_APP=1 pytest tests/test_query_workshop_guard.py`` 快速跑。
"""
import asyncio
import json

import pytest


def _run(coro):
    return asyncio.run(coro)


def _auth(uid: int = 42):
    """最小 auth 替身（``_allowed_for_user`` 被 monkeypatch，不会走真实权限链）。"""
    return type("A", (), {"user": type("U", (), {"id": uid, "is_superuser": False})()})()


#: 白名单外的表名（典型：被数据域/ABAC 收窄的用户不该看到 sys_user）
OUT_TABLE = "sys_user"

#: 注入串列名（列名会拼进 ``SELECT "{col}"``，含空格/分号必然不是合法标识符）
COL_INJECT = "x FROM sys_user; DROP TABLE ai_query_settings; --"


def _no_db(*_a, **_k):
    raise AssertionError("未过白名单校验就碰了数据库（校验没在拼 SQL 前生效）")


# --------------------------------------------------------------------------- #
# 数据库替身：只放行「读应用配置」这一次 execute，之后任何 execute = 没拦住
# --------------------------------------------------------------------------- #
class _FakeResult:
    """``execute`` 返回值替身（fetchone / fetchall / keys / scalar）。"""

    def __init__(self, row=None, keys=(), rows=()):
        self._row = row
        self._keys = list(keys)
        self._rows = list(rows)

    def fetchone(self):
        return self._row

    def fetchall(self):
        return list(self._rows)

    def keys(self):
        return list(self._keys)

    def scalar(self):
        return None if self._row is None else self._row[0]


class _FakeCtx:
    """``async with async_db_session() as db`` 的替身上下文。"""

    def __init__(self, handler):
        self._handler = handler

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def execute(self, stmt, params=None):
        return self._handler(str(stmt), params)


class _FakeSessionFactory:
    """整体替换 ``async_db_session``：既能调用（）建会话，也有 ``.begin()``。"""

    def __init__(self, handler):
        self._handler = handler

    def __call__(self):
        return _FakeCtx(self._handler)

    def begin(self):
        return _FakeCtx(self._handler)


def _seq(responses):
    """按调用顺序返回结果；超出预设次数即「校验没生效还去查/写数据」。"""
    state = {"sqls": [], "params": []}

    def handler(sql, params):
        state["sqls"].append(sql)
        state["params"].append(params)
        if not responses:
            raise AssertionError(f"校验没生效就执行了数据 SQL：{sql}")
        return responses.pop(0)

    return handler, state


def _patch(monkeypatch, allowed=("ai_models",), db=None):
    """白名单 + 数据库打桩；``db=None`` 表示**任何**数据库访问都要失败。"""
    import app.plugin.module_ai.query.service as S

    allow = set(allowed)

    async def _allowed(auth):
        return allow

    monkeypatch.setattr(S.AiQueryService, "_allowed_for_user", staticmethod(_allowed))
    monkeypatch.setattr(S, "async_db_session", db if db is not None else _no_db)


# ===========================================================================
# 入口一：upsert_workshop_app（保存，配置的唯一写入口）
# ===========================================================================
def test_save_rejects_non_whitelist_object_table(monkeypatch):
    """白名单外表必须在保存时被拒（否则预览等于任意表读取），且不碰数据库。"""
    _patch(monkeypatch)
    from app.core.exceptions import CustomException
    from app.plugin.module_ai.query.service import AiQueryService as Q

    with pytest.raises(CustomException) as ei:
        _run(Q.upsert_workshop_app(
            {"name": "演示", "object_table": OUT_TABLE, "columns": ["id"]}, auth=_auth()))
    assert "白名单" in str(ei.value), (
        f"白名单外表 {OUT_TABLE} 没被拒绝（可保存成任意表读取应用）：{ei.value}")


def test_save_rejects_injection_column(monkeypatch):
    """columns 注入串必须被逐列标识符校验拒绝（列名会拼进 SELECT）。"""
    _patch(monkeypatch)
    from app.core.exceptions import CustomException
    from app.plugin.module_ai.query.service import AiQueryService as Q

    with pytest.raises(CustomException) as ei:
        _run(Q.upsert_workshop_app(
            {"name": "演示", "object_table": "ai_models", "columns": [COL_INJECT]},
            auth=_auth()))
    assert "非法列名" in str(ei.value), (
        f"注入列名没被拒绝（SQL 注入）：{ei.value}")


def test_save_rejects_empty_object_table(monkeypatch):
    """object_table 为空必须拒绝（fail-closed），不能落库后再退化成 SELECT * 全表导出。"""
    _patch(monkeypatch)
    from app.core.exceptions import CustomException
    from app.plugin.module_ai.query.service import AiQueryService as Q

    with pytest.raises(CustomException) as ei:
        _run(Q.upsert_workshop_app(
            {"name": "演示", "object_table": "", "columns": ["id"]}, auth=_auth()))
    assert "非法表名" in str(ei.value), (
        f"空表名没被拒绝（预览会退化成全表导出）：{ei.value}")


def test_save_passes_valid_table_and_columns(monkeypatch):
    """正向对照：白名单内合法表 + 合法列应正常保存（别把功能修死）。"""
    handler, state = _seq([_FakeResult(row=(9,))])
    _patch(monkeypatch, db=_FakeSessionFactory(handler))
    from app.plugin.module_ai.query.service import AiQueryService as Q

    out = _run(Q.upsert_workshop_app(
        {"name": "演示", "object_table": "ai_models", "columns": ["id", "name"]},
        auth=_auth()))
    assert out == {"id": 9}
    saved = state["params"][0]
    assert saved["o"] == "ai_models", f"合法表没被原样保存：{saved}"
    assert json.loads(saved["c"]) == ["id", "name"], f"合法列没被原样保存：{saved}"


# ===========================================================================
# 入口二：workshop_preview（预览，拼 SELECT 读真实数据）
# ===========================================================================
def test_preview_rejects_non_whitelist_object_table(monkeypatch):
    """配置指向白名单外表时必须抛错，且读完配置后**不再执行任何数据 SQL**。"""
    handler, state = _seq([_FakeResult(row=(OUT_TABLE, ["id"], "table"))])
    _patch(monkeypatch, db=_FakeSessionFactory(handler))
    from app.core.exceptions import CustomException
    from app.plugin.module_ai.query.service import AiQueryService as Q

    with pytest.raises(CustomException) as ei:
        _run(Q.workshop_preview(app_id=7, auth=_auth(), limit=10))
    assert "白名单" in str(ei.value), (
        f"白名单外表 {OUT_TABLE} 没被拒绝（预览 = 任意表读取）：{ei.value}")
    assert len(state["sqls"]) == 1, (
        f"校验失败后仍执行了数据 SQL：{state['sqls'][1:]}")


def test_preview_rejects_injection_column(monkeypatch):
    """columns 注入串必须在拼 SELECT 之前被拒，且不执行数据 SQL。"""
    handler, state = _seq([_FakeResult(row=("ai_models", [COL_INJECT], "table"))])
    _patch(monkeypatch, db=_FakeSessionFactory(handler))
    from app.core.exceptions import CustomException
    from app.plugin.module_ai.query.service import AiQueryService as Q

    with pytest.raises(CustomException) as ei:
        _run(Q.workshop_preview(app_id=7, auth=_auth(), limit=10))
    assert "非法列名" in str(ei.value), (
        f"注入列名没被拒绝（SQL 注入）：{ei.value}")
    assert len(state["sqls"]) == 1, (
        f"校验失败后仍执行了数据 SQL：{state['sqls'][1:]}")


def test_preview_passes_valid_table_and_columns(monkeypatch):
    """正向对照：白名单内合法表 + 合法列应正常出预览数据。"""
    handler, state = _seq([
        _FakeResult(row=("ai_models", ["id", "name"], "table")),
        _FakeResult(keys=["id", "name"], rows=[(1, "a")]),
    ])
    _patch(monkeypatch, db=_FakeSessionFactory(handler))
    from app.plugin.module_ai.query.service import AiQueryService as Q

    out = _run(Q.workshop_preview(app_id=7, auth=_auth(), limit=10))
    assert out.get("ok") is True, f"合法配置预览失败：{out}"
    assert out["columns"] == ["id", "name"]
    assert '"ai_models"' in state["sqls"][1], (
        f"数据 SQL 没用校验后的表名拼装：{state['sqls'][1]}")


# ===========================================================================
# 入口三：workshop_submit（表单提交写入，信任的是库里的配置）
# ===========================================================================
def test_submit_rejects_non_whitelist_object_table(monkeypatch):
    """历史行（保存期校验之前落库）也要在写入前被拦：白名单外直接抛错、不写库。"""
    handler, state = _seq([_FakeResult(row=(OUT_TABLE, ["id"]))])
    _patch(monkeypatch, db=_FakeSessionFactory(handler))
    from app.core.exceptions import CustomException
    from app.plugin.module_ai.query.service import AiQueryService as Q

    with pytest.raises(CustomException) as ei:
        _run(Q.workshop_submit(app_id=7, data={"id": 1}, auth=_auth()))
    assert "白名单" in str(ei.value), (
        f"白名单外表 {OUT_TABLE} 没被拒绝（可越权写任意表）：{ei.value}")
    assert len(state["sqls"]) == 1, (
        f"校验失败后仍执行了写入 SQL：{state['sqls'][1:]}")


def test_submit_passes_valid_table_and_columns(monkeypatch):
    """正向对照：写白名单（``_WORKSHOP_WRITABLE``）内合法表 + 合法列应正常提交。"""
    handler, state = _seq([
        _FakeResult(row=("ont_orders", ["id", "amount"])),
        _FakeResult(),
    ])
    _patch(monkeypatch, allowed=("ont_orders",), db=_FakeSessionFactory(handler))
    from app.plugin.module_ai.query.service import AiQueryService as Q

    out = _run(Q.workshop_submit(app_id=7, data={"amount": 5, "evil": "x"}, auth=_auth()))
    assert out == {"ok": True}
    write_sql = state["sqls"][1]
    assert '"ont_orders"' in write_sql and '"amount"' in write_sql, (
        f"写入 SQL 没按校验后的标识符拼装：{write_sql}")


# ===========================================================================
# 共用护栏本身（两道校验的正向出口，别把功能修死）
# ===========================================================================
def test_require_workshop_source_passes_valid_config(monkeypatch):
    """白名单内合法表 + 合法列应原样放行（返回值即后续 SQL 唯一的数据来源）。"""
    _patch(monkeypatch)
    from app.plugin.module_ai.query.service import AiQueryService as Q

    out = _run(Q._require_workshop_source("ai_models", ["id", "name"], _auth()))
    assert out == ("ai_models", ["id", "name"])
