"""AI 集成开放平台 —— 嵌入能力服务（P4'）。

- :meth:`EmbedService.get_target`：按形态取嵌入目标（缺/停用均返回 ``None`` 由调用方判）。
- :meth:`EmbedService.issue_token`：签发短期 access_token——明文仅返回一次，
  库内只存 ``sha256``，并绑定 ``app + kind + target_id``（单目标最小权限）。
"""
from __future__ import annotations

import time
from collections.abc import AsyncIterator
from datetime import datetime, timedelta
from types import SimpleNamespace
from typing import TYPE_CHECKING

from sqlalchemy import select

from app.core.database import async_db_session
from app.core.exceptions import CustomException
from app.plugin.module_ai.sessions.model import AiSessionModel

from .model import (
    AiIntegrationAccessTokenModel,
    AiIntegrationAppModel,
    AiIntegrationEmbedSessionModel,
)
from .service import (
    DevelopService,
    _generate_embed_token,
    _hash_embed_token,
    clamp_embed_ttl,
)

if TYPE_CHECKING:  # 仅类型标注，避免运行期循环导入
    from .auth import EmbedContext


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

    @classmethod
    async def prepare_session(cls, ctx: "EmbedContext", sid: str) -> tuple[int, bool]:
        """解析/建立 ``(app_id, sid)`` → 平台会话映射，返回 ``(session_id, session_reset)``。

        - 同 ``sid`` 换形态/换目标 → 403（防串会话）；
        - 无映射或映射过期 → 新建平台会话并重置映射（闲置 TTL 24 小时）；
        - 未过期 → 仅刷新 ``last_active_at``。
        """
        now = datetime.now()
        async with async_db_session.begin() as db:
            row = (
                await db.execute(
                    select(AiIntegrationEmbedSessionModel).where(
                        AiIntegrationEmbedSessionModel.app_id == ctx.app_id,
                        AiIntegrationEmbedSessionModel.sid == sid,
                        AiIntegrationEmbedSessionModel.is_deleted.is_(False),
                    )
                )
            ).scalar_one_or_none()
            if row is not None and (row.kind != ctx.kind or row.target_id != ctx.target_id):
                raise CustomException(msg="会话绑定无效", code=10403, status_code=403)
            reset = row is None or row.expires_at <= now
            if not reset:
                row.last_active_at = now
                return row.session_id, False
            # 新建平台会话（复用既有会话模型，归属打 source_app_id）
            session = AiSessionModel(
                title=f"嵌入-{ctx.kind}-{ctx.target_id}"[:255],
                user_id=None,
                source_app_id=ctx.app_id,
            )
            db.add(session)
            await db.flush()
            expires_at = now + timedelta(hours=24)
            if row is None:
                db.add(
                    AiIntegrationEmbedSessionModel(
                        app_id=ctx.app_id,
                        sid=sid,
                        kind=ctx.kind,
                        target_id=ctx.target_id,
                        session_id=session.id,
                        expires_at=expires_at,
                        last_active_at=now,
                    )
                )
            else:
                row.session_id = session.id
                row.expires_at = expires_at
                row.last_active_at = now
            return session.id, True

    @classmethod
    async def run_stream(
        cls,
        ctx: "EmbedContext",
        sid: str,
        app_row: AiIntegrationAppModel,
        session_id: int,
        session_reset: bool,
        message: str,
        redis=None,
    ) -> AsyncIterator[str]:
        """嵌入对话流：首帧 ``data-embed``，随后透传三形态既有 run 服务的 UI 帧。

        - 上下文来自**服务端会话**（客户端只传 ``sid`` + ``message``）；
        - 匿名垫片 ``SimpleNamespace(user=None)``：既有 run 服务经 ``getattr`` 取 uid，
          ``None`` 已被容忍；
        - 审计在流结束时写入（成功/异常都写；明文 token 不落审计）。
        """
        from app.plugin.module_ai.sessions.service import AiSessionService
        from app.plugin.module_ai.streaming import UiMessageStream

        ms = UiMessageStream()
        started = time.perf_counter()
        status = "success"
        error_text: str | None = None
        try:
            yield ms.data("embed", {"session_reset": session_reset, "sid": sid})
            history = await AiSessionService.get_messages(session_id)
            ui_messages = [{"role": m["role"], "parts": m["parts"]} for m in history]
            ui_messages.append(
                {"role": "user", "parts": [{"type": "text", "text": message}]}
            )
            auth = SimpleNamespace(user=None)  # 匿名垫片（uid=None）
            if ctx.kind == "agent":
                from app.plugin.module_ai.agent.service import AiAgentService

                gen = AiAgentService.run_ui_stream(
                    ctx.target_id, ui_messages, auth, None, session_id
                )
            elif ctx.kind == "app":
                from app.plugin.module_ai.apps.service import run_app_ui_stream

                gen = run_app_ui_stream(ctx.target_id, ui_messages, auth, None, session_id)
            else:
                from app.plugin.module_ai.workflow.service import AiWorkflowService

                gen = AiWorkflowService.run_ui_stream(
                    ctx.target_id, ui_messages, auth, None, session_id, redis=redis
                )
            async for frame in gen:
                yield frame
        except Exception as e:  # noqa: BLE001
            status = "error"
            error_text = str(e)[:250]
            raise
        finally:
            await DevelopService.log_call(
                app_row,
                category="embed",
                capability="run",
                method="EMBED",
                transport="sse",
                session_id=str(session_id),
                request_path="/run",
                request_body={
                    "sid": sid,
                    "kind": ctx.kind,
                    "target_id": ctx.target_id,
                    "message": message[:80],
                },
                status=status,
                error=error_text,
                latency_ms=int((time.perf_counter() - started) * 1000),
            )

    @classmethod
    async def check_limits(cls, redis, ctx: "EmbedContext", ip: str) -> None:
        """固定窗口限流（token/IP 双键）+ 按日配额；超限抛 429。

        - 限流：``INCR``+``EXPIRE 60``，键 ``ai:embed:rl:t:{hash12}`` / ``ai:embed:rl:ip:{ip}``；
        - 配额：``app.quota["embed"]`` 为自然日次数上限（缺省/0=不限），
          键 ``ai:embed:quota:{app_id}:{YYYYMMDD}``；
        - ``redis`` 为空时整体跳过（降级，不阻断对话）。
        """
        if redis is None:
            return
        from app.config.setting import settings

        async def _hit(key: str, cap: int, ttl: int = 60) -> bool:
            """计数 +1 并判断是否超限（固定窗口，首次命中时设过期）。"""
            count = int(await redis.incr(key))
            if count == 1:
                await redis.expire(key, ttl)
            return count > cap

        if await _hit(
            f"ai:embed:rl:t:{ctx.token_hash12}", settings.EMBED_RATE_TOKEN_PER_MIN
        ) or await _hit(f"ai:embed:rl:ip:{ip or 'na'}", settings.EMBED_RATE_IP_PER_MIN):
            raise CustomException(msg="访问过于频繁，请稍后再试", code=10429, status_code=429)

        quota = (ctx.quota or {}).get("embed")
        if isinstance(quota, int) and quota > 0:
            day = datetime.now().strftime("%Y%m%d")
            count = int(await redis.incr(f"ai:embed:quota:{ctx.app_id}:{day}"))
            if count == 1:
                await redis.expire(f"ai:embed:quota:{ctx.app_id}:{day}", 86400)
            if count > quota:
                raise CustomException(msg="今日嵌入调用配额已用完", code=10429, status_code=429)
