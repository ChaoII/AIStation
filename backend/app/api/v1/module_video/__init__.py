from fastapi import APIRouter

video_router = APIRouter(prefix="/video")


def _register_video_routers():
    from .alarm.controller import AlarmRouter
    from .algorithm.controller import AlgorithmRouter
    from .camera.controller import CameraRouter
    from .edge.controller import EdgeRouter
    from .event.controller import EventRouter
    from .face_gallery.controller import FaceGalleryRouter
    from .inference.controller import SnapshotRouter
    from .layout.controller import LayoutRouter
    from .preview.controller import PreviewRouter
    from .record.controller import RecordRouter
    from .scene.controller import SceneRouter
    video_router.include_router(AlarmRouter)
    video_router.include_router(AlgorithmRouter)
    video_router.include_router(CameraRouter)
    video_router.include_router(EdgeRouter)
    video_router.include_router(EventRouter)
    video_router.include_router(FaceGalleryRouter)
    video_router.include_router(LayoutRouter)
    video_router.include_router(PreviewRouter)
    video_router.include_router(RecordRouter)
    video_router.include_router(SceneRouter)
    video_router.include_router(SnapshotRouter)
