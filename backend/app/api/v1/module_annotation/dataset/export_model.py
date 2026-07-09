from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.base_model import MappedBase


class DatasetExportModel(MappedBase):
    __tablename__ = "annotation_dataset_export"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    dataset_id: Mapped[int] = mapped_column(
        ForeignKey("annotation_dataset.id", ondelete="CASCADE"), comment="数据集ID"
    )
    format: Mapped[str] = mapped_column(String(32), comment="导出格式")
    exported_by: Mapped[int] = mapped_column(Integer, comment="导出用户ID")
    download_url: Mapped[str | None] = mapped_column(String(512), nullable=True, comment="下载地址")
    file_size: Mapped[int] = mapped_column(Integer, default=0, comment="导出文件大小(bytes)")
    checksum: Mapped[str | None] = mapped_column(String(64), nullable=True, comment="MD5")
    export_time: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, comment="导出时间")
    extra: Mapped[dict | None] = mapped_column(JSONB, nullable=True, default=None, comment="额外信息")