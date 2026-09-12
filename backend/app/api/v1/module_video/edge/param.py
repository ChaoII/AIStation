from fastapi import Query


class EdgeQueryParam:
    """边缘设备列表查询参数。"""

    def __init__(
        self,
        name: str | None = Query(None, description="设备名称"),
        code: str | None = Query(None, description="设备编码"),
        status: str | None = Query(None, description="状态"),
    ) -> None:
        if name:
            self.name = ("like", name)
        if code:
            self.code = ("like", code)
        self.status = status
