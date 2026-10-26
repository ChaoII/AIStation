"""个人空间扩容申请 + 管理员审核 + 按用户配额覆盖 测试。"""
import asyncio

import pytest
from sqlalchemy import delete, select

from app.config.setting import settings
from app.core.database import async_db_session
from app.core.exceptions import CustomException
from app.plugin.module_ai.space import service
from app.plugin.module_ai.space.model import AiSpaceQuotaRequestModel, AiSpaceUserQuotaModel

DEFAULT_MB = int(settings.AI_SPACE_QUOTA_MB)  # 2048
DEFAULT_BYTES = DEFAULT_MB * 1024 * 1024


@pytest.fixture(autouse=True)
def _clean_quota():
    """用例间清空扩容申请 / 用户配额覆盖表 / 站内通知表。"""

    async def _clean():
        from app.api.v1.module_system.notification.model import UserNotificationModel

        async with async_db_session.begin() as db:
            await db.execute(delete(AiSpaceQuotaRequestModel))
            await db.execute(delete(AiSpaceUserQuotaModel))
            await db.execute(delete(UserNotificationModel))

    asyncio.run(_clean())
    yield


def _admin_id(test_client, auth_headers) -> int:
    from app.api.v1.module_system.user.model import UserModel

    async def _run():
        async with async_db_session() as db:
            u = await db.scalar(select(UserModel).where(UserModel.username == "admin"))
            assert u is not None, "admin 用户不存在"
            return u.id

    return asyncio.run(_run())


# ---------------------------------------------------------------- #
# 配额（默认 2G / 生效配额）
# ---------------------------------------------------------------- #
def test_quota_default_is_2g(test_client, auth_headers):
    uid = _admin_id(test_client, auth_headers)
    q = asyncio.run(service.SpaceService.quota(uid))
    assert q["quota_bytes"] == DEFAULT_BYTES
    assert q["default_quota_bytes"] == DEFAULT_BYTES
    assert q["has_pending_request"] is False


def test_quota_reflects_user_override(test_client, auth_headers):
    uid = _admin_id(test_client, auth_headers)

    async def _seed():
        async with async_db_session.begin() as db:
            db.add(AiSpaceUserQuotaModel(user_id=uid, quota_mb=8192, updated_by=uid))

    asyncio.run(_seed())
    q = asyncio.run(service.SpaceService.quota(uid))
    assert q["quota_bytes"] == 8192 * 1024 * 1024


# ---------------------------------------------------------------- #
# 提交申请
# ---------------------------------------------------------------- #
def test_submit_request_and_pending_block(test_client, auth_headers):
    uid = _admin_id(test_client, auth_headers)
    r = asyncio.run(service.SpaceService.submit_request(uid, 4096, "需要更大空间"))
    assert r["status"] == "pending" and r["target_mb"] == 4096

    with pytest.raises(CustomException):
        asyncio.run(service.SpaceService.submit_request(uid, 8192, "重复提交"))

    with pytest.raises(CustomException):
        asyncio.run(service.SpaceService.submit_request(uid, 1024, "目标不大于当前"))

    mine = asyncio.run(service.SpaceService.list_requests(uid))
    assert len(mine) == 1 and mine[0]["target_mb"] == 4096


# ---------------------------------------------------------------- #
# 审核
# ---------------------------------------------------------------- #
def test_review_approve_updates_user_quota(test_client, auth_headers):
    uid = _admin_id(test_client, auth_headers)
    r = asyncio.run(service.SpaceService.submit_request(uid, 4096, "请批"))
    review = asyncio.run(service.SpaceService.review_request(r["request_id"], True, 5120, "批准", uid))
    assert review["status"] == "approved"
    q = asyncio.run(service.SpaceService.quota(uid))
    assert q["quota_bytes"] == 5120 * 1024 * 1024


def test_review_reject_keeps_default(test_client, auth_headers):
    uid = _admin_id(test_client, auth_headers)
    r = asyncio.run(service.SpaceService.submit_request(uid, 4096, "理由"))
    review = asyncio.run(service.SpaceService.review_request(r["request_id"], False, None, "不批", uid))
    assert review["status"] == "rejected"
    q = asyncio.run(service.SpaceService.quota(uid))
    assert q["quota_bytes"] == DEFAULT_BYTES


