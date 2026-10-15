"""技能广场服务：CRUD、分类统计、精选、安装计数、按技能注入内容。"""
from __future__ import annotations

from sqlalchemy import select

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
        """分类统计（含未分类），供前端分类 tab。

        在 Python 侧聚合：PG 对 ``GROUP BY`` 表达式要求逐字一致，参数化后
        select 与 group_by 的参数编号不同会被判定为不同表达式（GroupingError）。
        """
        async with async_db_session() as db:
            rows = (
                await db.execute(
                    select(AiSkillModel.category).where(AiSkillModel.is_deleted.is_(False))
                )
            ).scalars().all()
        counter: dict[str, int] = {}
        for c in rows:
            key = (c or "").strip() or "未分类"
            counter[key] = counter.get(key, 0) + 1
        return [
            {"name": k, "count": v}
            for k, v in sorted(counter.items(), key=lambda kv: -kv[1])
        ]

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
    async def batch_status(cls, ids: list[int], enabled: bool, auth) -> int:
        """批量启用/停用技能。"""
        async with async_db_session.begin() as db:
            count = 0
            for sid in ids:
                s = await db.get(AiSkillModel, sid)
                if s and not s.is_deleted:
                    s.enabled = enabled
                    s.updated_id = getattr(getattr(auth, "user", None), "id", None)
                    count += 1
            return count

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

    # ---------- 导入（SkillHub / Claude Skills 的 SKILL.md 与 Zip） ----------

    @classmethod
    async def _unique_name(cls, db, base: str) -> str:
        """同名技能自动加序号，便于区分多次导入。"""
        name = (base or "未命名技能")[:120]
        candidate, idx = name, 2
        while await db.scalar(
            select(AiSkillModel).where(
                AiSkillModel.name == candidate, AiSkillModel.is_deleted.is_(False)
            )
        ):
            candidate = f"{name}-{idx}"
            idx += 1
        return candidate

    @classmethod
    async def _persist_import(cls, parsed: dict, category, source, auth) -> dict:
        """把解析结果落库为技能（默认停用，用户检查后再启用）。"""
        async with async_db_session.begin() as db:
            name = await cls._unique_name(db, parsed["name"])
            s = AiSkillModel(
                name=name,
                description=parsed.get("description") or "",
                content=parsed.get("content") or "",
                skill_type="instruction",
                category=(category or "导入技能")[:64],
                author=(parsed.get("author") or f"外部导入（{source or 'SkillHub'}）")[:64],
                version=parsed.get("version") or "1.0",
                scripts=parsed.get("scripts") or None,
                config={
                    "source": source or "SkillHub",
                    "source_file": parsed.get("source_file"),
                    "import_tags": parsed.get("tags") or [],
                },
                icon="",
                featured=False,
                sort_order=0,
                enabled=False,  # 导入后默认停用：先人工检查内容与脚本，再启用
                created_id=auth.user.id,
                updated_id=auth.user.id,
            )
            db.add(s)
            await db.flush()
            return _to_dict(s)

    @classmethod
    async def import_skill(cls, data, auth) -> dict:
        """导入技能：解析粘贴的 SKILL.md 内容。"""
        from .importer import parse_skill_md

        parsed = parse_skill_md(data.content, fallback_name=data.name or "")
        if data.name:
            parsed["name"] = data.name
        return await cls._persist_import(parsed, data.category, data.source, auth)

    @classmethod
    async def import_skill_zip(
        cls, file_bytes: bytes, filename: str | None, category, source, auth
    ) -> dict:
        """导入技能：解析上传的 Zip 包（优先 SKILL.md）。"""
        from .importer import parse_zip

        fallback = (filename or "").rsplit(".", 1)[0]
        parsed = parse_zip(file_bytes, fallback_name=fallback)
        return await cls._persist_import(parsed, category, source, auth)

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
