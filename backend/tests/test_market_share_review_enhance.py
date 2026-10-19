"""市场「分享 + 审核」增强测试：

分享：
- 支持直接分享个人资产（含未提交市场的工具/技能/MCP/插件）；
- 分享列表分页；
- 接受分享时校验市场商品状态（未上架/已下架不可接收）。

审核：
- 防重复审核（已通过/已驳回的商品拒绝再审）；
- 审核列表分页 + 提交者名 owner_name；
- 批量审核。
"""
import asyncio
import uuid

from sqlalchemy import select

from app.api.v1.module_system.user.model import UserModel
from app.core.database import async_db_session
from app.plugin.module_ai.market.model import AiMarketItemModel
from app.plugin.module_ai.tools_catalog.model import AiToolModel


def _new_name(prefix: str = "pytest_sh_enh") -> str:
    return f"{prefix}_{uuid.uuid4().hex[:8]}"


def _admin_id() -> int:
    async def _go():
        async with async_db_session() as db:
            return (
                await db.execute(select(UserModel.id).where(UserModel.username == "admin"))
            ).scalar()
    return asyncio.run(_go())


def _seed_personal_tool(name: str, owner_id: int) -> int:
    """直插一条属于指定用户的 HTTP 工具，返回真实 id。"""
    async def _go():
        async with async_db_session.begin() as db:
            row = AiToolModel(
                name=name,
                kind="http",
                source="http",
                method="GET",
                url="http://x.test/{q}",
                headers={"X-Test": "1"},
                params_schema={"type": "object", "properties": {"q": {"type": "string"}}},
                enabled=True,
                description="个人工具",
                created_id=owner_id,
                updated_id=owner_id,
            )
            db.add(row)
            await db.flush()
            return row.id
    return asyncio.run(_go())


def _seed_item(status: str = "approved", owner_id: int | None = None) -> int:
    async def _go():
        async with async_db_session.begin() as db:
            item = AiMarketItemModel(
                asset_type="tool",
                name=_new_name(),
                description="市场商品",
                status=status,
                owner_id=owner_id,
                payload={"name": _new_name(), "kind": "http", "method": "GET", "url": "http://x.test/"},
                install_count=0,
                favorite_count=0,
            )
            db.add(item)
            await db.flush()
            return item.id
    return asyncio.run(_go())


def _make_user(test_client, auth_headers, tag: str) -> tuple[dict, int]:
    """创建用户并返回 (请求头, 用户id)，提升为超管以通过权限校验。"""
    suffix = uuid.uuid4().hex[:8]
    role = test_client.post(
        "/api/v1/system/role/create",
        headers=auth_headers,
        json={
            "name": f"pytest-shenh-{tag}-{suffix}",
            "code": f"SH{tag.upper()}{suffix}"[:20],
            "order": 999,
            "data_scope": 1,
            "status": "0",
        },
    )
    assert role.status_code == 200, role.text
    role_id = role.json()["data"]["id"]
    username = f"shuser{tag}{suffix}"
    user = test_client.post(
        "/api/v1/system/user/create",
        headers=auth_headers,
        json={
            "username": username,
            "name": f"增强分享用户{tag}",
            "password": "123456",
            "status": "0",
            "role_ids": [role_id],
        },
    )
    assert user.status_code == 200, user.text
    user_id = user.json()["data"]["id"]

    async def _promote():
        async with async_db_session.begin() as db:
            u = await db.get(UserModel, user_id)
            u.is_superuser = True
    asyncio.run(_promote())
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


def _tools_of_user_by_prefix(user_id: int, prefix: str) -> int:
    """统计某用户（created_id=user_id）拥有的、名称以 prefix 开头的工具数。"""
    async def _go():
        async with async_db_session() as db:
            rows = (
                await db.execute(
                    select(AiToolModel.id).where(
                        AiToolModel.created_id == user_id,
                        AiToolModel.name.like(f"{prefix}%"),
                    )
                )
            ).scalars().all()
            return len(rows)
    return asyncio.run(_go())


# ---------- 分享增强 ----------

