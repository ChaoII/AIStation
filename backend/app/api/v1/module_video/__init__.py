from fastapi import APIRouter

video_router = APIRouter(prefix="/video")


def _register_video_routers():
    from .alarm.controller import AlarmRouter
    from .camera.controller import CameraRouter
    from .event.controller import EventRouter
    from .preview.controller import PreviewRouter
    from .record.controller import RecordRouter
    video_router.include_router(AlarmRouter)
    video_router.include_router(CameraRouter)
    video_router.include_router(EventRouter)
    video_router.include_router(PreviewRouter)
    video_router.include_router(RecordRouter)
