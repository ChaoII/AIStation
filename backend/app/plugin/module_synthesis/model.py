"""数据合成任务模型。"""
from sqlalchemy import ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.base_model import ModelMixin, UserMixin


class SynthesisJobModel(ModelMixin, UserMixin):
    __tablename__ = "synthesis_job"

    provider: Mapped[str] = mapped_column(String(64), comment="合成器 key，如 license_plate")
    name: Mapped[str] = mapped_column(String(128), default="车牌合成", comment="任务名称")
    dataset_id: Mapped[int | None] = mapped_column(
        ForeignKey("annotation_dataset.id"), nullable=True, comment="目标数据集ID"
    )
    params: Mapped[dict] = mapped_column(JSONB, default=dict, comment="合成参数 JSON")
    status: Mapped[str] = mapped_column(String(16), default="pending", comment="pending/running/completed/failed")
    total: Mapped[int] = mapped_column(Integer, default=0, comment="计划生成数量")
    done: Mapped[int] = mapped_column(Integer, default=0, comment="已完成数量")
    error: Mapped[str | None] = mapped_column(Text, nullable=True, comment="失败原因")
    results: Mapped[list] = mapped_column(JSONB, default=list, comment="产物元数据（不含大图 base64）")

    __mapper_args__ = {"eager_defaults": True}
