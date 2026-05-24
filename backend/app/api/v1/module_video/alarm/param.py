
from fastapi import Query


class AlarmRecordQueryParam:
    def __init__(
        self,
        camera_id: int | None = Query(None, description="摄像机ID"),
        alarm_type: str | None = Query(None, description="告警类型"),
        severity: str | None = Query(None, description="严重级别"),
        status: str | None = Query(None, description="状态"),
    ) -> None:
        self.camera_id = camera_id
        self.alarm_type = alarm_type
        self.severity = severity
        self.status = status
