"""AI 集成开放平台 —— 调用审批（敏感能力的「先审批后执行」）。

触发条件（两者同时满足）：

1. 应用 ``requires_approval = true``；
2. 能力被注册表标记 ``requires_approval = true``（当前为 ``agent.delete``、
   ``train.create`` / ``train.start`` / ``train.stop``）。

流程：调用方发起 → 落一行 ``pending`` 审批（**不执行**）→ 管理端批准时以原应用身份
执行并把结果写回审批行；拒绝则只记状态与意见。无论批准/拒绝都写审计（``method`` 沿用
调用方出口，``capability`` 记录能力码，``status`` 为 ``pending`` / ``approved`` / ``rejected``）。
"""
from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any

from sqlalchemy import func, select

from app.core.database import async_db_session
from app.core.exceptions import CustomException

from .auth import AppContext
from .model import AiIntegrationAppModel, AiIntegrationApprovalModel
from .registry import Capability
from .service import _app_to_dict

log = logging.getLogger(__name__)


def _approval_to_dict(row: AiIntegrationApprovalModel) -> dict:
    """审批行 → 对外 dict（管理端表格与详情用）。"""
    return {
        "id": row.id,
        "created_time": row.created_time,
        "app_id": row.app_id,
        "appid": row.appid,
        "capability": row.capability,
        "category": row.category,
        "payload": row.payload or {},
        "status": row.status,
        "reviewed_at": row.reviewed_at,
        "reviewed_by": row.reviewed_by,
        "review_note": row.review_note,
        "result": row.result,
        "error": row.error,
    }


class ApprovalService:
    """调用审批的存取与审阅（执行由 ``openapi.invoke_capability`` 完成）。"""

    @classmethod
    async def create(
        cls, ctx: AppContext, cap: Capability, payload: dict
    ) -> AiIntegrationApprovalModel:
        """落一行待审批记录（payload 已由管道脱敏）。"""
        async with async_db_session.begin() as db:
            row = AiIntegrationApprovalModel(
                app_id=ctx.app_id,
                appid=ctx.appid,
                capability=cap.code,
                category=cap.category,
                payload=payload,
                status="pending",
            )
            db.add(row)
            await db.flush()
            await db.refresh(row)
        # 站内 + 外部通道通知管理员（best-effort：失败只记日志，不阻断调用方拿到 approval_id）
        await _notify_admins(row)
        await _notify_external(row)
        return row

    @classmethod
    async def list(
        cls,
        *,
        status: str | None = None,
        app_id: int | None = None,
        page_no: int = 1,
        page_size: int = 20,
    ) -> dict:
        """分页查询审批（可按状态/应用过滤）。"""
        page_no = max(int(page_no or 1), 1)
        page_size = max(1, min(int(page_size or 20), 100))
        wheres = []
        if status:
            wheres.append(AiIntegrationApprovalModel.status == status)
        if app_id is not None:
            wheres.append(AiIntegrationApprovalModel.app_id == app_id)
        async with async_db_session() as db:
            stmt = select(AiIntegrationApprovalModel)
            if wheres:
                stmt = stmt.where(*wheres)
            total = (
                await db.execute(select(func.count()).select_from(stmt.subquery()))
            ).scalar() or 0
            rows = (
                await db.execute(
                    stmt.order_by(AiIntegrationApprovalModel.id.desc())
                    .limit(page_size)
                    .offset((page_no - 1) * page_size)
                )
            ).scalars().all()
        return {
            "page_no": page_no,
            "page_size": page_size,
            "total": total,
            "has_next": page_no * page_size < total,
            "items": [_approval_to_dict(r) for r in rows],
        }

    @classmethod
    async def get(cls, approval_id: int) -> AiIntegrationApprovalModel | None:
        async with async_db_session() as db:
            return await db.get(AiIntegrationApprovalModel, approval_id)

    @classmethod
    async def mark_rejected(
        cls, approval_id: int, *, reviewer_id: int | None, note: str | None
    ) -> dict:
        """拒绝：只记状态与意见，不执行。"""
        async with async_db_session.begin() as db:
            row = await db.get(AiIntegrationApprovalModel, approval_id)
            if row is None:
                raise CustomException(msg="审批记录不存在", code=10404, status_code=404)
            if row.status != "pending":
                raise CustomException(msg="该审批已处理", code=10400, status_code=400)
            row.status = "rejected"
            row.reviewed_at = datetime.now()
            row.reviewed_by = reviewer_id
            row.review_note = (note or "")[:255] or None
            await db.flush()
            return _approval_to_dict(row)

    @classmethod
    async def mark_executed(
        cls,
        approval_id: int,
        *,
        reviewer_id: int | None,
        note: str | None,
        result: Any = None,
        error: str | None = None,
    ) -> dict:
        """批准后回写执行结果（成功 ``approved`` / 失败 ``failed``）。"""
        async with async_db_session.begin() as db:
            row = await db.get(AiIntegrationApprovalModel, approval_id)
            if row is None:
                raise CustomException(msg="审批记录不存在", code=10404, status_code=404)
            if row.status != "pending":
                raise CustomException(msg="该审批已处理", code=10400, status_code=400)
            row.status = "failed" if error else "approved"
            row.reviewed_at = datetime.now()
            row.reviewed_by = reviewer_id
            row.review_note = (note or "")[:255] or None
            row.error = (error or "")[:255] or None
            if result is not None and isinstance(result, (dict, list)):
                row.result = result
            elif result is not None:
                row.result = {"value": str(result)[:500]}
            await db.flush()
            return _approval_to_dict(row)

    @classmethod
    async def app_context(cls, app_id: int) -> AppContext:
        """按应用 ID 重建调用上下文（批准后以原应用身份执行）。"""
        async with async_db_session() as db:
            row = await db.get(AiIntegrationAppModel, app_id)
        if row is None or row.is_deleted:
            raise CustomException(msg="应用不存在", code=10404, status_code=404)
        if not row.enabled:
            raise CustomException(msg="应用已停用", code=10400, status_code=400)
        return AppContext(
            app_id=row.id,
            appid=row.appid,
            perms=set(row.capabilities or []),
            quota=row.quota,
            app=_app_to_dict(row),
        )


