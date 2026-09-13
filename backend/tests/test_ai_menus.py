"""AI 菜单收敛测试：保留 6 项（含种子 chat），下线 5 项。"""
import asyncio

from app.scripts import init_app

# 已下线页面（存量库应被置为 hidden=True）
REMOVED = ["AiOverview", "AiPlayground", "AiProvider", "AiReport", "Memory"]
# 必须保留且可见的页面
KEPT = ["AiModel", "AiPrompt", "AiTool", "AiApp", "AiLogs"]


def _ensure_removed_rows_visible() -> None:
    """保证 removed 页面在库中存在且可见，以验证 _ensure_ai_menus 会将其隐藏。"""
    from sqlalchemy import select

    from app.api.v1.module_system.menu.model import MenuModel
    from app.core.database import async_db_session

    async def _run() -> None:
        async with async_db_session() as db:
            async with db.begin():
                parent = await db.scalar(
                    select(MenuModel).where(
                        MenuModel.route_name == "AI", MenuModel.type == 1
                    )
                )
                assert parent is not None, "AI 父菜单不存在（种子数据未初始化）"
                for rname in REMOVED:
                    row = await db.scalar(
                        select(MenuModel).where(MenuModel.route_name == rname)
                    )
                    if row:
                        row.hidden = False
                        continue
                    db.add(
                        MenuModel(
                            name=rname,
                            type=2,
                            order=99,
                            route_name=rname,
                            route_path=f"/ai/{rname.lower()}",
                            component_path="",
                            parent_id=parent.id,
                            status="0",
                            is_deleted=False,
                            hidden=False,
                            title=rname,
                        )
                    )

    asyncio.run(_run())


def _fetch_menus():
    from sqlalchemy import select

    from app.api.v1.module_system.menu.model import MenuModel
    from app.core.database import async_db_session

    async def _run():
        async with async_db_session() as db:
            rows = (await db.execute(select(MenuModel))).scalars().all()
            return {r.route_name: r for r in rows if r.route_name}

    return asyncio.run(_run())


def test_ai_menus_collapsed(test_client):
    """_ensure_ai_menus 后：下线页 hidden=True，保留页可见，父菜单 redirect=/ai/chat。"""
    _ensure_removed_rows_visible()
    asyncio.run(init_app._ensure_ai_menus())
    menus = _fetch_menus()

    for rname in REMOVED:
        assert rname in menus, f"缺少待隐藏菜单 {rname}"
        assert menus[rname].hidden is True, f"{rname} 未被隐藏"
    for rname in KEPT:
        assert rname in menus, f"缺少保留菜单 {rname}"
        assert menus[rname].hidden is False, f"{rname} 被误隐藏"
    assert menus["Chat"].hidden is False, "chat 不应被隐藏"
    assert menus["AI"].redirect == "/ai/chat"


def test_ai_button_perms_drop_provider_report():
    """按钮权限不再包含 provider/report，保留 model/prompt/tool/app/assistant。"""
    perms = {code for code, _ in init_app.AI_BUTTON_PERMS}
    assert not any(code.startswith("module_ai:provider:") for code in perms)
    assert not any(code.startswith("module_ai:report:") for code in perms)
    for code in (
        "module_ai:model:query",
        "module_ai:prompt:create",
        "module_ai:tool:query",
        "module_ai:app:query",
        "module_ai:assistant:query",
    ):
        assert code in perms
