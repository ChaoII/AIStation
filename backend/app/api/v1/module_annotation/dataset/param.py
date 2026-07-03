from fastapi import Query


class DatasetQueryParam:
    def __init__(
        self,
        name: str | None = Query(None, description="数据集名称"),
        status: str | None = Query(None, description="状态: active/archived"),
    ):
        self.name = name
        self.status = status

    def get_conditions(self) -> list:
        conditions = []
        if self.name:
            conditions.append(("like", ("name", f"%{self.name}%")))
        if self.status:
            conditions.append(("eq", ("status", self.status)))
        return conditions
