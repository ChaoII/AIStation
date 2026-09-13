"""大模型配置服务：CRUD、运行时取用、连接测试。"""
from sqlalchemy import select, update

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
    async def get_runtime_model(cls) -> dict | None:
        """取默认且启用的模型；无则回退 env 配置；均无返回 None。"""
        async with async_db_session() as db:
            m = (
                await db.execute(
                    select(AiModelModel)
                    .where(
                        AiModelModel.is_deleted.is_(False),
                        AiModelModel.enabled.is_(True),
                    )
                    .order_by(AiModelModel.is_default.desc(), AiModelModel.id.desc())
                    .limit(1)
                )
            ).scalar_one_or_none()
            if m and m.base_url and m.model:
                return {
                    "base_url": m.base_url,
                    "api_key": m.api_key,
                    "model": m.model,
                    "temperature": m.temperature,
                    "max_tokens": m.max_tokens,
                    "extra_headers": m.extra_headers,
                }
        if settings.OPENAI_BASE_URL and settings.OPENAI_MODEL:
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
