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
        base = {
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
        # 类型专属元信息（供卡片展示更饱满）
        if kind == "agent":
            meta = {
                "role": getattr(row, "agent_role", "") or "",
                "model_id": getattr(row, "model_id", None),
                "tools": len(getattr(row, "tool_ids", []) or []),
                "skills": len(getattr(row, "skill_ids", []) or []),
                "mcp": len(getattr(row, "mcp_ids", []) or []),
                "knowledge": len(getattr(row, "knowledge_ids", []) or []),
            }
        elif kind == "workflow":
            graph = getattr(row, "graph", None) or {}
            meta = {"nodes": len(graph.get("nodes", []) or [])}
        elif kind == "app":
            meta = {
                "model_id": getattr(row, "model_id", None),
                "tools": len(getattr(row, "tools", []) or []),
                "app_type": getattr(row, "app_type", "") or "",
                "output_format": getattr(row, "output_format", "") or "",
            }
        else:  # cron
            meta = {
                "cron": getattr(row, "cron", "") or "",
                "target_type": getattr(row, "target_type", "") or "",
                "next_run_time": getattr(row, "next_run_time", None),
            }
        base["meta"] = meta
        return base

    # ---------- 定时任务条目 ----------

    @classmethod
    async def list_cron(cls, category_id: int | None = None, target_type: str | None = None) -> dict:
        from sqlalchemy import select as _sel

        async with async_db_session() as db:
            stmt = _sel(AiWorkspaceCronModel).where(AiWorkspaceCronModel.is_deleted.is_(False))
            if category_id:
                stmt = stmt.where(AiWorkspaceCronModel.category_id == category_id)
            if target_type:
                stmt = stmt.where(AiWorkspaceCronModel.target_type == target_type)
            rows = (await db.execute(stmt.order_by(AiWorkspaceCronModel.id.desc()))).scalars().all()
            items = [cls._cron_dict(r) for r in rows]
            return {"total": len(items), "items": items}

    @staticmethod
    def _cron_dict(r: AiWorkspaceCronModel) -> dict:
        return {
            "id": r.id,
            "name": r.name,
            "description": r.description or "",
            "cron": r.cron or "",
            "target_type": r.target_type or "agent",
            "target_id": r.target_id,
            "category_id": r.category_id,
            "enabled": bool(r.enabled),
            "last_run_time": r.last_run_time,
            "next_run_time": r.next_run_time,
        }

    @staticmethod
    def _compute_next_run(cron: str):
        from datetime import datetime

        from apscheduler.triggers.cron import CronTrigger

        try:
            trigger = CronTrigger.from_crontab(cron)
        except Exception as exc:  # noqa: BLE001
            raise CustomException(msg=f"cron 表达式无效：{exc}") from exc
        return trigger.get_next_fire_time(None, datetime.now())

    @classmethod
    async def create_cron(cls, data, auth) -> dict:
        next_run = cls._compute_next_run(data.cron) if data.enabled else None
        async with async_db_session.begin() as db:
            row = AiWorkspaceCronModel(
                name=data.name,
                description=data.description,
                cron=data.cron,
                target_type=data.target_type,
                target_id=data.target_id,
                category_id=data.category_id,
                enabled=data.enabled,
                next_run_time=next_run,
                created_id=auth.user.id,
                updated_id=auth.user.id,
            )
            db.add(row)
            await db.flush()
            return cls._cron_dict(row)

    @classmethod
    async def update_cron(cls, cron_id: int, data, auth) -> dict | None:
        async with async_db_session.begin() as db:
            row = await db.get(AiWorkspaceCronModel, cron_id)
            if not row or row.is_deleted:
                return None
            for key in ("name", "description", "cron", "target_type", "target_id", "category_id", "enabled"):
                val = getattr(data, key, None)
                if val is not None:
                    setattr(row, key, val)
            # 重新计算下次运行
            if data.cron is not None or data.enabled is not None:
                row.next_run_time = cls._compute_next_run(row.cron) if row.enabled else None
            row.updated_id = auth.user.id
            await db.flush()
            return cls._cron_dict(row)

    @classmethod
    async def delete_cron(cls, cron_id: int, auth) -> None:
        async with async_db_session.begin() as db:
            row = await db.get(AiWorkspaceCronModel, cron_id)
            if not row or row.is_deleted:
                raise CustomException(msg="定时任务不存在")
            await db.delete(row)

    @classmethod
    async def cron_scheduler(cls) -> None:
        """后台轮询：每分钟检查到期定时任务并尝试执行。"""
        import asyncio
        from datetime import datetime

        aiokill = False
        while not aiokill:
            try:
                now = datetime.now()
                async with async_db_session() as db:
                    rows = (
                        await db.execute(
                            select(AiWorkspaceCronModel).where(
                                AiWorkspaceCronModel.enabled.is_(True),
                                AiWorkspaceCronModel.is_deleted.is_(False),
                            )
                        )
                    ).scalars().all()
                    for r in rows:
                        if r.next_run_time is not None and r.next_run_time <= now:
                            # 标记运行并计算下一次
                            r.last_run_time = now
                            try:
                                r.next_run_time = cls._compute_next_run(r.cron)
                            except Exception:  # noqa: BLE001
                                r.enabled = False
                            await db.flush()
                            try:
                                await cls._run_target(r.target_type, r.target_id)
                            except Exception as exc:  # noqa: BLE001
                                print(f"⚠️ 定时任务 #{r.id} 执行失败：{exc}", flush=True)
            except Exception as exc:  # noqa: BLE001
                print(f"⚠️ 定时任务调度异常：{exc}", flush=True)
            await asyncio.sleep(60)

    @classmethod
    async def _run_target(cls, target_type: str, target_id: int) -> None:
        """执行绑定的资产（工作流用其 run_schedule；agent/app 由对应 run 非流式执行）。"""
        if target_type == "workflow":
            from app.plugin.module_ai.workflow.service import AiWorkflowService

            await AiWorkflowService.run_schedule(target_id)
            return
        # agent / app：暂不做非流式执行，仅记录（后续接入）
        print(f"ℹ️ 定时任务目标 {target_type}#{target_id} 执行（非流式执行待接入）", flush=True)
