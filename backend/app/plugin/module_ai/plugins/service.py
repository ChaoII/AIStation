"""AI 能力插件服务：内置预置 + CRUD + 启停 + 执行器就绪判定。"""
from datetime import datetime

from sqlalchemy import select

from app.core.database import async_db_session
from app.core.exceptions import CustomException

from .model import AiPluginModel
from .plugin_executor import PLUGIN_EXECUTORS, PLUGIN_SPEC_MAP, PLUGIN_SPECS


def _to_dict(p: AiPluginModel) -> dict:
    return {
        "id": p.id,
        "key": p.key,
        "label": p.label or "",
        "kind": p.kind or "builtin",
        "config": p.config or {},
        "config_schema": p.config_schema or {},
        "executor_ready": bool(p.executor_ready),
        "enabled": bool(p.enabled),
        "description": p.description or "",
        "created_time": p.created_time,
    }


async def ensure_builtins(db) -> None:
    """惰性预置内置插件（按 key 幂等，不覆盖用户改动）。"""
    existing = set(
        (
            await db.execute(select(AiPluginModel.key).where(AiPluginModel.is_deleted.is_(False)))
        ).scalars().all()
    )
    for spec in PLUGIN_SPECS:
        if spec["key"] in existing:
            continue
        db.add(
            AiPluginModel(
                key=spec["key"],
                label=spec["label"],
                kind="builtin",
                config={},
                config_schema=spec.get("config_schema") or {},
                executor_ready=bool(spec.get("executor_ready")),
                enabled=True,
                description=spec.get("description") or "",
            )
        )
    # 显式 flush：会话关闭 autoflush 时，后续查询才看得到刚预置的行
    await db.flush()


class PluginService:

    @classmethod
    async def list_plugins(cls) -> list[dict]:
        async with async_db_session.begin() as db:
            await ensure_builtins(db)
            rows = (
                await db.execute(
                    select(AiPluginModel)
                    .where(AiPluginModel.is_deleted.is_(False))
                    .order_by(AiPluginModel.id.asc())
                )
            ).scalars().all()
            return [_to_dict(p) for p in rows]

    @classmethod
    async def create(cls, data, auth) -> dict:
        async with async_db_session.begin() as db:
            exists = await db.scalar(
                select(AiPluginModel).where(
                    AiPluginModel.key == data.key, AiPluginModel.is_deleted.is_(False)
                )
            )
            if exists:
                raise CustomException(msg=f"插件标识已存在：{data.key}")
            spec = PLUGIN_SPEC_MAP.get(data.key)
            p = AiPluginModel(
                key=data.key,
                label=data.label or (spec or {}).get("label") or data.key,
                kind=data.kind or "custom",
                config=data.config,
                config_schema=data.config_schema or (spec or {}).get("config_schema") or {},
                executor_ready=data.key in PLUGIN_EXECUTORS,
                enabled=data.enabled,
                description=data.description or (spec or {}).get("description") or "",
                created_id=auth.user.id,
                updated_id=auth.user.id,
            )
            db.add(p)
            await db.flush()
            return _to_dict(p)

    @classmethod
    async def update(cls, plugin_id: int, data, auth) -> dict | None:
        async with async_db_session.begin() as db:
            p = await db.get(AiPluginModel, plugin_id)
            if not p or p.is_deleted:
                return None
            for key in ("label", "config", "config_schema", "enabled", "description"):
                val = getattr(data, key, None)
                if val is not None:
                    setattr(p, key, val)
            p.updated_id = auth.user.id
            await db.flush()
            return _to_dict(p)

    @classmethod
    async def delete(cls, ids: list[int], user_id: int) -> None:
        """软删除插件：保留行，避免市场安装关系悬垂（列表已按 is_deleted 过滤）。"""
        async with async_db_session.begin() as db:
            now = datetime.now()
            for pid in ids:
                p = await db.get(AiPluginModel, pid)
                if p and not p.is_deleted:
                    p.is_deleted = True
                    p.deleted_time = now
                    p.deleted_id = user_id
                    p.updated_id = user_id
                    # 释放唯一 key：允许重新创建同 key 插件
                    suffix = f"__deleted_{p.id}_{int(now.timestamp())}"
                    p.key = f"{(p.key or '')[: 64 - len(suffix)]}{suffix}"

    @classmethod
    async def toggle(cls, plugin_id: int, enabled: bool, auth) -> dict | None:
        async with async_db_session.begin() as db:
            p = await db.get(AiPluginModel, plugin_id)
            if not p or p.is_deleted:
                return None
            p.enabled = bool(enabled)
            p.updated_id = auth.user.id
            await db.flush()
            return _to_dict(p)

    @classmethod
    async def enabled_plugins(cls) -> list[dict]:
        """取启用且执行器就绪的插件（供 Agent 运行时注入能力说明）。"""
        async with async_db_session.begin() as db:
            await ensure_builtins(db)
            rows = (
                await db.execute(
                    select(AiPluginModel)
                    .where(
                        AiPluginModel.is_deleted.is_(False),
                        AiPluginModel.enabled.is_(True),
                    )
                    .order_by(AiPluginModel.id.asc())
                )
            ).scalars().all()
            return [_to_dict(p) for p in rows if p.key in PLUGIN_EXECUTORS]
