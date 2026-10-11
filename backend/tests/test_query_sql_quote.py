"""外部（大小写敏感）数据源标识符加引号 + 快路径失败兜底。

纯逻辑部分可 ``PYTEST_NO_APP=1`` 快速跑；涉及 service/executor 的按默认模式跑。

背景（实测）：ds:4 是大小写敏感的 PG，表/列名必须加双引号。
指标模板 `SELECT SUM(BALANCEQTY) FROM FUEL_CB_COALBALANCE` 未加引号 →
PG 折成小写 → `UndefinedTableError: 关系 "fuel_cb_coalbalance" 不存在`；
且该异常不是 `CustomException`，`ask()` 不捕获 → 整题崩溃且**不回退慢路径**。
"""
import asyncio

#: 与 ds:4 真库一致的形状（大写、大小写敏感）
SCHEMA = {
    "FUEL_CB_COALBALANCE": ["ID", "BALANCEQTY", "CONTRACTPRICE"],
    "FUEL_CB_COALCONTRACT": ["ID", "CONTRACTAMOUNT"],
    "DTXY_PMXX": ["ID", "LF", "RZ"],
}


# ===========================================================================
# 1) 标识符加引号（纯函数）
# ===========================================================================
def test_quotes_table_and_column_for_case_sensitive_schema():
    from app.plugin.module_ai.query.sql_quote import quote_schema_identifiers

    out = quote_schema_identifiers(
        "SELECT SUM(BALANCEQTY) AS 结算总量 FROM FUEL_CB_COALBALANCE", SCHEMA
    )
    assert '"BALANCEQTY"' in out, f"列名必须加引号: {out}"
    assert '"FUEL_CB_COALBALANCE"' in out, f"表名必须加引号: {out}"
    # 不能残留未加引号的表名（否则 PG 仍会折成小写）
    assert "FUEL_CB_COALBALANCE" not in out.replace('"FUEL_CB_COALBALANCE"', ""), out


def test_quotes_lowercase_input_back_to_real_case():
    from app.plugin.module_ai.query.sql_quote import quote_schema_identifiers

    out = quote_schema_identifiers("select count(*) from fuel_cb_coalbalance", SCHEMA)
    assert '"FUEL_CB_COALBALANCE"' in out, f"小写输入应还原成真名并加引号: {out}"


def test_leaves_unknown_identifiers_untouched():
    from app.plugin.module_ai.query.sql_quote import quote_schema_identifiers

    out = quote_schema_identifiers("SELECT 1 AS x FROM some_other_table", SCHEMA)
    assert "some_other_table" in out
    assert '"some_other_table"' not in out, f"未知表不应被加引号: {out}"


def test_qualified_column_is_quoted_but_alias_is_not():
    from app.plugin.module_ai.query.sql_quote import quote_schema_identifiers

    out = quote_schema_identifiers(
        "SELECT c.CONTRACTPRICE FROM FUEL_CB_COALBALANCE c", SCHEMA
    )
    assert '"CONTRACTPRICE"' in out, f"限定列名要加引号: {out}"
    assert '"FUEL_CB_COALBALANCE"' in out
    assert '"c"' not in out, f"别名不是表名，不能加引号: {out}"


def test_chinese_alias_is_not_quoted():
    from app.plugin.module_ai.query.sql_quote import quote_schema_identifiers

    out = quote_schema_identifiers('SELECT COUNT(*) AS 总数 FROM DTXY_PMXX', SCHEMA)
    assert '"DTXY_PMXX"' in out
    assert '"总数"' not in out, f"中文别名不应被加引号: {out}"


def test_empty_schema_returns_sql_unchanged():
    from app.plugin.module_ai.query.sql_quote import quote_schema_identifiers

    sql = "SELECT 1"
    assert quote_schema_identifiers(sql, {}) == sql


# ===========================================================================
# 1b) 白名单校验要大小写不敏感（模型可能把小写名写出来）
# ===========================================================================
def test_unqualified_column_resolves_against_query_tables_not_global_pool():
    """全局列池里**别的表**有同名小写列时不能用它 —— 必须用本查询涉及表的真实列名。

    实测：模型写 `p.facilityid`（别名限定/小写），全局池里另有某表的小写
    `facilityid`，于是被"保持原样"引号成 `"facilityid"` → PG 找不到该列 → 整题报错。
    """
    from app.plugin.module_ai.query.sql_quote import quote_schema_identifiers

    schema = {
        "CMMS_POINT": ["ID", "FACILITYID", "CODE"],
        "CMMS_FACILITY": ["ID", "NAME"],
        "OTHER_T": ["facilityid"],          # 别的表有同名小写列（干扰项）
    }
    sql = (
        'SELECT p.facilityid FROM (SELECT facilityid FROM "CMMS_POINT") p '
        'JOIN "CMMS_FACILITY" f ON p.facilityid = f."ID"'
    )
    out = quote_schema_identifiers(sql, schema)
    assert '"FACILITYID"' in out, out
    assert '"facilityid"' not in out, out


