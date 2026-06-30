from datetime import datetime

from pydantic import BaseModel, Field


class BBoxModel(BaseModel):
    x: float = Field(..., ge=0, le=1, description="左上角 x（归一化）")
    y: float = Field(..., ge=0, le=1, description="左上角 y（归一化）")
    width: float = Field(..., ge=0, le=1, description="宽度（归一化）")
    height: float = Field(..., ge=0, le=1, description="高度（归一化）")


class DetectionItem(BaseModel):
    label: str = Field(..., description="标签名称")
    label_id: int = Field(..., description="标签 ID")
    confidence: float = Field(..., ge=0, le=1, description="置信度")
    bbox: BBoxModel = Field(..., description="边界框")


class DetectionEventSchema(BaseModel):
    task_id: int = Field(..., description="算法任务 ID")
    camera_id: int = Field(..., description="摄像头 ID")
    algorithm_type: str = Field(..., description="算法类型")
    detections: list[DetectionItem] = Field(default_factory=list, description="检测结果列表")
    snapshot_data: str | None = Field(default=None, description="base64 JPEG 快照数据")
    snapshot_path: str | None = Field(default=None, description="快照文件路径（相对 detectors_dir）")
    frame_timestamp: datetime | None = Field(default=None, description="帧时间戳")
    inference_latency_ms: float | None = Field(default=None, description="推理延迟（毫秒）")


class InferenceStatusSchema(BaseModel):
    task_id: int
    status: str = Field(..., description="RUNNING / STOPPED / ERROR / UNKNOWN")
    pid: int | None = None
    uptime_seconds: float | None = None
    fps: float | None = None
    inference_latency_ms: float | None = None
