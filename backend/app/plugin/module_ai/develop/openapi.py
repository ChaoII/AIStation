"""AI 集成开放平台 —— 开放面能力调用管道（REST 与 MCP 共用）。

管道（对齐 spec §6.3 六步鉴权管道的 3~6 步；第 1、2 步由
``get_app_api_auth`` / MCP 鉴权包装层完成）：

1. 查能力注册表（未注册 → 404）；
2. 权限点校验（缺失 → 403 + ``denied`` 审计）；
3. 限流（appid/IP 双键固定窗口）与按品类日配额（超限 → 429）；
4. 执行 handler（复用既有 service）；
5. 审计（成功/拒绝/异常都写 ``ai_integration_call_logs``，``method`` 取
   ``REST`` / ``MCP``，**绝不写入 appkey / access_token 明文**）。

审计写入使用**独立会话**（不占用调用方事务），并保证异常不吞掉业务结果。
"""
from __future__ import annotations

import time
from datetime import datetime
from typing import Any

from app.core.database import async_db_session
from app.core.exceptions import CustomException

from .auth import AppContext, require_app_perm
from .model import AiIntegrationAppModel
from .registry import Capability, get_capability
from .service import DevelopService

#: 审计请求体里需要剔除的键（凭证类，任何出口都不落库）。
_SENSITIVE_KEYS = {"appkey", "app_key", "token", "access_token", "authorization", "secret"}
#: 审计请求体/摘要的截断长度。
_BODY_TEXT_LIMIT = 200
_SUMMARY_LIMIT = 200


def _sanitize_body(payload: Any) -> dict:
    """把请求体转成可落库的 dict：剔除凭证键、超长文本截断、只保留浅层结构。"""
    if not isinstance(payload, dict):
        return {}
    out: dict = {}
    for key, value in payload.items():
        if str(key).lower() in _SENSITIVE_KEYS:
            out[key] = "***"
            continue
        if isinstance(value, str):
            out[key] = value[:_BODY_TEXT_LIMIT]
        elif isinstance(value, (int, float, bool)) or value is None:
            out[key] = value
        elif isinstance(value, (list, tuple)):
            out[key] = f"[{len(value)} items]"
        elif isinstance(value, dict):
            out[key] = "{...}"
        else:
            out[key] = str(value)[:80]
    return out


def _summarize(result: Any) -> str | None:
    """把 handler 结果压成一行摘要（列表记条数，dict 记键，其余取字符串）。"""
    if result is None:
        return None
    if isinstance(result, dict):
        if "items" in result and isinstance(result["items"], list):
            return f"items={len(result['items'])}"
        if "id" in result:
            return f"id={result['id']}"
        return ",".join(list(result.keys())[:6])[: _SUMMARY_LIMIT]
    if isinstance(result, (list, tuple)):
        return f"items={len(result)}"
    return str(result)[:_SUMMARY_LIMIT]


async def audit_call(
    ctx: AppContext,
    *,
    category: str,
    capability: str,
    method: str,
    status: str,
    error: str | None = None,
    latency_ms: int = 0,
    result_summary: str | None = None,
    request_body: dict | None = None,
    request_path: str | None = None,
    session_id: str | None = None,
    transport: str | None = None,
    client_info: str | None = None,
) -> None:
    """写一条开放面调用审计（按 ``ctx.app_id`` 重新取 ORM 行）。

    审计失败只记日志、不抛出——调用方已拿到业务结果时不能被审计拖垮。
    """
    try:
        async with async_db_session() as db:
            row = await db.get(AiIntegrationAppModel, ctx.app_id)
        if row is None:
            return
        await DevelopService.log_call(
            row,
            category=category,
            capability=capability,
            method=method,
            status=status,
            error=(error or "")[:255] or None,
            latency_ms=latency_ms,
            result_summary=result_summary,
            request_body=request_body,
            request_path=request_path,
            session_id=session_id,
            transport=transport,
            client_info=client_info,
        )
    except Exception:  # noqa: BLE001 - 审计失败不得影响业务
        pass


async def check_open_limits(
    redis, ctx: AppContext, *, category: str, ip: str = ""
) -> None:
    """开放面限流 + 按品类日配额；超限抛 429。

    - 限流：固定窗口 60s，键 ``ai:open:rl:app:{appid}`` / ``ai:open:rl:ip:{ip}``
      （``settings.OPEN_API_RATE_APP_PER_MIN`` / ``OPEN_API_RATE_IP_PER_MIN``）；
    - 配额：``app.quota[category]`` 为自然日次数上限（缺省/0 = 不限），
      键 ``ai:open:quota:{app_id}:{category}:{YYYYMMDD}``；
    - ``redis`` 为空（未配置/不可用）时整体跳过，降级为不限流。
    """
    if redis is None:
        return
    from app.config.setting import settings

    async def _hit(key: str, cap: int) -> bool:
        count = int(await redis.incr(key))
        if count == 1:
            await redis.expire(key, 60)
        return count > cap

    if await _hit(
        f"ai:open:rl:app:{ctx.appid}", settings.OPEN_API_RATE_APP_PER_MIN
    ) or await _hit(f"ai:open:rl:ip:{ip or 'na'}", settings.OPEN_API_RATE_IP_PER_MIN):
        raise CustomException(msg="访问过于频繁，请稍后再试", code=10429, status_code=429)

    quota = (ctx.quota or {}).get(category)
    if isinstance(quota, int) and quota > 0:
        day = datetime.now().strftime("%Y%m%d")
        key = f"ai:open:quota:{ctx.app_id}:{category}:{day}"
        count = int(await redis.incr(key))
        if count == 1:
            await redis.expire(key, 86400)
        if count > quota:
            raise CustomException(msg="今日调用配额已用完", code=10429, status_code=429)