def test_unqualified_column_single_table_still_works():
    from app.plugin.module_ai.query.sql_quote import quote_schema_identifiers

    schema = {"CMMS_POINT": ["ID", "FACILITYID"], "OTHER_T": ["facilityid"]}
    out = quote_schema_identifiers('SELECT facilityid FROM "CMMS_POINT"', schema)
    assert '"FACILITYID"' in out, out
    assert '"facilityid"' not in out, out


def test_validate_sql_accepts_case_insensitive_table_name():
    from app.plugin.module_ai.query.service import validate_sql

    out = validate_sql("SELECT 1 FROM fuel_cb_coalbalance", {"FUEL_CB_COALBALANCE"})
    assert "fuel_cb_coalbalance" in out.lower()


def test_validate_sql_still_rejects_unknown_table():
    from app.core.exceptions import CustomException
    from app.plugin.module_ai.query.service import validate_sql

    try:
        validate_sql("SELECT 1 FROM not_allowed_table", {"FUEL_CB_COALBALANCE"})
    except CustomException:
        pass
    else:
        raise AssertionError("非白名单表必须被拒绝")


def test_unparseable_sql_is_returned_unchanged():
    from app.plugin.module_ai.query.sql_quote import quote_schema_identifiers

    sql = "SELECT FROM WHERE (("
    assert quote_schema_identifiers(sql, SCHEMA) == sql


def test_exact_case_wins_over_lowercase_collision_from_another_table():
    """真库里存在"别的表有小写同名列"时，不能把已写对的大写名改坏。

    实测：ai_query_schema 里某张表有 `contractprice`（小写），
    合并列池时把 `CONTRACTPRICE` 覆盖成小写 → 执行报「字段 contractprice 不存在」。
    """
    from app.plugin.module_ai.query.sql_quote import quote_schema_identifiers

    schema = {
        "FUEL_CB_COALBALANCE": ["ID", "CONTRACTPRICE"],
        "OTHER_TABLE": ["id", "contractprice"],
    }
    out = quote_schema_identifiers(
        'SELECT AVG("CONTRACTPRICE") FROM "FUEL_CB_COALBALANCE"', schema
    )
    assert '"CONTRACTPRICE"' in out, f"已写对的大写名不能被改坏: {out}"
    assert '"contractprice"' not in out, out


def test_unqualified_column_uses_the_only_table_in_the_query():
    from app.plugin.module_ai.query.sql_quote import quote_schema_identifiers

    schema = {"A_TABLE": ["AMOUNT"], "B_TABLE": ["amount"]}
    out = quote_schema_identifiers("SELECT SUM(amount) FROM A_TABLE", schema)
    assert '"AMOUNT"' in out, f"单表查询应按该表的真实列名: {out}"


# ===========================================================================
# 2) 执行层：驱动异常必须包装成 CustomException（否则上层 catch 不到）
# ===========================================================================
def test_custom_ds_execution_reports_the_quoted_sql(monkeypatch):
    """回报给用户的 SQL 必须是**实际执行**的那条（已加引号），否则排查会被误导。"""
    from app.plugin.module_ai.query import executor as ex
    from app.plugin.module_ai.query import service as svc

    async def _schema(ds_id):
        return [{"table": "FUEL_CB_COALBALANCE", "columns": [{"name": "CONTRACTPRICE"}]}]

    async def _load(ds_id):
        return object()

    captured = {}

    async def _exec(cfg, sql):
        captured["sql"] = sql
        return {"columns": [], "rows": [], "took_ms": 1}

    monkeypatch.setattr(svc, "list_ds_schema", _schema)
    monkeypatch.setattr(svc, "_load_ds", _load)
    monkeypatch.setattr(svc, "_ds_cfg_from_model", lambda ds: {})
    monkeypatch.setattr(ex, "execute_select", _exec)

    out = asyncio.run(
        svc._execute_custom_ds_sql(
            4, "SELECT AVG(CONTRACTPRICE) FROM FUEL_CB_COALBALANCE", None
        )
    )
    assert '"CONTRACTPRICE"' in out["sql"], f"回报的 SQL 应是加引号后的: {out.get('sql')}"
    assert out["sql"] == captured["sql"], "回报的 SQL 必须与实际执行的一致"


class _BoomConn:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def execute(self, *a, **k):
        raise RuntimeError("driver boom")


class _BoomEngine:
    def connect(self):
        return _BoomConn()

    async def dispose(self):
        return None


