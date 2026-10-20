"""问数字段级 ACL（敏感字段拦截）必须收口到唯一执行出口（P0-3）。

修前：字段级 ACL（``_ont_sql_violations``）**只**挂在 ``AiQueryService._execute_one``
一个出口上 —— 问数主链路（ask / ask_stream）走它，但另外两条同权限码的取数路径
各自直连 ``_execute_sql``，把 ACL 整段绕过了：

  1. **报表执行** ``report.run_report``：有 ``validate_sql`` + ``_secure_ont_sql``，
     但从不做字段级 ACL；
  2. **指标执行** ``_execute_metric``：同样只有白名单 + 本体行/列改写。

现实攻击面：``metrics/save``、``reports`` 的写权限与问数同码
（``module_ai:query:ask``）—— **能问数就能造一条读敏感列的指标/报表模板并执行**，
``ai_query_asset_columns.sensitive=true`` 或本体属性 ``sensitive`` 的字段被原样读出。

修后：四条路径共用 ``_execute_one`` 作为**唯一**的系统库取数收口
（白名单 → 字段级 ACL → 本体行/列改写 → 执行），ACL 只有一份实现；
且保持 fail-closed：ACL 检查自身出错一律拒绝执行，不得退化成 fail-open。

本文件是纯逻辑测试（白名单 / 敏感列元数据 / 执行层全部打桩），可用
``PYTEST_NO_APP=1 pytest tests/test_query_acl_single_choke.py`` 快速跑。
"""
import asyncio

import pytest


def _run(coro):
    return asyncio.run(coro)


def _auth(uid: int = 42):
    """最小 auth 替身（白名单与 ACL 元数据均被打桩，不会走真实权限链）。"""
    return type("A", (), {"user": type("U", (), {"id": uid, "is_superuser": False})()})()


#: 被标记为敏感的业务表 / 列（口径同 ``_sensitive_asset_cols``：
#: ``ai_query_asset_columns.sensitive=true``）
TABLE = "video_cameras"
SENSITIVE_COL = "password"
SAFE_COL = "name"


def _patch(monkeypatch, executed: list):
    """打桩：按用户白名单 + 敏感列元数据 + 本体改写 + 执行层。

    ``executed`` 收集真正进入执行层的 SQL —— ACL 生效时它必须保持为空。
    """
    import app.plugin.module_ai.query.service as S
    from app.plugin.module_ai.query.service import AiQueryService as Q

    async def _allowed(auth):
        return {TABLE}

    async def _no_sensitive_grant(uid):
        return False          # 非超管、无 sensitive_ok 放行规则

    async def _sensitive_cols(table):
        return [SENSITIVE_COL] if table == TABLE else []

    async def _secure(sql, auth):
        return {"sql": sql, "deny": False, "rewritten": [], "msg": ""}

    async def _exec(sql):
        executed.append(sql)
        return {"columns": [SAFE_COL], "rows": [["cam-1"]], "took_ms": 1}

    monkeypatch.setattr(Q, "_allowed_for_user", staticmethod(_allowed))
    monkeypatch.setattr(Q, "_can_see_sensitive", staticmethod(_no_sensitive_grant))
    monkeypatch.setattr(Q, "_sensitive_asset_cols", staticmethod(_sensitive_cols))
    monkeypatch.setattr(S, "_secure_ont_sql", _secure)
    monkeypatch.setattr(S, "_execute_sql", _exec)


def _patch_report(monkeypatch, sql_template: str):
    import app.plugin.module_ai.query.report as R

    async def _get(rid):
        return {"id": rid, "key": "R_X", "name": "X", "datasource": "system",
                "sql_template": sql_template, "params": []}

    monkeypatch.setattr(R, "get_report", _get)


# ===========================================================================
# ① 报表执行：引用敏感字段必须被拒
# ===========================================================================
def test_run_report_denies_sensitive_field(monkeypatch):
    """报表模板 SELECT 敏感列 → 字段级 ACL 拒绝，且不执行任何数据 SQL。"""
    executed: list = []
    _patch(monkeypatch, executed)
    _patch_report(monkeypatch, f"SELECT {SENSITIVE_COL} FROM {TABLE}")

    from app.core.exceptions import CustomException
    from app.plugin.module_ai.query.report import run_report

    with pytest.raises(CustomException) as ei:
        _run(run_report(1, {}, auth=_auth()))
    assert "字段级权限" in str(ei.value), (
        f"报表读敏感列没被拒（可造模板绕过字段级 ACL）：{ei.value}")
    assert executed == [], f"敏感字段报表被执行了：{executed}"