def test_share_personal_asset_without_market(test_client, auth_headers):
    """直接分享个人资产（未提交市场）→ 接收方获得真实资产。"""
    owner = _admin_id()
    tool_name = _new_name("pytest_personal")
    real_id = _seed_personal_tool(tool_name, owner)
    headers_b, bid = _make_user(test_client, auth_headers, "pa")

    r = test_client.post(
        "/api/v1/ai/market/shares/share",
        headers=auth_headers,
        json={"asset_type": "tool", "real_id": real_id, "to_user_id": bid, "message": "直接分享"},
    )
    assert r.status_code == 200, r.text
    share_id = r.json()["data"]["id"]
    assert r.json()["data"]["asset_type"] == "tool"

    acc = test_client.post(f"/api/v1/ai/market/shares/{share_id}/accept", headers=headers_b)
    assert acc.status_code == 200, acc.text
    assert acc.json()["data"]["status"] == "accepted"
    # 接收方获得一份属于自己（created_id=bid）的副本工具（名称带前缀，因分享人已有同名行可能加后缀）
    assert _tools_of_user_by_prefix(bid, tool_name) == 1


def test_share_list_pagination(test_client, auth_headers):
    """分享列表支持分页。"""
    headers_b, bid = _make_user(test_client, auth_headers, "pg")
    item_ids = [_seed_item("approved") for _ in range(3)]
    for iid in item_ids:
        r = test_client.post(
            "/api/v1/ai/market/shares/share",
            headers=auth_headers,
            json={"item_id": iid, "to_user_id": bid},
        )
        assert r.status_code == 200, r.text

    page1 = test_client.get(
        "/api/v1/ai/market/shares",
        params={"direction": "in", "page_no": 1, "page_size": 2},
        headers=headers_b,
    ).json()["data"]
    assert page1["total"] == 3
    assert len(page1["items"]) == 2
    assert page1["page_no"] == 1

    page2 = test_client.get(
        "/api/v1/ai/market/shares",
        params={"direction": "in", "page_no": 2, "page_size": 2},
        headers=headers_b,
    ).json()["data"]
    assert len(page2["items"]) == 1


def test_accept_share_rejects_non_approved_item(test_client, auth_headers):
    """接受分享时校验市场商品状态：未上架商品不可接收。"""
    headers_b, bid = _make_user(test_client, auth_headers, "na")
    item_id = _seed_item("approved")
    r = test_client.post(
        "/api/v1/ai/market/shares/share",
        headers=auth_headers,
        json={"item_id": item_id, "to_user_id": bid},
    )
    share_id = r.json()["data"]["id"]

    # 分享后商品被下架（分享本身只允许已上架商品，故用下架制造非 approved 状态）
    off = test_client.post(
        "/api/v1/ai/market/review",
        headers=auth_headers,
        json={"item_id": item_id, "action": "offline", "remark": "测试下架"},
    )
    assert off.status_code == 200, off.text

    acc = test_client.post(f"/api/v1/ai/market/shares/{share_id}/accept", headers=headers_b)
    assert acc.status_code != 200
    assert "上架" in acc.json()["msg"] or "审核" in acc.json()["msg"]


# ---------- 审核增强 ----------

def test_review_already_processed_rejected(test_client, auth_headers):
    """已通过的商品再次审核（驳回）被拒绝。"""
    item_id = _seed_item("approved", owner_id=_admin_id())
    r = test_client.post(
        "/api/v1/ai/market/review",
        headers=auth_headers,
        json={"item_id": item_id, "action": "reject", "remark": "重复审核"},
    )
    assert r.status_code != 200
    assert "已审核" in r.json()["msg"]
    # 状态保持不变
    d = test_client.get(f"/api/v1/ai/market/items/{item_id}", headers=auth_headers).json()["data"]
    assert d["status"] == "approved"


def test_review_list_pagination_and_owner_name(test_client, auth_headers):
    """审核列表支持分页且带提交者名。"""
    _seed_item("pending", owner_id=_admin_id())
    _seed_item("pending", owner_id=_admin_id())
    lst = test_client.get(
        "/api/v1/ai/market/review/list",
        params={"status": "pending", "page_no": 1, "page_size": 1},
        headers=auth_headers,
    ).json()["data"]
    assert lst["page_no"] == 1
    assert len(lst["items"]) <= 1
    assert lst["total"] >= 2
    # 每项带提交者名（admin 为超管用户名 admin）
    assert all(isinstance(i["owner_name"], str) for i in lst["items"])


def test_review_batch(test_client, auth_headers):
    """批量审核多条 pending 商品。"""
    ids = [_seed_item("pending", owner_id=_admin_id()) for _ in range(2)]
    r = test_client.post(
        "/api/v1/ai/market/review/batch",
        headers=auth_headers,
        json={"items": [{"item_id": i, "action": "approve", "remark": "批量通过"} for i in ids]},
    )
    assert r.status_code == 200, r.text
    results = r.json()["data"]["results"]
    assert len(results) == 2
    assert all(x["ok"] is True for x in results)
    assert all(x["status"] == "approved" for x in results)
