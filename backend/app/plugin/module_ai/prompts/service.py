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

    # 提示词模板库（AIP 常用角色/场景）
    _TEMPLATES = [
        {"key": "data_query", "name": "数据问数助手", "category": "数据",
         "blocks": [{"type": "instruction", "content": "你是数据问数助手，基于系统数据回答用户问题。使用本体驱动的方式确定数据域、对象与字段，确保回答准确。变量：{{question}}"}],
         "variables": ["question"]},
        {"key": "knowledge", "name": "知识库问答", "category": "知识",
         "blocks": [{"type": "instruction", "content": "你是知识库问答助手，优先引用知识库内容回答，并在合适处以 [来源] 标注。变量：{{question}}"}],
         "variables": ["question"]},
        {"key": "summarize", "name": "摘要总结", "category": "产出",
         "blocks": [{"type": "instruction", "content": "对以下内容做要点摘要，输出结构化要点。内容：{{content}}"}],
         "variables": ["content"]},
        {"key": "customer_service", "name": "客服助手", "category": "服务",
         "blocks": [{"type": "instruction", "content": "你是客服助手，友好、准确、简洁地解答用户问题。变量：{{question}}"}],
         "variables": ["question"]},
    ]

    @classmethod
    async def prompt_templates(cls) -> list[dict]:
        return cls._TEMPLATES

    @classmethod
    async def create_from_template(cls, key: str, name: str, auth) -> dict | None:
        tpl = next((t for t in cls._TEMPLATES if t["key"] == key), None)
        if not tpl:
            return None
        from types import SimpleNamespace as SN
        data = SN(name=name or tpl["name"], category=tpl["category"],
                  blocks=tpl["blocks"], variables=tpl["variables"],
                  enabled=True)
        return await cls.create(data, auth)

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

    @classmethod
    async def batch_status(cls, ids: list[int], enabled: bool, auth) -> int:
        """批量启用/停用提示词。"""
        async with async_db_session.begin() as db:
            count = 0
            for pid in ids:
                p = await db.get(AiPromptModel, pid)
                if p and not p.is_deleted:
                    p.enabled = enabled
                    p.updated_id = getattr(getattr(auth, "user", None), "id", None)
                    count += 1
            return count