def test_review_twice_blocked(test_client, auth_headers):
    uid = _admin_id(test_client, auth_headers)
    r = asyncio.run(service.SpaceService.submit_request(uid, 4096, "理由"))
    rid = r["request_id"]
    asyncio.run(service.SpaceService.review_request(rid, True, 4096, "ok", uid))
    with pytest.raises(CustomException):
        asyncio.run(service.SpaceService.review_request(rid, False, None, "再批", uid))


def test_list_all_requests_with_username(test_client, auth_headers):
    uid = _admin_id(test_client, auth_headers)
    asyncio.run(service.SpaceService.submit_request(uid, 4096, "请批"))
    allr = asyncio.run(service.SpaceService.list_all_requests())
    assert any(r["username"] == "admin" and r["target_mb"] == 4096 for r in allr)
    # 按状态过滤
    pending = asyncio.run(service.SpaceService.list_all_requests("pending"))
    assert all(r["status"] == "pending" for r in pending)


# ---------------------------------------------------------------- #
# 通知联动：提交 → 通知超级管理员；审核 → 通知申请人
# ---------------------------------------------------------------- #
def _notifications(uid: int) -> list[dict]:
    from app.api.v1.module_system.notification.model import UserNotificationModel

    async def _run():
        async with async_db_session() as db:
            rows = (
                await db.execute(
                    select(UserNotificationModel)
                    .where(UserNotificationModel.user_id == uid)
                    .order_by(UserNotificationModel.id)
                )
            ).scalars().all()
            return [{"title": r.title, "module": r.module, "type": r.type, "content": r.content} for r in rows]

    return asyncio.run(_run())


def test_submit_notifies_super_admins(test_client, auth_headers):
    uid = _admin_id(test_client, auth_headers)
    asyncio.run(service.SpaceService.submit_request(uid, 4096, "请批"))
    notes = [n for n in _notifications(uid) if n["module"] == "space"]
    assert any(
        n["type"] == "space_quota_pending" and "扩容申请" in n["title"] for n in notes
    ), "提交申请应给超级管理员发「待审核」站内通知"


def test_review_approve_notifies_applicant(test_client, auth_headers):
    uid = _admin_id(test_client, auth_headers)
    r = asyncio.run(service.SpaceService.submit_request(uid, 4096, "请批"))
    asyncio.run(service.SpaceService.review_request(r["request_id"], True, 4096, "批准", uid))
    notes = [n for n in _notifications(uid) if n["module"] == "space"]
    assert any(
        n["type"] == "space_quota_reviewed" and "已通过" in n["title"] for n in notes
    ), "审核通过应给申请人发已通过通知"


def test_review_reject_notifies_applicant(test_client, auth_headers):
    uid = _admin_id(test_client, auth_headers)
    r = asyncio.run(service.SpaceService.submit_request(uid, 4096, "请批"))
    asyncio.run(service.SpaceService.review_request(r["request_id"], False, None, "不批", uid))
    notes = [n for n in _notifications(uid) if n["module"] == "space"]
    assert any(
        n["type"] == "space_quota_reviewed" and "已驳回" in n["title"] for n in notes
    ), "审核驳回应给申请人发已驳回通知"


# ---------------------------------------------------------------- #
# API 全链路
# ---------------------------------------------------------------- #
def test_api_flow(test_client, auth_headers):
    h = auth_headers
    r = test_client.post(
        "/api/v1/ai/space/quota/request",
        json={"target_mb": 6144, "reason": "API 测试"},
        headers=h,
    )
    assert r.status_code == 200, r.text
    rid = r.json()["data"]["request_id"]

    mine = test_client.get("/api/v1/ai/space/quota/requests/mine", headers=h).json()["data"]
    assert any(m["id"] == rid for m in mine)

    allr = test_client.get("/api/v1/ai/space/quota/requests", headers=h).json()["data"]
    assert any(m["id"] == rid for m in allr)

    rr = test_client.post(
        f"/api/v1/ai/space/quota/requests/{rid}/review",
        json={"approve": True, "quota_mb": 6144, "note": "ok"},
        headers=h,
    )
    assert rr.status_code == 200, rr.text

    q = test_client.get("/api/v1/ai/space/quota", headers=h).json()["data"]
    assert q["quota_bytes"] == 6144 * 1024 * 1024
