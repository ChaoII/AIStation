"""数据合成服务：车牌合成 + 入库数据集 + 标注写入 + 任务持久化。"""
import asyncio
import base64
import io
import uuid

from app.core.logger import log
from app.utils.s3_client import s3_client

from .license_plate import PROVIDERS, render_license_plate, to_png_bytes
from .model import SynthesisJobModel
from .schema import GeneratedItem, JobOut, PlateGenerateReq, PlateGenerateResp, ProviderOut


async def list_providers() -> list[ProviderOut]:
    return [ProviderOut(**p) for p in PROVIDERS]


def _png_thumb_b64(content: bytes) -> str:
    from PIL import Image

    img = Image.open(io.BytesIO(content))
    img.thumbnail((320, 320))
    buf = io.BytesIO()
    img.convert("RGB").save(buf, format="JPEG", quality=70)
    return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()


def _disturbances_dict(req: PlateGenerateReq) -> dict:
    if req.disturbances is None:
        return {}
    return req.disturbances.model_dump()


async def _ensure_detection_task(db, dataset_id: int, auth) -> int:
    """确保数据集存在一个 detection 标注任务（用于承接合成标注）。"""
    from sqlalchemy import select

    from app.api.v1.module_annotation.dataset.model import AnnotationType
    from app.api.v1.module_annotation.task.model import AnnotationTaskModel
    from app.core.audit import set_create_audit

    existing = (
        await db.execute(
            select(AnnotationTaskModel).where(
                AnnotationTaskModel.dataset_id == dataset_id,
                AnnotationTaskModel.name == "车牌合成标注",
                AnnotationTaskModel.is_deleted == False,  # noqa: E712
            )
        )
    ).scalar_one_or_none()
    if existing:
        return existing.id

    task = AnnotationTaskModel(
        dataset_id=dataset_id,
        name="车牌合成标注",
        task_type=AnnotationType.DETECTION,
        status="pending",
        assignees=[],
        classes=[{"id": 1, "name": "plate", "color": "#409eff"}],
        progress=0,
    )
    set_create_audit(task, auth)
    db.add(task)
    await db.flush()
    return task.id


async def _write_annotation(db, task_id: int, image_id: int, item: GeneratedItem, auth) -> None:
    """为一张合成图写入一条检测标注记录（归一化 AxisAlignedBox）。"""
    from app.api.v1.module_annotation.annotation.model import AnnotationRecordModel
    from app.core.audit import set_create_audit

    b = item.bbox
    ann = {
        "id": uuid.uuid4().hex,
        "type": "AxisAlignedBox",
        "class_id": 1,
        "x1": b["x1"],
        "y1": b["y1"],
        "x2": b["x2"],
        "y2": b["y2"],
    }
    rec = AnnotationRecordModel(
        task_id=task_id,
        image_id=image_id,
        annotation_data=[ann],
        version=1,
    )
    set_create_audit(rec, auth)
    db.add(rec)