async def _notify_admins(row: AiIntegrationApprovalModel) -> None:
    """有待审批时给**超级管理员（role_id=1）**发站内通知（best-effort，绝不阻断调用）。"""
    try:
        from sqlalchemy import select

        from app.api.v1.module_system.notification.service import NotificationService
        from app.api.v1.module_system.user.model import UserRolesModel

        async with async_db_session() as db:
            user_ids = (
                await db.execute(
                    select(UserRolesModel.user_id).where(UserRolesModel.role_id == 1).distinct()
                )
            ).scalars().all()
        for uid in user_ids:
            await NotificationService.create_notification(
                int(uid),
                title=f"AI 集成调用待审批：{row.capability}",
                content=(
                    f"应用 {row.appid} 申请调用敏感能力 {row.capability}，请到「AI 集成 → 调用审批」"
                    f"处理（批准后立即执行）。"
                ),
                type="system",
                module="ai",
                module_id=row.id,
            )
    except Exception as e:  # noqa: BLE001 - 通知失败不影响主流程
        log.warning(f"[approvals] 站内通知发送失败（忽略）: {e}")


#: 审批通知允许的**外部通道**（复用告警模块 app/utils/notification.py 的
#: ``_send_{channel}``；``ws_push`` 是告警大屏广播，不在此列以免污染大屏）。
_EXTERNAL_CHANNELS = ("email", "webhook", "sms")


def _build_approval_alarm(row: AiIntegrationApprovalModel) -> tuple[dict, dict]:
    """把审批行适配成既有告警通知函数认识的 ``(alarm, rule)`` 结构。

    复用而非重写：邮件正文/签名/重试等全部沿用告警模块的实现，
    这里只做字段映射（``alarm_type`` = 待审批标题，``description`` = 说明）。
    """
    now = datetime.now()
    alarm = {
        "alarm_type": f"调用待审批：{row.capability}",
        "severity": "WARNING",
        "description": (
            f"应用 {row.appid}（ID {row.app_id}）申请调用敏感能力 {row.capability}"
            f"（品类 {row.category}），请到「AI 集成 → 调用审批」批准或拒绝；"
            f"批准后立即以该应用身份执行。"
        ),
        "alarm_time": str(now),
        "camera_name": "AIStation 开放平台",
        "camera_id": "",
        "rule_id": row.id,
        "rule_name": "AI 集成调用审批",
        "snapshot_path": "",
    }
    rule = {"id": 0, "name": "AI 集成调用审批", "notify_channels": []}
    return alarm, rule


