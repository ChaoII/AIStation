"""个人工作空间：文件夹表 + 文件元信息表

Revision ID: c0ffee111111
Revises: f6b7c8d9e0a1
Create Date: 2026-10-19 00:00:00.000000

说明：手写迁移。autogenerate 会因本项目存在大量未被模型覆盖的历史/影子表
（ont_* 等）产生无关 DROP，因此只保留本特性所需变更。
插件模块表（ai_*）可由应用启动 create_all 兜底，此处 ``has_table`` 幂等守卫，
避免空库全链重放（SQLite 回归）失败。
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c0ffee111111"
down_revision: str | None = "f6b7c8d9e0a1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _base_cols() -> list[sa.Column]:
    """ModelMixin 通用列（与模型一致）。"""
    return [
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("uuid", sa.String(length=64), nullable=False, unique=True),
        sa.Column("status", sa.String(length=10), nullable=False, server_default="0"),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("created_time", sa.DateTime(), nullable=False),
        sa.Column("updated_time", sa.DateTime(), nullable=False),
        sa.Column("is_deleted", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("deleted_time", sa.DateTime(), nullable=True),
    ]


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)

    if "ai_space_folders" not in insp.get_table_names():
        op.create_table(
            "ai_space_folders",
            *_base_cols(),
            sa.Column("name", sa.String(length=255), nullable=False, comment="文件夹名称"),
            sa.Column(
                "user_id", sa.Integer(), sa.ForeignKey("sys_user.id", ondelete="CASCADE"),
                nullable=False, comment="归属用户ID",
            ),
            sa.Column(
                "parent_id", sa.Integer(),
                sa.ForeignKey("ai_space_folders.id", ondelete="CASCADE"),
                nullable=True, comment="父文件夹ID（空为根目录）",
            ),
            comment="个人工作空间文件夹表",
        )

    if "ai_space_files" not in insp.get_table_names():
        op.create_table(
            "ai_space_files",
            *_base_cols(),
            sa.Column(
                "folder_id", sa.Integer(),
                sa.ForeignKey("ai_space_folders.id", ondelete="CASCADE"),
                nullable=True, comment="所属文件夹ID（空为根目录）",
            ),
            sa.Column(
                "user_id", sa.Integer(), sa.ForeignKey("sys_user.id", ondelete="CASCADE"),
                nullable=False, comment="归属用户ID",
            ),
            sa.Column("name", sa.String(length=255), nullable=False, comment="文件名（含扩展名）"),
            sa.Column("ext", sa.String(length=32), nullable=False, server_default="", comment="扩展名（小写，不含点）"),
            sa.Column(
                "file_type", sa.String(length=32), nullable=False, server_default="other",
                comment="分类 image/pdf/docx/txt/md/csv/json/video/audio/other",
            ),
            sa.Column(
                "mime_type", sa.String(length=128), nullable=False,
                server_default="application/octet-stream", comment="MIME 类型",
            ),
            sa.Column("size", sa.BigInteger(), nullable=False, server_default="0", comment="文件大小（字节）"),
            sa.Column(
                "object_key", sa.String(length=512), nullable=False, unique=True,
                comment="对象存储 Key",
            ),
            sa.Column(
                "source", sa.String(length=16), nullable=False, server_default="upload",
                comment="来源 upload=用户上传 agent=智能体生成",
            ),
            comment="个人工作空间文件表",
        )


def downgrade() -> None:
    op.drop_table("ai_space_files")
    op.drop_table("ai_space_folders")
