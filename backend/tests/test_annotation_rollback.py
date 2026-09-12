"""标注回滚：回滚生成新版本且内容等于目标版本。"""
import asyncio
from types import SimpleNamespace

from app.api.v1.module_annotation.annotation.model import AnnotationRecordModel
from app.api.v1.module_annotation.annotation.service import AnnotationService
from app.api.v1.module_annotation.dataset.model import AnnotationImageModel, DatasetModel
from app.core.database import async_db_session


def test_rollback_creates_new_version_with_target_content():
    async def _run():
        async with async_db_session.begin() as db:
            ds = DatasetModel(name="P5A回滚集")
            db.add(ds)
            await db.flush()
            img = AnnotationImageModel(
                dataset_id=ds.id,
                filename="a.jpg",
                object_key="a.jpg",
                width=100,
                height=100,
                status="annotated",
            )
            db.add(img)
            await db.flush()
            image_id = img.id
            db.add(
                AnnotationRecordModel(
                    task_id=999,
                    image_id=image_id,
                    annotation_data=[{"v": 1}],
                    version=1,
                    created_id=1,
                )
            )
            db.add(
                AnnotationRecordModel(
                    task_id=999,
                    image_id=image_id,
                    annotation_data=[{"v": 2}],
                    version=2,
                    created_id=1,
                )
            )

        auth = SimpleNamespace(user=SimpleNamespace(id=1))
        result = await AnnotationService.rollback_annotation(999, image_id, 1, auth)
        assert result["version"] == 3

        async with async_db_session() as db:
            from sqlalchemy import select

            rows = (
                await db.execute(
                    select(AnnotationRecordModel)
                    .where(AnnotationRecordModel.image_id == image_id)
                    .order_by(AnnotationRecordModel.version)
                )
            ).scalars().all()
            assert [r.version for r in rows] == [1, 2, 3]
            assert rows[-1].annotation_data == [{"v": 1}]

    asyncio.run(_run())
