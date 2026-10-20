"""agno 工具调用路径的 SQL 执行必须与主链路共用同一份 ACL（P0-4）。

修前：``agno_query_tools`` 里两个**执行 SQL 的工具入口**自己直连 ``_execute_sql``，
白名单用的是**全局** ``_system_allowed()``（不按用户收窄），字段级 ACL 完全不经过：

  1. ``run_sql``（模块级工具函数，Agent ``tools=[...]`` 可直接注册）；
  2. ``_SafeSqlTools.run_sql_query``（Agno 官方 SQLTools 的重写版，单选 ``AGNO_SQL_TOOLS``）。

于是模型通过工具调用生成的 SQL 既不受数据域/ABAC 收窄约束，也不拦敏感字段——
与 P0-3（报表/指标绕过）同一类越权读取，只是入口不同。

修后：工具路径**没有**「无身份执行」这条退路（fail-closed），
执行统一走 ``AiQueryService._execute_one(sql, SYSTEM_DS, auth)``（白名单 → 字段级 ACL →
本体行/列改写 → 执行），auth 由**按请求构造**的工具工厂注入：

  - ``build_query_tools(auth)``：给 Agent 用的工具集（工具名/签名/文档与 ``QUERY_TOOLS`` 一致，
    LLM 依赖 tool schema，不得变）；
  - ``build_sql_tools(auth)`` / ``build_agno_sql_tools(auth)``：执行类工具（绑定 auth）。

本文件是纯逻辑测试（白名单 / 敏感列元数据 / 本体改写 / 执行层全部打桩），可用
``PYTEST_NO_APP=1 pytest tests/test_query_agno_tool_acl.py`` 快速跑。
"""
import asyncio


def _run(coro):
    return asyncio.run(coro)


def _auth(uid: int = 42):
    """最小 auth 替身（白名单与 ACL 元数据均被打桩，不会走真实权限链）。"""
    return type("A", (), {"user": type("U", (), {"id": uid, "is_superuser": False})()})()


#: 用户数据域内的业务表 / 其中被标记敏感的列（口径同 ``_sensitive_asset_cols``）
TABLE = "video_cameras"
SENSITIVE_COL = "password"
SAFE_COL = "name"

#: 数据域**外**的表（全局白名单里有，用户白名单里没有）
OUT_TABLE = "sys_user"


def _patch(monkeypatch, executed: list, allowed=(TABLE,)):
    """打桩：按用户白名单 + 全局白名单 + 敏感列元数据 + 本体改写 + 执行层。

    - ``_allowed_for_user`` → 只有 ``allowed``（模拟数据域/ABAC 收窄后的用户白名单）；
    - ``_system_allowed`` → ``allowed`` ∪ ``{OUT_TABLE}``（全局白名单**故意**更宽，
      工具若还用全局白名单，域外表与敏感列都会被放行）；
    - ``executed`` 收集真正进入执行层的 SQL —— ACL 生效时它必须保持为空。
    """
    import app.plugin.module_ai.query.service as S
    from app.plugin.module_ai.query.service import AiQueryService as Q

    async def _allowed(auth):
        return set(allowed)

    async def _global_allowed():
        return set(allowed) | {OUT_TABLE}

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
    monkeypatch.setattr(S, "_system_allowed", _global_allowed)
    monkeypatch.setattr(S, "_secure_ont_sql", _secure)
    monkeypatch.setattr(S, "_execute_sql", _exec)


# ===========================================================================
# ① 工具执行读敏感字段的 SQL → 必须被字段级 ACL 拒绝
# ===========================================================================
def test_tool_run_sql_denies_sensitive_column(monkeypatch):
    """绑定身份的 run_sql 读敏感列 → 拒绝，且不执行任何数据 SQL。"""
    executed: list = []
    _patch(monkeypatch, executed)

    from app.plugin.module_ai.query.agno_query_tools import build_sql_tools

    tool = build_sql_tools(_auth())[0]
    out = _run(tool(f"SELECT {SENSITIVE_COL} FROM {TABLE}"))
    assert "字段级权限" in out, (
        f"工具路径读敏感列没被拒（模型可造 SQL 绕过字段级 ACL）：{out}")
    assert executed == [], f"敏感字段 SQL 被执行了：{executed}"


def test_agno_sql_toolkit_denies_sensitive_column(monkeypatch):
    """Agno 官方 SQLTools 路径（run_sql_query）读敏感列 → 同样拒绝。"""
    executed: list = []
    _patch(monkeypatch, executed)

    from app.plugin.module_ai.query.agno_query_tools import build_agno_sql_tools

    kit = build_agno_sql_tools(_auth())
    out = _run(kit.run_sql_query(f"SELECT {SENSITIVE_COL} FROM {TABLE}"))
    assert "字段级权限" in out, (
        f"Agno SQL 工具读敏感列没被拒（绕过字段级 ACL）：{out}")
    assert executed == [], f"敏感字段 SQL 被执行了：{executed}"


