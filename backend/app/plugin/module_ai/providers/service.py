"""提供商服务：CRUD、测试连接、拉取远端模型列表。"""
from sqlalchemy import select

from app.core.database import async_db_session
from app.core.exceptions import CustomException
from app.plugin.module_ai.provider.service import _mask, build_headers

from .model import AiProviderModel


def _to_dict(p: AiProviderModel) -> dict:
    return {
        "id": p.id,
        "name": p.name,
        "protocol": p.protocol,
        "base_url": p.base_url,
        "enabled": p.enabled,
        "extra_headers": p.extra_headers,
        "description": p.description,
        "api_key_masked": _mask(p.api_key),
    }


class AiProviderService:

    @classmethod
    async def list_providers(cls) -> list[dict]:
        async with async_db_session() as db:
            rows = (
                await db.execute(
                    select(AiProviderModel)
                    .where(AiProviderModel.is_deleted.is_(False))
                    .order_by(AiProviderModel.id.desc())
                )
            ).scalars().all()
            return [_to_dict(p) for p in rows]

    @classmethod
    async def create(cls, data, auth) -> dict:
        async with async_db_session.begin() as db:
            p = AiProviderModel(
                name=data.name,
                protocol=data.protocol,
                base_url=data.base_url or "",
                api_key=data.api_key or "",
                extra_headers=data.extra_headers,
                enabled=data.enabled,
                description=getattr(data, "description", None),
                created_id=auth.user.id,
                updated_id=auth.user.id,
            )
            db.add(p)
            await db.flush()
            return _to_dict(p)

    @classmethod
    async def update(cls, provider_id: int, data, auth) -> dict | None:
        async with async_db_session.begin() as db:
            p = await db.get(AiProviderModel, provider_id)
            if not p or p.is_deleted:
                return None
            for key in ("name", "protocol", "base_url", "enabled", "extra_headers", "description"):
                val = getattr(data, key, None)
                if val is not None:
                    setattr(p, key, val)
            api_key = getattr(data, "api_key", None)
            if api_key:
                p.api_key = api_key
            p.updated_id = auth.user.id
            await db.flush()
            return _to_dict(p)

    @classmethod
    async def delete(cls, ids: list[int]) -> None:
        async with async_db_session.begin() as db:
            for pid in ids:
                p = await db.get(AiProviderModel, pid)
                if p:
                    await db.delete(p)

    @classmethod
    async def _load(cls, provider_id: int) -> AiProviderModel:
        async with async_db_session() as db:
            p = await db.get(AiProviderModel, provider_id)
            if not p or p.is_deleted:
                raise CustomException(msg="提供商不存在")
            return p

    @classmethod
    async def remote_models(cls, provider_id: int) -> list[str]:
        p = await cls._load(provider_id)
        if not p.base_url:
            raise CustomException(msg="base_url 不能为空")
        import httpx

        url = p.base_url.rstrip("/") + "/models"
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.get(
                    url,
                    headers={
                        "Authorization": f"Bearer {p.api_key}" if p.api_key else "",
                        **build_headers(p.base_url, p.extra_headers),
                    },
                )
            if resp.status_code >= 400:
                raise CustomException(msg=f"拉取失败 HTTP {resp.status_code}: {resp.text[:200]}")
            data = resp.json()
            items = data.get("data") if isinstance(data, dict) else data
            return [str(x.get("id")) for x in (items or []) if isinstance(x, dict) and x.get("id")]
        except CustomException:
            raise
        except Exception as e:
            raise CustomException(msg=f"拉取失败: {e}")
