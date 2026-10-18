"""AI 工作台服务：分类树 CRUD + 多类型条目聚合。"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import select

from app.core.database import async_db_session
from app.core.exceptions import CustomException
from app.utils.common_util import traversal_to_tree
from app.utils.trigger_util import TriggerUtil

from .model import AiWorkspaceCategoryModel, AiWorkspaceCronModel

#: 可聚合的类型 → (本模块模型, 名称字段, 中文名)。
#: agent/workflow/app 的表**不在这里**——它们由各模块的 list_* 接口取数（见 items()）；
#: 这里只留本模块自己的 cron 表。
_TYPES = {
    "cron": (AiWorkspaceCronModel, "name", "定时任务"),
}
#: 全部可聚合类型（跨模块的三种 + 本模块的 cron）
ALL_TYPES = ("agent", "workflow", "app", "cron")

#: 类型默认图标（Element Plus 图标组件名；条目未设 icon/avatar 或设为非图片图标时用于卡片展示）
_TYPE_ICON = {
    "agent": "User",
    "workflow": "Connection",
    "app": "Monitor",
    "cron": "Timer",
}


#: 启用中的定时任务必须有触发表达式：空表达式 = 「已启用但永不触发」的静默失效，
#: 用户看不到任何提示。三处写入路径（工作台 / 工作流 / 训练）口径必须一致。
_EMPTY_TRIGGER_MSG = "请先配置触发时间（分 时 日 月 周）"


def _is_image_icon(icon: str) -> bool:
    """判断图标是否为图片路径（http(s)/图片扩展名/agent-icons 等），非图片则用类型默认图标。"""
    i = (icon or "").strip()
    return bool(
        i
        and (
            i.startswith("http://")
            or i.startswith("https://")
            or i.endswith((".png", ".jpg", ".jpeg", ".svg", ".webp", ".gif"))
            or i.startswith("market-icons/")
            or i.startswith("agent-icons/")
        )
    )


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
        """按分类/全部聚合 agent/workflow/app/cron 为统一条目。

        跨模块取数走**各模块自己的接口**（``list_agents`` / ``list_workflows`` / ``list_apps``），
        不直读它们的表；分类与启用过滤在本模块内做（条目量小，不值得给 owner 加过滤参数）。
        ``cron`` 是本模块自己的表，保持直读。
        """
        from app.plugin.module_ai.agent.service import AiAgentService
        from app.plugin.module_ai.apps.service import AiAppService
        from app.plugin.module_ai.workflow.service import AiWorkflowService

        if asset_type and asset_type not in ALL_TYPES:
            raise CustomException(msg=f"不支持的条目类型：{asset_type}")
        #: 跨模块类型 → (取数接口, 名称字段, 中文名)
        cross = {
            "agent": (AiAgentService.list_agents, "agent_name", "智能体"),
            "workflow": (AiWorkflowService.list_workflows, "name", "工作流"),
            "app": (AiAppService.list_apps, "name", "应用"),
        }
        async with async_db_session() as db:
            # 若选中父分类，则包含其所有后代分类
            cat_ids = None
            if category_id:
                cat_ids = await cls._descendant_ids(db, category_id)
            out: list[dict] = []
            for kind in ALL_TYPES:
                if asset_type and asset_type != kind:
                    continue
                if kind == "cron":  # 本模块自己的表
                    model, name_field, label = _TYPES[kind]
                    rows = (
                        await db.execute(select(model).where(model.is_deleted.is_(False)))
                    ).scalars().all()
                    out.extend(cls._to_item(kind, r, label, name_field) for r in rows)
                    continue
                fetch, name_field, label = cross[kind]
                for r in await fetch():
                    if not r.get("enabled", True):
                        continue
                    if cat_ids is not None and r.get("category_id") not in cat_ids:
                        continue
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
    def _g(row, key: str, default=None):
        """条目取值：他模块接口返回 **dict**，本模块 cron 是 **ORM 行**，统一取值。"""
        if isinstance(row, dict):
            v = row.get(key, default)
        else:
            v = getattr(row, key, default)
        return default if v is None else v

    @classmethod
    def _to_item(cls, kind: str, row, label: str, name_field: str) -> dict:
        icon = cls._g(row, "icon", "") or cls._g(row, "avatar", "")
        if not _is_image_icon(icon):
            icon = _TYPE_ICON.get(kind, icon or "")
        base = {
            "type": kind,
            "id": cls._g(row, "id"),
            "name": cls._g(row, name_field, "") or "",
            "description": cls._g(row, "description", "") or "",
            "enabled": bool(cls._g(row, "enabled", True)),
            "icon": icon,
            "color": cls._g(row, "color", "") or "",
            "category_id": cls._g(row, "category_id"),
            "label": label,
            "created_time": cls._g(row, "created_time"),
        }
        # 类型专属元信息（供卡片展示更饱满）
        if kind == "agent":
            meta = {
                "role": cls._g(row, "agent_role", "") or "",
                "model_id": cls._g(row, "model_id"),
                "tools": len(cls._g(row, "tool_ids", []) or []),
                "skills": len(cls._g(row, "skill_ids", []) or []),
                "mcp": len(cls._g(row, "mcp_ids", []) or []),
                "knowledge": len(cls._g(row, "knowledge_ids", []) or []),
            }
        elif kind == "workflow":
            graph = cls._g(row, "graph", {}) or {}
            meta = {"nodes": len(graph.get("nodes", []) or [])}
        elif kind == "app":
            meta = {
                "model_id": cls._g(row, "model_id"),
                "tools": len(cls._g(row, "tools", []) or []),
                "app_type": cls._g(row, "app_type", "") or "",
                "output_format": cls._g(row, "output_format", "") or "",
            }
        else:  # cron
            meta = {
                "cron": cls._g(row, "trigger_args", "") or "",
                "target_type": cls._g(row, "target_type", "") or "",
                "next_run_time": cls._g(row, "next_run_time"),
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
        trigger = r.trigger or "cron"
        trigger_args = r.trigger_args or ""
        return {
            "id": r.id,
            "name": r.name,
            "description": r.description or "",
            "trigger": trigger,
            "trigger_args": trigger_args,
            # 兼容字段：前端 C 阶段切到 trigger/trigger_args 之前仍读 `cron`
            "cron": trigger_args if trigger == "cron" else "",
            "target_type": r.target_type or "agent",
            "target_id": r.target_id,
            "category_id": r.category_id,
            "enabled": bool(r.enabled),
            "last_run_time": r.last_run_time,
            "next_run_time": r.next_run_time,
        }

    @staticmethod
    def _resolve_trigger(cron: str | None, enabled: bool) -> tuple[str, str | None]:
        """把 `cron` 入参解析为 `(trigger, trigger_args)`（统一层是唯一口径）。

        - 非空表达式：先 `TriggerUtil.validate`（非法 → 400，原因原样回显），再 `TriggerUtil.normalize`
          —— 写入即规范化（`0 9 * * 1-5` → `0 9 * * mon,tue,wed,thu,fri`）；
        - 空值 + **启用中**：明确报错。否则会落一条「已启用但永不触发」的行：建行成功、
          `next_run_time` 为空、永不执行，用户完全无感知（静默失效）；
        - 空值 + 未启用：视为「未配置」（`trigger_args=None`），保住「关闭调度 / 清空配置」语义。
        """
        if not cron or not str(cron).strip():
            if enabled:
                raise CustomException(msg=_EMPTY_TRIGGER_MSG, code=400, status_code=400)
            return "cron", None
        ok, reason = TriggerUtil.validate("cron", cron)
        if not ok:
            raise CustomException(msg=reason, code=400, status_code=400)
        trigger, args = TriggerUtil.normalize("cron", cron)
        return trigger, args

    @staticmethod
    def _next_run_time(trigger: str | None, trigger_args) -> datetime | None:
        """下次运行时间一律来自统一层；未配置表达式（历史空行）返回 `None`。

        `trigger` 为 NULL 的历史行按 `cron` 兜底（与 `_cron_dict` 同口径）：否则统一层会抛
        「未知触发类型」，被调用方的 `except` 吞掉后**静默把用户任务置为禁用**。
        """
        if not trigger_args:
            return None
        return TriggerUtil.next_run(trigger or "cron", trigger_args)

    @classmethod
    async def create_cron(cls, data, auth) -> dict:
        trigger, trigger_args = cls._resolve_trigger(data.cron, bool(data.enabled))
        next_run = cls._next_run_time(trigger, trigger_args) if data.enabled else None
        async with async_db_session.begin() as db:
            row = AiWorkspaceCronModel(
                name=data.name,
                description=data.description,
                trigger=trigger,
                trigger_args=trigger_args,
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
            for key in (
                "name",
                "description",
                "target_type",
                "target_id",
                "category_id",
                "enabled",
            ):
                val = getattr(data, key, None)
                if val is not None:
                    setattr(row, key, val)
            if data.cron is not None:
                row.trigger, row.trigger_args = cls._resolve_trigger(data.cron, bool(row.enabled))
            elif data.enabled is True and not row.trigger_args:
                # 只切「启用」而库里没有表达式：同样不留「已启用但永不触发」的行
                raise CustomException(msg=_EMPTY_TRIGGER_MSG, code=400, status_code=400)
            # 重新计算下次运行（表达式或启停变化时；一律走统一层）
            if data.cron is not None or data.enabled is not None:
                row.next_run_time = (
                    cls._next_run_time(row.trigger, row.trigger_args) if row.enabled else None
                )
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
        from zoneinfo import ZoneInfo

        from loguru import logger

        # 下次运行时间来自统一层（Asia/Shanghai），比较统一到该时区的墙上时间，
        # 避免 aware（PG 的 timestamptz）与 naive 混用
        timezone = ZoneInfo(TriggerUtil.TIMEZONE)
        aiokill = False
        while not aiokill:
            try:
                now = datetime.now(timezone).replace(tzinfo=None)
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
                        due = r.next_run_time.replace(tzinfo=None) if r.next_run_time else None
                        if due is not None and due <= now:
                            # 标记运行并计算下一次（统一层）
                            r.last_run_time = now
                            try:
                                r.next_run_time = cls._next_run_time(r.trigger, r.trigger_args)
                            except Exception:  # noqa: BLE001
                                r.enabled = False
                            await db.flush()
                            try:
                                await cls._run_target(r.target_type, r.target_id)
                            except Exception as exc:  # noqa: BLE001
                                logger.error(f"定时任务 #{r.id} 执行失败：{exc}")
            except Exception as exc:  # noqa: BLE001
                logger.error(f"定时任务调度异常：{exc}")
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
