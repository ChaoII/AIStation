from sqlalchemy import desc, select

from app.core.database import async_db_session

from .export_model import DatasetExportModel


class DatasetExportService:

    @classmethod
    async def list_exports(cls, dataset_id: int) -> list[dict]:
        async with async_db_session() as db:
            result = await db.execute(
                select(DatasetExportModel)
                .where(DatasetExportModel.dataset_id == dataset_id)
                .order_by(desc(DatasetExportModel.export_time))
            )
            rows = result.scalars().all()
            return [
                {
                    "id": r.id,
                    "format": r.format,
                    "file_size": r.file_size,
                    "checksum": r.checksum,
                    "export_time": r.export_time.isoformat() if r.export_time else None,
                    "exported_by": r.exported_by,
                    "download_url": r.download_url,
                }
                for r in rows
            ]
