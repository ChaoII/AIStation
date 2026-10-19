"""个人工作空间模型：多级文件夹 + 文件元信息（二进制存 RustFS/S3）。

隔离规则：所有业务查询强制 ``user_id == 当前登录用户``（服务层保证），
不提供任何共享视图；表仅存元信息，文件内容在 S3（object_key 前缀按用户隔离）。
"""
from __future__ import annotations

from sqlalchemy import BigInteger, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.base_model import ModelMixin


class AiSpaceFolderModel(ModelMixin):
    """个人空间文件夹（多级，parent_id 为 NULL 表示根目录）。"""

    __tablename__ = "ai_space_folders"
    __table_args__ = ({"comment": "个人工作空间文件夹表"},)

    name: Mapped[str] = mapped_column(String(255), nullable=False, comment="文件夹名称")
    user_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("sys_user.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="归属用户ID",
    )
    parent_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("ai_space_folders.id", ondelete="CASCADE"),
        nullable=True,
        default=None,
        index=True,
        comment="父文件夹ID（空为根目录）",
    )


class AiSpaceFileModel(ModelMixin):
    """个人空间文件元信息（内容在 RustFS/S3，object_key 唯一）。"""

    __tablename__ = "ai_space_files"
    __table_args__ = ({"comment": "个人工作空间文件表"},)

    folder_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("ai_space_folders.id", ondelete="CASCADE"),
        nullable=True,
        default=None,
        index=True,
        comment="所属文件夹ID（空为根目录）",
    )
    user_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("sys_user.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="归属用户ID",
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False, comment="文件名（含扩展名）")
    ext: Mapped[str] = mapped_column(String(32), nullable=False, default="", comment="扩展名（小写，不含点）")
    file_type: Mapped[str] = mapped_column(
        String(32), nullable=False, default="other", comment="分类 image/pdf/docx/txt/md/csv/json/video/audio/other"
    )
    mime_type: Mapped[str] = mapped_column(String(128), nullable=False, default="application/octet-stream", comment="MIME 类型")
    size: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0, comment="文件大小（字节）")
    object_key: Mapped[str] = mapped_column(
        String(512), nullable=False, unique=True, comment="对象存储 Key"
    )
    source: Mapped[str] = mapped_column(
        String(16), nullable=False, default="upload", comment="来源 upload=用户上传 agent=智能体生成"
    )
