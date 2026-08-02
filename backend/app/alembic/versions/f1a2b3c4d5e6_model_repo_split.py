"""模型仓库/版本拆分迁移

Revision ID: f1a2b3c4d5e6
Revises: e5f6a7b8c9d0
Create Date: 2026-08-02

"""
import uuid

import sqlalchemy as sa
from alembic import op

revision: str = "f1a2b3c4d5e6"
down_revision: str | None = "e5f6a7b8c9d0"
branch_labels: str | None = None
depends_on: str | None = None


def _normalize_version(raw: str | None) -> str:
    """'vv1' / 'v1' / '1' -> 'v1'"""
    digits = "".join(ch for ch in (raw or "") if ch.isdigit())
    n = int(digits) if digits else 1
    return f"v{n}"


def upgrade() -> None:
    # 复用现有 PG 枚举类型 trainframework（train_models.framework 已用它，避免重复 CREATE TYPE）
    op.create_table(
        "train_model_repos",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("uuid", sa.String(36), nullable=True),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("framework", sa.Enum(name="trainframework"), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("latest_version_id", sa.Integer(), nullable=True),
        sa.Column("annotation_dataset_id", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(16), server_default="draft", nullable=False),
        sa.Column("is_deleted", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("created_id", sa.Integer(), nullable=True),
        sa.Column("updated_id", sa.Integer(), nullable=True),
        sa.Column("deleted_id", sa.Integer(), nullable=True),
        sa.Column("created_time", sa.DateTime(), nullable=True),
        sa.Column("updated_time", sa.DateTime(), nullable=True),
        sa.Column("deleted_time", sa.DateTime(), nullable=True),
        sa.UniqueConstraint("name"),
    )
    op.add_column("train_models", sa.Column("repo_id", sa.Integer(), nullable=True))

    # 聚合回填：按 name 建仓库，版本号规范化
    conn = op.get_bind()
    rows = conn.execute(
        sa.text("SELECT id, name, version, framework FROM train_models WHERE is_deleted = false")
    ).fetchall()
    repos: dict[str, int] = {}
    for row in rows:
        rid, name, version, framework = row
        if name not in repos:
            result = conn.execute(
                sa.text(
                    "INSERT INTO train_model_repos (uuid, name, framework, status, created_time, updated_time) "
                    "VALUES (:uuid, :name, :framework, 'draft', NOW(), NOW()) RETURNING id"
                ),
                {"uuid": str(uuid.uuid4()), "name": name, "framework": framework},
            )
            repo_id = result.scalar()
            repos[name] = repo_id
        else:
            repo_id = repos[name]
        norm_ver = _normalize_version(version)
        conn.execute(
            sa.text("UPDATE train_models SET repo_id = :rid, version = :ver WHERE id = :id"),
            {"rid": repo_id, "ver": norm_ver, "id": rid},
        )

    # 回填 latest_version_id：每个仓库取 created_time 最新版本
    repo_rows = conn.execute(
        sa.text(
            "SELECT r.id, v.id AS vid FROM train_model_repos r "
            "JOIN LATERAL ("
            "  SELECT id FROM train_models v "
            "  WHERE v.repo_id = r.id AND v.is_deleted = false "
            "  ORDER BY v.created_time DESC NULLS LAST, v.id DESC LIMIT 1"
            ") v ON true"
        )
    ).fetchall()
    for repo_id, vid in repo_rows:
        conn.execute(
            sa.text("UPDATE train_model_repos SET latest_version_id = :vid WHERE id = :rid"),
            {"vid": vid, "rid": repo_id},
        )


def downgrade() -> None:
    op.drop_column("train_models", "repo_id")
    op.drop_table("train_model_repos")
