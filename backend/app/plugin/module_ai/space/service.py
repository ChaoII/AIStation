"""个人工作空间服务：文件夹/文件元信息 CRUD + S3 落盘 + 配额。

隔离规则：所有方法接收显式 ``user_id``，查询一律带
``<Model>.user_id == user_id`` 过滤；不存在/越权统一抛 ValueError（对外 404 语义，
不暴露存在性）。文件二进制存 RustFS/S3（``app.utils.s3_client``），
object_key 前缀 ``ai-space/{user_id}/...`` 按用户隔离。
"""
from __future__ import annotations

from sqlalchemy import select

from app.core.database import async_db_session
from app.core.exceptions import CustomException
from app.core.logger import log
from app.utils.common_util import traversal_to_tree

from .model import AiSpaceFileModel, AiSpaceFolderModel


class SpaceService:

    # ---------------- 内部工具 ----------------

    @staticmethod
    def _to_quota_bytes(mb_value: int) -> int:
        return mb_value * 1024 * 1024

    @classmethod
    async def _used_bytes(cls, db, user_id: int) -> int:
        from sqlalchemy import func, select

        v = (
            await db.execute(
                select(func.coalesce(func.sum(AiSpaceFileModel.size), 0)).where(
                    AiSpaceFileModel.user_id == user_id,
                    AiSpaceFileModel.is_deleted.is_(False),
                )
            )
        ).scalar()
        return int(v or 0)

    @staticmethod
    def _file_dict(f: AiSpaceFileModel) -> dict:
        return {
            "id": f.id,
            "uuid": f.uuid,
            "name": f.name,
            "ext": f.ext,
            "file_type": f.file_type,
            "mime_type": f.mime_type,
            "size": f.size,
            "source": f.source,
            "folder_id": f.folder_id,
            "created_time": f.created_time,
            "updated_time": f.updated_time,
        }

    @staticmethod
    def _folder_dict(f: AiSpaceFolderModel) -> dict:
        return {
            "id": f.id,
            "name": f.name,
            "parent_id": f.parent_id,
        }

    # ---------------- 配额 ----------------

    @classmethod
    async def quota(cls, user_id: int) -> dict:
        """返回 {used_bytes, quota_bytes, max_file_bytes}。"""
        from app.config.setting import settings

        async with async_db_session() as db:
            used = await cls._used_bytes(db, user_id)
        return {
            "used_bytes": used,
            "quota_bytes": cls._to_quota_bytes(settings.AI_SPACE_QUOTA_MB),
            "max_file_bytes": cls._to_quota_bytes(settings.AI_SPACE_MAX_FILE_MB),
        }

    @classmethod
    async def _check_quota(cls, db, user_id: int, add_bytes: int) -> None:
        """校验新增字节数不超单文件与总配额，超限抛 CustomException(400)。"""
        from app.config.setting import settings

        max_file = cls._to_quota_bytes(settings.AI_SPACE_MAX_FILE_MB)
        if add_bytes > max_file:
            raise CustomException(
                msg=f"单文件超过上限 {settings.AI_SPACE_MAX_FILE_MB}MB",
                code=400, status_code=400,
            )
        used = await cls._used_bytes(db, user_id)
        quota = cls._to_quota_bytes(settings.AI_SPACE_QUOTA_MB)
        if used + add_bytes > quota:
            raise CustomException(
                msg=f"个人空间配额不足：已用 {used / 1024 / 1024:.1f}MB / 共 {settings.AI_SPACE_QUOTA_MB}MB，请清理后重试",
                code=400, status_code=400,
            )

    # ---------------- 文件夹 ----------------

    @classmethod
    async def folder_tree(cls, user_id: int) -> list[dict]:
        """当前用户文件夹树（多级，只含未删）。"""
        async with async_db_session() as db:
            rows = (
                await db.execute(
                    select(AiSpaceFolderModel)
                    .where(
                        AiSpaceFolderModel.user_id == user_id,
                        AiSpaceFolderModel.is_deleted.is_(False),
                    )
                    .order_by(AiSpaceFolderModel.id.asc())
                )
            ).scalars().all()
            flat = [
                {"id": r.id, "name": r.name, "parent_id": r.parent_id}
                for r in rows
            ]
            return traversal_to_tree(flat)

    @classmethod
    async def create_folder(cls, name: str, parent_id: int | None, user_id: int) -> dict:
        async with async_db_session.begin() as db:
            if parent_id:
                parent = await db.get(AiSpaceFolderModel, parent_id)
                if not parent or parent.is_deleted or parent.user_id != user_id:
                    raise CustomException(msg="父文件夹不存在", code=400, status_code=400)
            row = AiSpaceFolderModel(name=name, user_id=user_id, parent_id=parent_id)
            db.add(row)
            await db.flush()
            return {"id": row.id, "name": row.name, "parent_id": row.parent_id}

    @classmethod
    async def rename_folder(cls, folder_id: int, name: str, user_id: int) -> dict | None:
        async with async_db_session.begin() as db:
            row = await db.get(AiSpaceFolderModel, folder_id)
            if not row or row.is_deleted or row.user_id != user_id:
                return None
            row.name = name
            await db.flush()
            return {"id": row.id, "name": row.name, "parent_id": row.parent_id}

    @classmethod
    async def _descendant_folder_ids(cls, db, root_id: int) -> list[int]:
        """收集 root 文件夹及其所有后代文件夹 id（仅当前用户可见口径由调用方保证）。"""
        rows = (
            await db.execute(
                select(AiSpaceFolderModel.id, AiSpaceFolderModel.parent_id).where(
                    AiSpaceFolderModel.is_deleted.is_(False)
                )
            )
        ).all()
        children: dict[int | None, list[int]] = {}
        for cid, pid in rows:
            children.setdefault(pid, []).append(cid)
        ids = [root_id]
        stack = [root_id]
        seen = {root_id}
        while stack:
            cur = stack.pop()
            for child in children.get(cur, []):
                if child not in seen:
                    seen.add(child)
                    ids.append(child)
                    stack.append(child)
        return ids

    @classmethod
    async def delete_folder(cls, folder_id: int, user_id: int) -> dict:
        """删除文件夹（级联：软删全部子文件夹与文件，并删 S3 对象）。

        返回 {"deleted_files": n}。S3 删除失败仅记日志，不阻塞 DB。
        """
        async with async_db_session.begin() as db:
            root = await db.get(AiSpaceFolderModel, folder_id)
            if not root or root.is_deleted or root.user_id != user_id:
                raise CustomException(msg="文件夹不存在", code=400, status_code=400)
            folder_ids = await cls._descendant_folder_ids(db, folder_id)
            files = (
                await db.execute(
                    select(AiSpaceFileModel).where(
                        AiSpaceFileModel.folder_id.in_(folder_ids),
                        AiSpaceFileModel.user_id == user_id,
                        AiSpaceFileModel.is_deleted.is_(False),
                    )
                )
            ).scalars().all()
            object_keys = [f.object_key for f in files]
            from datetime import datetime

            now = datetime.now()
            for f in files:
                f.is_deleted = True
                f.deleted_time = now
            for fid in folder_ids:
                row = await db.get(AiSpaceFolderModel, fid)
                if row:
                    row.is_deleted = True
                    row.deleted_time = now
        if object_keys:
            try:
                import asyncio

                from app.utils.s3_client import s3_client

                await asyncio.to_thread(s3_client.delete_objects, object_keys)
            except Exception as exc:  # noqa: BLE001 对象删除失败不阻塞元信息删除
                log.warning(f"个人空间文件夹 #{folder_id} 级联删除 S3 对象失败：{str(exc)[:200]}")
        return {"deleted_files": len(object_keys)}

    # ---------------- 文件 ----------------

    @classmethod
    async def get_file(cls, file_id: int, user_id: int) -> dict:
        async with async_db_session() as db:
            row = await db.get(AiSpaceFileModel, file_id)
            if not row or row.is_deleted or row.user_id != user_id:
                raise ValueError("文件不存在")
            return cls._file_dict(row)

    @classmethod
    async def list_files(
        cls, user_id: int, folder_id: int | None = None, keyword: str | None = None,
        file_type: str | None = None, page_no: int = 1, page_size: int = 20,
    ) -> dict:
        from sqlalchemy import func, select

        async with async_db_session() as db:
            base = select(AiSpaceFileModel).where(
                AiSpaceFileModel.user_id == user_id,
                AiSpaceFileModel.is_deleted.is_(False),
            )
            if folder_id is not None:
                base = base.where(AiSpaceFileModel.folder_id == folder_id)
            if file_type:
                base = base.where(AiSpaceFileModel.file_type == file_type)
            if keyword:
                base = base.where(AiSpaceFileModel.name.like(f"%{keyword}%"))
            total = (
                await db.execute(select(func.count()).select_from(base.subquery()))
            ).scalar() or 0
            page_no = max(1, page_no)
            page_size = max(1, min(page_size, 100))
            rows = (
                await db.execute(
                    base.order_by(AiSpaceFileModel.id.desc())
                    .offset((page_no - 1) * page_size)
                    .limit(page_size)
                )
            ).scalars().all()
            items = [cls._file_dict(r) for r in rows]
            return {
                "page_no": page_no,
                "page_size": page_size,
                "total": int(total),
                "has_next": page_no * page_size < total,
                "items": items,
            }

    @classmethod
    async def upload_file(
        cls, user_id: int, filename: str, data: bytes,
        folder_id: int | None = None, source: str = "upload",
    ) -> dict:
        """上传文件：校验（文件夹归属/大小/配额）→ S3 → 元信息入库。"""
        import asyncio
        import io
        import uuid as uuid_mod
        from datetime import datetime

        from app.plugin.module_ai.space.filetype import (
            classify_file,
            get_ext,
            guess_mime,
            sanitize_filename,
        )
        from app.utils.s3_client import s3_client

        name = sanitize_filename(filename)
        ext = get_ext(name)
        file_type = classify_file(name)
        if file_type == "other":
            raise CustomException(
                msg="不支持的文件类型，请上传图片/PDF/Word/文本/CSV/JSON 等", code=400, status_code=400
            )
        if not data:
            raise CustomException(msg="文件内容为空", code=400, status_code=400)

        async with async_db_session.begin() as db:
            if folder_id:
                folder = await db.get(AiSpaceFolderModel, folder_id)
                if not folder or folder.is_deleted or folder.user_id != user_id:
                    raise CustomException(msg="目标文件夹不存在", code=400, status_code=400)
            await cls._check_quota(db, user_id, len(data))
            object_key = f"ai-space/{user_id}/{datetime.now():%Y%m%d}/{uuid_mod.uuid4().hex}.{ext}" if ext else f"ai-space/{user_id}/{datetime.now():%Y%m%d}/{uuid_mod.uuid4().hex}"
            mime = guess_mime(ext)
            await asyncio.to_thread(
                s3_client.upload_fileobj, io.BytesIO(data), object_key, content_type=mime,
            )
            row = AiSpaceFileModel(
                folder_id=folder_id, user_id=user_id, name=name, ext=ext,
                file_type=file_type, mime_type=mime, size=len(data),
                object_key=object_key, source=source,
            )
            db.add(row)
            await db.flush()
            return cls._file_dict(row)

    @classmethod
    async def rename_file(cls, file_id: int, name: str, user_id: int) -> dict | None:
        async with async_db_session.begin() as db:
            row = await db.get(AiSpaceFileModel, file_id)
            if not row or row.is_deleted or row.user_id != user_id:
                return None
            row.name = name
            await db.flush()
            return cls._file_dict(row)

    @classmethod
    async def move_file(cls, file_id: int, folder_id: int | None, user_id: int) -> dict | None:
        async with async_db_session.begin() as db:
            row = await db.get(AiSpaceFileModel, file_id)
            if not row or row.is_deleted or row.user_id != user_id:
                return None
            if folder_id is not None:
                folder = await db.get(AiSpaceFolderModel, folder_id)
                if not folder or folder.is_deleted or folder.user_id != user_id:
                    raise CustomException(msg="目标文件夹不存在", code=400, status_code=400)
                if folder_id == (row.folder_id or 0):
                    raise CustomException(msg="文件已在该文件夹中", code=400, status_code=400)
            row.folder_id = folder_id
            await db.flush()
            return cls._file_dict(row)

    @classmethod
    async def delete_files(cls, file_ids: list[int], user_id: int) -> dict:
        """批量删除：软删元信息 + 删 S3 对象，返回 {"deleted": n}。"""
        import asyncio

        from app.utils.s3_client import s3_client

        async with async_db_session.begin() as db:
            rows = (
                await db.execute(
                    select(AiSpaceFileModel).where(
                        AiSpaceFileModel.id.in_(file_ids),
                        AiSpaceFileModel.user_id == user_id,
                        AiSpaceFileModel.is_deleted.is_(False),
                    )
                )
            ).scalars().all()
            object_keys = [r.object_key for r in rows]
            from datetime import datetime

            now = datetime.now()
            for r in rows:
                r.is_deleted = True
                r.deleted_time = now
        if object_keys:
            try:
                await asyncio.to_thread(s3_client.delete_objects, object_keys)
            except Exception as exc:  # noqa: BLE001
                log.warning(f"个人空间批量删除 S3 对象失败：{str(exc)[:200]}")
        return {"deleted": len(object_keys)}

    @classmethod
    async def _download_meta(cls, file_id: int, user_id: int) -> dict:
        """下载元信息：{object_key, name, mime_type, file_type}。不存在/越权抛 ValueError。"""
        async with async_db_session() as db:
            row = await db.get(AiSpaceFileModel, file_id)
            if not row or row.is_deleted or row.user_id != user_id:
                raise ValueError("文件不存在")
            return {
                "object_key": row.object_key,
                "name": row.name,
                "mime_type": row.mime_type,
                "file_type": row.file_type,
            }

    @classmethod
    async def download_file(cls, file_id: int, user_id: int) -> dict:
        return await cls._download_meta(file_id, user_id)

    @classmethod
    async def preview_file(cls, file_id: int, user_id: int) -> dict:
        """预览：文本类返回 {kind:"text", content, truncated}；其余返回 {kind: file_type}。

        文本类内容超 500KB 截断并标记 truncated=True。
        """
        from app.plugin.module_ai.assistant.agno_service import _extract_doc_text

        meta = await cls._download_meta(file_id, user_id)
        ft = meta["file_type"]
        if ft not in ("txt", "md", "csv", "json"):
            return {"kind": ft}
        import asyncio

        from app.utils.s3_client import s3_client

        obj = await asyncio.to_thread(s3_client.get_object, meta["object_key"])
        body = obj["Body"]
        limit = 500 * 1024
        raw = await asyncio.to_thread(body.read, limit + 1)
        truncated = len(raw) > limit
        text = _extract_doc_text(raw[:limit] if truncated else raw, meta["mime_type"], meta["name"])
        if truncated:
            text += "\n…（内容过长已截断）"
        return {"kind": "text", "content": text, "truncated": truncated}

    @classmethod
    async def get_file_bytes(cls, user_id: int, file_id: int) -> dict:
        """供智能体读取/对话引用：S3 取全量字节（>20MB 抛 ValueError）。

        返回 {data, mime_type, name, file_type}。
        """
        meta = await cls._download_meta(file_id, user_id)
        import asyncio

        from app.utils.s3_client import s3_client

        obj = await asyncio.to_thread(s3_client.get_object, meta["object_key"])
        raw = await asyncio.to_thread(obj["Body"].read)
        limit = 20 * 1024 * 1024
        if len(raw) > limit:
            raise ValueError("文件超过 20MB，无法作为智能体输入")
        return {
            "data": raw,
            "mime_type": meta["mime_type"],
            "name": meta["name"],
            "file_type": meta["file_type"],
        }

    # ---------------- 智能体工具入口 ----------------

    @classmethod
    async def save_agent_file(cls, user_id: int, name: str, content: str, file_type: str | None = None) -> dict:
        """智能体保存文本内容到个人空间（source=agent）。"""
        from app.plugin.module_ai.space.filetype import sanitize_filename

        safe_name = sanitize_filename(name)
        data = content.encode("utf-8")
        # 无扩展名时按 file_type 补全
        if "." not in safe_name and file_type:
            ext_map = {"md": "md", "txt": "txt", "csv": "csv", "json": "json", "markdown": "md"}
            if file_type in ext_map:
                safe_name = f"{safe_name}.{ext_map[file_type]}"
        return await cls.upload_file(
            user_id, safe_name, data, folder_id=None, source="agent"
        )

    @classmethod
    async def list_for_agent(cls, user_id: int, keyword: str | None = None, limit: int = 20) -> list[dict]:
        async with async_db_session() as db:
            from sqlalchemy import select

            stmt = (
                select(AiSpaceFileModel)
                .where(
                    AiSpaceFileModel.user_id == user_id,
                    AiSpaceFileModel.is_deleted.is_(False),
                )
                .order_by(AiSpaceFileModel.id.desc())
                .limit(max(1, min(limit, 50)))
            )
            if keyword:
                stmt = stmt.where(AiSpaceFileModel.name.like(f"%{keyword}%"))
            rows = (await db.execute(stmt)).scalars().all()
            return [
                {
                    "file_id": r.id,
                    "name": r.name,
                    "file_type": r.file_type,
                    "size": r.size,
                    "source": r.source,
                    "created_time": r.created_time,
                }
                for r in rows
            ]

    @classmethod
    async def read_for_agent(cls, user_id: int, file_id: int) -> str:
        """智能体读取文本内容：文本类原文；pdf/docx 抽取；图片抛 ValueError；>100KB 截断。"""
        from app.plugin.module_ai.assistant.agno_service import _extract_doc_text

        try:
            got = await cls.get_file_bytes(user_id, file_id)
        except ValueError:
            raise
        ft = got["file_type"]
        if ft == "image":
            raise ValueError("图片文件请用户直接查看，不支持文本读取")
        limit = 100 * 1024
        data = got["data"]
        truncated = len(data) > limit
        text = _extract_doc_text(
            data[:limit] if truncated else data, got["mime_type"], got["name"]
        )
        if truncated:
            text += "\n…（内容过长已截断）"
        return text
