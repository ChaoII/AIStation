"""时间序列事件标注数据模型测试：枚举、模型字段、互斥、迁移 up/down。"""
from importlib import import_module
from pathlib import Path

from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, inspect, text

from app.api.v1.module_annotation.annotation.model import AnnotationRecordModel
from app.api.v1.module_annotation.dataset.model import (
    AnnotationTimeSeriesModel,
    AnnotationType,
    DatasetModel,
    ImageStatus,
)

_VERSION_DIR = Path(__file__).parent.parent / "app" / "alembic" / "versions"


def test_time_series_event_enum():
    assert AnnotationType.TIME_SERIES_EVENT == "time_series_event"


def test_time_series_model_table_and_defaults():
    assert AnnotationTimeSeriesModel.__tablename__ == "annotation_time_series"
    cols = AnnotationTimeSeriesModel.__table__.columns
    assert "dataset_id" in cols
    assert "name" in cols
    assert "object_key" in cols
    assert "time_column" in cols
    assert "value_columns" in cols
    assert "row_count" in cols
    assert "time_unit" in cols
    assert "start_time" in cols
    assert "end_time" in cols
    assert "size_bytes" in cols
    assert cols["row_count"].default.arg == 0
    assert cols["time_unit"].type.length == 8
    assert cols["size_bytes"].default.arg == 0
    assert cols["annotation_count"].default.arg == 0
    assert cols["status"].default.arg is ImageStatus.UNANNOTATED


def test_time_series_model_nullable_fields():
    cols = AnnotationTimeSeriesModel.__table__.columns
    assert cols["start_time"].nullable is True
    assert cols["end_time"].nullable is True
    assert cols["locked_by"].nullable is True
    assert cols["locked_at"].nullable is True


def test_dataset_time_series_relationship_and_count():
    dcols = DatasetModel.__table__.columns
    assert "time_series_count" in dcols
    assert dcols["time_series_count"].default.arg == 0
    rels = DatasetModel.__mapper__.relationships
    assert "time_series" in rels
    assert rels["time_series"].argument == "AnnotationTimeSeriesModel"


def test_annotation_record_time_series_id():
    cols = AnnotationRecordModel.__table__.columns
    assert "time_series_id" in cols
    assert cols["time_series_id"].nullable is True


def test_annotation_record_time_series_composite_index():
    indexes = {idx.name: idx for idx in AnnotationRecordModel.__table__.indexes}
    assert "ix_annotation_record_task_timeseries_version" in indexes
    assert set(indexes["ix_annotation_record_task_timeseries_version"].columns.keys()) == {
        "task_id",
        "time_series_id",
        "version",
    }


def _load_migration():
    matches = list(_VERSION_DIR.glob("7a8b9c0d1e2f_*.py"))
    assert len(matches) == 1, f"期望唯一迁移文件: {matches}"
    return import_module(f"app.alembic.versions.{matches[0].stem}")


def _run_upgrade(connection, mod):
    ctx = MigrationContext.configure(connection)
    with Operations.context(ctx):
        mod.upgrade()


def _run_downgrade(connection, mod):
    ctx = MigrationContext.configure(connection)
    with Operations.context(ctx):
        mod.downgrade()


def test_migration_up_down_reversible():
    """迁移在空 SQLite 上可 upgrade/downgrade 且干净可逆。"""
    mod = _load_migration()
    # 线性单头：直连既有 head，无分叉。
    assert mod.revision == "7a8b9c0d1e2f"
    assert mod.down_revision == "6a7b8c9d0e1f"

    engine = create_engine("sqlite://")
    with engine.begin() as conn:
        # 预建被迁移补列/建索引所依赖的基表（模拟已存在的数据集/标注记录）。
        conn.execute(text("CREATE TABLE annotation_dataset (id INTEGER PRIMARY KEY)"))
        conn.execute(
            text(
                "CREATE TABLE annotation_record "
                "(id INTEGER PRIMARY KEY, task_id INTEGER, version INTEGER)"
            )
        )
        _run_upgrade(conn, mod)

        insp = inspect(conn)
        assert insp.has_table("annotation_time_series")
        ds_cols = {c["name"] for c in insp.get_columns("annotation_dataset")}
        assert "time_series_count" in ds_cols
        rec_cols = {c["name"] for c in insp.get_columns("annotation_record")}
        assert "time_series_id" in rec_cols
        rec_indexes = {ix["name"] for ix in insp.get_indexes("annotation_record")}
        assert "ix_annotation_record_task_timeseries_version" in rec_indexes

        # downgrade 干净回滚：删除列与表。
        _run_downgrade(conn, mod)
        assert not inspect(conn).has_table("annotation_time_series")
        ds_cols = {c["name"] for c in inspect(conn).get_columns("annotation_dataset")}
        assert "time_series_count" not in ds_cols
        rec_cols = {c["name"] for c in inspect(conn).get_columns("annotation_record")}
        assert "time_series_id" not in rec_cols
