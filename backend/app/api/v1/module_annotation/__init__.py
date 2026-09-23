from fastapi import APIRouter

annotation_router = APIRouter(prefix="/annotation")


def _register_annotation_routers():
    from .annotation.controller import AnnotationRouter
    from .dataset.audio_controller import AudioRouter
    from .dataset.clean.controller import CleanRouter
    from .dataset.controller import DatasetRouter
    from .dataset.document_controller import DocumentRouter
    from .dataset.export_controller import ExportRouter
    from .dataset.time_series_controller import TimeSeriesRouter
    from .dataset.video_controller import VideoRouter
    from .task.controller import TaskRouter
    annotation_router.include_router(DatasetRouter)
    annotation_router.include_router(AudioRouter)
    annotation_router.include_router(VideoRouter)
    annotation_router.include_router(DocumentRouter)
    annotation_router.include_router(TimeSeriesRouter)
    annotation_router.include_router(TaskRouter)
    annotation_router.include_router(AnnotationRouter)
    annotation_router.include_router(ExportRouter)
    annotation_router.include_router(CleanRouter)
    from .stats.controller import StatsRouter
    annotation_router.include_router(StatsRouter)


def get_collaboration_router():
    from .collaboration.controller import CollaborationRouter

    return CollaborationRouter
