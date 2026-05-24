
from fastapi import Query


class EventQueryParam:
    def __init__(
        self,
        name: str | None = Query(None, description="联动名称"),
        trigger_event: str | None = Query(None, description="触发事件"),
        action_type: str | None = Query(None, description="动作类型"),
        status: bool | None = Query(None, description="是否启用"),
    ) -> None:
        if name:
            self.name = ("like", name)
        self.trigger_event = trigger_event
        self.action_type = action_type
        self.status = status
