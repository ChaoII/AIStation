from fastapi import Query

from app.core.validator import DateTimeStr


class RecordPlanQueryParam:
    def __init__(
        self,
        camera_id: int | None = Query(None, description="摄像机ID"),
        plan_type: str | None = Query(None, description="计划类型"),
        status: bool | None = Query(None, description="是否启用"),
    ) -> None:
        self.camera_id = camera_id
        self.plan_type = plan_type
        self.status = status


class RecordFileQueryParam:
    def __init__(
        self,
        camera_id: int | None = Query(None, description="摄像机ID"),
        record_type: str | None = Query(None, description="录制类型"),
        format: str | None = Query(None, description="文件格式"),
        start_time: DateTimeStr | None = Query(None, description="开始时间"),
        end_time: DateTimeStr | None = Query(None, description="结束时间"),
    ) -> None:
        self.camera_id = camera_id
        self.record_type = record_type
        self.format = format
        if start_time and end_time:
            self.start_time = ("between", (start_time, end_time))
            self.end_time = None


class RecordExecutionLogQueryParam:
    def __init__(
        self,
        camera_id: int | None = Query(None, description="摄像机ID"),
        plan_id: int | None = Query(None, description="计划ID"),
        status: str | None = Query(None, description="状态"),
        trigger_type: str | None = Query(None, description="触发方式"),
        start_time: DateTimeStr | None = Query(None, description="开始时间"),
        end_time: DateTimeStr | None = Query(None, description="结束时间"),
    ) -> None:
        self.camera_id = camera_id
        self.plan_id = plan_id
        self.status = status
        self.trigger_type = trigger_type
        if start_time and end_time:
            self.start_time = ("between", (start_time, end_time))
            self.end_time = None
