"""为存量标注图片回填缩略图。

用法（工作目录 backend）:
    uv run python scripts/backfill_annotation_thumbnails.py --dataset-id 12 --limit 100
    uv run python scripts/backfill_annotation_thumbnails.py --dry-run
"""
import argparse
import asyncio
import io
import os
import sys

# 允许直接以脚本运行：把 backend 根目录加入 sys.path，并在导入 app 前固定环境
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
os.environ.setdefault("ENVIRONMENT", "dev")

from sqlalchemy import select

from app.api.v1.module_annotation.dataset.media import process_image
from app.api.v1.module_annotation.dataset.model import AnnotationImageModel
from app.core.database import async_db_session
from app.utils.s3_client import s3_client


def _register_models() -> None:
    """注册全部 SQLAlchemy 模型，避免 relationship 解析失败。"""
    from main import create_app

    create_app()


async def _run(dataset_id: int | None, limit: int | None, dry_run: bool) -> tuple[int, int]:
    done = skipped = 0
    async with async_db_session() as db:
        stmt = select(AnnotationImageModel).where(
            AnnotationImageModel.thumbnail_key.is_(None),
            AnnotationImageModel.is_deleted == False,  # noqa: E712
        )
        if dataset_id:
            stmt = stmt.where(AnnotationImageModel.dataset_id == dataset_id)
        if limit:
            stmt = stmt.limit(limit)
        images = (await db.execute(stmt)).scalars().all()

        for img in images:
            try:
                data = s3_client.download_fileobj(img.object_key)
                _, _, thumb = process_image(data.read())
                if not thumb:
                    skipped += 1
                    continue
                thumb_key = f"datasets/{img.dataset_id}/thumbnails/{img.id}.jpg"
                if dry_run:
                    done += 1
                    continue
                s3_client.upload_fileobj(io.BytesIO(thumb), thumb_key, None, "image/jpeg")
                img.thumbnail_key = thumb_key
                await db.flush()
                done += 1
            except Exception as e:
                print(f"[skip] image={img.id} {e}")
                skipped += 1
    return done, skipped


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--dataset-id", type=int, default=None)
    p.add_argument("--limit", type=int, default=None)
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args()
    _register_models()
    done, skipped = asyncio.run(_run(args.dataset_id, args.limit, args.dry_run))
    print(f"完成：生成 {done}，跳过 {skipped}")


if __name__ == "__main__":
    main()
