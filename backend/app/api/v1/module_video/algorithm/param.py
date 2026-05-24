
from fastapi import Query


class AlgorithmQueryParam:
    def __init__(
        self,
        name: str | None = Query(None, description="算法名称"),
        algorithm_type: str | None = Query(None, description="算法类型"),
        status: bool | None = Query(None, description="是否启用"),
    ) -> None:
        if name:
            self.name = ("like", name)
        self.algorithm_type = algorithm_type
        self.status = status


class AlgorithmTaskQueryParam:
    def __init__(
        self,
        camera_id: int | None = Query(None, description="摄像机ID"),
        algorithm_id: int | None = Query(None, description="算法ID"),
        status: str | None = Query(None, description="状态"),
    ) -> None:
        self.camera_id = camera_id
        self.algorithm_id = algorithm_id
        self.status = status
