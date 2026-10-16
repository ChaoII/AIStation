"""AI 工作台服务：分类树 CRUD + 多类型条目聚合。"""
from __future__ import annotations

from sqlalchemy import select

from app.core.database import async_db_session
from app.core.exceptions import CustomException
from app.plugin.module_ai.agent.model import AiAgentModel
from app.plugin.module_ai.apps.model import AiAppModel
from app.plugin.module_ai.workflow.model import AiWorkflowModel
from app.utils.common_util import traversal_to_tree

from .model import AiWorkspaceCategoryModel, AiWorkspaceCronModel

#: 可聚合的类型 → (模型, 名称字段, 中文名)
_TYPES = {
    "agent": (AiAgentModel, "agent_name", "智能体"),
    "workflow": (AiWorkflowModel, "name", "工作流"),
    "app": (AiAppModel, "name", "应用"),
    "cron": (AiWorkspaceCronModel, "name", "定时任务"),
}
ALL_TYPES = tuple(_TYPES.keys())


class WorkspaceService:

    # ---------- 分类 ----------

    @classmethod
    async def list_tree(cls) -> list[dict]:
        """返回分类树（多级）。"""
        async with async_db_session() as db:
            rows = (
                await db.execute(
                    select(AiWorkspaceCategoryModel).where(
                        AiWorkspaceCategoryModel.is_deleted.is_(False)
                    ).order_by(AiWorkspaceCategoryModel.sort.asc(), AiWorkspaceCategoryModel.id.asc())
                )
            ).scalars().all()
            flat = [
                {
                    "id": c.id,
                    "name": c.name,
                    "parent_id": c.parent_id,
                    "icon": c.icon or "",
                    "color": c.color or "",
                    "sort": c.sort or 0,
                }
                for c in rows
            ]
            return traversal_to_tree(flat)

    @classmethod
    async def create_category(cls, data, auth) -> dict:
        async with async_db_session.begin() as db:
            if data.parent_id:
                parent = await db.get(AiWorkspaceCategoryModel, data.parent_id)
                if not parent or parent.is_deleted:
                    raise CustomException(msg="父分类不存在")
            row = AiWorkspaceCategoryModel(
                name=data.name,
                parent_id=data.parent_id,
                icon=data.icon or "",
                color=data.color or "",
                sort=data.sort or 0,
                created_id=auth.user.id,
                updated_id=auth.user.id,
            )
            db.add(row)
            await db.flush()
            return {"id": row.id, "name": row.name}

    @classmethod
    async def update_category(cls, cat_id: int, data, auth) -> dict | None:
        async with async_db_session.begin() as db:
            row = await db.get(AiWorkspaceCategoryModel, cat_id)
            if not row or row.is_deleted:
                return None
            for key in ("name", "icon", "color", "sort"):
                val = getattr(data, key, None)
                if val is not None:
                    setattr(row, key, val)
            row.updated_id = auth.user.id
            await db.flush()
            return {"id": row.id, "name": row.name}

    @classmethod
    async def delete_category(cls, cat_id: int, auth) -> None:
        async with async_db_session.begin() as db:
            row = await db.get(AiWorkspaceCategoryModel, cat_id)
            if not row or row.is_deleted:
                raise CustomException(msg="分类不存在")
            # 子分类的 parent_id 由 FK SET NULL 置空；条目 category_id 同理
            await db.delete(row)

    # ---------- 聚合条目 ----------

    @classmethod
    async def items(cls, category_id: int | None = None, asset_type: str | None = None) -> dict:
        """按分类/全部聚合 agent/workflow/app/cron 为统一条目。"""
        if asset_type and asset_type not in ALL_TYPES:
            raise CustomException(msg=f"不支持的条目类型：{asset_type}")
        async with async_db_session() as db:
            # 若选中父分类，则包含其所有后代分类
            cat_ids = None
            if category_id:
                cat_ids = await cls._descendant_ids(db, category_id)
            out: list[dict] = []
            for kind in ALL_TYPES:
                if asset_type and asset_type != kind:
                    continue
                model, name_field, label = _TYPES[kind]
                stmt = select(model).where(model.is_deleted.is_(False))
                if hasattr(model, "enabled"):
                    stmt = stmt.where(model.enabled.is_(True))
                if cat_ids is not None:
                    stmt = stmt.where(model.category_id.in_(cat_ids))
                rows = (await db.execute(stmt)).scalars().all()
                for r in rows:
                    out.append(cls._to_item(kind, r, label, name_field))
            out.sort(key=lambda x: (x["category_id"] or 0, x["id"] or 0))
            return {"total": len(out), "items": out}

    @classmethod
    async def _descendant_ids(cls, db, root_id: int) -> set[int]:
        """收集 root 及其所有后代分类 id。"""
        all_rows = (
            await db.execute(
                select(AiWorkspaceCategoryModel.id, AiWorkspaceCategoryModel.parent_id)
            )
        ).all()
        children: dict[int | None, list[int]] = {}
        for cid, pid in all_rows:
            children.setdefault(pid, []).append(cid)
        ids: set[int] = {root_id}
        stack = [root_id]
        while stack:
            cur = stack.pop()
            for child in children.get(cur, []):
                if child not in ids:
                    ids.add(child)
                    stack.append(child)
        return ids

    @staticmethod
    def _to_item(kind: str, row, label: str, name_field: str) -> dict:
        return {
            "type": kind,
            "id": row.id,
            "name": getattr(row, name_field) or "",
            "description": getattr(row, "description", "") or "",
            "enabled": bool(getattr(row, "enabled", True)),
            "icon": getattr(row, "icon", "") or (getattr(row, "avatar", "") or ""),
            "color": getattr(row, "color", "") or "",
            "category_id": getattr(row, "category_id", None),
            "label": label,
        }