def test_execute_select_wraps_driver_error(monkeypatch):
    from app.core.exceptions import CustomException
    from app.plugin.module_ai.query import executor as ex

    monkeypatch.setattr(ex, "build_engine", lambda cfg: _BoomEngine())
    try:
        asyncio.run(ex.execute_select({"type": "postgres"}, "SELECT 1"))
    except CustomException as e:
        assert "driver boom" in str(e.msg), e.msg
    else:
        raise AssertionError("驱动异常必须包装成 CustomException")


# ===========================================================================
# 4) 评测必须**比对结果值**（否则 data_accuracy 只是"SQL 跑通了"）
# ===========================================================================
def _run_once_with(monkeypatch, gold_rows, model_rows):
    from app.plugin.module_ai.query import eval_runner as R
    from app.plugin.module_ai.query import eval_set as ES

    cases = [{"id": 1, "question": "q", "gold_sql": "SELECT 1 AS c", "datasource": "system",
              "difficulty": "简单", "scenario": "s", "form": "f", "expected_metric": ""}]
    saved: list = []

    async def _cases(**k):
        return cases

    async def _schema(ds):
        return {}

    async def _ask(question, auth, ds, force_slow=False):
        return {"path": "slow", "sql": "SELECT 2 AS c", "columns": ["c"], "rows": model_rows,
                "is_error": False, "took_ms": 1, "metric": None, "retrieved": None}

    async def _gold(ds, sql):
        return {"columns": ["c"], "rows": gold_rows}

    async def _save(run_id, row):
        saved.append(row)

    async def _finish(run_id, results, status="done"):
        pass

    monkeypatch.setattr(ES, "list_cases", _cases)
    monkeypatch.setattr(R, "_resolve_schema", _schema)
    monkeypatch.setattr(R, "_ask", _ask)
    monkeypatch.setattr(R, "_run_gold_sql", _gold, raising=False)
    monkeypatch.setattr(R, "_save_result", _save)
    monkeypatch.setattr(R, "_finish_run", _finish)
    R._RUNS["t_eval_gold"] = {"run_id": "t_eval_gold", "status": "running", "total": 0,
                              "done": 0, "current": "", "summary": None, "error": ""}

    asyncio.run(R._run_once("t_eval_gold", None, {}))
    return saved[0]


def test_run_once_marks_wrong_when_values_differ(monkeypatch):
    row = _run_once_with(monkeypatch, gold_rows=[[1]], model_rows=[[2]])
    assert row["gold_match"] is False, "金标 1 vs 模型 2 必须判错（不能只看 SQL 跑通）"


def test_run_once_marks_correct_when_values_equal(monkeypatch):
    row = _run_once_with(monkeypatch, gold_rows=[[1]], model_rows=[[1]])
    assert row["gold_match"] is True


# ===========================================================================
# 5) ask()：快路径任何异常都要回退慢路径，而不是整题崩溃
# ===========================================================================
def test_ask_falls_back_to_slow_path_on_metric_crash(monkeypatch):
    from app.plugin.module_ai.query import service as svc

    metric = {
        "key": "avg_contract_price", "name": "平均合同单价", "datasource": "ds:4",
        "sql_template": "SELECT AVG(CONTRACTPRICE) FROM FUEL_CB_COALBALANCE",
        "params": [], "dimensions": [], "cache_ttl": 0,
    }

    async def _seed(cls):
        return None

    async def _sess(cls, *a, **k):
        return {"id": 1}

    async def _metrics(cls, *a, **k):
        return [metric]

    async def _terms(cls, *a, **k):
        return []

    async def _boom(metric, params, auth=None):
        # 模拟"驱动异常没被包装"的真实故障
        raise RuntimeError("relation \"fuel_cb_coalbalance\" does not exist")

    async def _saved(cls, *a, **k):
        return object()

    async def _slow(cls, question, sess_id, ds, auth):
        return {"path": "slow", "marker": "fallback"}

    monkeypatch.setattr(svc.AiQueryService, "ensure_system_seed", classmethod(_seed))
    monkeypatch.setattr(svc.AiQueryService, "get_or_create_session", classmethod(_sess))
    monkeypatch.setattr(svc.AiQueryService, "list_metrics", classmethod(_metrics))
    monkeypatch.setattr(svc.AiQueryService, "list_terms", classmethod(_terms))
    monkeypatch.setattr(svc.AiQueryService, "_save_message", classmethod(_saved))
    monkeypatch.setattr(svc.AiQueryService, "_slow_path", classmethod(_slow))
    monkeypatch.setattr(svc, "_match_metric", lambda q, m, t: metric)
    monkeypatch.setattr(svc, "_execute_metric", _boom)

    out = asyncio.run(
        svc.AiQueryService.ask("平均合同单价是多少？", auth=None, datasource="ds:4")
    )
    assert out == {"path": "slow", "marker": "fallback"}, (
        f"快路径崩溃必须回退慢路径，实际: {out}"
    )
