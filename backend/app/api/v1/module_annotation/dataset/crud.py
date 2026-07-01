from typing import Any

from app.core.base_crud import CRUDBase

from .model import DatasetModel, AnnotationImageModel
from .schema import DatasetCreateSchema, DatasetUpdateSchema


class DatasetCRUD(CRUDBase[DatasetModel, DatasetCreateSchema, DatasetUpdateSchema]):
    def __init__(self, auth: Any | None = None):
        super().__init__(DatasetModel, auth=auth)


dataset_crud = DatasetCRUD()


class ImageCRUD(CRUDBase[AnnotationImageModel, Any, Any]):
    def __init__(self, auth: Any | None = None):
        super().__init__(AnnotationImageModel, auth=auth)


image_crud = ImageCRUD()