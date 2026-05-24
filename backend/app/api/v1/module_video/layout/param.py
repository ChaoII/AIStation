
from fastapi import Query


class LayoutQueryParam:
    def __init__(
        self,
        name: str | None = Query(None, description="布局名称"),
        grid_type: str | None = Query(None, description="布局类型"),
        is_default: bool | None = Query(None, description="是否默认"),
    ) -> None:
        if name:
            self.name = ("like", name)
        self.grid_type = grid_type
        self.is_default = is_default
