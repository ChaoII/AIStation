"""智能问数核心逻辑单元测试：SQL 安全 / 时间解析 / 指标匹配 / 模板渲染。"""
import pytest

from app.plugin.module_ai.query.service import (
    _match_metric,
    _render_template,
    parse_time_range,
    validate_sql,
    SYSTEM_ALLOWED_TABLES,
)


# ---------------------------------------------------------------------------
# validate_sql：只读 + 单语句 + 白名单 + LIMIT
# ---------------------------------------------------------------------------
class TestValidateSql:
    def test_accept_select(self):
        sql = "SELECT COUNT(*) FROM video_alarm_records"
        out = validate_sql(sql, SYSTEM_ALLOWED_TABLES)
        assert out.startswith("SELECT")
        assert "LIMIT" in out

    def test_reject_delete(self):
        with pytest.raises(Exception):
            validate_sql("DELETE FROM video_alarm_records", SYSTEM_ALLOWED_TABLES)

    def test_reject_multi_statement(self):
        with pytest.raises(Exception):
            validate_sql("SELECT 1; SELECT 2", SYSTEM_ALLOWED_TABLES)

    def test_comment_injection_neutralized(self):
        # `--` 后的内容整行被当作注释剥离，注入被中和而非放大
        out = validate_sql("SELECT 1 -- ; DROP TABLE t", SYSTEM_ALLOWED_TABLES)
        assert "DROP" not in out.upper()

    def test_reject_semicolon_after_real_stmt(self):
        with pytest.raises(Exception):
            validate_sql("SELECT 1; DROP TABLE t", SYSTEM_ALLOWED_TABLES)

    def test_reject_unknown_table(self):
        with pytest.raises(Exception):
            validate_sql("SELECT * FROM hack_table", SYSTEM_ALLOWED_TABLES)

    def test_reject_insert(self):
        with pytest.raises(Exception):
            validate_sql("INSERT INTO video_alarm_records VALUES (1)", SYSTEM_ALLOWED_TABLES)

    def test_reject_empty(self):
        with pytest.raises(Exception):
            validate_sql("", SYSTEM_ALLOWED_TABLES)

    def test_limit_not_duplicated(self):
        sql = "SELECT * FROM video_cameras LIMIT 5"
        out = validate_sql(sql, SYSTEM_ALLOWED_TABLES)
        assert out.count("LIMIT") == 1


# ---------------------------------------------------------------------------
# parse_time_range
# ---------------------------------------------------------------------------
class TestParseTime:
    def test_days_explicit(self):
        assert parse_time_range("最近7天告警") == {"days": 7}

    def test_today(self):
        assert parse_time_range("今天告警数") == {"days": 1}

    def test_month(self):
        assert parse_time_range("本月告警数") == {"days": 30}

    def test_week(self):
        assert parse_time_range("本周告警数") == {"days": 7}

    def test_none(self):
        assert parse_time_range("在线摄像头数") == {}


# ---------------------------------------------------------------------------
# _render_template
# ---------------------------------------------------------------------------
class TestRenderTemplate:
    def test_number(self):
        sql = _render_template("SELECT * WHERE days={days}", {"days": 7})
        assert "7" in sql

    def test_string_sanitized(self):
        with pytest.raises(Exception):
            _render_template("SELECT * WHERE x={a}", {"a": "1; DROP"})

    def test_missing_keeps_placeholder(self):
        sql = _render_template("SELECT * WHERE x={a}", {})
        assert "{a}" in sql


# ---------------------------------------------------------------------------
# _match_metric
# ---------------------------------------------------------------------------
def _mk_metrics():
    return [
        {
            "key": "alert_count_today", "name": "今日告警数", "enabled": True,
            "agg": "count", "unit": "条", "sql_template": "SELECT 1", "params": [],
            "dimensions": [], "description": "", "permission_tag": "", "sort": 0,
            "cache_ttl": 30,
        },
        {
            "key": "camera_online_count", "name": "在线摄像头数", "enabled": True,
            "agg": "count", "unit": "台", "sql_template": "SELECT 2", "params": [],
            "dimensions": [], "description": "", "permission_tag": "", "sort": 0,
            "cache_ttl": 30,
        },
    ]


class TestMatchMetric:
    def test_metric_name_hit(self):
        m = _match_metric("今日告警数是多少", _mk_metrics(), [])
        assert m["key"] == "alert_count_today"

    def test_term_alias_hit(self):
        terms = [{"term": "报警", "metric_key": "alert_count_today", "type": "metric"}]
        m = _match_metric("今天报警多少条", _mk_metrics(), terms)
        assert m["key"] == "alert_count_today"

    def test_no_match(self):
        assert _match_metric("我想知道天气", _mk_metrics(), []) is None


# ---------------------------------------------------------------------------
# 阶段B：自定义数据源连接串
# ---------------------------------------------------------------------------
class TestDsUrl:
    def test_postgres_url(self):
        from app.plugin.module_ai.query.executor import _url

        u = _url({"type": "postgres", "host": "h", "port": 5432, "database": "db",
                  "username": "u", "password": "p"})
        assert u == "postgresql+asyncpg://u:p@h:5432/db"

    def test_mysql_url(self):
        from app.plugin.module_ai.query.executor import _url

        u = _url({"type": "mysql", "host": "h", "port": 3306, "database": "db",
                  "username": "u", "password": "p"})
        assert u == "mysql+asyncmy://u:p@h:3306/db"

    def test_sqlite_url(self):
        from app.plugin.module_ai.query.executor import _url

        u = _url({"type": "sqlite", "database": "/tmp/a.db"})
        assert u == "sqlite+aiosqlite:////tmp/a.db"

    def test_unsupported_type(self):
        from app.plugin.module_ai.query.executor import _url

        assert _url({"type": "api"}) is None


