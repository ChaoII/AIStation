from fastapi import APIRouter

annotation_router = APIRouter(prefix="/annotation")


def _register_annotation_routers():
    from .dataset.controller import DatasetRouter
    from .task.controller import TaskRouter
    from .annotation.controller import AnnotationRouter
    from .collaboration.controller import CollaborationRouter
    annotation_router.include_router(DatasetRouter)
    annotation_router.include_router(TaskRouter)
    annotation_router.include_router(AnnotationRouter)
    annotation_router.include_router(CollaborationRouter)