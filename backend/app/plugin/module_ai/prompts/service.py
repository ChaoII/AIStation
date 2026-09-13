"""提示词服务：CRUD 与渲染工具。"""
import re

from sqlalchemy import select

from app.core.database import async_db_session

from .model import AiPromptModel

# 匹配 {{变量名}}，变量名允许字母数字下划线以及中文
_VAR_RE = re.compile(r"\{\{\s*([\w\u4e00-\u9fa5]+)\s*\}\}")


def render_prompt(blocks: list[dict] | None, values: dict | None = None) -> str:
    """将有序块渲染为提示词文本：替换 {{变量}}，未知变量原样保留。"""
    values = values or {}
    parts = []
    for b in blocks or []:
        text = b.get("content") or ""
        text = _VAR_RE.sub(lambda m: str(values.get(m.group(1), m.group(0))), text)
        parts.append(f"【{b.get('type', 'instruction')}】\n{text}")
    return "\n\n".join(parts)


def _to_dict(p: AiPromptModel) -> dict:
    return {
        "id": p.id,
        "name": p.name,
        "category": p.category or "",
        "blocks": p.blocks or [],
        "variables": p.variables or [],
        "version": p.version or 1,
        "enabled": p.enabled,
        "created_time": p.created_time,
        "updated_time": p.updated_time,
    }


class AiPromptService:

    @classmethod
    async def list_prompts(cls) -> list[dict]:
        async with async_db_session() as db:
            rows = (
                await db.execute(
                    select(AiPromptModel)
                    .where(AiPromptModel.is_deleted.is_(False))
                    .order_by(AiPromptModel.id.desc())
                )
            ).scalars().all()
            return [_to_dict(p) for p in rows]

    @classmethod
    async def get_prompt(cls, prompt_id: int) -> dict | None:
        async with async_db_session() as db:
            p = await db.get(AiPromptModel, prompt_id)
            if not p or p.is_deleted:
                return None
            return _to_dict(p)

    @classmethod
    async def create(cls, data, auth) -> dict:
        async with async_db_session.begin() as db:
            p = AiPromptModel(
                name=data.name,
                category=data.category or "",
                blocks=data.blocks or [],
                variables=data.variables or [],
                version=1,
                enabled=data.enabled,
                created_id=auth.user.id,
                updated_id=auth.user.id,
            )
            db.add(p)
            await db.flush()
            return _to_dict(p)

    @classmethod
    async def update(cls, prompt_id: int, data, auth) -> dict | None:
        async with async_db_session.begin() as db:
            p = await db.get(AiPromptModel, prompt_id)
            if not p or p.is_deleted:
                return None
            for key in ("name", "category", "variables", "enabled"):
                val = getattr(data, key, None)
                if val is not None:
                    setattr(p, key, val)
            if data.version is not None:
                p.version = data.version
            # 内容变更时自动递增版本号
            if data.blocks is not None:
                p.blocks = data.blocks
                if data.version is None:
                    p.version = (p.version or 1) + 1
            p.updated_id = auth.user.id
            await db.flush()
            return _to_dict(p)

    @classmethod
    async def delete(cls, ids: list[int]) -> None:
        async with async_db_session.begin() as db:
            for pid in ids:
                p = await db.get(AiPromptModel, pid)
                if p:
                    await db.delete(p)
