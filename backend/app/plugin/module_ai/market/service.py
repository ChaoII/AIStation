"""AI 能力市场服务：首页/列表/详情/安装/收藏（橱窗层，安装=复制真实资产）。

设计约定（见 2026-10-15-ai-capability-market-design.md）：
- 市场表 ``ai_market_items`` 为统一橱窗，``payload`` 保存资产快照；
- 安装 = 把 payload 复制成用户自己的真实资产（ai_tools/ai_skills/ai_mcp_servers/ai_plugins），
  并通过 ``ai_market_relations`` 记录 installed 关系保证幂等；
- Agent 绑定零侵入：工具/技能/插件绑定用户自己的真实记录，MCP 通过 mcp_ids。
"""
from sqlalchemy import func, or_, select

from app.core.database import async_db_session
from app.core.exceptions import CustomException
from app.plugin.module_ai.mcp.model import AiMcpServerModel
from app.plugin.module_ai.plugins.model import AiPluginModel
from app.plugin.module_ai.skill.model import AiSkillModel
from app.plugin.module_ai.tools_catalog.model import AiToolModel

from .model import AiMarketItemModel, AiMarketRelationModel

# 允许上架的资产类型
VALID_ASSET_TYPES = ("tool", "skill", "mcp", "plugin")


def _ensure_asset_type(asset_type: str) -> str:
    """校验资产类型，非法抛 CustomException。"""
    if asset_type not in VALID_ASSET_TYPES:
        raise CustomException(msg=f"不支持的资产类型：{asset_type}")
    return asset_type


def _to_dict(item: AiMarketItemModel, installed: bool = False, favorited: bool = False) -> dict:
    return {
        "id": item.id,
        "asset_type": item.asset_type,
        "name": item.name,
        "description": item.description or "",
        "icon": item.icon or "",
        "category": item.category or "",
        "tags": item.tags or [],
        "version": item.version or "1.0",
        "owner_id": item.owner_id,
        "is_official": bool(item.is_official),
        "featured": bool(item.featured),
        "status": item.status,
        "payload": item.payload,
        "source_id": item.source_id,
        "install_count": item.install_count or 0,
        "favorite_count": item.favorite_count or 0,
        "audit_remark": item.audit_remark or "",
        "created_time": item.created_time,
        "installed": installed,
        "favorited": favorited,
    }


async def _unique_name(db, model, base: str, field: str = "name") -> str:
    """生成不与现有记录冲突的唯一名（name/key 唯一约束兜底）。"""
    name = base or "unnamed"
    candidate = name
    idx = 2
    while True:
        exists = await db.scalar(
            select(model).where(getattr(model, field) == candidate)
        )
        if not exists:
            return candidate
        candidate = f"{name}_{idx}"
        idx += 1


async def _materialize(db, item: AiMarketItemModel, user_id: int) -> int:
    """把商品 payload 复制成当前用户的真实资产，返回真实记录 id。

    幂等性由调用方（relations installed 记录）保证；此函数只负责“复制出一份”。
    """
    payload = item.payload or {}
    asset_type = item.asset_type
    if asset_type == "tool":
        name = await _unique_name(db, AiToolModel, payload.get("name") or item.name)
        row = AiToolModel(
            name=name,
            kind=payload.get("kind") or "http",
            source=str(payload.get("source") or "system"),
            config=payload.get("config"),
            method=(payload.get("method") or "GET").upper(),
            url=payload.get("url") or "",
            headers=payload.get("headers"),
            params_schema=payload.get("params_schema"),
            code=payload.get("code", ""),
            timeout=int(payload.get("timeout") or 10),
            enabled=bool(payload.get("enabled", True)),
            description=payload.get("description") or item.description or "",
            created_id=user_id,
            updated_id=user_id,
        )
        db.add(row)
        await db.flush()
        return row.id
    if asset_type == "skill":
        name = await _unique_name(db, AiSkillModel, payload.get("name") or item.name)
        row = AiSkillModel(
            name=name,
            description=payload.get("description") or item.description or "",
            content=payload.get("content", ""),
            skill_type=payload.get("skill_type") or "tool",
            category=payload.get("category") or item.category or "",
            author=payload.get("author") or "",
            version=payload.get("version") or "1.0",
            scripts=payload.get("scripts"),
            config=payload.get("config"),
            icon=payload.get("icon") or item.icon or "",
            featured=False,
            sort_order=0,
            enabled=bool(payload.get("enabled", True)),
            created_id=user_id,
            updated_id=user_id,
        )
        db.add(row)
        await db.flush()
        return row.id
    if asset_type == "mcp":
        name = await _unique_name(db, AiMcpServerModel, payload.get("name") or item.name)
        row = AiMcpServerModel(
            name=name,
            transport=payload.get("transport") or "streamable-http",
            command=payload.get("command") or "",
            args=payload.get("args") or [],
            env=payload.get("env"),
            url=payload.get("url") or "",
            headers=payload.get("headers"),
            auth_type=payload.get("auth_type") or "none",
            enabled=bool(payload.get("enabled", True)),
            description=payload.get("description") or item.description or "",
            created_id=user_id,
            updated_id=user_id,
        )
        db.add(row)
        await db.flush()
        return row.id
    if asset_type == "plugin":
        key = await _unique_name(db, AiPluginModel, payload.get("key") or item.name, field="key")
        row = AiPluginModel(
            key=key,
            label=payload.get("label") or item.name,
            kind=payload.get("kind") or "builtin",
            config=payload.get("config"),
            config_schema=payload.get("config_schema"),
            executor_ready=bool(payload.get("executor_ready", False)),
            enabled=bool(payload.get("enabled", True)),
            description=payload.get("description") or item.description or "",
            created_id=user_id,
            updated_id=user_id,
        )
        db.add(row)
        await db.flush()
        return row.id
    raise CustomException(msg=f"不支持的资产类型：{asset_type}")


