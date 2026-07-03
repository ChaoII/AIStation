from app.core.base_crud import CRUDBase

from .model import AnnotationRecordModel
from .schema import AnnotationSaveSchema


class AnnotationCRUD(CRUDBase[AnnotationRecordModel, AnnotationSaveSchema, AnnotationSaveSchema]):
    def __init__(self, auth=None):
        super().__init__(AnnotationRecordModel, auth=auth)
