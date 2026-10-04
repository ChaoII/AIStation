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


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
