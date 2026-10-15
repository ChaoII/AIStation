"""市场点对点分享 API 测试。"""
import asyncio
import uuid

from sqlalchemy import select

from app.api.v1.module_system.user.model import UserModel
from app.core.database import async_db_session
from app.plugin.module_ai.market.model import AiMarketItemModel
from app.plugin.module_ai.tools_catalog.model import AiToolModel


def _new_name(prefix: str = "pytest_share") -> str:
    return f"{prefix}_{uuid.uuid4().hex[:8]}"


def _admin_id() -> int:
    async def _go():
        async with async_db_session() as db:
            return (
                await db.execute(select(UserModel.id).where(UserModel.username == "admin"))
            ).scalar()
    return asyncio.run(_go())


def _seed_approved_item(name: str | None = None) -> int:
    tool_name = name or _new_name()

    async def _go():
        async with async_db_session.begin() as db:
            item = AiMarketItemModel(
                asset_type="tool",
                name=tool_name,
                description="可分享商品",
                status="approved",
                payload={
                    "name": tool_name,
                    "kind": "http",
                    "method": "GET",
                    "url": "http://x.test/",
                    "enabled": True,
                },
                install_count=0,
                favorite_count=0,
            )
            db.add(item)
            await db.flush()
            return item.id, tool_name

    return asyncio.run(_go())


def _promote_superuser(user_id: int) -> None:
    """把用户提升为超管（接口禁止创建超管，测试里直插以通过权限校验）。"""

    async def _go():
        async with async_db_session.begin() as db:
            user = await db.get(UserModel, user_id)
            user.is_superuser = True

    asyncio.run(_go())


def _make_user(test_client, auth_headers, tag: str) -> tuple[dict, int]:
    """创建用户并返回 (请求头, 用户id)。

    提升为超管以便通过接口权限校验——本用例关注的是**分享可见性与归属**，
    权限拒绝本身由 ``test_share_requires_permission`` 单独覆盖。
    """
    suffix = uuid.uuid4().hex[:8]
    role = test_client.post(
        "/api/v1/system/role/create",
        headers=auth_headers,
        json={
            "name": f"pytest-share-{tag}-{suffix}",
            "code": f"SHR{tag}{suffix}"[:20],
            "order": 999,
            "data_scope": 1,
            "status": "0",
        },
    )
    assert role.status_code == 200, role.text
    role_id = role.json()["data"]["id"]
    username = f"shru{tag}{suffix}"
    user = test_client.post(
        "/api/v1/system/user/create",
        headers=auth_headers,
        json={
            "username": username,
            "name": f"分享用户{tag}",
            "password": "123456",
            "status": "0",
            "role_ids": [role_id],
        },
    )
    assert user.status_code == 200, user.text
    user_id = user.json()["data"]["id"]
    _promote_superuser(user_id)
    login = test_client.post(
        "/api/v1/system/auth/login",
        data={"username": username, "password": "123456"},
        headers={"X-Forwarded-For": "127.0.0.1"},
    )
    assert login.status_code == 200, login.text
    return (
        {
            "Authorization": f"Bearer {login.json()['data']['access_token']}",
            "X-Forwarded-For": "127.0.0.1",
        },
        user_id,
    )


def _tools_of_user(user_id: int, name: str) -> int:
    async def _go():
        async with async_db_session() as db:
            rows = (
                await db.execute(
                    select(AiToolModel).where(
                        AiToolModel.created_id == user_id, AiToolModel.name == name
                    )
                )
            ).scalars().all()
            return len(rows)
    return asyncio.run(_go())


def test_share_to_self_rejected(test_client, auth_headers):
    """不能分享给自己。"""
    item_id, _ = _seed_approved_item()
    r = test_client.post(
        "/api/v1/ai/market/shares/share",
        headers=auth_headers,
        json={"item_id": item_id, "to_user_id": _admin_id(), "message": "self"},
    )
    assert r.status_code != 200
    assert "自己" in r.json()["msg"]


