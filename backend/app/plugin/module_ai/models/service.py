"""大模型配置服务：CRUD、运行时取用、连接测试。"""
from sqlalchemy import func, or_, select, update

from app.config.setting import settings
from app.core.database import async_db_session
from app.core.exceptions import CustomException

from .model import AiModelModel


def _mask(key: str | None) -> str:
    if not key:
        return ""
    return f"{key[:4]}****{key[-4:]}" if len(key) > 8 else "****"


def build_headers(base_url: str | None, extra_headers: dict | None = None, session_id: str = "aistation") -> dict:
    """构造请求头：opencode 网关需 x-opencode-session；再合并自定义头。"""
    headers: dict[str, str] = {}
    if base_url and "opencode.ai" in base_url:
        headers["x-opencode-session"] = session_id
        headers["User-Agent"] = "aistation/1.0"
    if extra_headers:
        headers.update({str(k): str(v) for k, v in extra_headers.items()})
    return headers


def _to_dict(m: AiModelModel) -> dict:
    return {
        "id": m.id,
        "name": m.name,
        "provider": m.provider,
        "provider_id": m.provider_id,
        "usage": m.usage,
        "capabilities": m.capabilities,
        "context_window": m.context_window,
        "base_url": m.base_url,
        "model": m.model,
        "temperature": m.temperature,
        "max_tokens": m.max_tokens,
        "enabled": m.enabled,
        "is_default": m.is_default,
        "extra_headers": m.extra_headers,
        "description": m.description,
        "api_key_masked": _mask(m.api_key),
        "created_time": m.created_time,
    }


