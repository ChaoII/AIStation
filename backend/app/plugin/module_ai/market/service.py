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

from .model import AiMarketItemModel, AiMarketRelationModel, AiMarketShareModel

#: 资产类型 → 真实模型（我的资产统一维护用）
_ASSET_MODELS = {
    "tool": AiToolModel,
    "skill": AiSkillModel,
    "mcp": AiMcpServerModel,
    "plugin": AiPluginModel,
}

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


async def _snapshot(db, asset_type: str, source_id: int) -> tuple[dict, int]:
    """读取个人真实资产并生成市场快照 payload，返回 ``(payload, owner_id)``。"""
    _ensure_asset_type(asset_type)
    if asset_type == "tool":
        row = await db.get(AiToolModel, source_id)
        if not row or row.is_deleted:
            raise CustomException(msg="来源工具不存在")
        return (
            {
                "name": row.name,
                "kind": row.kind or "builtin",
                "source": row.source or "system",
                "config": row.config,
                "method": row.method or "GET",
                "url": row.url or "",
                "headers": row.headers,
                "params_schema": row.params_schema,
                "code": row.code or "",
                "timeout": row.timeout or 10,
                "enabled": bool(row.enabled),
                "description": row.description or "",
            },
            row.created_id,
        )
    if asset_type == "skill":
        row = await db.get(AiSkillModel, source_id)
        if not row or row.is_deleted:
            raise CustomException(msg="来源技能不存在")
        return (
            {
                "name": row.name,
                "description": row.description or "",
                "content": row.content or "",
                "skill_type": row.skill_type or "tool",
                "category": row.category or "",
                "author": row.author or "",
                "version": row.version or "1.0",
                "scripts": row.scripts,
                "config": row.config,
                "icon": row.icon or "",
                "enabled": bool(row.enabled),
            },
            row.created_id,
        )
    if asset_type == "mcp":
        row = await db.get(AiMcpServerModel, source_id)
        if not row or row.is_deleted:
            raise CustomException(msg="来源 MCP 服务器不存在")
        return (
            {
                "name": row.name,
                "transport": row.transport or "streamable-http",
                "command": row.command or "",
                "args": row.args or [],
                "env": row.env,
                "url": row.url or "",
                "headers": row.headers,
                "auth_type": row.auth_type or "none",
                "enabled": bool(row.enabled),
                "description": row.description or "",
            },
            row.created_id,
        )
    row = await db.get(AiPluginModel, source_id)
    if not row or row.is_deleted:
        raise CustomException(msg="来源插件不存在")
    return (
        {
            "key": row.key,
            "label": row.label or "",
            "kind": row.kind or "builtin",
            "config": row.config,
            "config_schema": row.config_schema,
            "executor_ready": bool(row.executor_ready),
            "enabled": bool(row.enabled),
            "description": row.description or "",
        },
        row.created_id,
    )


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


class _BundleChild:
    """能力包（bundle）内的子项：借用父商品的名称/图标，复用 _materialize 递归安装。"""

    def __init__(self, asset_type: str, payload: dict, parent) -> None:
        self.asset_type = asset_type
        self.payload = payload
        self.name = payload.get("name") or parent.name
        self.description = payload.get("description") or parent.description
        self.icon = parent.icon


class _SharedAssetProxy:
    """个人资产分享的 materialize 代理：以分享时快照 + 最小字段凑成 ``_materialize`` 所需形态。"""

    def __init__(
        self,
        asset_type: str,
        payload: dict,
        name: str,
        description: str,
        icon: str,
        category: str,
    ) -> None:
        self.asset_type = asset_type
        self.payload = payload
        self.name = name or ""
        self.description = description or ""
        self.icon = icon or ""
        self.category = category or ""