# ===========================================================================
# ② 工具执行数据域外的表 → 必须按**用户**白名单拒绝
# ===========================================================================
def test_tool_run_sql_rejects_out_of_domain_table(monkeypatch):
    """域外表（全局白名单有、用户白名单没有）→ 拒绝，且不执行任何数据 SQL。"""
    executed: list = []
    _patch(monkeypatch, executed, allowed=(TABLE,))

    from app.plugin.module_ai.query.agno_query_tools import build_sql_tools

    tool = build_sql_tools(_auth())[0]
    out = _run(tool(f"SELECT id FROM {OUT_TABLE}"))
    assert "白名单" in out, (
        f"工具路径没按用户白名单收窄（数据域隔离失效）：{out}")
    assert executed == [], f"域外表 SQL 被执行了：{executed}"


# ===========================================================================
# ③ 正向对照：白名单内、不碰敏感列的工具调用仍能正常返回结果（别把功能修死）
# ===========================================================================
def test_tool_run_sql_allows_legal_sql(monkeypatch):
    """合法 SQL → 正常执行并返回列/行（返回文案结构不变，模型据此自修复）。"""
    executed: list = []
    _patch(monkeypatch, executed)

    from app.plugin.module_ai.query.agno_query_tools import build_sql_tools

    tool = build_sql_tools(_auth())[0]
    out = _run(tool(f"SELECT {SAFE_COL} FROM {TABLE}"))
    assert "执行成功" in out and "cam-1" in out, f"合法 SQL 被误杀：{out}"
    assert "执行成功，共 1 行" in out, out
    assert len(executed) == 1, f"合法 SQL 没有被执行：{executed}"


# ===========================================================================
# ④ fail-closed：没有调用者身份时**不得**退回全局白名单直接执行
# ===========================================================================
def test_module_level_run_sql_fails_closed_without_auth(monkeypatch):
    """模块级 run_sql（无身份）→ 拒绝执行，不碰执行层。"""
    executed: list = []
    _patch(monkeypatch, executed)

    from app.plugin.module_ai.query.agno_query_tools import run_sql

    out = _run(run_sql(f"SELECT {SAFE_COL} FROM {TABLE}"))
    assert "拒绝执行" in out, f"无身份的模块级工具仍在执行 SQL（fail-open）：{out}"
    assert executed == [], f"无身份时仍执行了 SQL：{executed}"


def test_unbound_agno_sql_toolkit_fails_closed(monkeypatch):
    """模块级 AGNO_SQL_TOOLS（未绑定身份）→ 拒绝执行，不碰执行层。"""
    executed: list = []
    _patch(monkeypatch, executed)

    from app.plugin.module_ai.query.agno_query_tools import AGNO_SQL_TOOLS

    out = _run(AGNO_SQL_TOOLS.run_sql_query(f"SELECT {SAFE_COL} FROM {TABLE}"))
    assert "拒绝执行" in out, f"未绑定的 Agno SQL 工具仍在执行（fail-open）：{out}"
    assert executed == [], f"无身份时仍执行了 SQL：{executed}"


# ===========================================================================
# ⑤ 结构约束：工具 schema 不变（LLM 依赖），执行类工具一律按请求绑定身份
# ===========================================================================
def test_build_query_tools_keeps_tool_schema(monkeypatch):
    """``build_query_tools(auth)`` 的工具名/文档必须与 ``QUERY_TOOLS`` 完全一致。"""
    from app.plugin.module_ai.query.agno_query_tools import QUERY_TOOLS, build_query_tools

    tools = build_query_tools(_auth())
    assert [t.__name__ for t in tools] == [t.__name__ for t in QUERY_TOOLS]
    assert [t.__doc__ for t in tools] == [t.__doc__ for t in QUERY_TOOLS]


def test_bound_run_sql_keeps_name_and_doc(monkeypatch):
    """绑定身份的 run_sql 工具名/文档/参数与模块级一致（tool schema 稳定）。"""
    import inspect

    from app.plugin.module_ai.query.agno_query_tools import build_sql_tools, run_sql

    bound = build_sql_tools(_auth())[0]
    assert bound.__name__ == run_sql.__name__ == "run_sql"
    assert bound.__doc__ == run_sql.__doc__
    assert list(inspect.signature(bound).parameters) == ["sql"]


def test_build_query_tools_binds_exec_tools(monkeypatch):
    """QUERY_TOOLS 里出现的执行类工具必须被绑定身份（不得裸用模块级实现）。

    当前注册的 12 个工具都是只读元数据类，故这里直接校验工厂的映射规则：
    一旦 ``run_sql`` 回到注册表，``build_query_tools`` 必须换成绑定版本。
    """
    import app.plugin.module_ai.query.agno_query_tools as T

    calls: list = []

    def _factory(auth):
        def _tool(sql: str) -> str:
            """绑定替身。"""
            calls.append(auth)
            return "bound"

        _tool.__name__ = "run_sql"
        return _tool

    monkeypatch.setitem(T._AUTH_BOUND_TOOL_FACTORIES, "run_sql", _factory)
    monkeypatch.setattr(T, "QUERY_TOOLS", [T.run_sql, *T.QUERY_TOOLS])

    auth = _auth()
    tools = T.build_query_tools(auth)
    assert tools[0] is not T.run_sql, "exec 工具没有被换成绑定身份的版本"
    assert tools[0]("SELECT 1") == "bound"
    assert calls == [auth], calls
    assert [t.__name__ for t in tools[1:]] == [t.__name__ for t in T.QUERY_TOOLS[1:]]
