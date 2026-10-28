"""资产嵌入能力服务（面向 agent/工作流，脱离开放平台应用）。

- :meth:`AssetEmbedService.get_target`：按形态取嵌入目标（缺/停用返回 ``None``）。
- :meth:`AssetEmbedService.prepare_session`：解析/建立 ``(kind, target_id, sid)`` → 平台会话映射。
- :meth:`AssetEmbedService.run_stream`：嵌入对话流（首帧 ``data-embed``，透传目标运行服务的 UI 帧）。
- :meth:`AssetEmbedService.check_limits`：按令牌/IP 限流（固定窗口）。
"""
from __future__ import annotations

import asyncio
import json
import time
from collections.abc import AsyncIterator
from datetime import datetime, timedelta
from types import SimpleNamespace
from typing import TYPE_CHECKING

from sqlalchemy import select

from app.config.setting import settings
from app.core.database import async_db_session

if TYPE_CHECKING:
    from .auth import EmbedContext

from .model import AiAssetEmbedLogModel, AiAssetEmbedSessionModel

#: 嵌入会话闲置 TTL（小时）：每次使用滑动续期
SESSION_TTL_HOURS = 24


def _extract_stream_error(frame: str) -> str | None:
    """从 SSE 帧中提取 ``type=error`` 的文案（用于审计状态判定）。"""
    try:
        raw = frame[6:].strip() if frame.startswith("data: ") else frame.strip()
        payload = json.loads(raw)
    except Exception:  # noqa: BLE001
        return None
    if isinstance(payload, dict) and payload.get("type") == "error":
        return str(payload.get("errorText") or payload.get("message") or "运行失败")
    return None


