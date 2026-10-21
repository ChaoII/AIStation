"""AI 集成开放平台 —— 嵌入能力服务（P4'）。

- :meth:`EmbedService.get_target`：按形态取嵌入目标（缺/停用均返回 ``None`` 由调用方判）。
- :meth:`EmbedService.issue_token`：签发短期 access_token——明文仅返回一次，
  库内只存 ``sha256``，并绑定 ``app + kind + target_id``（单目标最小权限）。
"""
from __future__ import annotations

from datetime import datetime, timedelta

from app.core.database import async_db_session

from .model import AiIntegrationAccessTokenModel, AiIntegrationAppModel
from .service import _generate_embed_token, _hash_embed_token, clamp_embed_ttl


class EmbedService:
    """嵌入令牌与目标解析（供换票端点与公开面复用）。"""

    @classmethod
    async def get_target(cls, kind: str, target_id: int) -> dict | None:
        """按形态取目标元信息：``{"name", "description", "enabled"}``；不存在返回 ``None``。

        分派到各形态既有详情方法（agent/app/workflow），不重复实现查询逻辑。
        """
        data: dict | None
        if kind == "agent":
            from app.plugin.module_ai.agent.service import AiAgentService

            data = await AiAgentService.get_agent(target_id)
        elif kind == "app":
            from app.plugin.module_ai.apps.service import AiAppService

            data = await AiAppService.get_app(target_id)
        elif kind == "workflow":
            from app.plugin.module_ai.workflow.service import AiWorkflowService

            data = await AiWorkflowService.get_workflow(target_id)
        else:
            return None
        if not data:
            return None
        return {
            "name": data.get("name") or "",
            "description": data.get("description") or "",
            "enabled": bool(data.get("enabled")),
        }

    @classmethod
    async def issue_token(
        cls,
        app: AiIntegrationAppModel,
        kind: str,
        target_id: int,
        ttl: int | None = None,
        issued_by: str = "exchange",
    ) -> dict:
        """签发嵌入令牌：返回 ``{"token", "expires_in", "expires_at"}``（明文仅此一次）。"""
        expires_in = clamp_embed_ttl(ttl)
        token = _generate_embed_token()
        expires_at = datetime.now() + timedelta(seconds=expires_in)
        async with async_db_session.begin() as db:
            db.add(
                AiIntegrationAccessTokenModel(
                    app_id=app.id,
                    appid=app.appid,
                    kind=kind,
                    target_id=target_id,
                    token_hash=_hash_embed_token(token),
                    expires_at=expires_at,
                    revoked=False,
                    issued_by=issued_by,
                    use_count=0,
                )
            )
        return {
            "token": token,
            "expires_in": expires_in,
            "expires_at": expires_at.strftime("%Y-%m-%d %H:%M:%S"),
        }
