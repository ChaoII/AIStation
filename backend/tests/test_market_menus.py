"""能力市场相关菜单与权限种子测试。"""
import asyncio

from sqlalchemy import select

from app.api.v1.module_system.menu.model import MenuModel
from app.api.v1.module_system.role.model import RoleMenusModel
from app.core.database import async_db_session


def _menus_by_route(names: list[str]) -> dict[str, MenuModel]:
    async def _go():
        async with async_db_session() as db:
            rows = (
                await db.execute(select(MenuModel).where(MenuModel.route_name.in_(names)))
            ).scalars().all()
            return {m.route_name: m for m in rows}

    return asyncio.run(_go())


def _perms() -> set[str]:
    async def _go():
        async with async_db_session() as db:
            return set(
                (
                    await db.execute(
                        select(MenuModel.permission).where(
                            MenuModel.permission.like("module_ai:%")
                        )
                    )
                ).scalars().all()
            )

    return asyncio.run(_go())


def _admin_menu_ids() -> set[int]:
    async def _go():
        async with async_db_session() as db:
            return set(
                (
                    await db.execute(
                        select(RoleMenusModel.menu_id).where(RoleMenusModel.role_id == 1)
                    )
                ).scalars().all()
            )

    return asyncio.run(_go())


def test_market_menus_registered(test_client, auth_headers):
    """能力市场/MCP/插件菜单已注册且授权给 admin。"""
    menus = _menus_by_route(["AiMarket", "AiMcp", "AiPlugin"])
    assert set(menus) == {"AiMarket", "AiMcp", "AiPlugin"}
    assert menus["AiMarket"].route_path == "/ai/market"
    assert menus["AiMarket"].component_path == "module_ai/market/index"
    assert menus["AiMcp"].route_path == "/ai/mcp"
    assert menus["AiPlugin"].route_path == "/ai/plugin"
    granted = _admin_menu_ids()
    for m in menus.values():
        assert m.id in granted, f"菜单 {m.route_name} 未授权给 admin"
        assert m.status == "0"


def test_market_permissions_registered(test_client, auth_headers):
    """市场/MCP/插件权限码已注册。"""
    perms = _perms()
    expected = {
        "module_ai:market:query",
        "module_ai:market:install",
        "module_ai:market:submit",
        "module_ai:market:share",
        "module_ai:market:review",
        "module_ai:mcp:query",
        "module_ai:mcp:create",
        "module_ai:mcp:update",
        "module_ai:mcp:delete",
        "module_ai:plugin:query",
        "module_ai:plugin:create",
        "module_ai:plugin:update",
        "module_ai:plugin:delete",
    }
    missing = expected - perms
    assert not missing, f"缺少权限码：{missing}"
