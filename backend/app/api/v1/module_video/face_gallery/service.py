"""人脸底库服务：录入/更新、列表、删除、比对，以及供规则叶子使用的前程缓存刷新。

存储与相似度方案见 ``store.py``：JSON 列 + Python 余弦，无 pgvector 依赖。
"""
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.module_system.auth.schema import AuthSchema
from app.core.database import async_db_session
from app.core.exceptions import CustomException

from .crud import FaceGalleryCRUD
from .model import FaceGalleryModel
from .schema import FaceGalleryEnrollSchema, FaceGalleryMatchSchema, FaceGalleryOutSchema
from .store import best_similarity, face_gallery_store, is_valid_embedding


def _to_entry(row: FaceGalleryModel) -> dict:
    """ORM 行 → 缓存条目（含特征向量）。"""
    emb = list(row.embedding or [])
    return {
        "id": row.id,
        "name": row.name,
        "person_no": row.person_no,
        "model_key": row.model_key,
        "embedding": emb,
        "dimension": len(emb),
    }


class FaceGalleryService:

    @classmethod
    async def _fetch_entries(cls, db: AsyncSession) -> list[dict]:
        """从数据库读取全部有效底库条目（未删除且启用）。"""
        stmt = select(FaceGalleryModel).where(
            FaceGalleryModel.is_deleted.is_(False),
            FaceGalleryModel.status == "0",
        )
        rows = (await db.execute(stmt)).scalars().all()
        return [_to_entry(r) for r in rows if is_valid_embedding(r.embedding)]

    @classmethod
    async def refresh_cache(cls, db: AsyncSession | None = None) -> int:
        """刷新进程内底库缓存，返回加载条目数。

        - 传入请求会话时复用该会话（可看到同事务内已 flush 的增改）；
        - 未传入时自开会话（启动加载 / 独立刷新）。
        """
        if db is not None:
            entries = await cls._fetch_entries(db)
        else:
            async with async_db_session() as session:
                entries = await cls._fetch_entries(session)
        face_gallery_store.replace(entries)
        return len(entries)

    @classmethod
    async def count_active_service(cls) -> int:
        """有效底库条目数（供场景目录给出「底库为空」提示）。"""
        async with async_db_session() as session:
            stmt = select(func.count(FaceGalleryModel.id)).where(
                FaceGalleryModel.is_deleted.is_(False),
                FaceGalleryModel.status == "0",
            )
            return int((await session.execute(stmt)).scalar() or 0)

    @classmethod
    async def enroll_service(cls, data: FaceGalleryEnrollSchema, auth: AuthSchema) -> dict:
        """录入或更新底库条目（提供 id 且存在时更新，否则新增）。"""
        crud = FaceGalleryCRUD(auth)
        payload = data.model_dump(exclude={"id"})
        payload["dimension"] = data.dimension or len(data.embedding)
        if data.id is not None:
            existing = await crud.get_by_id_crud(id=data.id)
            if not existing:
                raise CustomException(msg="底库条目不存在")
            item = await crud.update(id=data.id, data=payload)
        else:
            item = await crud.create(data=payload)
        # 同事务刷新缓存：立即对后续规则求值生效（无需等待请求提交）
        await cls.refresh_cache(db=auth.db)
        return FaceGalleryOutSchema.model_validate(item).model_dump()

    @classmethod
    async def get_list_service(
        cls, auth: AuthSchema, search: Any | None = None, order_by: list[dict[str, str]] | None = None
    ) -> list[dict]:
        """分页/条件查询底库（不含特征向量）。"""
        items = await FaceGalleryCRUD(auth).get_list_crud(
            search=search.__dict__ if search else None, order_by=order_by
        )
        return [FaceGalleryOutSchema.model_validate(item).model_dump() for item in items]

    @classmethod
    async def delete_service(cls, ids: list[int], auth: AuthSchema) -> None:
        """软删除底库条目并刷新缓存（删除后旧特征立即失效）。"""
        await FaceGalleryCRUD(auth).delete(ids=ids)
        await cls.refresh_cache(db=auth.db)

    @classmethod
    async def match_service(cls, data: FaceGalleryMatchSchema) -> list[dict]:
        """按余弦相似度返回 top-k 命中条目；空底库/非法向量返回空列表（fail-closed）。"""
        async with async_db_session() as session:
            entries = await cls._fetch_entries(session)
        scored: list[dict] = []
        dim = len(data.embedding)
        for entry in entries:
            if entry.get("dimension") != dim:
                # 维度不同的底库条目不可比（跨模型特征），跳过
                continue
            sim = best_similarity(data.embedding, [entry])
            if sim is None or sim < data.threshold:
                continue
            scored.append(
                {
                    "id": entry["id"],
                    "name": entry["name"],
                    "person_no": entry.get("person_no"),
                    "model_key": entry.get("model_key"),
                    "score": round(sim, 6),
                }
            )
        scored.sort(key=lambda x: x["score"], reverse=True)
        return scored[: data.top_k]
