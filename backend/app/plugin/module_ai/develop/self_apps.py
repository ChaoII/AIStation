"""AI 集成开放平台 —— 用户自助申请应用服务（模式 B）。

- 用户登录后自助申请 appid/appkey（先落待审核，管理员批准才生成应用并发放）。
- **能力上限校验**：申请/修改时逐条校验能力码对应平台权限串是否在申请者角色权限内
  （防越权提权）。
- 批准时以申请者身份生成 ``AiIntegrationAppModel``，绑定 ``owner_user_id``、
  ``source_type="self"``；数据按该用户过滤（与管理员分配 A 的 ``owner=null`` 区分）。
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import select

from app.core.database import async_db_session
from app.core.exceptions import CustomException

from .model import AiIntegrationAppApplyModel, AiIntegrationAppModel
from .perms import user_has_capability
from .registry import is_valid_capability_code
from .service import _generate_appid, _generate_appkey, _hash_appkey


def _apply_to_dict(row: AiIntegrationAppApplyModel) -> dict:
    """申请单 → 对外 dict（管理端表格/用户中心展示）。"""
    return {
        "id": row.id,
        "created_time": row.created_time,
        "updated_time": row.updated_time,
        "applicant_id": row.applicant_id,
        "name": row.name,
        "description": row.description or "",
        "capabilities": sorted(row.capabilities or []),
        "channels": row.channels or {},
        "reason": row.reason or "",
        "apply_status": row.apply_status,
        "reviewed_at": row.reviewed_at,
        "reviewed_by": row.reviewed_by,
        "review_note": row.review_note,
        "app_id": row.app_id,
    }


def _validate_capability_scope(user, caps: list[str]) -> list[str]:
    """校验申请能力码不超出用户角色权限；返回去重合法能力码列表。

    Raises:
        CustomException: 含非法能力码，或含用户无权限的能力码（400）。
    """
    if not caps:
        return []
    seen: set[str] = set()
    for code in caps:
        if not isinstance(code, str) or not code.strip():
            continue
        code = code.strip()
        if not is_valid_capability_code(code):
            raise CustomException(
                msg=f"能力码不合法：{code}", code=10400, status_code=400
            )
        if not user_has_capability(user, code):
            raise CustomException(
                msg=f"你无权限申请能力 {code}（需对应平台权限，无法为应用授权更高权限）",
                code=10400,
                status_code=400,
            )
        seen.add(code)
    return sorted(seen)


class SelfApplyService:
    """用户自助申请应用（模式 B）：申请 / 查询 / 修改 / 撤销 + 管理员审核。"""

    # ---------------- 用户侧 ----------------
    @classmethod
    async def submit(cls, user, data) -> dict:
        """提交自助申请（写 pending 申请单，不立即生成应用）。

        Raises:
            CustomException: 名称重复、能力越权。
        """
        caps = _validate_capability_scope(user, data.capabilities or [])
        if not caps and not data.capabilities:
            # 允许申请最小能力集（可为空，但需提示）；为空则通过
            pass
        async with async_db_session.begin() as db:
            # 名称查重（含已存在应用与已申请单）
            dup_app = await db.scalar(
                select(AiIntegrationAppModel).where(
                    AiIntegrationAppModel.name == data.name,
                    AiIntegrationAppModel.is_deleted.is_(False),
                )
            )
            if dup_app:
                raise CustomException(msg=f"应用名称已存在：{data.name}")
            dup_apply = await db.scalar(
                select(AiIntegrationAppApplyModel).where(
                    AiIntegrationAppApplyModel.name == data.name,
                    AiIntegrationAppApplyModel.apply_status == "pending",
                    AiIntegrationAppApplyModel.is_deleted.is_(False),
                )
            )
            if dup_apply:
                raise CustomException(msg=f"已有同名申请单待审核：{data.name}")
            row = AiIntegrationAppApplyModel(
                applicant_id=user.id,
                name=data.name,
                description=data.description,
                capabilities=caps,
                channels=data.channels,
                reason=getattr(data, "reason", None),
                apply_status="pending",
                created_id=user.id,
                updated_id=user.id,
            )
            db.add(row)
            await db.flush()
            await db.refresh(row)
            return _apply_to_dict(row)

    @classmethod
    async def list_mine(cls, user, *, page: int = 1, page_size: int = 20) -> dict:
        """列出当前用户自己的申请单。"""
        page = max(int(page or 1), 1)
        page_size = max(1, min(int(page_size or 20), 100))
        from sqlalchemy import func

        async with async_db_session() as db:
            base = select(AiIntegrationAppApplyModel).where(
                AiIntegrationAppApplyModel.applicant_id == user.id,
                AiIntegrationAppApplyModel.is_deleted.is_(False),
            )
            total = (
                await db.execute(select(func.count()).select_from(base.subquery()))
            ).scalar() or 0
            rows = (
                await db.execute(
                    base.order_by(AiIntegrationAppApplyModel.id.desc())
                    .offset((page - 1) * page_size)
                    .limit(page_size)
                )
            ).scalars().all()
            return {
                "page_no": page,
                "page_size": page_size,
                "total": total,
                "has_next": page * page_size < total,
                "items": [_apply_to_dict(r) for r in rows],
            }

    @classmethod
    async def update(cls, user, apply_id: int, data) -> dict:
        """修改自己的待审核申请单（仅 pending 可改；重校验能力上限）。"""
        async with async_db_session.begin() as db:
            row = await db.get(AiIntegrationAppApplyModel, apply_id)
            if row is None or row.is_deleted or row.applicant_id != user.id:
                raise CustomException(msg="申请单不存在", code=10404, status_code=404)
            if row.apply_status != "pending":
                raise CustomException(msg="该申请已处理，无法修改", code=10400, status_code=400)
            if data.name is not None and data.name and data.name != row.name:
                dup = await db.scalar(
                    select(AiIntegrationAppApplyModel).where(
                        AiIntegrationAppApplyModel.name == data.name,
                        AiIntegrationAppApplyModel.apply_status == "pending",
                        AiIntegrationAppApplyModel.is_deleted.is_(False),
                        AiIntegrationAppApplyModel.id != apply_id,
                    )
                )
                if dup:
                    raise CustomException(msg=f"已有同名申请单待审核：{data.name}")
                row.name = data.name
            if data.description is not None:
                row.description = data.description
            if data.capabilities is not None:
                row.capabilities = _validate_capability_scope(user, data.capabilities)
            if data.reason is not None:
                row.reason = data.reason
            row.updated_id = user.id
            await db.flush()
            await db.refresh(row)
            return _apply_to_dict(row)

    @classmethod
    async def cancel(cls, user, apply_id: int) -> None:
        """撤销自己的待审核申请单（仅 pending 可撤，置 rejected 并备注）。"""
        async with async_db_session.begin() as db:
            row = await db.get(AiIntegrationAppApplyModel, apply_id)
            if row is None or row.is_deleted or row.applicant_id != user.id:
                raise CustomException(msg="申请单不存在", code=10404, status_code=404)
            if row.apply_status != "pending":
                raise CustomException(msg="该申请已处理，无法撤销", code=10400, status_code=400)
            row.apply_status = "rejected"
            row.reviewed_at = datetime.now()
            row.review_note = "申请人主动撤销"
            row.updated_id = user.id
            await db.flush()

    # ---------------- 管理员侧 ----------------
    @classmethod
    async def list_all(
        cls,
        *,
        apply_status: str | None = None,
        applicant_id: int | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> dict:
        """管理员分页列出全部申请单（可按状态/申请者过滤）。"""
        from sqlalchemy import func

        page = max(int(page or 1), 1)
        page_size = max(1, min(int(page_size or 20), 100))
        wheres = [AiIntegrationAppApplyModel.is_deleted.is_(False)]
        if apply_status:
            wheres.append(AiIntegrationAppApplyModel.apply_status == apply_status)
        if applicant_id is not None:
            wheres.append(AiIntegrationAppApplyModel.applicant_id == applicant_id)
        async with async_db_session() as db:
            base = select(AiIntegrationAppApplyModel).where(*wheres)
            total = (
                await db.execute(select(func.count()).select_from(base.subquery()))
            ).scalar() or 0
            rows = (
                await db.execute(
                    base.order_by(AiIntegrationAppApplyModel.id.desc())
                    .offset((page - 1) * page_size)
                    .limit(page_size)
                )
            ).scalars().all()
            return {
                "page_no": page,
                "page_size": page_size,
                "total": total,
                "has_next": page * page_size < total,
                "items": [_apply_to_dict(r) for r in rows],
            }

    @classmethod
    async def review(cls, apply_id: int, *, approve: bool, reviewer_id: int | None, note: str | None) -> dict:
        """管理员审核申请单：批准生成应用，或驳回。

        - 批准：生成 ``AiIntegrationAppModel``（source_type="self"，owner_user_id=申请者），
          按申请的能力码授权，返回 appid/appkey 一次；申请单置 approved。
        - 驳回：仅记状态与意见。
        """
        async with async_db_session.begin() as db:
            row = await db.get(AiIntegrationAppApplyModel, apply_id)
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
                return _apply_to_dict(row)

            # 批准：生成应用。名称可能已被占用，加唯一后缀兜底。
            appid = _generate_appid()
            appkey = _generate_appkey()
            base_name = row.name or "自助应用"
            exists = await db.scalar(
                select(AiIntegrationAppModel).where(
                    AiIntegrationAppModel.name == base_name,
                    AiIntegrationAppModel.is_deleted.is_(False),
                )
            )
            name = (
                f"{base_name}_{row.applicant_id}"
                if exists
                else base_name
            )
            from .service import _app_to_dict

            app = AiIntegrationAppModel(
                name=name[:120],
                appid=appid,
                appkey_hash=_hash_appkey(appkey),
                description=row.description,
                enabled=True,
                capabilities=row.capabilities or [],
                channels=row.channels or None,
                requires_approval=True,
                source_type="self",
                owner_user_id=row.applicant_id,
                created_id=reviewer_id,
                updated_id=reviewer_id,
            )
            db.add(app)
            await db.flush()
            await db.refresh(app)

            row.app_id = app.id
            row.apply_status = "approved"
            row.reviewed_at = datetime.now()
            row.reviewed_by = reviewer_id
            row.review_note = (note or "已批准")[:255]
            row.updated_id = reviewer_id
            await db.flush()
            result = _apply_to_dict(row)
        result["app"] = _app_to_dict(app, appkey=appkey)
        return result