async def generate_license_plates(req: PlateGenerateReq, auth) -> PlateGenerateResp:
    """生成 count 张车牌合成图；指定数据集则上传入库并写标注；写入合成任务。"""
    from app.api.v1.module_annotation.dataset.media import (
        content_hash,
        content_type_for,
        process_image,
    )
    from app.api.v1.module_annotation.dataset.model import (
        AnnotationImageModel,
        DatasetModel,
        ImageStatus,
    )
    from app.core.audit import set_create_audit
    from app.core.database import async_db_session
    from app.core.exceptions import CustomException

    items: list[GeneratedItem] = []
    results_meta: list[dict] = []
    uploaded = False
    tasks = {}
    job_id = None
    dataset_id = req.dataset_id
    disturbances = _disturbances_dict(req)

    if dataset_id and req.upload:
        async with async_db_session() as db:
            ds = await db.get(DatasetModel, dataset_id)
            if not ds:
                raise CustomException(msg="数据集不存在", code=404, status_code=404)

    # 创建合成任务记录
    async with async_db_session.begin() as db:
        job = SynthesisJobModel(
            provider="license_plate",
            name="车牌合成",
            dataset_id=dataset_id,
            params={
                "plate_type": req.plate_type,
                "count": req.count,
                "seed": req.seed,
                "disturbances": disturbances,
                "width": req.width,
                "height": req.height,
                "upload": req.upload and bool(dataset_id),
                "with_annotation": req.with_annotation,
            },
            status="running",
            total=req.count,
            done=0,
        )
        set_create_audit(job, auth)
        db.add(job)
        await db.flush()
        job_id = job.id

    for i in range(req.count):
        seed = None if req.seed is None else req.seed + i
        result = render_license_plate(
            seed=seed,
            canvas_w=req.width,
            canvas_h=req.height,
            plate_type=req.plate_type,
            disturbances=disturbances,
        )
        content = to_png_bytes(result)
        filename = f"synth_plate_{uuid.uuid4().hex[:12]}.png"

        item = GeneratedItem(
            filename=filename,
            text=result.text,
            label=result.label,
            plate_type=result.plate_type,
            bbox=result.bbox,
            char_boxes=result.char_boxes,
            width=result.width,
            height=result.height,
            preview_base64=_png_thumb_b64(content),
        )

        if dataset_id and req.upload:
            digest = content_hash(content)
            ext = ".png"
            token = uuid.uuid4().hex
            object_key = f"datasets/{dataset_id}/images/{token}{ext}"
            thumb_key = f"datasets/{dataset_id}/thumbnails/{token}.jpg"
            width, height, thumb = await asyncio.to_thread(process_image, content)
            await asyncio.to_thread(
                s3_client.upload_fileobj, io.BytesIO(content), object_key,
                None, content_type_for(ext),
            )
            if thumb:
                await asyncio.to_thread(
                    s3_client.upload_fileobj, io.BytesIO(thumb), thumb_key,
                    None, "image/jpeg",
                )
            else:
                thumb_key = None
            async with async_db_session() as db:
                async with db.begin():
                    img = AnnotationImageModel(
                        dataset_id=dataset_id,
                        filename=filename,
                        object_key=object_key,
                        thumbnail_key=thumb_key,
                        content_hash=digest,
                        width=width,
                        height=height,
                        status=ImageStatus.ANNOTATED,
                    )
                    set_create_audit(img, auth)
                    db.add(img)
                    await db.flush()
                    item.image_id = img.id
                    # 标注写入
                    if req.with_annotation:
                        if dataset_id not in tasks:
                            tasks[dataset_id] = await _ensure_detection_task(db, dataset_id, auth)
                        await _write_annotation(db, tasks[dataset_id], img.id, item, auth)
            item.object_key = object_key
            uploaded = True

        items.append(item)
        results_meta.append({
            "filename": item.filename,
            "text": item.text,
            "plate_type": item.plate_type,
            "bbox": item.bbox,
            "image_id": item.image_id,
            "object_key": item.object_key,
        })

    # 任务完成
    async with async_db_session.begin() as db:
        j = await db.get(SynthesisJobModel, job_id)
        if j:
            j.done = len(items)
            j.status = "completed"
            j.results = results_meta

    log.info(f"✅ 车牌合成完成：{len(items)} 张，类型={req.plate_type}，入库={uploaded}")
    return PlateGenerateResp(provider="license_plate", job_id=job_id, uploaded=uploaded, items=items)


async def list_jobs(page_no: int = 1, page_size: int = 20) -> dict:
    from sqlalchemy import desc, func, select

    from app.core.database import async_db_session

    async with async_db_session() as db:
        total = (
            await db.execute(select(func.count()).select_from(SynthesisJobModel))
        ).scalar() or 0
        rows = (
            await db.execute(
                select(SynthesisJobModel)
                .order_by(desc(SynthesisJobModel.id))
                .offset((page_no - 1) * page_size)
                .limit(page_size)
            )
        ).scalars().all()
        items = [JobOut(
            id=r.id, provider=r.provider, name=r.name, dataset_id=r.dataset_id,
            params=r.params or {}, status=r.status, total=r.total, done=r.done,
            error=r.error, results=r.results or [],
            created_time=r.created_time.isoformat() if getattr(r, "created_time", None) else None,
        ) for r in rows]
        return {"page_no": page_no, "page_size": page_size, "total": total, "items": items}
