"""既有库自动补列清单（_ensure_missing_columns）覆盖测试。

保证模型新增列与「不跑 Alembic、仅重启后端」的兜底补列保持一致，
避免既有库因缺列在查询时 500。
"""
from app.scripts import init_app


def test_alarm_rules_columns_covered():
    """video_alarm_rules 的 params/rollout/group_id 必须在兜底补列清单内。"""
    cols = dict(init_app.ENSURE_NEW_COLUMNS["video_alarm_rules"])
    assert cols["conditions"] == "JSONB"
    assert "DEFAULT '{}'" in cols["params"]
    assert "DEFAULT '{}'" in cols["rollout"]
    assert cols["group_id"] == "INTEGER"


def test_algorithm_columns_covered():
    """H2：param_meta / previous_model_path / previous_version 必须登记（否则旧库 500）。"""
    cols = dict(init_app.ENSURE_NEW_COLUMNS["video_algorithms"])
    assert cols["param_meta"] == "JSONB"
    assert cols["previous_model_path"] == "VARCHAR(512)"
    assert cols["previous_version"] == "VARCHAR(32)"


def test_train_predicts_columns_covered():
    """旧版 train_predicts 兜底建表 DDL 缺 description/progress/error_log，需补登。"""
    cols = dict(init_app.ENSURE_NEW_COLUMNS["train_predicts"])
    assert cols["description"] == "TEXT"
    assert "INTEGER" in cols["progress"]
    assert cols["error_log"] == "TEXT"


def test_exec_ddl_isolates_failure():
    """H1：单条 DDL 失败必须返回 False 且不抛错，其它语句不受影响。"""
    import asyncio

    assert asyncio.run(init_app._exec_ddl("SELECT 1", "ok")) is True
    assert asyncio.run(
        init_app._exec_ddl("ALTER TABLE __no_such_table__ ADD COLUMN x INTEGER", "bad")
    ) is False


def test_all_entries_are_table_column_pairs():
    """清单结构合法：每项为 (列名, 类型) 二元组。"""
    for table, columns in init_app.ENSURE_NEW_COLUMNS.items():
        assert table
        for col_name, col_type in columns:
            assert isinstance(col_name, str) and col_name
            assert isinstance(col_type, str) and col_type
