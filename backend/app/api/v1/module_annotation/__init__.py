from fastapi import APIRouter

annotation_router = APIRouter(prefix="/annotation")


def _register_annotation_routers():
    from .annotation.controller import AnnotationRouter
    from .collaboration.controller import CollaborationRouter
    from .dataset.controller import DatasetRouter
    from .dataset.export_controller import ExportRouter
    from .task.controller import TaskRouter
    annotation_router.include_router(DatasetRouter)
    annotation_router.include_router(TaskRouter)
    annotation_router.include_router(AnnotationRouter)
    annotation_router.include_router(CollaborationRouter)
    annotation_router.include_router(ExportRouter)
    from .stats.controller import StatsRouter
    annotation_router.include_router(StatsRouter)