class AssetEmbedService:
    """资产嵌入：目标解析 / 会话映射 / 对话流 / 限流。"""

    @classmethod
    async def get_target(cls, kind: str, target_id: int) -> dict | None:
        """按形态取目标元信息：``{"name", "description", "enabled"}``；不存在返回 ``None``。"""
        data: dict | None
        if kind == "agent":
            from app.plugin.module_ai.agent.service import AiAgentService

            data = await AiAgentService.get_agent(target_id)
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
    async def prepare_session(cls, ctx: EmbedContext, sid: str) -> tuple[int, bool]:
        """解析/建立 ``(kind, target_id, sid)`` → 平台会话映射，返回 ``(session_id, session_reset)``。

        - 同 sid 换目标由唯一约束（kind,target_id,sid）兜底，不再串会话；
        - 无映射或映射过期 → 新建平台会话并重置映射（闲置 TTL 24h）；
        - 未过期 → 刷新 ``last_active_at`` 并**滑动续期**。
        """
        now = datetime.now()
        async with async_db_session.begin() as db:
            row = (
                await db.execute(
                    select(AiAssetEmbedSessionModel).where(
                        AiAssetEmbedSessionModel.kind == ctx.kind,
                        AiAssetEmbedSessionModel.target_id == ctx.target_id,
                        AiAssetEmbedSessionModel.sid == sid,
                        AiAssetEmbedSessionModel.is_deleted.is_(False),
                    )
                )
            ).scalar_one_or_none()
            reset = row is None or row.expires_at <= now
            if not reset:
                row.last_active_at = now
                row.expires_at = now + timedelta(hours=SESSION_TTL_HOURS)
                return row.session_id, False
            # 新建平台会话（复用既有会话模型）
            from app.plugin.module_ai.sessions.model import AiSessionModel

            session = AiSessionModel(
                title=f"嵌入-{ctx.kind}-{ctx.target_id}"[:255],
                user_id=None,
            )
            db.add(session)
            await db.flush()
            if row is None:
                db.add(
                    AiAssetEmbedSessionModel(
                        kind=ctx.kind,
                        target_id=ctx.target_id,
                        sid=sid,
                        session_id=session.id,
                        expires_at=now + timedelta(hours=SESSION_TTL_HOURS),
                        last_active_at=now,
                    )
                )
            else:
                row.session_id = session.id
                row.expires_at = now + timedelta(hours=SESSION_TTL_HOURS)
                row.last_active_at = now
            return session.id, True

    @classmethod
    async def run_stream(
        cls,
        ctx: EmbedContext,
        sid: str,
        session_id: int,
        session_reset: bool,
        message: str,
        redis=None,
    ) -> AsyncIterator[str]:
        """嵌入对话流：首帧 ``data-embed``，随后透传目标（agent/workflow）运行服务的 UI 帧。

        - 上下文来自**服务端会话**（客户端只传 ``sid`` + ``message``）；
        - 匿名垫片 ``SimpleNamespace(user=None)``：既有 run 服务经 ``getattr`` 取 uid，
          ``None`` 已被容忍；
        - 审计在流结束时写入 ``ai_asset_embed_logs``（成功/异常都写；明文 token 不落审计）。
        """
        from app.plugin.module_ai.agent.service import AiAgentService
        from app.plugin.module_ai.sessions.service import AiSessionService
        from app.plugin.module_ai.streaming import UiMessageStream
        from app.plugin.module_ai.workflow.service import AiWorkflowService

        ms = UiMessageStream()
        started = time.perf_counter()
        result_status = "success"
        error_text: str | None = None
        try:
            yield ms.data("embed", {"session_reset": session_reset, "sid": sid})
            history = await AiSessionService.get_messages(session_id)
            ui_messages = [{"role": m["role"], "parts": m["parts"]} for m in history]
            ui_messages.append({"role": "user", "parts": [{"type": "text", "text": message}]})
            auth = SimpleNamespace(user=None)  # 匿名垫片（uid=None）
            if ctx.kind == "agent":
                gen = AiAgentService.run_ui_stream(ctx.target_id, ui_messages, auth, None, session_id)
            else:
                gen = AiWorkflowService.run_ui_stream(
                    ctx.target_id, ui_messages, auth, None, session_id, redis=redis
                )
            async for frame in gen:
                # 流内 error 帧也计入审计状态，避免「用户看到失败、审计却是成功」
                if result_status == "success":
                    stream_err = _extract_stream_error(frame)
                    if stream_err:
                        result_status = "error"
                        error_text = stream_err[:250]
                yield frame
        except Exception as e:  # noqa: BLE001
            result_status = "error"
            error_text = str(e)[:250]
            raise
        finally:
            # 审计 fire-and-forget（独立后台任务 + 独立会话），避免客户端中断挂死请求
            try:
                asyncio.get_running_loop().create_task(
                    cls._write_log(
                        ctx=ctx,
                        sid=sid,
                        session_id=str(session_id),
                        message=message[:80],
                        result_status=result_status,
                        error=error_text,
                        latency_ms=int((time.perf_counter() - started) * 1000),
                    )
                )
            except RuntimeError:
                pass

    @staticmethod
    async def _write_log(
        ctx: EmbedContext,
        sid: str,
        session_id: str,
        message: str,
        result_status: str,
        error: str | None,
        latency_ms: int,
    ) -> None:
        async with async_db_session() as db:
            db.add(
                AiAssetEmbedLogModel(
                    kind=ctx.kind,
                    target_id=ctx.target_id,
                    session_id=session_id,
                    sid=sid,
                    message=message,
                    result_status=result_status,
                    error=error,
                    latency_ms=latency_ms,
                    token_hash12=ctx.token_hash12,
                    token_id=ctx.token_id,
                    client_ip=ctx.client_ip,
                )
            )
            await db.commit()

    @classmethod
    async def check_limits(cls, redis, ctx: EmbedContext, ip: str) -> None:
        """固定窗口限流（token/IP 双键），超限抛 429；``redis`` 为空时跳过（降级）。"""
        if redis is None:
            return

        async def _hit(key: str, cap: int, ttl: int = 60) -> bool:
            count = int(await redis.incr(key))
            if count == 1:
                await redis.expire(key, ttl)
            return count > cap

        if await _hit(
            f"ai:asset:rl:t:{ctx.token_hash12}", settings.EMBED_RATE_TOKEN_PER_MIN
        ) or await _hit(f"ai:asset:rl:ip:{ip or 'na'}", settings.EMBED_RATE_IP_PER_MIN):
            from app.core.exceptions import CustomException

            raise CustomException(msg="访问过于频繁，请稍后再试", code=10429, status_code=429)
