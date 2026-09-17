"""人脸底库服务：录入/更新、列表、删除、比对，以及供规则叶子使用的前程缓存刷新。

存储与相似度方案见 ``store.py``：JSON 列 + Python 余弦，无 pgvector 依赖。

多 worker 缓存一致性（B3 遗留修复）：
- 进程内缓存不共享，故用一个 **Redis 全局版本号**（``ai:face_gallery:version``）做失效信号：
  任一 worker 录入/删除后 ``INCR``，其余 worker 在事件热路径 ``sync_cache()`` 检测到版本号
  变化即重读 DB；
- Redis 不可用（未启用/故障）时退化为 **TTL 读穿**：缓存超过 ``DEFAULT_CACHE_TTL_SEC``
  即重读 DB。二者叠加：版本号提供近实时性，TTL 为「enroll 与事务提交之间」竞态窗口的
  最终一致上界（最坏 TTL 秒）。
"""
import asyncio
import time
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.module_system.auth.schema import AuthSchema
from app.config.setting import settings
from app.core.database import async_db_session
from app.core.exceptions import CustomException
from app.core.logger import logger

from .crud import FaceGalleryCRUD
from .model import FaceGalleryModel
from .schema import FaceGalleryEnrollSchema, FaceGalleryMatchSchema, FaceGalleryOutSchema
from .store import best_similarity, face_gallery_store, is_valid_embedding

#: 底库全局版本号键（跨 worker 失效信号）
_VERSION_KEY = "ai:face_gallery:version"

# 惰性 Redis 客户端（同 inference/temporal.py 的降级策略：失败进入冷却后自动重试）
_redis_client = None
_redis_failed = False
_redis_cooldown_until = 0.0
# 刷新串行化：避免并发事件同时触发 DB 重读（惊群）
_refresh_lock = asyncio.Lock()


def _mark_redis_failed(exc: Exception) -> None:
    """标记 Redis 不可用并进入冷却（冷却后自动重试，不再永久降级）。"""
    global _redis_client, _redis_failed, _redis_cooldown_until
    _redis_client = None
    if not _redis_failed:
        logger.warning(f"人脸底库版本号 Redis 不可用，降级为 TTL 读穿刷新: {exc}")
    _redis_failed = True
    cooldown = float(getattr(settings, "TEMPORAL_REDIS_COOLDOWN_SEC", 10.0) or 10.0)
    _redis_cooldown_until = time.monotonic() + max(0.0, cooldown)


def _get_redis():
    """惰性创建 Redis 客户端；不可用时返回 None（走 TTL 兜底）。"""
    global _redis_client, _redis_failed, _redis_cooldown_until
    if _redis_client is not None:
        return _redis_client
    if not settings.REDIS_ENABLE:
        return None
    if _redis_failed and time.monotonic() < _redis_cooldown_until:
        return None
    try:
        if getattr(settings, "TESTING", False):
            import fakeredis

            _redis_client = fakeredis.FakeStrictRedis(decode_responses=True)
        else:
            import redis

            timeout = float(getattr(settings, "TEMPORAL_REDIS_TIMEOUT", 0.5) or 0.5)
            _redis_client = redis.Redis.from_url(
                settings.REDIS_URI,
                encoding="utf-8",
                decode_responses=True,
                socket_connect_timeout=timeout,
                socket_timeout=timeout,
            )
            _redis_client.ping()
        _redis_failed = False
        _redis_cooldown_until = 0.0
    except Exception as e:
        _mark_redis_failed(e)
    return _redis_client


def _current_version() -> int | None:
    """读取全局版本号；Redis 不可用返回 None。"""
    rd = _get_redis()
    if rd is None:
        return None
    try:
        return int(rd.get(_VERSION_KEY) or 0)
    except Exception as e:
        _mark_redis_failed(e)
        return None


def _bump_version() -> None:
    """递增全局版本号（best-effort；失败不影响本地缓存刷新）。"""
    rd = _get_redis()
    if rd is None:
        return
    try:
        rd.incr(_VERSION_KEY)
    except Exception as e:
        _mark_redis_failed(e)


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
        - 未传入时自开会话（启动加载 / 独立刷新）；
        - 同步记录全局版本号（Redis 不可用则维持原值），以便后续 ``sync_cache`` 判定。
        """
        if db is not None:
            entries = await cls._fetch_entries(db)
        else:
            async with async_db_session() as session:
                entries = await cls._fetch_entries(session)
        version = _current_version()
        face_gallery_store.replace(entries, version=version)
        return len(entries)

    @classmethod
    async def sync_cache(cls) -> bool:
        """事件热路径调用：多 worker 下按版本号/短 TTL 检测跨进程变更并刷新本地缓存。

        返回是否实际重读了 DB。判定条件（满足其一）：
        - Redis 版本号与本地缓存版本号不一致（其他 worker 录入/删除）；
        - 本地缓存超过 TTL 未刷新（Redis 不可用，或版本号竞态窗口兜底）。
        刷新经进程内锁串行化，避免并发事件惊群。
        """
        version = _current_version()
        if version is not None:
            if version == face_gallery_store.version and not face_gallery_store.is_stale():
                return False
        elif not face_gallery_store.is_stale():
            return False

        async with _refresh_lock:
            # 双重检查：等待锁期间可能已被其他协程刷新
            version = _current_version()
            if version is not None:
                if version == face_gallery_store.version and not face_gallery_store.is_stale():
                    return False
            elif not face_gallery_store.is_stale():
                return False
            await cls.refresh_cache()
            return True

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
        if data.embedding is not None:
            payload["dimension"] = data.dimension or len(data.embedding)
        else:
            # 仅改名/元数据的更新：不动既有特征向量与维度
            payload.pop("embedding", None)
            payload.pop("dimension", None)
        if data.id is not None:
            existing = await crud.get_by_id_crud(id=data.id)
            if not existing:
                raise CustomException(msg="底库条目不存在")
            # 更新为「部分更新」语义：未提供的可空字段不覆盖既有值（如仅改名时不抹掉工号/底图）
            payload = {k: v for k, v in payload.items() if v is not None}
            item = await crud.update(id=data.id, data=payload)
        else:
            item = await crud.create(data=payload)
        # 先递增全局版本号（通知其他 worker 失效），再同事务刷新本地缓存：
        # 本进程立即对后续规则求值生效；其他 worker 在下一个带嵌入事件时按版本号重读。
        _bump_version()
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
        """软删除底库条目并刷新缓存（删除后旧特征立即失效，并通知其他 worker）。"""
        await FaceGalleryCRUD(auth).delete(ids=ids)
        _bump_version()
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
