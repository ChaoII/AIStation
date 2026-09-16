"""相机分组 parent_id 自引用外键回归（审计 M7）。

- 模型：``parent_id`` 必须是指向 ``video_camera_groups.id`` 的外键，``ON DELETE RESTRICT``；
- 数据库：开启 FK 约束时，删除仍有子分组的分组必须被拒绝（IntegrityError）；
- 迁移：存在补建该外键的迁移（幂等），down_revision 接在告警作用域约束之后。
"""
import pytest
import sqlalchemy as sa
from sqlalchemy import create_engine, event
from sqlalchemy.exc import IntegrityError

from app.api.v1.module_video.camera.model import CameraGroupModel

VERSIONS_DIR = __import__("pathlib").Path(__file__).parent.parent / "app" / "alembic" / "versions"


def test_model_parent_id_is_self_referential_fk():
    table = CameraGroupModel.__table__
    fks = [fk for fk in table.foreign_keys if fk.parent.name == "parent_id"]
    assert len(fks) == 1, "parent_id 必须有唯一自引用外键"
    fk = fks[0]
    assert fk.column.table.name == "video_camera_groups"
    assert fk.ondelete == "RESTRICT"
    assert fk.constraint.name == "fk_video_camera_groups_parent_id"


def test_parent_fk_blocks_deleting_parent_with_children(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'grp.db'}")

    @event.listens_for(engine, "connect")
    def _enable_fk(dbapi_conn, _record):  # pragma: no cover - 运行时钩子
        dbapi_conn.execute("PRAGMA foreign_keys=ON")

    CameraGroupModel.__table__.create(engine)
    groups = CameraGroupModel.__table__
    with engine.begin() as conn:
        conn.execute(groups.insert().values(name="parent"))
        parent_id = conn.execute(sa.select(sa.func.max(groups.c.id))).scalar()
        conn.execute(groups.insert().values(name="child", parent_id=parent_id))
    with pytest.raises(IntegrityError):
        with engine.begin() as conn:
            conn.execute(groups.delete().where(groups.c.id == parent_id))


def test_parent_fk_migration_exists_and_is_idempotent():
    matches = list(VERSIONS_DIR.glob("e6f7a8b9c0d1_*.py"))
    assert len(matches) == 1, matches
    src = matches[0].read_text(encoding="utf-8")
    assert '"d5e6f7a8b9c0"' in src
    assert "fk_video_camera_groups_parent_id" in src
    assert "batch_alter_table" in src  # SQLite 需重建表
    assert "RESTRICT" in src
    assert "parent_id IS NOT NULL" in src  # 悬挂父节点清理