async def _notify_external(row: AiIntegrationApprovalModel) -> None:
    """审批的外部通道通知（best-effort）。

    - 开关：``settings.APPROVAL_NOTIFY_CHANNELS``（逗号分隔，如 ``email,webhook``；空=关闭）；
    - 每通道 JSON 配置读系统参数 ``ai_approval_notify_{channel}``（管理员在参数管理页配），
      基础凭证沿用告警模块的 ``notify_smtp_*`` / ``notify_webhook_*`` 参数；
    - 单通道失败只记 warning，不影响站内通知与主流程。
    """
    from app.config.setting import settings
    from app.utils.notification import _send_email, _send_sms, _send_webhook, load_params

    channels = [
        c.strip().lower()
        for c in (settings.APPROVAL_NOTIFY_CHANNELS or "").split(",")
        if c.strip().lower() in _EXTERNAL_CHANNELS
    ]
    if not channels:
        return
    senders = {"email": _send_email, "webhook": _send_webhook, "sms": _send_sms}
    cfg_keys = [f"ai_approval_notify_{c}" for c in channels]
    async with async_db_session() as db:
        try:
            cfgs = await load_params(db, *cfg_keys)
        except Exception as e:  # noqa: BLE001
            log.warning(f"[approvals] 读取通知通道参数失败（忽略）: {e}")
            return
        alarm, rule = _build_approval_alarm(row)
        for channel in channels:
            key = f"ai_approval_notify_{channel}"
            raw = cfgs.get(key)
            try:
                cfg = json.loads(raw) if isinstance(raw, str) and raw.strip() else {}
            except ValueError:
                log.warning(
                    f"[approvals] 通道参数 {key} 不是合法 JSON，跳过该通道"
                )
                continue
            try:
                await senders[channel](db, alarm, rule, cfg)
            except Exception as e:  # noqa: BLE001 - 通道失败不影响主流程
                log.warning(
                    f"[approvals] 外部通道 {channel} 通知失败（忽略）: {e}"
                )


async def expire_stale_approvals(hours: int | None = None) -> int:
    """关闭超时的待审批（定时任务入口，模块级无参可直接被 APScheduler 调度）。

    超过 ``APPROVAL_PENDING_TTL_HOURS``（默认 24h）仍为 ``pending`` 的审批置为
    ``expired``，并给所属应用补一条审计（``status=expired``），避免申请方无限等待。

    Returns:
        本次关闭的审批条数。
    """
    from datetime import timedelta as _timedelta

    from sqlalchemy import select as _select

    from app.config.setting import settings

    from .openapi import audit_call

    ttl = hours if hours is not None else settings.APPROVAL_PENDING_TTL_HOURS
    cutoff = datetime.now() - _timedelta(hours=max(1, int(ttl)))
    expired_ids: list[int] = []
    async with async_db_session.begin() as db:
        rows = (
            await db.execute(
                _select(AiIntegrationApprovalModel).where(
                    AiIntegrationApprovalModel.status == "pending",
                    AiIntegrationApprovalModel.created_time <= cutoff,
                )
            )
        ).scalars().all()
        for row in rows:
            row.status = "expired"
            row.reviewed_at = datetime.now()
            row.review_note = f"审批超过 {ttl} 小时未处理，系统自动关闭"
            expired_ids.append(row.id)
    if not expired_ids:
        return 0
    # 事务已提交，按 id 重新取审计所需的字段（不要访问已过期的行属性）
    async with async_db_session() as db:
        fresh = (
            await db.execute(
                _select(AiIntegrationApprovalModel).where(
                    AiIntegrationApprovalModel.id.in_(expired_ids)
                )
            )
        ).scalars().all()
        audit_rows = [(r.id, r.app_id, r.category, r.capability) for r in fresh]
    for approval_id, app_id, category, capability in audit_rows:
        try:
            ctx = await ApprovalService.app_context(app_id)
            await audit_call(
                ctx,
                category=category,
                capability=capability,
                method="REST",
                status="expired",
                error="审批超时自动关闭",
                request_path=f"/approvals/{approval_id}",
            )
        except Exception:  # noqa: BLE001
            continue
    return len(expired_ids)
