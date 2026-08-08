from fastapi import Query


class DatasetQueryParam:
    def __init__(
        self,
        id: int | None = Query(None, description="数据集ID"),
        name: str | None = Query(None, description="数据集名称"),
        status: str | None = Query(None, description="状态: active/archived"),
    ):
        self.id = id
        self.name = name
        self.status = status

    def get_conditions(self) -> dict:
        # CRUDBase.page 期望 search 为 dict：{字段: (操作, 值)}
        conditions: dict = {}
        if self.id:
            conditions["id"] = self.id
        if self.name:
            conditions["name"] = ("like", self.name)
        if self.status:
            conditions["status"] = ("eq", self.status)
        return conditions
