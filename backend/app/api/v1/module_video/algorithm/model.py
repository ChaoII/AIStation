from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, Integer, String, DateTime, Text, ForeignKey
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.base_model import MappedBase, ModelMixin, UserMixin


class AlgorithmModel(ModelMixin, UserMixin):
    __tablename__ = "video_algorithms"
    __table_args__ = ({'comment': '算法配置表'})

    name: Mapped[str] = mapped_column(String(128), nullable=False, comment="算法名称")
    code: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, comment="算法编码")
    version: Mapped[str] = mapped_column(String(32), default="1.0.0", comment="版本号")

    algorithm_type: Mapped[str] = mapped_column(String(32), nullable=False, comment="算法类型: INTRUSION/LINE_CROSSING/FACE_DETECT/...")
    model_path: Mapped[Optional[str]] = mapped_column(String(512), nullable=True, comment="模型文件路径")
    plugin_path: Mapped[Optional[str]] = mapped_column(String(512), nullable=True, comment="C++ SDK插件路径")

    input_params: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True, comment="输入参数配置")
    output_schema: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True, comment="输出数据格式")

    status: Mapped[bool] = mapped_column(Boolean, default=True, comment="是否启用")
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True, comment="描述")


class AlgorithmTaskModel(ModelMixin, UserMixin):
    __tablename__ = "video_algorithm_tasks"
    __table_args__ = ({'comment': '算法任务表'})

    camera_id: Mapped[int] = mapped_column(Integer, ForeignKey("video_cameras.id", ondelete="CASCADE"), nullable=False, index=True)
    camera: Mapped[Optional["CameraModel"]] = relationship(lazy="selectin")
    algorithm_id: Mapped[int] = mapped_column(Integer, ForeignKey("video_algorithms.id", ondelete="CASCADE"), nullable=False)
    algorithm: Mapped[Optional["AlgorithmModel"]] = relationship(lazy="selectin")

    stream_type: Mapped[str] = mapped_column(String(16), default="SUB", comment="分析码流: MAIN/SUB")
    detect_region: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True, comment="检测区域")
    sensitivity: Mapped[int] = mapped_column(Integer, default=50, comment="灵敏度 1-100")

    schedule_json: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True, comment="生效时间段")
    status: Mapped[str] = mapped_column(String(16), default="STOPPED", comment="状态: RUNNING/STOPPED/ERROR")
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True, comment="描述")
