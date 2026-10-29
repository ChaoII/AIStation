"""AI 集成开放平台 —— 资源公开申请（主动公开治理）服务。

普通用户对自己「默认不公开」的私有资源发起公开申请，经管理员审核（内容合规）通过后
写回资源 ``is_public=true`` 生效；公开资源默认 ``public_perm=readonly``（只读）。

- 用户侧：提交公开申请 / 列出我的申请 / 撤销。
- 管理侧：列出全部 / 审核（批准 → 写回资源 is_public，驳回 → 仅记状态）。
- 自动审核开关 ``RESOURCE_PUBLIC_AUTO_AUDIT``：开启时对符合白名单的申请自动通过。
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import func, select

from app.core.database import async_db_session
from app.core.exceptions import CustomException

from .model import AiResourcePublicAuthModel


# --------------------------------------------------------------------------- #
# 资源品类 → 写回 is_public 的回调映射（延迟构造，避免循环导入）
# --------------------------------------------------------------------------- #
# 每个品类提供 `(async def set_public(resource_id, is_public, public_perm) -> dict|None)`
# 仅登记已接入公开治理、且可按 id 定位单个资源的品类。
def _resolvers() -> dict[str, Any]:
    from app.plugin.module_ai.develop.public_resolvers import build_resolvers

    return build_resolvers()


def _auth_to_dict(row: AiResourcePublicAuthModel) -> dict:
    """公开申请单 → 对外 dict。"""
    return {
        "id": row.id,
        "created_time": row.created_time,
        "updated_time": row.updated_time,
        "resource_type": row.resource_type,
        "resource_id": row.resource_id,
        "applicant_id": row.applicant_id,
        "resource_name": row.resource_name or "",
        "apply_status": row.apply_status,
        "public_perm": row.public_perm,
        "auto_audited": row.auto_audited,
        "reason": row.reason or "",
        "reviewed_at": row.reviewed_at,
        "reviewed_by": row.reviewed_by,
        "review_note": row.review_note,
    }


def _validate_resource_type(resource_type: str) -> None:
    """校验资源品类合法。"""
    resolvers = _resolvers()
    if resource_type not in resolvers:
        raise CustomException(
            msg=f"资源品类不支持公开：{resource_type}（支持 {sorted(resolvers)}）",
            code=10400,
            status_code=400,
        )


class PublicApplyService:
    """资源公开申请：用户提交 / 列表 / 撤销 + 管理员审核（含自动审核）。"""

    # ---------------- 用户侧 ----------------
    @classmethod
    async def submit(cls, user, *, resource_type: str, resource_id: int, reason: str | None) -> dict:
        """用户对自己「默认不公开」的私有资源发起公开申请。

        校验：品类合法、资源存在且属于本人（created_id==user.id）、尚未处于 pending。
        """
        _validate_resource_type(resource_type)
        resolvers = _resolvers()
        get_res = resolvers[resource_type]["get"]
        target = await get_res(resource_id)
        if target is None:
            raise CustomException(msg="资源不存在", code=10404, status_code=404)
        if target.get("created_id") != user.id and not getattr(user, "is_superuser", False):
            raise CustomException(
                msg="只能申请公开自己创建的资源", code=10403, status_code=403
            )
        # 已是公开，无需再申请
        if target.get("is_public"):
            raise CustomException(msg="该资源已是公开状态", code=10400, status_code=400)

        async with async_db_session.begin() as db:
            # 同名 pending 去重
            dup = await db.scalar(
                select(AiResourcePublicAuthModel).where(
                    AiResourcePublicAuthModel.resource_type == resource_type,
                    AiResourcePublicAuthModel.resource_id == resource_id,
                    AiResourcePublicAuthModel.apply_status == "pending",
                    AiResourcePublicAuthModel.is_deleted.is_(False),
                )
            )
            if dup:
                raise CustomException(msg="该资源已有待审核的公开申请", code=10400, status_code=400)

            row = AiResourcePublicAuthModel(
                resource_type=resource_type,
                resource_id=resource_id,
                applicant_id=user.id,
                resource_name=(target.get("name") or "")[:128],
                apply_status="pending",
                public_perm="readonly",
                reason=(reason or "")[:255] or None,
                created_id=user.id,
                updated_id=user.id,
            )
            db.add(row)
            await db.flush()
            await db.refresh(row)
            return _auth_to_dict(row)

    @classmethod
    async def list_mine(cls, user, *, apply_status: str | None = None, page: int = 1, page_size: int = 20) -> dict:
        """列出当前用户自己的公开申请单。"""
        page = max(int(page or 1), 1)
        page_size = max(1, min(int(page_size or 20), 100))
        async with async_db_session() as db:
            wheres = [
                AiResourcePublicAuthModel.applicant_id == user.id,
                AiResourcePublicAuthModel.is_deleted.is_(False),
            ]
            if apply_status:
                wheres.append(AiResourcePublicAuthModel.apply_status == apply_status)
            base = select(AiResourcePublicAuthModel).where(*wheres)
            total = (await db.execute(select(func.count()).select_from(base.subquery()))).scalar() or 0
            rows = (
                await db.execute(
                    base.order_by(AiResourcePublicAuthModel.id.desc())
                    .offset((page - 1) * page_size)
                    .limit(page_size)
                )
            ).scalars().all()
            return {
                "page_no": page,
                "page_size": page_size,
                "total": total,
                "has_next": page * page_size < total,
                "items": [_auth_to_dict(r) for r in rows],
            }

    @classmethod
    async def cancel(cls, user, auth_id: int) -> None:
        """撤销自己的待审核公开申请（仅 pending 可撤）。"""
        async with async_db_session.begin() as db:
            row = await db.get(AiResourcePublicAuthModel, auth_id)
            if row is None or row.is_deleted or row.applicant_id != user.id:
                raise CustomException(msg="申请单不存在", code=10404, status_code=404)
            if row.apply_status != "pending":
                raise CustomException(msg="该申请已处理，无法撤销", code=10400, status_code=400)
            row.apply_status = "rejected"
            row.reviewed_at = datetime.now()
            row.review_note = "申请人主动撤销"
            row.updated_id = user.id
            await db.flush()

    # ---------------- 管理侧 ----------------
    @classmethod
    async def list_all(
        cls,
        *,
        apply_status: str | None = None,
        resource_type: str | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> dict:
        """管理员分页列出全部公开申请（可按状态/品类过滤）。"""
        page = max(int(page or 1), 1)
        page_size = max(1, min(int(page_size or 20), 100))
        wheres = [AiResourcePublicAuthModel.is_deleted.is_(False)]
        if apply_status:
            wheres.append(AiResourcePublicAuthModel.apply_status == apply_status)
        if resource_type:
            wheres.append(AiResourcePublicAuthModel.resource_type == resource_type)
        async with async_db_session() as db:
            base = select(AiResourcePublicAuthModel).where(*wheres)
            total = (await db.execute(select(func.count()).select_from(base.subquery()))).scalar() or 0
            rows = (
                await db.execute(
                    base.order_by(AiResourcePublicAuthModel.id.desc())
                    .offset((page - 1) * page_size)
                    .limit(page_size)
                )
            ).scalars().all()
            return {
                "page_no": page,
                "page_size": page_size,
                "total": total,
                "has_next": page * page_size < total,
                "items": [_auth_to_dict(r) for r in rows],
            }

    @classmethod
    async def review(cls, auth_id: int, *, approve: bool, reviewer_id: int | None, note: str | None) -> dict:
        """管理员（或自动审核）审核公开申请。

        批准：写回资源 ``is_public=true``（按 ``public_perm``），申请置 approved；
        驳回：仅记状态与意见。
        """
        from app.config.setting import settings

        auto = bool(getattr(settings, "RESOURCE_PUBLIC_AUTO_AUDIT", False))
        async with async_db_session.begin() as db:
            row = await db.get(AiResourcePublicAuthModel, auth_id)
            if row is None or row.is_deleted:
                raise CustomException(msg="申请单不存在", code=10404, status_code=404)
            if row.apply_status != "pending":
                raise CustomException(msg="该申请已处理", code=10400, status_code=400)
            if not approve:
                row.apply_status = "rejected"
                row.reviewed_at = datetime.now()
                row.reviewed_by = reviewer_id
                row.review_note = (note or "管理员驳回")[:255]
                row.updated_id = reviewer_id
                await db.flush()
                return _auth_to_dict(row)

            # 批准：写回资源 is_public（在**同一事务**内，避免嵌套事务冲突）
            resolvers = _resolvers()
            set_public = resolvers[row.resource_type]["set_public"]
            await set_public(row.resource_id, True, row.public_perm, db=db)
            row.apply_status = "approved"
            row.reviewed_at = datetime.now()
            row.reviewed_by = reviewer_id
            row.auto_audited = bool(auto)
            row.review_note = (note or ("已自动审核通过" if auto else "已批准"))[:255]
            row.updated_id = reviewer_id
            await db.flush()
            await db.refresh(row)
            return _auth_to_dict(row)
