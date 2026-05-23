from typing import Optional
from fastapi import Query

from app.core.validator import DateTimeStr


class CameraQueryParam:
    def __init__(
        self,
        name: Optional[str] = Query(None, description="摄像机名称"),
        device_type: Optional[str] = Query(None, description="设备类型"),
        status: Optional[str] = Query(None, description="状态: ONLINE/OFFLINE/ERROR"),
        group_id: Optional[int] = Query(None, description="分组ID"),
        location: Optional[str] = Query(None, description="安装位置"),
        brand: Optional[str] = Query(None, description="品牌"),
        gb28181_device_id: Optional[str] = Query(None, description="GB28181设备ID"),
        start_time: Optional[DateTimeStr] = Query(None, description="开始时间"),
        end_time: Optional[DateTimeStr] = Query(None, description="结束时间"),
    ) -> None:
        self.name = ("like", name)
        self.location = ("like", location)
        self.brand = ("like", brand)
        self.device_type = device_type
        self.status = status
        self.group_id = group_id
        self.gb28181_device_id = gb28181_device_id
        if start_time and end_time:
            self.created_at = ("between", (start_time, end_time))
