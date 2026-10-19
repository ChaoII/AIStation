"""个人空间数据模型：文件夹/文件表读写（真库）。"""
import asyncio

from sqlalchemy import select

from app.core.database import async_db_session
from app.plugin.module_ai.space.model import AiSpaceFileModel, AiSpaceFolderModel


def test_folders_and_files_persist(test_client):
    """文件/文件夹可写入并读回，关联字段正确。"""
    async def _run():
        async with async_db_session.begin() as db:
            f = AiSpaceFolderModel(name="报告", user_id=1)
            db.add(f)
            await db.flush()
            fl = AiSpaceFileModel(
                uuid="u1", folder_id=f.id, user_id=1, name="a.txt",
                ext="txt", file_type="txt", mime_type="text/plain",
                size=10, object_key="ai-space/1/20261019/u1.txt", source="upload",
            )
            db.add(fl)
            await db.flush()
            fid, fdid = f.id, fl.id
        async with async_db_session() as db:
            row = await db.get(AiSpaceFileModel, fdid)
            folder = await db.get(AiSpaceFolderModel, fid)
            return row.name, row.folder_id, folder.name

    name, fdid, folder_name = asyncio.run(_run())
    assert name == "a.txt"
    assert fdid is not None
    assert folder_name == "报告"


def test_soft_delete_flag(test_client):
    """ModelMixin 提供 is_deleted 软删字段；按 user_id 索引可查询。"""
    async def _run():
        async with async_db_session.begin() as db:
            f = AiSpaceFolderModel(name="临时", user_id=1)
            db.add(f)
            await db.flush()
            fid = f.id
        async with async_db_session.begin() as db:
            rows = (
                await db.execute(
                    select(AiSpaceFolderModel).where(
                        AiSpaceFolderModel.user_id == 1,
                        AiSpaceFolderModel.id == fid,
                        AiSpaceFolderModel.is_deleted.is_(False),
                    )
                )
            ).scalars().all()
            return len(rows)

    assert asyncio.run(_run()) == 1
