"""市场浏览体验增强测试：排序 / 官方 / 我的提交筛选 / owner_name / 精选 shuffle。"""
import asyncio
import uuid

from sqlalchemy import select

from app.core.database import async_db_session
from app.plugin.module_ai.market.model import AiMarketItemModel


def _new_name(prefix: str = "pytest_bw") -> str:
    return f"{prefix}_{uuid.uuid4().hex[:8]}"


def _seed_approved_item(
    name: str,
    install_count: int = 0,
    favorite_count: int = 0,
    owner_id: int | None = None,
    official: bool = False,
    featured: bool = False,
    created_time: object = None,
) -> int:
    async def _go():
        async with async_db_session.begin() as db:
            kw = {}
            if created_time is not None:
                kw["created_time"] = created_time
            item = AiMarketItemModel(
                asset_type="tool",
                name=name,
                description="浏览测试",
                status="approved",
                owner_id=owner_id,
                is_official=official,
                featured=featured,
                payload={"name": name, "kind": "http", "method": "GET", "url": "http://x.test/"},
                install_count=install_count,
                favorite_count=favorite_count,
                **kw,
            )
            db.add(item)
            await db.flush()
            return item.id
    return asyncio.run(_go())


def _admin_id() -> int:
    from app.api.v1.module_system.user.model import UserModel

    async def _go():
        async with async_db_session() as db:
            return (
                await db.execute(select(UserModel.id).where(UserModel.username == "admin"))
            ).scalar()
    return asyncio.run(_go())


def _items_of(test_client, auth_headers, params: dict) -> list[dict]:
    r = test_client.get("/api/v1/ai/market/items", params=params, headers=auth_headers)
    assert r.status_code == 200, r.text
    return r.json()["data"]["items"]


def test_items_sort_by_install(test_client, auth_headers):
    """sort=install 按安装数降序（高安装数商品创建更早，默认最新序会把它排后）。"""
    from datetime import datetime

    hi = _seed_approved_item(_new_name(), install_count=20, created_time=datetime(2020, 1, 1))
    lo = _seed_approved_item(_new_name(), install_count=2, created_time=datetime(2021, 1, 1))
    items = _items_of(test_client, auth_headers, {"sort": "install"})
    idx_hi = next(i for i, x in enumerate(items) if x["id"] == hi)
    idx_lo = next(i for i, x in enumerate(items) if x["id"] == lo)
    assert idx_hi < idx_lo, "安装数多的应排在前面"


def test_items_sort_by_favorite(test_client, auth_headers):
    """sort=favorite 按收藏数降序。"""
    from datetime import datetime

    hi = _seed_approved_item(_new_name(), favorite_count=9, created_time=datetime(2020, 1, 1))
    lo = _seed_approved_item(_new_name(), favorite_count=1, created_time=datetime(2021, 1, 1))
    items = _items_of(test_client, auth_headers, {"sort": "favorite"})
    idx_hi = next(i for i, x in enumerate(items) if x["id"] == hi)
    idx_lo = next(i for i, x in enumerate(items) if x["id"] == lo)
    assert idx_hi < idx_lo, "收藏多的应排在前面"


def test_items_official_filter(test_client, auth_headers):
    """official=true 仅返回平台内置（is_official）商品。"""
    off = _seed_approved_item(_new_name(), official=True)
    u = _seed_approved_item(_new_name(), official=False)
    items = _items_of(test_client, auth_headers, {"official": True})
    ids = {x["id"] for x in items}
    assert off in ids
    assert u not in ids


def test_items_mine_filter(test_client, auth_headers):
    """mine=true 仅返回我提交的商品。"""
    admin = _admin_id()
    mine = _seed_approved_item(_new_name(), owner_id=admin)
    other = _seed_approved_item(_new_name(), owner_id=99999999)
    items = _items_of(test_client, auth_headers, {"mine": True})
    ids = {x["id"] for x in items}
    assert mine in ids
    assert other not in ids


def test_items_include_owner_name(test_client, auth_headers):
    """商品列表携带 submitter 名（owner_name）。"""
    admin = _admin_id()
    _seed_approved_item(_new_name(), owner_id=admin)
    items = _items_of(test_client, auth_headers, {"mine": True})
    assert items
    assert all(isinstance(x.get("owner_name"), str) for x in items)


def test_home_shuffle_returns_featured(test_client, auth_headers):
    """home shuffle=true 返回精选（approved+featured）商品，不报错。"""
    _seed_approved_item(_new_name(), featured=True, official=True)
    r = test_client.get("/api/v1/ai/market/home", params={"shuffle": True}, headers=auth_headers)
    assert r.status_code == 200, r.text
    featured = r.json()["data"]["featured"]
    assert isinstance(featured, list)
    assert all(x["status"] == "approved" for x in featured)