async def _materialize(
    db, item: AiMarketItemModel, user_id: int, reuse_by_name: bool = True
) -> int:
    """把商品 payload 复制成当前用户的真实资产，返回真实记录 id。

    幂等性由调用方（relations installed 记录）保证；此函数只负责“复制出一份”。

    ``reuse_by_name``：工具类型为 True 时，若已存在同名工具（平台内置/他人生成）则复用，
    安装即“启用”、不再复制带后缀新行；为 False 时（个人资产分享）强制给接收方新建一份。
    """
    payload = item.payload or {}
    asset_type = item.asset_type
    if asset_type == "tool":
        want_name = payload.get("name") or item.name
        # 平台已内置同名工具（agno/system）或用户已有同名行：直接复用，安装即"启用"，
        # 不再复制出带后缀的新行（否则派发时按名字找不到 agno 工具）。
        if reuse_by_name:
            existing = await db.scalar(
                select(AiToolModel).where(
                    AiToolModel.name == want_name,
                    AiToolModel.is_deleted.is_(False),
                )
            )
            if existing is not None:
                if not existing.enabled:
                    existing.enabled = True
                return existing.id
        name = await _unique_name(db, AiToolModel, want_name)
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
        # 能力包（bundle，对齐 Dify 插件语义）：先安装包内的技能 / 工具 / MCP，
        # 再落一条「包」记录，便于在能力市场里查看与追溯。
        bundle = payload.get("bundle") or {}
        if bundle:
            for sk in bundle.get("skills") or []:
                await _materialize(db, _BundleChild("skill", sk, item), user_id)
            for tl in bundle.get("tools") or []:
                await _materialize(db, _BundleChild("tool", tl, item), user_id)
            for mc in bundle.get("mcps") or []:
                await _materialize(db, _BundleChild("mcp", mc, item), user_id)
        key = await _unique_name(db, AiPluginModel, payload.get("key") or item.name, field="key")
        row = AiPluginModel(
            key=key,
            label=payload.get("label") or item.name,
            kind=payload.get("kind") or ("bundle" if bundle else "builtin"),
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
    async def home(cls, user_id: int, asset_type: str | None = None) -> dict:
        """市场首页：精选（上架+精选）与分类计数（仅统计已上架）。

        ``asset_type`` 传入时，精选与分类计数都限定在该类型内（前端类型页签联动分类栏）。
        """
        async with async_db_session() as db:
            featured_stmt = select(AiMarketItemModel).where(
                AiMarketItemModel.status == "approved",
                AiMarketItemModel.featured.is_(True),
            )
            if asset_type:
                featured_stmt = featured_stmt.where(
                    AiMarketItemModel.asset_type == asset_type
                )
            featured = (
                (
                    await db.execute(
                        featured_stmt.order_by(AiMarketItemModel.install_count.desc()).limit(12)
                    )
                )
                .scalars()
                .all()
            )
            # 分类计数：在 Python 侧聚合（PG 对 GROUP BY 表达式要求逐字一致，
            # 参数化后 select 与 group_by 的参数编号不同会被判定为不同表达式而报错）
            cat_stmt = select(AiMarketItemModel.category).where(
                AiMarketItemModel.status == "approved"
            )
            if asset_type:
                cat_stmt = cat_stmt.where(AiMarketItemModel.asset_type == asset_type)
            cat_rows = (await db.execute(cat_stmt)).scalars().all()
            counter: dict[str, int] = {}
            for c in cat_rows:
                key = (c or "").strip() or "未分类"
                counter[key] = counter.get(key, 0) + 1
            categories = [
                {"name": k, "count": v}
                for k, v in sorted(counter.items(), key=lambda kv: -kv[1])
            ]
            return {
                "featured": [
                    _to_dict(i, *await cls._relation_flags(db, user_id, i.id)) for i in featured
                ],
                "categories": categories,
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

    # ---------- 提交 / 撤回 / 我的资产 ----------

    @classmethod
    async def submit(cls, data, user_id: int) -> dict:
        """提交个人资产到市场：快照 payload，状态 pending，等待审核。"""
        name = (data.name or "").strip()
        if not name:
            raise CustomException(msg="商品名称不能为空")
        async with async_db_session.begin() as db:
            payload, owner_id = await _snapshot(db, data.asset_type, data.source_id)
            if owner_id != user_id:
                raise CustomException(msg="只能提交自己的资产")
            dup = await db.scalar(
                select(AiMarketItemModel).where(
                    AiMarketItemModel.asset_type == data.asset_type,
                    AiMarketItemModel.name == name,
                    AiMarketItemModel.status.in_(("pending", "approved")),
                    AiMarketItemModel.is_deleted.is_(False),
                )
            )
            if dup:
                raise CustomException(msg=f"该资产已提交过（状态：{dup.status}）")
            item = AiMarketItemModel(
                asset_type=data.asset_type,
                name=name,
                description=data.description or "",
                icon=data.icon or "",
                category=data.category or "",
                tags=data.tags or [],
                version=data.version or "1.0",
                owner_id=user_id,
                is_official=False,
                featured=False,
                status="pending",
                payload=payload,
                source_id=data.source_id,
                install_count=0,
                favorite_count=0,
            )
            db.add(item)
            await db.flush()
            return _to_dict(item)

    @classmethod
    async def withdraw(cls, item_id: int, user_id: int) -> dict:
        """撤回自己的商品（下架），撤回后不可安装。"""
        async with async_db_session.begin() as db:
            item = await db.get(AiMarketItemModel, item_id)
            if not item or item.is_deleted:
                raise CustomException(msg="商品不存在")
            if item.owner_id != user_id:
                raise CustomException(msg="只能撤回自己提交的商品")
            item.status = "offline"
            return _to_dict(item)

    @classmethod
    async def list_mine(cls, user_id: int, asset_type: str | None = None) -> dict:
        """我的资产：个人真实资产 + 关联的市场提交状态。"""
        async with async_db_session() as db:
            # 我提交的市场商品（按 asset_type + source_id 建立索引）
            market_rows = (
                await db.execute(
                    select(AiMarketItemModel).where(
                        AiMarketItemModel.owner_id == user_id,
                        AiMarketItemModel.is_deleted.is_(False),
                    )
                )
            ).scalars().all()
            market_map: dict[tuple[str, int], dict] = {}
            for m in market_rows:
                if m.source_id is not None:
                    market_map[(m.asset_type, m.source_id)] = {
                        "item_id": m.id,
                        "status": m.status,
                        "featured": bool(m.featured),
                        "install_count": m.install_count or 0,
                        "audit_remark": m.audit_remark or "",
                        "icon": m.icon or "",
                    }

            result: list[dict] = []

            async def _collect(model, kind: str, name_field: str = "name"):
                rows = (
                    await db.execute(
                        select(model).where(
                            model.created_id == user_id,
                            model.is_deleted.is_(False),
                        )
                    )
                ).scalars().all()
                for r in rows:
                    market = market_map.get((kind, r.id))
                    result.append(
                        {
                            "asset_type": kind,
                            "real_id": r.id,
                            "name": getattr(r, name_field) or "",
                            "description": getattr(r, "description", "") or "",
                            "category": getattr(r, "category", "") or "",
                            "enabled": bool(getattr(r, "enabled", True)),
                            # 图标：优先真实资产自带（技能），否则用关联市场商品的图标
                            "icon": (getattr(r, "icon", "") or "") or ((market or {}).get("icon") or ""),
                            "market": market,
                        }
                    )

            if asset_type in (None, "", "tool"):
                await _collect(AiToolModel, "tool")
            if asset_type in (None, "", "skill"):
                await _collect(AiSkillModel, "skill")
            if asset_type in (None, "", "mcp"):
                await _collect(AiMcpServerModel, "mcp")
            if asset_type in (None, "", "plugin"):
                await _collect(AiPluginModel, "plugin", name_field="label")
            return {"items": result, "total": len(result)}

    # ---------- 审核 ----------

    @classmethod
    async def review_list(
        cls,
        status: str | None = None,
        asset_type: str | None = None,
        page_no: int = 1,
        page_size: int = 20,
    ) -> dict:
        """审核列表：默认待审核（pending），可按状态/资产类型过滤，分页，带提交者名。"""
        from app.api.v1.module_system.user.model import UserModel

        async with async_db_session() as db:
            stmt = select(AiMarketItemModel).where(AiMarketItemModel.is_deleted.is_(False))
            if status:
                stmt = stmt.where(AiMarketItemModel.status == status)
            else:
                stmt = stmt.where(AiMarketItemModel.status == "pending")
            if asset_type:
                stmt = stmt.where(AiMarketItemModel.asset_type == asset_type)
            total = (
                (await db.execute(select(func.count()).select_from(stmt.subquery()))).scalar() or 0
            )
            rows = (
                await db.execute(
                    stmt.order_by(AiMarketItemModel.created_time.desc())
                    .offset((page_no - 1) * page_size)
                    .limit(page_size)
                )
            ).scalars().all()
            # 批量取提交者名
            owner_ids = {r.owner_id for r in rows if r.owner_id}
            names: dict[int, str] = {}
            if owner_ids:
                urows = (
                    await db.execute(select(UserModel.id, UserModel.name).where(UserModel.id.in_(owner_ids)))
                ).all()
                names = dict(urows)
            items = []
            for r in rows:
                d = _to_dict(r)
                d["owner_name"] = names.get(r.owner_id, "") if r.owner_id else ""
                items.append(d)
            return {"page_no": page_no, "page_size": page_size, "total": total, "items": items}

    @classmethod
    async def review(cls, item_id: int, action: str, remark: str, user_id: int) -> dict:
        """审核商品：approve 上架 / reject 驳回（带意见）。已审核商品拒绝再审。"""
        if action not in ("approve", "reject"):
            raise CustomException(msg="审核动作不合法")
        async with async_db_session.begin() as db:
            item = await db.get(AiMarketItemModel, item_id)
            if not item or item.is_deleted:
                raise CustomException(msg="商品不存在")
            if item.status in ("approved", "rejected"):
                raise CustomException(msg="该商品已审核，请勿重复审核")
            from datetime import datetime

            item.status = "approved" if action == "approve" else "rejected"
            item.audit_remark = remark or ""
            item.audit_user = user_id
            item.audit_time = datetime.now()
            return _to_dict(item)

    @classmethod
    async def review_batch(cls, items: list, user_id: int) -> dict:
        """批量审核：逐条通过/驳回，返回每条结果（不因单条失败中断）。"""
        results = []
        for it in items:
            try:
                res = await cls.review(it.item_id, it.action, it.remark or "", user_id)
                results.append({"item_id": it.item_id, "ok": True, "status": res["status"]})
            except CustomException as e:
                results.append({"item_id": it.item_id, "ok": False, "msg": str(e)})
        return {"results": results}

    @classmethod
    async def set_featured(cls, item_id: int, featured: bool) -> dict:
        """设置/取消精选（审核权限）。"""
        async with async_db_session.begin() as db:
            item = await db.get(AiMarketItemModel, item_id)
            if not item or item.is_deleted:
                raise CustomException(msg="商品不存在")
            item.featured = bool(featured)
            return _to_dict(item)

    # ---------- 点对点分享 ----------

    @classmethod
    async def share_item(cls, data, user_id: int) -> dict:
        """把商品/个人资产分享给指定用户（不可分享给自己，接收人必须存在）。

        ``data`` 为 ``MarketShareSchema``：二选一来源——
        - ``item_id``：分享市场商品；
        - ``asset_type`` + ``real_id``：分享个人资产（含未提交市场的），快照存入分享记录。
        """

        from app.api.v1.module_system.user.model import UserModel

        if data.to_user_id == user_id:
            raise CustomException(msg="不能分享给自己")
        async with async_db_session.begin() as db:
            target = await db.get(UserModel, data.to_user_id)
            if not target or target.is_deleted:
                raise CustomException(msg="接收用户不存在")

            if data.item_id is not None:
                # 分享市场商品
                item = await db.get(AiMarketItemModel, data.item_id)
                if not item or item.is_deleted:
                    raise CustomException(msg="商品不存在")
                dup = await db.scalar(
                    select(AiMarketShareModel).where(
                        AiMarketShareModel.item_id == item.id,
                        AiMarketShareModel.from_user_id == user_id,
                        AiMarketShareModel.to_user_id == data.to_user_id,
                        AiMarketShareModel.status == "pending",
                        AiMarketShareModel.is_deleted.is_(False),
                    )
                )
                if dup:
                    raise CustomException(msg="已有一条待接收的分享")
                share = AiMarketShareModel(
                    item_id=item.id,
                    from_user_id=user_id,
                    to_user_id=data.to_user_id,
                    status="pending",
                    message=data.message or "",
                )
            else:
                # 分享个人资产（含未提交市场的）
                payload, owner_id = await _snapshot(db, data.asset_type, data.real_id)
                if owner_id != user_id:
                    raise CustomException(msg="只能分享自己的资产")
                dup = await db.scalar(
                    select(AiMarketShareModel).where(
                        AiMarketShareModel.asset_type == data.asset_type,
                        AiMarketShareModel.source_id == data.real_id,
                        AiMarketShareModel.from_user_id == user_id,
                        AiMarketShareModel.to_user_id == data.to_user_id,
                        AiMarketShareModel.status == "pending",
                        AiMarketShareModel.is_deleted.is_(False),
                    )
                )
                if dup:
                    raise CustomException(msg="已有一条待接收的分享")
                share = AiMarketShareModel(
                    asset_type=data.asset_type,
                    payload=payload,
                    asset_name=payload.get("name") or payload.get("label") or "",
                    asset_icon=payload.get("icon") or "",
                    source_id=data.real_id,
                    from_user_id=user_id,
                    to_user_id=data.to_user_id,
                    status="pending",
                    message=data.message or "",
                )
            db.add(share)
            await db.flush()
            return await cls._share_dict(db, share)

    @classmethod
    async def _share_dict(cls, db, share: AiMarketShareModel) -> dict:
        """组装分享记录输出（含资产摘要与双方用户名）。"""
        from app.api.v1.module_system.user.model import UserModel

        item = await db.get(AiMarketItemModel, share.item_id) if share.item_id else None
        from_user = await db.get(UserModel, share.from_user_id)
        to_user = await db.get(UserModel, share.to_user_id)
        # 分享市场商品时以商品信息为准；分享个人资产时以记录内快照为准
        asset_type = (item.asset_type if item else share.asset_type) or ""
        asset_name = (item.name if item else share.asset_name) or ""
        asset_icon = (item.icon if item else share.asset_icon) or ""
        return {
            "id": share.id,
            "item_id": share.item_id,
            "source": "market" if item else "asset",
            "asset_type": asset_type,
            "asset_name": asset_name,
            "asset_icon": asset_icon,
            "item_name": asset_name,
            "item_type": asset_type,
            "item_icon": asset_icon,
            "item_description": (item.description or "") if item else "",
            "from_user_id": share.from_user_id,
            "from_user_name": from_user.name if from_user else "",
            "to_user_id": share.to_user_id,
            "to_user_name": to_user.name if to_user else "",
            "status": share.status,
            "message": share.message or "",
            "created_time": share.created_time,
        }

    @classmethod
    async def list_shares(
        cls,
        user_id: int,
        direction: str = "in",
        status: str | None = None,
        page_no: int = 1,
        page_size: int = 20,
    ) -> dict:
        """分享列表：dir=in 收件箱 / dir=out 发件箱（严格按 from/to 过滤），分页。"""
        async with async_db_session() as db:
            stmt = select(AiMarketShareModel).where(AiMarketShareModel.is_deleted.is_(False))
            if direction == "out":
                stmt = stmt.where(AiMarketShareModel.from_user_id == user_id)
            else:
                stmt = stmt.where(AiMarketShareModel.to_user_id == user_id)
            if status:
                stmt = stmt.where(AiMarketShareModel.status == status)
            total = (await db.execute(select(func.count()).select_from(stmt.subquery()))).scalar() or 0
            rows = (
                await db.execute(
                    stmt.order_by(AiMarketShareModel.created_time.desc())
                    .offset((page_no - 1) * page_size)
                    .limit(page_size)
                )
            ).scalars().all()
            return {
                "page_no": page_no,
                "page_size": page_size,
                "total": total,
                "items": [await cls._share_dict(db, s) for s in rows],
            }

    @classmethod
    async def accept_share(cls, share_id: int, user_id: int) -> dict:
        """接收分享：把资产复制为接收方真实资产，并标记 accepted。

        - 分享市场商品：需商品 ``status==approved`` 才可接收，并校验安装幂等；
        - 分享个人资产：以分享记录内快照 materialize（可重复安装）。
        """
        async with async_db_session.begin() as db:
            share = await db.get(AiMarketShareModel, share_id)
            if not share or share.is_deleted:
                raise CustomException(msg="分享记录不存在")
            if share.to_user_id != user_id:
                raise CustomException(msg="无权处理该分享")
            if share.status != "pending":
                raise CustomException(msg="该分享已处理")

            real_id: int | None = None
            if share.item_id:
                # 分享市场商品：校验上架 + 安装幂等
                item = await db.get(AiMarketItemModel, share.item_id)
                if not item or item.is_deleted:
                    raise CustomException(msg="商品已不存在")
                if item.status != "approved":
                    raise CustomException(msg="商品未上架或未通过审核，无法接收")
                rel = await db.scalar(
                    select(AiMarketRelationModel).where(
                        AiMarketRelationModel.user_id == user_id,
                        AiMarketRelationModel.item_id == item.id,
                        AiMarketRelationModel.kind == "installed",
                        AiMarketRelationModel.is_deleted.is_(False),
                    )
                )
                if not rel:
                    real_id = await _materialize(db, item, user_id)
                    db.add(
                        AiMarketRelationModel(
                            user_id=user_id,
                            item_id=item.id,
                            kind="installed",
                            description=str(real_id),
                        )
                    )
                    item.install_count = (item.install_count or 0) + 1
                else:
                    try:
                        real_id = int(rel.description) if rel.description else None
                    except (TypeError, ValueError):
                        real_id = None
            else:
                # 分享个人资产：以快照 materialize
                payload = share.payload or {}
                proxy = _SharedAssetProxy(
                    asset_type=share.asset_type or "tool",
                    payload=payload,
                    name=share.asset_name or payload.get("name") or "",
                    description=payload.get("description") or "",
                    icon=share.asset_icon or payload.get("icon") or "",
                    category=payload.get("category") or "",
                )
                # 个人资产分享：强制给接收方新建一份，不复用分享人的同名资产
                real_id = await _materialize(db, proxy, user_id, reuse_by_name=False)
            share.status = "accepted"
            return {"share_id": share_id, "status": "accepted", "real_id": real_id}

    @classmethod
    async def reject_share(cls, share_id: int, user_id: int) -> dict:
        """拒绝分享。"""
        async with async_db_session.begin() as db:
            share = await db.get(AiMarketShareModel, share_id)
            if not share or share.is_deleted:
                raise CustomException(msg="分享记录不存在")
            if share.to_user_id != user_id:
                raise CustomException(msg="无权处理该分享")
            if share.status != "pending":
                raise CustomException(msg="该分享已处理")
            share.status = "rejected"
            return {"share_id": share_id, "status": "rejected"}

    # ---------- 我的资产：统一维护（启停 / 删除） ----------

    @classmethod
    async def toggle_asset(cls, asset_type: str, real_id: int, enabled: bool, user_id: int) -> dict:
        """统一启停入口：按资产类型定位真实资产行（仅限本人）。"""
        model = _ASSET_MODELS.get(asset_type)
        if model is None:
            raise CustomException(msg=f"不支持的资产类型：{asset_type}")
        async with async_db_session.begin() as db:
            row = await db.get(model, real_id)
            if not row or row.is_deleted:
                raise CustomException(msg="资产不存在")
            if getattr(row, "created_id", None) != user_id:
                raise CustomException(msg="只能操作自己的资产")
            row.enabled = bool(enabled)
            if hasattr(row, "updated_id"):
                row.updated_id = user_id
            return {"asset_type": asset_type, "real_id": real_id, "enabled": bool(enabled)}

    @classmethod
    async def delete_asset(cls, asset_type: str, real_id: int, user_id: int) -> dict:
        """统一删除入口（软删除真实资产，仅限本人）。"""
        model = _ASSET_MODELS.get(asset_type)
        if model is None:
            raise CustomException(msg=f"不支持的资产类型：{asset_type}")
        async with async_db_session.begin() as db:
            row = await db.get(model, real_id)
            if not row or row.is_deleted:
                raise CustomException(msg="资产不存在")
            if getattr(row, "created_id", None) != user_id:
                raise CustomException(msg="只能删除自己的资产")
            await db.delete(row)
            return {"asset_type": asset_type, "real_id": real_id, "deleted": True}
