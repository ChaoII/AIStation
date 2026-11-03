"""字段级 ACL 必须对**自定义数据源**同样生效。

之前的断点：本体/资产里把「煤款单价」标成 sensitive，走系统库的问数会被拦，
但走 ds:4（燃煤业务库）的问数**照样查得出来** —— 因为 `_execute_custom_ds_sql`
里根本没有这道检查。标记于是变成装饰品。
"""

import asyncio
from types import SimpleNamespace

import pytest

from app.core.exceptions import CustomException
from app.plugin.module_ai.query import service as S


def _auth(uid: int = 2, superuser: bool = False):
    return SimpleNamespace(user=SimpleNamespace(id=uid, is_superuser=superuser))


def _patch_ds(monkeypatch, violations: list[str]):
    """把外部源执行链路的"外部依赖"全部替换掉，只保留被验证的那段逻辑。"""
    async def _noop_assert(ds_id, auth):
        return None

    async def _fake_load(ds_id):
        return SimpleNamespace(id=ds_id, type="postgres", host="h", port=1,
                               database="d", username="u", password="p", allowed_roles=[])

    async def _fake_schema(ds_id):
        return [{"table": "FUEL_CB_COALBALANCE",
                 "columns": [{"name": "COALPRICE"}, {"name": "ID"}]}]

    async def _fake_viol(sql, user_id):
        return list(violations)

    monkeypatch.setattr(S, "_assert_ds_access", _noop_assert)
    monkeypatch.setattr(S, "_load_ds", _fake_load)
    monkeypatch.setattr(S, "list_ds_schema", _fake_schema)
    monkeypatch.setattr(S.AiQueryService, "_ont_sql_violations",
                        classmethod(lambda cls, sql, uid: _fake_viol(sql, uid)))


def test_custom_ds_blocks_sensitive_column(monkeypatch):
    """非超管查敏感列 → 拒绝执行，且错误信息点名了该列。"""
    _patch_ds(monkeypatch, ["FUEL_CB_COALBALANCE.COALPRICE"])
    sql = 'SELECT "COALPRICE" FROM "FUEL_CB_COALBALANCE" LIMIT 10'
    with pytest.raises(CustomException) as ei:
        asyncio.run(S._execute_custom_ds_sql(4, sql, _auth(uid=2)))
    assert "字段级权限" in str(ei.value.msg), ei.value.msg
    assert "COALPRICE" in str(ei.value.msg)


def test_custom_ds_allows_when_no_violation(monkeypatch):
    """没有命中敏感列 → 继续执行（这里只验证没被 ACL 拦；外部连接用假的）。"""
    _patch_ds(monkeypatch, [])
    called = {}

    class _FakeEx:
        @staticmethod
        async def execute_select(cfg, sql, **kwargs):  # noqa: ANN001, ARG004
            # max_rows / timeout 是 service 从设置项传下来的（有守护测试）
            called["sql"] = sql
            return {"columns": ["ID"], "rows": [[1]], "took_ms": 1}

    monkeypatch.setattr(S, "_ex", _FakeEx, raising=False)
    monkeypatch.setattr("app.plugin.module_ai.query.executor.execute_select",
                        _FakeEx.execute_select, raising=False)
    sql = 'SELECT "ID" FROM "FUEL_CB_COALBALANCE" LIMIT 10'
    out = asyncio.run(S._execute_custom_ds_sql(4, sql, _auth(uid=2)))
    assert out.get("rows") == [[1]]
    assert called.get("sql")


def test_acl_check_failure_is_fail_closed(monkeypatch):
    """ACL 自身报错时必须拒绝执行，不能"检查失败就放行"。"""
    async def _boom(cls, sql, uid):
        raise RuntimeError("acl down")

    async def _noop_assert(ds_id, auth):
        return None

    async def _fake_load(ds_id):
        return SimpleNamespace(id=ds_id, type="postgres", host="h", port=1,
                               database="d", username="u", password="p", allowed_roles=[])

    async def _fake_schema(ds_id):
        return [{"table": "FUEL_CB_COALBALANCE", "columns": [{"name": "ID"}]}]

    monkeypatch.setattr(S, "_assert_ds_access", _noop_assert)
    monkeypatch.setattr(S, "_load_ds", _fake_load)
    monkeypatch.setattr(S, "list_ds_schema", _fake_schema)
    monkeypatch.setattr(S.AiQueryService, "_ont_sql_violations",
                        classmethod(lambda cls, sql, uid: _boom(cls, sql, uid)))
    with pytest.raises(CustomException) as ei:
        asyncio.run(S._execute_custom_ds_sql(
            4, 'SELECT "ID" FROM "FUEL_CB_COALBALANCE" LIMIT 10', _auth(uid=2)))
    assert "拒绝执行" in str(ei.value.msg), ei.value.msg