def test_share_visibility_isolation(test_client, auth_headers):
    """C 看不到 A→B 的分享；B 收件箱可见；A 发件箱可见。"""
    item_id, _ = _seed_approved_item()
    headers_b, _bid = _make_user(test_client, auth_headers, "b")
    headers_c, _cid = _make_user(test_client, auth_headers, "c")

    r = test_client.post(
        "/api/v1/ai/market/shares/share",
        headers=auth_headers,
        json={"item_id": item_id, "to_user_id": _bid, "message": "给你用"},
    )
    assert r.status_code == 200, r.text
    share_id = r.json()["data"]["id"]

    inbox_b = test_client.get(
        "/api/v1/ai/market/shares", params={"direction": "in"}, headers=headers_b
    ).json()["data"]
    assert any(s["id"] == share_id for s in inbox_b["items"])

    inbox_c = test_client.get(
        "/api/v1/ai/market/shares", params={"direction": "in"}, headers=headers_c
    ).json()["data"]
    assert not any(s["id"] == share_id for s in inbox_c["items"])

    outbox_a = test_client.get(
        "/api/v1/ai/market/shares", params={"direction": "out"}, headers=auth_headers
    ).json()["data"]
    assert any(s["id"] == share_id for s in outbox_a["items"])


def test_accept_share_copies_asset(test_client, auth_headers):
    """接收分享后接收方获得真实资产，状态 accepted。"""
    item_id, tool_name = _seed_approved_item()
    headers_b, bid = _make_user(test_client, auth_headers, "d")
    r = test_client.post(
        "/api/v1/ai/market/shares/share",
        headers=auth_headers,
        json={"item_id": item_id, "to_user_id": bid, "message": "接收测试"},
    )
    share_id = r.json()["data"]["id"]

    acc = test_client.post(
        f"/api/v1/ai/market/shares/{share_id}/accept", headers=headers_b
    )
    assert acc.status_code == 200, acc.text
    assert acc.json()["data"]["status"] == "accepted"
    assert _tools_of_user(bid, tool_name) == 1


def test_reject_share(test_client, auth_headers):
    """拒绝分享后状态 rejected，不复制资产。"""
    item_id, tool_name = _seed_approved_item()
    headers_b, bid = _make_user(test_client, auth_headers, "e")
    r = test_client.post(
        "/api/v1/ai/market/shares/share",
        headers=auth_headers,
        json={"item_id": item_id, "to_user_id": bid},
    )
    share_id = r.json()["data"]["id"]
    rej = test_client.post(
        f"/api/v1/ai/market/shares/{share_id}/reject", headers=headers_b
    )
    assert rej.json()["data"]["status"] == "rejected"
    assert _tools_of_user(bid, tool_name) == 0


def test_accept_by_wrong_user_rejected(test_client, auth_headers):
    """非接收方不能接收别人的分享。"""
    item_id, _ = _seed_approved_item()
    headers_b, bid = _make_user(test_client, auth_headers, "f")
    headers_c, _cid = _make_user(test_client, auth_headers, "g")
    r = test_client.post(
        "/api/v1/ai/market/shares/share",
        headers=auth_headers,
        json={"item_id": item_id, "to_user_id": bid},
    )
    share_id = r.json()["data"]["id"]
    bad = test_client.post(f"/api/v1/ai/market/shares/{share_id}/accept", headers=headers_c)
    assert bad.status_code != 200
    assert "无权" in bad.json()["msg"]


def test_share_requires_permission(test_client, auth_headers):
    """无 share 权限的用户发起分享 → 403。"""
    suffix = uuid.uuid4().hex[:8]
    role = test_client.post(
        "/api/v1/system/role/create",
        headers=auth_headers,
        json={
            "name": f"pytest-share-nop-{suffix}",
            "code": f"NOP{suffix}"[:20],
            "order": 999,
            "data_scope": 1,
            "status": "0",
        },
    )
    role_id = role.json()["data"]["id"]
    username = f"nop{suffix}"
    test_client.post(
        "/api/v1/system/user/create",
        headers=auth_headers,
        json={
            "username": username,
            "name": "无权限用户",
            "password": "123456",
            "status": "0",
            "role_ids": [role_id],
        },
    )
    login = test_client.post(
        "/api/v1/system/auth/login",
        data={"username": username, "password": "123456"},
        headers={"X-Forwarded-For": "127.0.0.1"},
    )
    limited = {
        "Authorization": f"Bearer {login.json()['data']['access_token']}",
        "X-Forwarded-For": "127.0.0.1",
    }
    item_id, _ = _seed_approved_item()
    r = test_client.post(
        "/api/v1/ai/market/shares/share",
        headers=limited,
        json={"item_id": item_id, "to_user_id": _admin_id()},
    )
    assert r.status_code == 403, r.text
