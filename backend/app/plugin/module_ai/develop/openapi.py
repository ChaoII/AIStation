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

from .auth import AppContext, require_capability
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
            out[key] = value[:_body_limit()]
        elif isinstance(value, (int, float, bool)) or value is None:
            out[key] = value
        elif isinstance(value, (list, tuple)):
            out[key] = f"[{len(value)} items]"
        elif isinstance(value, dict):
            out[key] = "{...}"
        else:
            out[key] = str(value)[:80]
    return out


def _body_limit() -> int:
    """审计请求体的单字段截断上限（``OPEN_AUDIT_BODY_LIMIT``，夹紧 100..2000）。"""
    from app.config.setting import settings

    return max(100, min(int(getattr(settings, "OPEN_AUDIT_BODY_LIMIT", 200) or 200), 2000))


def _strip_secrets(payload: Any) -> dict:
    """只剔除凭证键、**保留完整参数**（审批后要按原参数执行，不能截断）。"""
    if not isinstance(payload, dict):
        return {}
    return {
        key: ("***" if str(key).lower() in _SENSITIVE_KEYS else value)
        for key, value in payload.items()
    }


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


def _app_requires_approval(ctx: AppContext) -> bool:
    """应用是否开启「调用需人工审批」（``app`` 为对外 dict，取不到按未开启处理）。"""
    return bool((ctx.app or {}).get("requires_approval"))


def _validate_payload(cap: Capability, payload: dict) -> None:
    """审批入队前先按能力的 JSON Schema 校验入参。

    审批门禁发生在 handler 之前，若不先校验，**参数非法的请求也会被排进审批队列**，
    管理员批准时才失败——既浪费人工，也让审批列表变成垃圾场。这里做一次
    轻量 JSON Schema 校验（失败即 400）；schema 缺失或校验器异常时放行。
    """
    schema = cap.input_schema or {}
    if not schema.get("properties") and not schema.get("required"):
        return
    try:
        from jsonschema import ValidationError, validate
    except Exception:  # noqa: BLE001 - 未安装校验库则跳过（不阻断）
        return
    try:
        validate(instance=payload, schema=schema)
    except ValidationError as exc:
        field = ".".join(str(p) for p in exc.absolute_path) or "(root)"
        raise CustomException(
            msg=f"参数不合法：{field} {exc.message}", code=10400, status_code=400
        ) from exc


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
    bypass_approval: bool = False,
) -> Any:
    """执行一次开放面能力调用（REST / MCP 共用入口）。

    Args:
        ctx: 已鉴权应用上下文（凭证与 app 状态已校验）。
        code: 能力码（``"agent.list"``）。
        payload: 能力入参（JSON 对象）。
        method: 出口标识，``"REST"`` 或 ``"MCP"``（写入审计，并决定按哪条出口校验授权）。
        redis: 限流/配额用的 Redis 客户端；``None`` 时跳过限流。
        request_path / transport / client_info / ip / session_id: 审计与限流上下文。
        bypass_approval: 审批通过后由审批模块以原应用身份执行时置 ``True``，
            跳过审批门禁（避免二次入队）。

    Returns:
        handler 的返回值（JSON 可序列化）；若命中审批门禁，返回
        ``{"status": "pending_approval", "approval_id": ...}``。

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
        require_capability(ctx, cap.code, "mcp" if method == "MCP" else "rest")
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

    # 敏感能力 + 应用开启审批：落待审批行，**本次不执行**（管理员批准后由
    # approvals 模块以原应用身份执行；批准执行时 bypass_approval=True）。
    if cap.requires_approval and not bypass_approval and _app_requires_approval(ctx):
        from .approvals import ApprovalService

        # 先校验入参，避免把非法请求排进审批队列
        _validate_payload(cap, payload or {})
        # 审批行保存**完整入参**（仅剔除凭证键）：批准后要按原参数执行，
        # 不能用审计用的截断体，否则长文本参数会被截断导致执行语义变化。
        row = await ApprovalService.create(ctx, cap, _strip_secrets(payload))
        await audit_call(
            ctx,
            category=cap.category,
            capability=cap.code,
            method=method,
            status="pending",
            error="待管理员审批",
            request_body=body,
            request_path=request_path,
            transport=transport,
            client_info=client_info,
            session_id=session_id,
        )
        return {
            "status": "pending_approval",
            "approval_id": row.id,
            "capability": cap.code,
            "message": "该操作需管理员审批，已进入待审批队列；批准后自动执行",
        }

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
