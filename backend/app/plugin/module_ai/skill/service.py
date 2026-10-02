"""技能广场服务：CRUD、分类统计、精选、安装计数、按技能注入内容。"""
from __future__ import annotations

from sqlalchemy import func, select

from app.core.database import async_db_session

from .model import AiSkillModel


def _to_dict(s: AiSkillModel) -> dict:
    return {
        "id": s.id,
        "name": s.name,
        "description": s.description or "",
        "content": s.content or "",
        "skill_type": s.skill_type or "tool",
        "category": s.category or "",
        "author": s.author or "",
        "version": s.version or "1.0",
        "scripts": s.scripts,
        "config": s.config,
        "icon": s.icon or "",
        "featured": s.featured,
        "install_count": s.install_count or 0,
        "sort_order": s.sort_order or 0,
        "enabled": s.enabled,
        "created_time": s.created_time,
        "updated_time": s.updated_time,
    }


class AiSkillService:

    @classmethod
    async def list_skills(cls, category: str | None = None, skill_type: str | None = None) -> list[dict]:
        async with async_db_session() as db:
            stmt = select(AiSkillModel).where(AiSkillModel.is_deleted.is_(False))
            if category:
                stmt = stmt.where(AiSkillModel.category == category)
            if skill_type:
                stmt = stmt.where(AiSkillModel.skill_type == skill_type)
            rows = (
                await db.execute(
                    stmt.order_by(AiSkillModel.sort_order.asc(), AiSkillModel.id.desc())
                )
            ).scalars().all()
            return [_to_dict(s) for s in rows]

    @classmethod
    async def get_skill(cls, skill_id: int) -> dict | None:
        async with async_db_session() as db:
            s = await db.get(AiSkillModel, skill_id)
            if not s or s.is_deleted:
                return None
            return _to_dict(s)

    @classmethod
    async def get_skills_by_ids(cls, skill_ids: list[int]) -> list[dict]:
        """按 ID 批量取启用技能（供 Agent 运行注入）。"""
        if not skill_ids:
            return []
        async with async_db_session() as db:
            rows = (
                await db.execute(
                    select(AiSkillModel).where(
                        AiSkillModel.is_deleted.is_(False),
                        AiSkillModel.enabled.is_(True),
                        AiSkillModel.id.in_(skill_ids),
                    )
                )
            ).scalars().all()
            return [_to_dict(s) for s in rows]

    @classmethod
    async def categories(cls) -> list[dict]:
        """分类统计（含未分类），供前端分类 tab。"""
        async with async_db_session() as db:
            name_col = func.coalesce(func.nullif(AiSkillModel.category, ""), "未分类")
            rows = (
                await db.execute(
                    select(name_col.label("name"), func.count().label("count"))
                    .where(AiSkillModel.is_deleted.is_(False))
                    .group_by(name_col)
                    .order_by(func.count().desc())
                )
            ).all()
            return [{"name": r.name, "count": r.count} for r in rows]

    @classmethod
    async def create(cls, data, auth) -> dict:
        async with async_db_session.begin() as db:
            s = AiSkillModel(
                name=data.name,
                description=data.description or "",
                content=data.content or "",
                skill_type=data.skill_type or "tool",
                category=data.category or "",
                author=data.author or "",
                version=data.version or "1.0",
                scripts=data.scripts,
                config=data.config,
                icon=data.icon or "",
                featured=data.featured,
                sort_order=data.sort_order or 0,
                enabled=data.enabled,
                created_id=auth.user.id,
                updated_id=auth.user.id,
            )
            db.add(s)
            await db.flush()
            return _to_dict(s)

    @classmethod
    async def update(cls, skill_id: int, data, auth) -> dict | None:
        async with async_db_session.begin() as db:
            s = await db.get(AiSkillModel, skill_id)
            if not s or s.is_deleted:
                return None
            for key in (
                "name", "description", "content", "skill_type", "category", "author",
                "version", "scripts", "config", "icon", "featured", "sort_order", "enabled",
            ):
                if getattr(data, key) is not None:
                    setattr(s, key, getattr(data, key))
            s.updated_id = auth.user.id
            await db.flush()
            return _to_dict(s)

    @classmethod
    async def delete(cls, ids: list[int]) -> None:
        async with async_db_session.begin() as db:
            for sid in ids:
                s = await db.get(AiSkillModel, sid)
                if s:
                    await db.delete(s)

    @classmethod
    async def toggle_featured(cls, skill_id: int, featured: bool, auth) -> dict | None:
        async with async_db_session.begin() as db:
            s = await db.get(AiSkillModel, skill_id)
            if not s or s.is_deleted:
                return None
            s.featured = featured
            s.updated_id = auth.user.id
            await db.flush()
            return _to_dict(s)

    @classmethod
    async def bump_install(cls, skill_ids: list[int], delta: int) -> None:
        """安装计数增减（安装 +1 / 卸载 -1），失败仅告警不阻断。"""
        if not skill_ids:
            return
        async with async_db_session.begin() as db:
            for sid in skill_ids:
                s = await db.get(AiSkillModel, sid)
                if s:
                    s.install_count = max(0, (s.install_count or 0) + delta)