# ===========================================================================
# ② 指标执行：引用敏感字段必须被拒
# ===========================================================================
def test_execute_metric_denies_sensitive_field(monkeypatch):
    """指标模板 SELECT 敏感列 → 字段级 ACL 拒绝，且不执行任何数据 SQL。"""
    executed: list = []
    _patch(monkeypatch, executed)

    from app.core.exceptions import CustomException
    from app.plugin.module_ai.query.service import _execute_metric

    metric = {"key": "m_pwd", "name": "密码清单", "datasource": "system",
              "sql_template": f"SELECT {SENSITIVE_COL} FROM {TABLE}"}
    with pytest.raises(CustomException) as ei:
        _run(_execute_metric(metric, {}, _auth()))
    assert "字段级权限" in str(ei.value), (
        f"指标读敏感列没被拒（可造指标绕过字段级 ACL）：{ei.value}")
    assert executed == [], f"敏感字段指标被执行了：{executed}"


# ===========================================================================
# ③ 正向对照：不涉及敏感字段的报表/指标仍能正常执行（别把功能修死）
# ===========================================================================
def test_run_report_allows_non_sensitive_field(monkeypatch):
    """报表只读非敏感列 → 正常执行并返回结果（返回结构不变）。"""
    executed: list = []
    _patch(monkeypatch, executed)
    _patch_report(monkeypatch, f"SELECT {SAFE_COL} FROM {TABLE}")

    from app.plugin.module_ai.query.report import run_report

    out = _run(run_report(1, {}, auth=_auth()))
    assert out["rows"] == [["cam-1"]], out
    assert out["columns"] == [SAFE_COL], out
    assert len(executed) == 1, f"正常报表没有被执行：{executed}"


def test_execute_metric_allows_non_sensitive_field(monkeypatch):
    """指标只读非敏感列 → 正常执行并返回结果（columns/rows/sql 不变）。"""
    executed: list = []
    _patch(monkeypatch, executed)

    from app.plugin.module_ai.query.service import _execute_metric

    metric = {"key": "m_name", "name": "摄像头名", "datasource": "system",
              "sql_template": f"SELECT {SAFE_COL} FROM {TABLE}"}
    out = _run(_execute_metric(metric, {}, _auth()))
    assert out["rows"] == [["cam-1"]], out
    assert out["columns"] == [SAFE_COL], out
    assert out["sql"], "指标结果缺 sql 字段（前端依赖）"
    assert len(executed) == 1, f"正常指标没有被执行：{executed}"


# ===========================================================================
# ④ fail-closed：ACL 检查自身出错时必须拒绝执行（不得 fail-open）
# ===========================================================================
def test_run_report_fails_closed_when_acl_errors(monkeypatch):
    """报表路径的 ACL 检查炸了也必须拒绝，而不是放行未过滤的查询。"""
    executed: list = []
    _patch(monkeypatch, executed)
    _patch_report(monkeypatch, f"SELECT {SAFE_COL} FROM {TABLE}")

    from app.plugin.module_ai.query.service import AiQueryService as Q

    async def _boom(sql, uid):
        raise RuntimeError("元数据查询失败")

    monkeypatch.setattr(Q, "_ont_sql_violations", staticmethod(_boom))

    from app.core.exceptions import CustomException
    from app.plugin.module_ai.query.report import run_report

    with pytest.raises(CustomException) as ei:
        _run(run_report(1, {}, auth=_auth()))
    assert "权限" in str(ei.value), f"ACL 出错时放行了（fail-open）：{ei.value}"
    assert executed == [], f"ACL 出错时仍执行了 SQL：{executed}"


# ===========================================================================
# ⑤ 结构约束：报表/指标必须与 ask 共用 `_execute_one` 收口
# ===========================================================================
def test_report_and_metric_share_execute_one_choke(monkeypatch):
    """两条绕过路径必须各**调用一次** ``_execute_one``（不得自己直连执行层）。

    这是「唯一收口」的结构性约束：ACL 只写在 ``_execute_one`` 里，
    任何直连 ``_execute_sql`` 的路径都等于绕过字段级 ACL。
    """
    calls: list = []
    _patch(monkeypatch, [])
    _patch_report(monkeypatch, f"SELECT {SAFE_COL} FROM {TABLE}")

    from app.plugin.module_ai.query.service import AiQueryService as Q

    async def _one(cls, sql, datasource, auth):
        calls.append((sql, datasource))
        return {"columns": [SAFE_COL], "rows": [["cam-1"]], "took_ms": 1}

    monkeypatch.setattr(Q, "_execute_one", classmethod(_one))

    from app.plugin.module_ai.query.report import run_report
    from app.plugin.module_ai.query.service import _execute_metric

    _run(run_report(1, {}, auth=_auth()))
    _run(_execute_metric(
        {"key": "m_name", "name": "摄像头名", "datasource": "system",
         "sql_template": f"SELECT {SAFE_COL} FROM {TABLE}"}, {}, _auth()))

    assert len(calls) == 2, f"报表/指标没走共同收口 `_execute_one`：{calls}"
    assert all(ds == "system" for _, ds in calls), calls
