from app.core.base_crud import CRUDBase

from .model import AnnotationTaskModel
from .schema import TaskCreateSchema, TaskUpdateSchema


class TaskCRUD(CRUDBase[AnnotationTaskModel, TaskCreateSchema, TaskUpdateSchema]):
    def __init__(self, auth=None):
        super().__init__(AnnotationTaskModel, auth=auth)