async def invoke_capability(
    ctx: AppContext,
    code: str,
    payload: dict | None = None,
    *,
    method: str = "REST",
    redis=None,
    request_path: str | None = None,
    transport: str | None = None,
    client_info: str | None = None,
    ip: str = "",
    session_id: str | None = None,
) -> Any:
    """执行一次开放面能力调用（REST / MCP 共用入口）。

    Args:
        ctx: 已鉴权应用上下文（凭证与 app 状态已校验）。
        code: 能力码（``"agent.list"``）。
        payload: 能力入参（JSON 对象）。
        method: 出口标识，``"REST"`` 或 ``"MCP"``（写入审计）。
        redis: 限流/配额用的 Redis 客户端；``None`` 时跳过限流。
        request_path / transport / client_info / ip / session_id: 审计与限流上下文。

    Returns:
        handler 的返回值（JSON 可序列化）。

    Raises:
        CustomException: 404（能力不存在）、403（无权限）、429（限流/配额）、
            503（能力暂不可用）或 handler 自身抛出的业务错误。
    """
    cap: Capability | None = get_capability(code)
    if cap is None:
        raise CustomException(msg="能力不存在", code=10404, status_code=404)

    body = _sanitize_body(payload)
    started = time.perf_counter()

    try:
        require_app_perm(ctx, cap.perm)
    except CustomException as e:
        await audit_call(
            ctx,
            category=cap.category,
            capability=cap.code,
            method=method,
            status="denied",
            error=e.msg,
            request_body=body,
            request_path=request_path,
            transport=transport,
            client_info=client_info,
            session_id=session_id,
        )
        raise

    try:
        await check_open_limits(redis, ctx, category=cap.category, ip=ip)
    except CustomException as e:
        await audit_call(
            ctx,
            category=cap.category,
            capability=cap.code,
            method=method,
            status="denied",
            error=e.msg,
            request_body=body,
            request_path=request_path,
            transport=transport,
            client_info=client_info,
            session_id=session_id,
        )
        raise

    if cap.handler is None:
        raise CustomException(msg="能力暂不可用", code=10405, status_code=503)

    try:
        result = await cap.handler(app_ctx=ctx, payload=payload or {})
    except CustomException as e:
        await audit_call(
            ctx,
            category=cap.category,
            capability=cap.code,
            method=method,
            status="denied" if e.status_code in (401, 403, 404) else "failed",
            error=e.msg,
            latency_ms=int((time.perf_counter() - started) * 1000),
            request_body=body,
            request_path=request_path,
            transport=transport,
            client_info=client_info,
            session_id=session_id,
        )
        raise
    except ValueError as e:
        # 既有 service 的业务校验用 ValueError（如「仅 pending 任务可编辑」）：
        # 归为 400 参数/状态错误，不要把用户的输入问题报成服务端故障。
        await audit_call(
            ctx,
            category=cap.category,
            capability=cap.code,
            method=method,
            status="failed",
            error=str(e),
            latency_ms=int((time.perf_counter() - started) * 1000),
            request_body=body,
            request_path=request_path,
            transport=transport,
            client_info=client_info,
            session_id=session_id,
        )
        raise CustomException(msg=str(e), code=10400, status_code=400) from e
    except Exception as e:  # noqa: BLE001 - 统一转成审计 + 500
        await audit_call(
            ctx,
            category=cap.category,
            capability=cap.code,
            method=method,
            status="failed",
            error=str(e),
            latency_ms=int((time.perf_counter() - started) * 1000),
            request_body=body,
            request_path=request_path,
            transport=transport,
            client_info=client_info,
            session_id=session_id,
        )
        raise CustomException(msg=f"能力执行失败：{e}", code=10500, status_code=500) from e

    await audit_call(
        ctx,
        category=cap.category,
        capability=cap.code,
        method=method,
        status="success",
        latency_ms=int((time.perf_counter() - started) * 1000),
        result_summary=_summarize(result),
        request_body=body,
        request_path=request_path,
        transport=transport,
        client_info=client_info,
        session_id=session_id,
    )
    return result
