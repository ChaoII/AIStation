"""市场安装/收藏/查询 API 测试。"""
import asyncio
import uuid

from sqlalchemy import select

from app.core.database import async_db_session
from app.plugin.module_ai.market.model import AiMarketItemModel
from app.plugin.module_ai.market.service import MarketService
from app.plugin.module_ai.tools_catalog.model import AiToolModel


def _new_name(prefix: str = "pytest_mkt") -> str:
    return f"{prefix}_{uuid.uuid4().hex[:8]}"


def _seed_item(asset_type: str = "tool", status: str = "approved", **payload) -> int:
    """直插一条市场商品，返回商品 id。"""
    name = _new_name()

    async def _go():
        async with async_db_session.begin() as db:
            item = AiMarketItemModel(
                asset_type=asset_type,
                name=name,
                description="市场测试商品",
                icon="🚀",
                category="测试分类",
                tags=["test"],
                version="1.0",
                is_official=False,
                featured=False,
                status=status,
                payload=payload or _default_payload(asset_type, name),
                source_id=None,
                install_count=0,
                favorite_count=0,
            )
            db.add(item)
            await db.flush()
            return item.id

    return asyncio.run(_go())


def _default_payload(asset_type: str, name: str) -> dict:
    if asset_type == "tool":
        return {
            "name": name,
            "kind": "http",
            "method": "GET",
            "url": "http://x.test/{q}",
            "headers": {"X-Test": "1"},
            "params_schema": {"type": "object", "properties": {"q": {"type": "string"}}},
            "enabled": True,
            "description": "可测试 HTTP 工具",
        }
    if asset_type == "skill":
        return {"name": name, "description": "技能描述", "content": "# 技能", "skill_type": "instruction", "category": "测试分类", "enabled": True}
    if asset_type == "mcp":
        return {"name": name, "transport": "streamable-http", "url": "http://x.test/mcp", "auth_type": "none", "enabled": True}
    return {"key": name, "label": "插件", "kind": "builtin", "executor_ready": True, "enabled": True}


def _count_tools(name: str) -> int:
    async def _go():
        async with async_db_session() as db:
            rows = (
                await db.execute(
                    select(AiToolModel).where(AiToolModel.name == name)
                )
            ).scalars().all()
            return len(rows)
    return asyncio.run(_go())


def test_install_tool_creates_real_tool(test_client, auth_headers):
    """安装工具商品 → ai_tools 出现一条真实记录，且关系表记录 installed。"""
    name = _new_name()
    item_id = _seed_item("tool", "approved", **_default_payload("tool", name))
    r = test_client.post(
        f"/api/v1/ai/market/items/{item_id}/install", headers=auth_headers
    )
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert data["installed"] is True
    assert data["real_id"] > 0
    # 资产行存在
    assert _count_tools(name) == 1
    # 详情返回 installed=True
    d = test_client.get(
        f"/api/v1/ai/market/items/{item_id}", headers=auth_headers
    ).json()["data"]
    assert d["installed"] is True


def test_install_idempotent(test_client, auth_headers):
    """重复安装同一商品：只产生一条真实资产（幂等）。"""
    name = _new_name()
    item_id = _seed_item("tool", "approved", **_default_payload("tool", name))
    r1 = test_client.post(
        f"/api/v1/ai/market/items/{item_id}/install", headers=auth_headers
    )
    assert r1.json()["data"]["installed"] is True
    r2 = test_client.post(
        f"/api/v1/ai/market/items/{item_id}/install", headers=auth_headers
    )
    assert r2.json()["data"]["installed"] is False
    assert r2.json()["data"]["exists"] is True
    assert _count_tools(name) == 1


def test_install_pending_rejected(test_client, auth_headers):
    """未上架商品不可安装。"""
    item_id = _seed_item("tool", "pending", **_default_payload("tool", _new_name()))
    r = test_client.post(
        f"/api/v1/ai/market/items/{item_id}/install", headers=auth_headers
    )
    assert r.status_code != 200
    assert "未上架" in r.json()["msg"]


def test_install_requires_auth(test_client):
    """未登录安装返回 401/403。"""
    item_id = _seed_item("tool", "approved", **_default_payload("tool", _new_name()))
    r = test_client.post(f"/api/v1/ai/market/items/{item_id}/install")
    assert r.status_code in (401, 403)


def test_favorite_toggle(test_client, auth_headers):
    """收藏→列表/详情标志→取消收藏。"""
    item_id = _seed_item("tool", "approved", **_default_payload("tool", _new_name()))
    r = test_client.post(f"/api/v1/ai/market/items/{item_id}/favorite", headers=auth_headers)
    assert r.json()["data"]["favorited"] is True
    d = test_client.get(f"/api/v1/ai/market/items/{item_id}", headers=auth_headers).json()["data"]
    assert d["favorited"] is True
    r2 = test_client.delete(f"/api/v1/ai/market/items/{item_id}/favorite", headers=auth_headers)
    assert r2.json()["data"]["favorited"] is False
    d2 = test_client.get(f"/api/v1/ai/market/items/{item_id}", headers=auth_headers).json()["data"]
    assert d2["favorited"] is False


def test_market_list_filter_by_type_and_keyword(test_client, auth_headers):
    """列表：类型/关键词过滤，且只显示 approved。"""
    name = _new_name("pytest_filtercat")
    _seed_item("tool", "approved", **_default_payload("tool", name))
    _seed_item("skill", "approved", **_default_payload("skill", _new_name()))
    _seed_item("skill", "pending", **_default_payload("skill", _new_name()))

    r = test_client.get(
        "/api/v1/ai/market/items", params={"type": "skill", "keyword": "测试商品"},
        headers=auth_headers,
    )
    data = r.json()["data"]
    assert data["total"] >= 1
    assert all(i["asset_type"] == "skill" for i in data["items"])
    # pending 不出现
    assert all(i["status"] == "approved" for i in data["items"])


def test_market_home_shape(test_client, auth_headers):
    """首页返回精选列表与分类计数。"""
    r = test_client.get("/api/v1/ai/market/home", headers=auth_headers)
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert "featured" in data and "categories" in data
