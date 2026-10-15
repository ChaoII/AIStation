"""市场提交/审核/撤回/精选 API 测试。"""
import asyncio
import uuid

from sqlalchemy import select

from app.api.v1.module_system.user.model import UserModel
from app.core.database import async_db_session
from app.plugin.module_ai.market.model import AiMarketItemModel
from app.plugin.module_ai.tools_catalog.model import AiToolModel


def _new_name(prefix: str = "pytest_rev") -> str:
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


def _seed_item(status: str = "pending", owner_id: int | None = None) -> int:
    async def _go():
        async with async_db_session.begin() as db:
            item = AiMarketItemModel(
                asset_type="tool",
                name=_new_name(),
                description="待审商品",
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


def _create_limited_user(test_client, auth_headers) -> dict:
    """创建无任何菜单权限的用户，返回其请求头。"""
    suffix = uuid.uuid4().hex[:8]
    role = test_client.post(
        "/api/v1/system/role/create",
        headers=auth_headers,
        json={
            "name": f"pytest-mkt-{suffix}",
            "code": f"MKT{suffix}",
            "order": 999,
            "data_scope": 1,
            "status": "0",
        },
    )
    assert role.status_code == 200, role.text
    role_id = role.json()["data"]["id"]
    username = f"mktuser{suffix}"
    user = test_client.post(
        "/api/v1/system/user/create",
        headers=auth_headers,
        json={
            "username": username,
            "name": "市场受限用户",
            "password": "123456",
            "status": "0",
            "role_ids": [role_id],
        },
    )
    assert user.status_code == 200, user.text
    login = test_client.post(
        "/api/v1/system/auth/login",
        data={"username": username, "password": "123456"},
        headers={"X-Forwarded-For": "127.0.0.1"},
    )
    assert login.status_code == 200, login.text
    return {
        "Authorization": f"Bearer {login.json()['data']['access_token']}",
        "X-Forwarded-For": "127.0.0.1",
    }


def test_review_requires_permission(test_client, auth_headers):
    """无 review 权限的用户访问审核接口 → 403。"""
    limited = _create_limited_user(test_client, auth_headers)
    r1 = test_client.get("/api/v1/ai/market/review/list", headers=limited)
    assert r1.status_code == 403, r1.text
    r2 = test_client.post(
        "/api/v1/ai/market/review",
        json={"item_id": 1, "action": "approve"},
        headers=limited,
    )
    assert r2.status_code == 403, r2.text


def test_submit_approve_then_install(test_client, auth_headers):
    """提交个人工具 → pending → 审核通过 → 市场可安装。"""
    owner = _admin_id()
    tool_name = _new_name("pytest_submit")
    real_id = _seed_personal_tool(tool_name, owner)

    r = test_client.post(
        "/api/v1/ai/market/submit",
        headers=auth_headers,
        json={
            "asset_type": "tool",
            "source_id": real_id,
            "name": tool_name,
            "description": "我要上架",
            "category": "效率",
            "version": "1.0",
        },
    )
    assert r.status_code == 200, r.text
    item = r.json()["data"]
    assert item["status"] == "pending"
    item_id = item["id"]

    # pending 状态出现在审核列表
    lst = test_client.get("/api/v1/ai/market/review/list", headers=auth_headers).json()["data"]
    assert any(i["id"] == item_id for i in lst["items"])

    # 审核通过
    rev = test_client.post(
        "/api/v1/ai/market/review",
        headers=auth_headers,
        json={"item_id": item_id, "action": "approve", "remark": "通过"},
    )
    assert rev.json()["data"]["status"] == "approved"

    # 现在可以安装（会复制出一条新工具）
    inst = test_client.post(f"/api/v1/ai/market/items/{item_id}/install", headers=auth_headers)
    assert inst.status_code == 200, inst.text
    assert inst.json()["data"]["installed"] is True


def test_reject_with_remark(test_client, auth_headers):
    """驳回商品带审核意见。"""
    item_id = _seed_item("pending", owner_id=_admin_id())
    r = test_client.post(
        "/api/v1/ai/market/review",
        headers=auth_headers,
        json={"item_id": item_id, "action": "reject", "remark": "描述不完整"},
    )
    assert r.json()["data"]["status"] == "rejected"
    assert r.json()["data"]["audit_remark"] == "描述不完整"


def test_withdraw_blocks_install(test_client, auth_headers):
    """撤回后商品不可安装。"""
    owner = _admin_id()
    tool_name = _new_name("pytest_withdraw")
    real_id = _seed_personal_tool(tool_name, owner)
    sub = test_client.post(
        "/api/v1/ai/market/submit",
        headers=auth_headers,
        json={"asset_type": "tool", "source_id": real_id, "name": tool_name},
    )
    item_id = sub.json()["data"]["id"]
    # 先审核通过使其可安装
    test_client.post(
        "/api/v1/ai/market/review",
        headers=auth_headers,
        json={"item_id": item_id, "action": "approve"},
    )
    # 撤回
    w = test_client.post(f"/api/v1/ai/market/items/{item_id}/withdraw", headers=auth_headers)
    assert w.json()["data"]["status"] == "offline"
    # 安装被拒
    inst = test_client.post(f"/api/v1/ai/market/items/{item_id}/install", headers=auth_headers)
    assert inst.status_code != 200
    assert "未上架" in inst.json()["msg"]


def test_submit_others_asset_rejected(test_client, auth_headers):
    """不能提交别人的资产。"""
    other_id = 999999  # 不存在的 created_id
    tool_name = _new_name("pytest_other")
    real_id = _seed_personal_tool(tool_name, other_id)
    r = test_client.post(
        "/api/v1/ai/market/submit",
        headers=auth_headers,
        json={"asset_type": "tool", "source_id": real_id, "name": tool_name},
    )
    assert r.status_code != 200
    assert "自己的资产" in r.json()["msg"]


def test_feature_toggle(test_client, auth_headers):
    """精选开关生效（首页精选位有限，此处只校验标记本身）。"""
    item_id = _seed_item("approved", owner_id=_admin_id())
    r = test_client.post(
        f"/api/v1/ai/market/items/{item_id}/feature",
        params={"featured": True},
        headers=auth_headers,
    )
    assert r.json()["data"]["featured"] is True
    # 详情可见标记
    d = test_client.get(f"/api/v1/ai/market/items/{item_id}", headers=auth_headers).json()["data"]
    assert d["featured"] is True


def test_mine_lists_real_assets_with_market_status(test_client, auth_headers):
    """我的资产返回真实资产并附带市场提交状态。"""
    owner = _admin_id()
    tool_name = _new_name("pytest_mine")
    real_id = _seed_personal_tool(tool_name, owner)
    sub = test_client.post(
        "/api/v1/ai/market/submit",
        headers=auth_headers,
        json={"asset_type": "tool", "source_id": real_id, "name": tool_name},
    )
    item_id = sub.json()["data"]["id"]

    mine = test_client.get(
        "/api/v1/ai/market/mine", params={"asset_type": "tool"}, headers=auth_headers
    ).json()["data"]
    row = next(i for i in mine["items"] if i["real_id"] == real_id)
    assert row["market"]["item_id"] == item_id
    assert row["market"]["status"] == "pending"
