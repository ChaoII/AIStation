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

from datetime import datetime
from typing import Any

from sqlalchemy import func, select

from app.core.database import async_db_session
from app.core.exceptions import CustomException

from .auth import AppContext
from .model import AiIntegrationApprovalModel, AiIntegrationAppModel
from .registry import Capability
from .service import _app_to_dict


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
