from fastapi import Query


class FaceGalleryQueryParam:
    """底库列表查询参数（模糊匹配 name/person_no，精确匹配 model_key/kind）。"""

    def __init__(
        self,
        name: str | None = Query(None, description="人员姓名/标签"),
        person_no: str | None = Query(None, description="工号/自定义编号"),
        model_key: str | None = Query(None, description="特征模型标识"),
        kind: str | None = Query(None, description="底库类型：face / reid"),
    ) -> None:
        if name:
            self.name = ("like", name)
        if person_no:
            self.person_no = ("like", person_no)
        self.model_key = model_key
        self.kind = kind.strip().lower() if isinstance(kind, str) and kind.strip() else None
