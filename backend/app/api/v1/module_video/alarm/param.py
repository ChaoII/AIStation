from typing import Optional
from fastapi import Query


class AlarmRecordQueryParam:
    def __init__(
        self,
        camera_id: Optional[int] = Query(None, description="摄像机ID"),
        alarm_type: Optional[str] = Query(None, description="告警类型"),
        severity: Optional[str] = Query(None, description="严重级别"),
        status: Optional[str] = Query(None, description="状态"),
    ) -> None:
        self.camera_id = camera_id
        self.alarm_type = alarm_type
        self.severity = severity
        self.status = status