class TestCustomDsValidate:
    def test_custom_allowed_table_pass(self):
        out = validate_sql("SELECT * FROM sales", {"sales"})
        assert "LIMIT" in out

    def test_custom_unknown_table_reject(self):
        with pytest.raises(Exception):
            validate_sql("SELECT * FROM secret", {"sales"})

    def test_render_uses_sanitize(self):
        from app.plugin.module_ai.query.service import _render_template

        sql = _render_template(
            "SELECT COUNT(*) FROM t WHERE day >= CURRENT_DATE - INTERVAL '{days}' DAY",
            {"days": 7},
        )
        assert "7" in sql


# ---------------------------------------------------------------------------
# 阶段C：Redis 缓存 key 确定性
# ---------------------------------------------------------------------------
class TestCacheKey:
    def test_deterministic(self):
        from app.plugin.module_ai.query.service import AiQueryService

        k1 = AiQueryService._cache_key({"datasource": "system", "key": "alert_count_today"}, {"days": 7})
        k2 = AiQueryService._cache_key({"datasource": "system", "key": "alert_count_today"}, {"days": 7})
        assert k1 == k2
        assert k1.startswith("ai:query:")

    def test_diff_params_diff_key(self):
        from app.plugin.module_ai.query.service import AiQueryService

        k1 = AiQueryService._cache_key({"datasource": "system", "key": "k"}, {"days": 7})
        k2 = AiQueryService._cache_key({"datasource": "system", "key": "k"}, {"days": 30})
        assert k1 != k2


# ---------------------------------------------------------------------------
# 阶段：数据源角色授权
# ---------------------------------------------------------------------------
class _R:
    def __init__(self, code):
        self.code = code


class TestDsRoleAuth:
    def test_user_role_codes(self):
        from app.plugin.module_ai.query.service import _user_role_codes

        auth = type("A", (), {"user": type("U", (), {"roles": [_R("admin"), _R("viewer")]})()})()
        assert _user_role_codes(auth) == {"admin", "viewer"}

    def test_user_role_codes_empty(self):
        from app.plugin.module_ai.query.service import _user_role_codes

        auth = type("A", (), {"user": type("U", (), {"roles": None})()})()
        assert _user_role_codes(auth) == set()


# ---------------------------------------------------------------------------
# 阶段：schema 裁剪 + sqlglot AST 校验
# ---------------------------------------------------------------------------
class TestSchemaPrune:
    def test_relevant_tables_alarm(self):
        from app.plugin.module_ai.query.service import AiQueryService

        schema = {
            "video_alarm_records": ["alarm_time(timestamp)", "alarm_type(varchar)", "camera_id(int)"],
            "video_cameras": ["name(varchar)", "group_id(int)"],
            "train_tasks": ["name(varchar)", "status(varchar)"],
            "sys_user": ["username(varchar)"],
        }
        rel = AiQueryService._relevant_tables("统计告警数量", schema, [], [])
        assert "video_alarm_records" in rel
        assert "video_cameras" in rel or "train_tasks" in rel or "sys_user" in rel


class TestSqlglotValidate:
    def test_accept_select(self):
        assert "LIMIT" in validate_sql("SELECT * FROM video_cameras", SYSTEM_ALLOWED_TABLES)

    def test_reject_insert_via_ast(self):
        with pytest.raises(Exception):
            validate_sql("INSERT INTO t VALUES (1)", SYSTEM_ALLOWED_TABLES)


# ---------------------------------------------------------------------------
# 阶段：embedding 语义检索（schema linking）辅助函数
# ---------------------------------------------------------------------------
class TestSemanticHelpers:
    def test_cosine_identical(self):
        from app.plugin.module_ai.query.service import _cosine

        v = [1.0, 2.0, 3.0]
        assert abs(_cosine(v, v) - 1.0) < 1e-6

    def test_cosine_orthogonal(self):
        from app.plugin.module_ai.query.service import _cosine

        assert abs(_cosine([1.0, 0.0], [0.0, 1.0])) < 1e-6

    def test_tables_in_sql(self):
        from app.plugin.module_ai.query.service import _tables_in_sql

        ts = _tables_in_sql(
            "SELECT c.name FROM video_cameras c JOIN video_alarm_records r ON r.camera_id=c.id"
        )
        assert "video_cameras" in ts and "video_alarm_records" in ts


# ---------------------------------------------------------------------------
# 分层检索（jieba + 融合）
# ---------------------------------------------------------------------------
class TestRetrieval:
    def test_tokenize_includes_chinese_and_latin(self):
        from app.plugin.module_ai.query.retrieval import tokenize

        toks = tokenize("每个摄像头组的告警数量 video_alarm")
        assert any("告警" in t or "告警" == t for t in toks)
        assert "video_alarm" in toks

    def test_keyword_score_higher_on_overlap(self):
        from app.plugin.module_ai.query.retrieval import keyword_score

        s1 = keyword_score("告警数量", "每告警数量统计")
        s2 = keyword_score("告警数量", "训练任务进度")
        assert s1 > s2

    def test_cosine(self):
        from app.plugin.module_ai.query.retrieval import _cosine

        assert abs(_cosine([1, 0], [1, 0]) - 1.0) < 1e-6
        assert abs(_cosine([1, 0], [0, 1])) < 1e-6


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
