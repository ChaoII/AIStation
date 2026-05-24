from typing import Optional

from sqlalchemy import Boolean, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.base_model import ModelMixin, UserMixin


class AlgorithmModel(ModelMixin, UserMixin):
    __tablename__ = "video_algorithms"
    __table_args__ = ({'comment': '算法配置表'})

    name: Mapped[str] = mapped_column(String(128), nullable=False, comment="算法名称")
    code: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, comment="算法编码")
    version: Mapped[str] = mapped_column(String(32), default="1.0.0", comment="版本号")

    algorithm_type: Mapped[str] = mapped_column(String(32), nullable=False, comment="算法类型: INTRUSION/LINE_CROSSING/FACE_DETECT/...")
    model_path: Mapped[str | None] = mapped_column(String(512), nullable=True, comment="模型文件路径")
    plugin_path: Mapped[str | None] = mapped_column(String(512), nullable=True, comment="C++ SDK插件路径")

    model_file_config: Mapped[dict | None] = mapped_column(JSONB, nullable=True, default=dict, comment="模型配置（格式、加密密钥、解密参数等）")
    runtime_config: Mapped[dict | None] = mapped_column(JSONB, nullable=True, default=dict, comment="运行时配置（推理引擎、GPU、线程数、批处理大小等）")
    preset_params: Mapped[dict | None] = mapped_column(JSONB, nullable=True, default=dict, comment="预设算法参数（按算法类型动态定义，如置信度阈值、人数上限等）")

    input_params: Mapped[dict | None] = mapped_column(JSONB, nullable=True, default=dict, comment="输入参数配置")
    output_schema: Mapped[dict | None] = mapped_column(JSONB, nullable=True, default=dict, comment="输出数据格式（绘制框、标签、颜色等）")

    status: Mapped[bool] = mapped_column(Boolean, default=True, comment="是否启用")
    description: Mapped[str | None] = mapped_column(Text, nullable=True, comment="描述")


class AlgorithmTaskModel(ModelMixin, UserMixin):
    __tablename__ = "video_algorithm_tasks"
    __table_args__ = ({'comment': '算法任务表'})

    camera_id: Mapped[int] = mapped_column(Integer, ForeignKey("video_cameras.id", ondelete="CASCADE"), nullable=False, index=True)
    camera: Mapped[Optional["CameraModel"]] = relationship(lazy="selectin")
    algorithm_id: Mapped[int] = mapped_column(Integer, ForeignKey("video_algorithms.id", ondelete="CASCADE"), nullable=False)
    algorithm: Mapped[Optional["AlgorithmModel"]] = relationship(lazy="selectin")

    stream_type: Mapped[str] = mapped_column(String(16), default="SUB", comment="分析码流: MAIN/SUB")
    detect_region: Mapped[dict | None] = mapped_column(JSONB, nullable=True, default=dict, comment="检测区域")
    sensitivity: Mapped[int] = mapped_column(Integer, default=50, comment="灵敏度 1-100")

    schedule_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True, default=dict, comment="生效时间段")
    runtime_overrides: Mapped[dict | None] = mapped_column(JSONB, nullable=True, default=dict, comment="运行时参数覆盖值")
    params_overrides: Mapped[dict | None] = mapped_column(JSONB, nullable=True, default=dict, comment="算法参数覆盖值（针对该布控点位调整阈值等）")

    status: Mapped[str] = mapped_column(String(16), default="STOPPED", comment="状态: RUNNING/STOPPED/ERROR")
    description: Mapped[str | None] = mapped_column(Text, nullable=True, comment="描述")