class AiModelService:

    @classmethod
    async def count_models(cls) -> int:
        """未删除的模型配置数量（控制台/看板跨模块取数入口，不暴露模型）。"""
        async with async_db_session() as db:
            return int(
                (
                    await db.execute(
                        select(func.count())
                        .select_from(AiModelModel)
                        .where(AiModelModel.is_deleted.is_(False))
                    )
                ).scalar()
                or 0
            )

    @classmethod
    async def import_models(cls, items: list[dict], user_id: int | None = None) -> dict:
        """批量导入模型配置（按 ``base_url + model`` 去重），返回 ``{imported, skipped, total}``。

        **跨模块写 `ai_models` 的唯一入口**：providers 的「一键导入远端模型」只经本接口落库，
        不自己建模型行——表结构/默认值变更才只需改这一处。
        """
        imported = skipped = 0
        todo = [it for it in (items or []) if (it.get("model") or "").strip()]
        async with async_db_session.begin() as db:
            for it in todo:
                base_url = it.get("base_url") or ""
                mid = str(it["model"]).strip()
                exists = (
                    await db.execute(
                        select(AiModelModel).where(
                            AiModelModel.base_url == base_url,
                            AiModelModel.model == mid,
                            AiModelModel.is_deleted.is_(False),
                        )
                    )
                ).scalar_one_or_none()
                if exists:
                    skipped += 1
                    continue
                db.add(
                    AiModelModel(
                        name=it.get("name") or mid,
                        provider=it.get("provider") or "openai_compatible",
                        provider_id=it.get("provider_id"),
                        usage=it.get("usage") or "chat",
                        base_url=base_url,
                        api_key=it.get("api_key") or "",
                        model=mid,
                        temperature=it.get("temperature", 0.3),
                        max_tokens=it.get("max_tokens", 2048),
                        enabled=True,
                        extra_headers=it.get("extra_headers"),
                        created_id=user_id,
                        updated_id=user_id,
                    )
                )
                imported += 1
        return {"imported": imported, "skipped": skipped, "total": len(todo)}

    @classmethod
    async def list_models(cls) -> list[dict]:
        async with async_db_session() as db:
            rows = (
                await db.execute(
                    select(AiModelModel)
                    .where(AiModelModel.is_deleted.is_(False))
                    .order_by(AiModelModel.is_default.desc(), AiModelModel.id.desc())
                )
            ).scalars().all()
            return [_to_dict(m) for m in rows]

    @classmethod
    async def get_runtime_model(
        cls,
        usage: str | None = None,
        model_id: int | None = None,
        *,
        allow_env_fallback: bool = True,
    ) -> dict | None:
        """取默认且启用的模型（可按用途过滤）；解析所属提供商；无则回退 env。

        给定 ``model_id`` 时按指定模型解析（仍要求启用且未删除），跳过 ``usage`` 过滤。
        ``allow_env_fallback=False`` 用于「指定模型已失效就报错」的场景（如知识库
        绑定了一个已被删除的嵌入模型，不应悄悄改用全局 env 模型）。
        """
        async with async_db_session() as db:
            if model_id is not None:
                m = await db.get(AiModelModel, model_id)
                if not m or m.is_deleted or not m.enabled:
                    m = None
            else:
                stmt = select(AiModelModel).where(
                    AiModelModel.is_deleted.is_(False),
                    AiModelModel.enabled.is_(True),
                )
                if usage:
                    stmt = stmt.where(
                        or_(AiModelModel.usage == usage, AiModelModel.usage.is_(None))
                    )
                m = (
                    await db.execute(
                        stmt.order_by(
                            AiModelModel.is_default.desc(), AiModelModel.id.desc()
                        ).limit(1)
                    )
                ).scalar_one_or_none()
            if m and m.model:
                base_url = m.base_url
                api_key = m.api_key
                headers = dict(m.extra_headers or {})
                if m.provider_id:
                    from app.plugin.module_ai.providers.model import AiProviderModel

                    p = await db.get(AiProviderModel, m.provider_id)
                    if p and not p.is_deleted:
                        base_url = base_url or p.base_url
                        api_key = api_key or p.api_key
                        headers = {**(p.extra_headers or {}), **headers}
                if base_url:
                    return {
                        "base_url": base_url,
                        "api_key": api_key,
                        "model": m.model,
                        "usage": m.usage,
                        "temperature": m.temperature,
                        "max_tokens": m.max_tokens,
                        "extra_headers": headers or None,
                    }
        if allow_env_fallback and settings.OPENAI_BASE_URL and settings.OPENAI_MODEL:
            return {
                "base_url": settings.OPENAI_BASE_URL,
                "api_key": settings.OPENAI_API_KEY,
                "model": settings.OPENAI_MODEL,
                "temperature": 0.3,
                "max_tokens": 2048,
            }
        return None

    @classmethod
    async def create(cls, data, auth) -> dict:
        async with async_db_session.begin() as db:
            m = AiModelModel(
                name=data.name,
                provider=data.provider,
                provider_id=getattr(data, "provider_id", None),
                usage=getattr(data, "usage", "chat"),
                capabilities=getattr(data, "capabilities", None),
                context_window=getattr(data, "context_window", None),
                base_url=data.base_url or "",
                api_key=data.api_key or "",
                model=data.model or "",
                temperature=data.temperature,
                max_tokens=data.max_tokens,
                enabled=data.enabled,
                is_default=data.is_default,
                extra_headers=data.extra_headers,
                description=getattr(data, "description", None),
                created_id=auth.user.id,
                updated_id=auth.user.id,
            )
            db.add(m)
            await db.flush()
            if m.is_default:
                await db.execute(
                    update(AiModelModel)
                    .where(AiModelModel.id != m.id)
                    .values(is_default=False)
                )
            return _to_dict(m)

    @classmethod
    async def update(cls, model_id: int, data, auth) -> dict | None:
        async with async_db_session.begin() as db:
            m = await db.get(AiModelModel, model_id)
            if not m or m.is_deleted:
                return None
            for key in (
                "name",
                "provider",
                "provider_id",
                "usage",
                "capabilities",
                "context_window",
                "base_url",
                "model",
                "temperature",
                "max_tokens",
                "enabled",
                "is_default",
                "extra_headers",
                "description",
            ):
                val = getattr(data, key, None)
                if val is not None:
                    setattr(m, key, val)
            # 未传 api_key（None 或空串）时保留原值
            api_key = getattr(data, "api_key", None)
            if api_key:
                m.api_key = api_key
            m.updated_id = auth.user.id
            if m.is_default:
                await db.execute(
                    update(AiModelModel)
                    .where(AiModelModel.id != m.id)
                    .values(is_default=False)
                )
            await db.flush()
            return _to_dict(m)

    @classmethod
    async def set_default(cls, model_id: int) -> dict | None:
        async with async_db_session.begin() as db:
            m = await db.get(AiModelModel, model_id)
            if not m or m.is_deleted:
                return None
            await db.execute(update(AiModelModel).values(is_default=False))
            m.is_default = True
            await db.flush()
            return _to_dict(m)

    @classmethod
    async def batch_status(cls, ids: list[int], enabled: bool, auth) -> int:
        """批量启用/停用模型配置。"""
        async with async_db_session.begin() as db:
            count = 0
            for mid in ids:
                m = await db.get(AiModelModel, mid)
                if m and not m.is_deleted:
                    m.enabled = enabled
                    m.updated_id = getattr(getattr(auth, "user", None), "id", None)
                    count += 1
            return count

    @classmethod
    async def delete(cls, ids: list[int]) -> None:
        async with async_db_session.begin() as db:
            for mid in ids:
                m = await db.get(AiModelModel, mid)
                if m:
                    await db.delete(m)

    @classmethod
    async def test_connection(cls, data) -> dict:
        """用已保存配置或临时参数调用一次 LLM 验证连通性。"""
        cfg: dict | None = None
        extra_headers: dict | None = None
        if data.id:
            async with async_db_session() as db:
                m = await db.get(AiModelModel, data.id)
                if not m:
                    raise CustomException(msg="配置不存在")
                # 以已保存配置为底，允许用表单中已填的新值覆盖（便于编辑态未改 Key 时测试新地址）
                cfg = {
                    "base_url": data.base_url or m.base_url,
                    "api_key": data.api_key or m.api_key,
                    "model": data.model or m.model,
                }
                extra_headers = m.extra_headers
        else:
            cfg = {
                "base_url": data.base_url,
                "api_key": data.api_key,
                "model": data.model,
            }
            extra_headers = getattr(data, "extra_headers", None)

        if not cfg or not cfg.get("base_url") or not cfg.get("model"):
            raise CustomException(msg="base_url 与 model 不能为空")

        from openai import AsyncOpenAI

        client = AsyncOpenAI(
            base_url=cfg["base_url"],
            api_key=cfg["api_key"] or "sk-none",
            default_headers=build_headers(cfg["base_url"], extra_headers),
        )
        try:
            resp = await client.chat.completions.create(
                model=cfg["model"],
                messages=[{"role": "user", "content": "ping，请只回复 pong"}],
                max_tokens=8,
            )
            return {"ok": True, "reply": (resp.choices[0].message.content or "").strip()}
        except Exception as e:
            raise CustomException(msg=f"连接失败: {e}")