class MarketService:

    # ---------- 查询 ----------

    @classmethod
    async def home(cls, user_id: int) -> dict:
        """市场首页：精选（上架+精选）与分类计数（仅统计已上架）。"""
        async with async_db_session() as db:
            featured = (
                (
                    await db.execute(
                        select(AiMarketItemModel)
                        .where(
                            AiMarketItemModel.status == "approved",
                            AiMarketItemModel.featured.is_(True),
                        )
                        .order_by(AiMarketItemModel.install_count.desc())
                        .limit(8)
                    )
                )
                .scalars()
                .all()
            )
            category_rows = (
                await db.execute(
                    select(
                        func.coalesce(func.nullif(AiMarketItemModel.category, ""), "未分类").label(
                            "name"
                        ),
                        func.count().label("count"),
                    )
                    .where(AiMarketItemModel.status == "approved")
                    .group_by("name")
                    .order_by(func.count().desc())
                )
            ).all()
            return {
                "featured": [
                    _to_dict(i, *await cls._relation_flags(db, user_id, i.id)) for i in featured
                ],
                "categories": [{"name": r.name, "count": r.count} for r in category_rows],
            }

    @classmethod
    async def _relation_flags(cls, db, user_id: int, item_id: int) -> tuple[bool, bool]:
        """查询某商品对某用户的 installed/favorited 标志。"""
        rows = (
            await db.execute(
                select(AiMarketRelationModel.kind).where(
                    AiMarketRelationModel.user_id == user_id,
                    AiMarketRelationModel.item_id == item_id,
                    AiMarketRelationModel.is_deleted.is_(False),
                )
            )
        ).scalars().all()
        return "installed" in rows, "favorited" in rows

    @classmethod
    async def list_items(cls, query, user_id: int) -> dict:
        """市场列表：默认只显示已上架（approved）；支持类型/分类/关键词/个人关系过滤。"""
        async with async_db_session() as db:
            stmt = select(AiMarketItemModel).where(AiMarketItemModel.status == "approved")
            if getattr(query, "type", None):
                stmt = stmt.where(AiMarketItemModel.asset_type == query.type)
            if getattr(query, "category", None):
                stmt = stmt.where(AiMarketItemModel.category == query.category)
            if getattr(query, "keyword", None):
                kw = f"%{query.keyword}%"
                stmt = stmt.where(
                    or_(
                        AiMarketItemModel.name.ilike(kw),
                        AiMarketItemModel.description.ilike(kw),
                    )
                )
            if getattr(query, "favorite", False) or getattr(query, "installed", False):
                kinds = []
                if query.favorite:
                    kinds.append("favorited")
                if query.installed:
                    kinds.append("installed")
                sub = select(AiMarketRelationModel.item_id).where(
                    AiMarketRelationModel.user_id == user_id,
                    AiMarketRelationModel.kind.in_(kinds),
                    AiMarketRelationModel.is_deleted.is_(False),
                )
                stmt = stmt.where(AiMarketItemModel.id.in_(sub))

            total = (await db.execute(select(func.count()).select_from(stmt.subquery()))).scalar() or 0
            rows = (
                await db.execute(
                    stmt.order_by(AiMarketItemModel.created_time.desc())
                    .offset((query.page_no - 1) * query.page_size)
                    .limit(query.page_size)
                )
            ).scalars().all()

            # 批量取关系标志，避免 N+1
            if not rows:
                return {"page_no": query.page_no, "page_size": query.page_size, "total": total, "items": []}
            ids = [r.id for r in rows]
            rel_rows = (
                await db.execute(
                    select(AiMarketRelationModel.item_id, AiMarketRelationModel.kind).where(
                        AiMarketRelationModel.user_id == user_id,
                        AiMarketRelationModel.item_id.in_(ids),
                        AiMarketRelationModel.is_deleted.is_(False),
                    )
                )
            ).all()
            flags: dict[int, set[str]] = {}
            for item_id, kind in rel_rows:
                flags.setdefault(item_id, set()).add(kind)
            return {
                "page_no": query.page_no,
                "page_size": query.page_size,
                "total": total,
                "items": [
                    _to_dict(
                        r,
                        "installed" in flags.get(r.id, set()),
                        "favorited" in flags.get(r.id, set()),
                    )
                    for r in rows
                ],
            }

    @classmethod
    async def detail(cls, item_id: int, user_id: int) -> dict | None:
        """商品详情（任何状态可见，带安装/收藏标志）。"""
        async with async_db_session() as db:
            item = await db.get(AiMarketItemModel, item_id)
            if not item or item.is_deleted:
                return None
            installed, favorited = await cls._relation_flags(db, user_id, item_id)
            return _to_dict(item, installed, favorited)

    # ---------- 收藏 ----------

    @classmethod
    async def favorite(cls, item_id: int, user_id: int, on: bool) -> dict:
        """收藏/取消收藏（幂等）。"""
        async with async_db_session.begin() as db:
            item = await db.get(AiMarketItemModel, item_id)
            if not item or item.is_deleted:
                raise CustomException(msg="商品不存在")
            rel = await db.scalar(
                select(AiMarketRelationModel).where(
                    AiMarketRelationModel.user_id == user_id,
                    AiMarketRelationModel.item_id == item_id,
                    AiMarketRelationModel.kind == "favorited",
                    AiMarketRelationModel.is_deleted.is_(False),
                )
            )
            if on and not rel:
                db.add(
                    AiMarketRelationModel(
                        user_id=user_id,
                        item_id=item_id,
                        kind="favorited",
                    )
                )
                item.favorite_count = (item.favorite_count or 0) + 1
            elif not on and rel:
                await db.delete(rel)
                item.favorite_count = max((item.favorite_count or 0) - 1, 0)
            return {"item_id": item_id, "favorited": bool(on)}

    # ---------- 安装 ----------

    @classmethod
    async def install(cls, item_id: int, user_id: int) -> dict:
        """安装商品：复制 payload 为真实资产（幂等）。

        返回: ``{installed, exists, real_id, asset_type}``
        - 首次安装: installed=True, exists=False, real_id=真实资产 id
        - 已安装: installed=False, exists=True, real_id=已有真实资产 id（若无记录返回原值）
        """
        async with async_db_session.begin() as db:
            item = await db.get(AiMarketItemModel, item_id)
            if not item or item.is_deleted:
                raise CustomException(msg="商品不存在")
            if item.status != "approved":
                raise CustomException(msg="商品未上架，无法安装")
            # 幂等：已安装直接返回已有关系
            rel = await db.scalar(
                select(AiMarketRelationModel).where(
                    AiMarketRelationModel.user_id == user_id,
                    AiMarketRelationModel.item_id == item_id,
                    AiMarketRelationModel.kind == "installed",
                    AiMarketRelationModel.is_deleted.is_(False),
                )
            )
            if rel:
                # relation.description 里存了已复制的真实资产 id
                try:
                    real_id = int(rel.description) if rel.description else None
                except (TypeError, ValueError):
                    real_id = None
                return {
                    "installed": False,
                    "exists": True,
                    "real_id": real_id,
                    "asset_type": item.asset_type,
                }
            real_id = await _materialize(db, item, user_id)
            db.add(
                AiMarketRelationModel(
                    user_id=user_id,
                    item_id=item_id,
                    kind="installed",
                    description=str(real_id),
                )
            )
            item.install_count = (item.install_count or 0) + 1
            return {
                "installed": True,
                "exists": False,
                "real_id": real_id,
                "asset_type": item.asset_type,
                "name": item.name,
            }
