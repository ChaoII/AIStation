"""AI 菜单测试：AI 父菜单落地 /ai/overview（控制台），功能页保留，仅平台下线页隐藏。"""
import asyncio

from app.scripts import init_app

# 已下线平台页面（存量库应被置为 hidden=True）
# 含四个已并入「能力市场 → 我的资产」统一维护的独立页：技能广场/工具管理/MCP管理/能力插件
REMOVED = [
    "AiProvider",
    "AiPlayground",
    "AiReport",
    "Memory",
    "AiSkill",
    "AiTool",
    "AiMcp",
    "AiPlugin",
    "Chat",
]
# 页面保留：控制台/模型/提示词/应用/日志，其余功能页也保留
KEPT = ["AiModel", "AiPrompt", "AiApp", "AiLogs"]
# 富功能页保留（智能体/工作流独立菜单已并入「工作台」，不再作为独立页面菜单）
RICH_KEPT = ["AiOverview", "AiKnowledge", "AiProviderManage"]
# 「智能问数」独立菜单目录：目录 + 4 个独立页面子菜单；数据资产继续并入数据与集成
QUERY_GROUP = "AiQueryGroup"
QUERY_GROUP_MENUS: dict[str, tuple[str, str, int]] = {
    "AiIntegration": ("module_ai/integration/index", "/ai/integration", 1),
    "AiQuery": ("module_ai/query/index", "/ai/query", 2),
    "AiEval": ("module_ai/eval/index", "/ai/eval", 3),
    "AiQueryReports": ("module_ai/query/reports", "/ai/query/reports", 4),
}


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


def test_ai_space_menu_registered(test_client):
    """_ensure_ai_menus 后：个人工作空间菜单落地且可见，按钮权限已注册。"""
    asyncio.run(init_app._ensure_ai_menus())
    menus = _fetch_menus()
    m = menus["AiPersonalSpace"]
    assert m.hidden is False and m.route_path == "/ai/space"
    assert m.component_path == "module_ai/space/index"
    perms = {c for c, _ in init_app.AI_BUTTON_PERMS}
    assert {
        "module_ai:space:query",
        "module_ai:space:upload",
        "module_ai:space:download",
        "module_ai:space:delete",
        "module_ai:space:manage",
    } <= perms


def test_ai_cron_menu_registered(test_client):
    """_ensure_ai_menus 后：定时任务独立菜单落地且可见，cron 按钮权限（含立即执行）已注册。"""
    asyncio.run(init_app._ensure_ai_menus())
    menus = _fetch_menus()
    m = menus["AiCron"]
    assert m.hidden is False and m.route_path == "/ai/cron"
    assert m.component_path == "module_ai/cron/index"
    assert m.permission == "module_ai:cron:query"
    perms = {c for c, _ in init_app.AI_BUTTON_PERMS}
    assert {
        "module_ai:cron:query",
        "module_ai:cron:create",
        "module_ai:cron:update",
        "module_ai:cron:delete",
        "module_ai:cron:run",
    } <= perms


def test_ai_menu_groups(test_client):
    """AI 菜单分组：4 个分组目录存在且子菜单归组、组内有序（存量/新建库都幂等）。"""
    asyncio.run(init_app._ensure_ai_menus())
    asyncio.run(init_app._ensure_develop_menus())
    asyncio.run(init_app._ensure_ai_menu_groups())
    menus = _fetch_menus()
    for spec in init_app.AI_MENU_GROUPS:
        grp = menus[spec["route_name"]]
        # type=1 目录：route_path/redirect 必须非空，否则 current/info 校验失败拖垮菜单
        assert grp.type == 1 and grp.hidden is False
        assert grp.route_path == spec["redirect"]
        assert grp.redirect == spec["redirect"]
        for idx, rname in enumerate(spec["menus"], start=1):
            child = menus[rname]
            assert child.parent_id == grp.id, f"{rname} 未归入 {spec['title']}"
            assert child.order == idx, f"{rname} 组内顺序错误"
    # 工作台 / 定时任务：拉平到 AI 顶层（不进任何分组目录）
    ai_parent = menus["AI"]
    for rname in ("AiWorkbench", "AiCron"):
        assert menus[rname].parent_id == ai_parent.id, f"{rname} 应拉平在 AI 顶层"
    # 已废弃的「智能体与编排」分组目录必须被清理
    assert "AiGroupBuild" not in menus
    # 重复调用幂等（不产生重复目录）
    asyncio.run(init_app._ensure_ai_menu_groups())
    menus2 = _fetch_menus()
    assert len(menus2) == len(menus)


def test_ai_menus_collapsed(test_client):
    """_ensure_ai_menus 后：控制台页可见并落地，富功能页保留，下线页 hidden。"""
    _ensure_removed_rows_visible()
    asyncio.run(init_app._ensure_ai_menus())
    menus = _fetch_menus()

    for rname in REMOVED:
        assert rname in menus, f"缺少待隐藏菜单 {rname}"
        assert menus[rname].hidden is True, f"{rname} 未被隐藏"
    for rname in KEPT + RICH_KEPT:
        assert rname in menus, f"缺少保留菜单 {rname}"
        assert menus[rname].hidden is False, f"{rname} 被误隐藏"
    assert menus["AI"].redirect == "/ai/overview"
    # Chat 独立页已下线（前端 module_ai/chat/index 已删除）：随 REMOVED 统一隐藏
    assert menus["Chat"].hidden is True


def test_ai_button_perms_keep_provider_report():
    """按钮权限保留 provider/report，且包含核心 model/prompt/tool/app/assistant。"""
    perms = {code for code, _ in init_app.AI_BUTTON_PERMS}
    assert any(code.startswith("module_ai:provider:") for code in perms)
    for code in (
        "module_ai:model:query",
        "module_ai:prompt:create",
        "module_ai:tool:query",
        "module_ai:app:query",
        "module_ai:assistant:query",
        "module_ai:agent:query",
        "module_ai:workflow:query",
    ):
        assert code in perms


def _ensure_legacy_merged_state() -> None:
    """把四个功能页置为『合并工作台』遗留状态（hidden + redirect 到工作台页签，智能问数指向工作台容器）：
    行存在则更新，不存在则插入（模拟当前存量库），验证 _ensure_ai_menus 会迁移为独立菜单目录。"""
    from sqlalchemy import select

    from app.api.v1.module_system.menu.model import MenuModel
    from app.core.database import async_db_session

    # 历史定义（component 为独立页面路径；insert 时用，update 时直接覆盖为 legacy 状态）
    LEGACY = {
        "AiIntegration": ("数据与集成", "/ai/integration", "module_ai/integration/index", 21, "el-icon-Connection"),
        "AiEval": ("问数评测", "/ai/eval", "module_ai/eval/index", 34, "el-icon-DataAnalysis"),
        "AiQueryReports": ("自定义报表", "/ai/query/reports", "module_ai/query/reports", 35, "el-icon-Tickets"),
        "AiAsset": ("数据资产", "/ai/asset", "module_ai/asset/index", 24, "el-icon-DataBoard"),
    }

    async def _run() -> None:
        async with async_db_session() as db:
            async with db.begin():
                parent = await db.scalar(
                    select(MenuModel).where(
                        MenuModel.route_name == "AI", MenuModel.type == 1
                    )
                )
                assert parent is not None, "AI 父菜单不存在（种子数据未初始化）"
                for rname, (title, rpath, comp, order, icon) in LEGACY.items():
                    row = await db.scalar(
                        select(MenuModel).where(MenuModel.route_name == rname)
                    )
                    if not row:
                        row = MenuModel(
                            name=title,
                            type=2,
                            icon=icon,
                            order=order,
                            route_name=rname,
                            route_path=rpath,
                            component_path=comp,
                            permission="module_ai:query:ask",
                            parent_id=parent.id,
                            status="0",
                            is_deleted=False,
                            hidden=False,
                            title=title,
                        )
                        db.add(row)
                        await db.flush()
                    row.hidden = True
                    row.redirect = {
                        "AiIntegration": "/ai/query?tab=integration",
                        "AiEval": "/ai/query?tab=eval",
                        "AiQueryReports": "/ai/query?tab=reports",
                        "AiAsset": "/ai/query?tab=integration",
                    }[rname]
                    row.component_path = comp
                ask = await db.scalar(
                    select(MenuModel).where(MenuModel.route_name == "AiQuery")
                )
                if not ask:
                    ask = MenuModel(
                        name="智能问数",
                        type=2,
                        icon="el-icon-ChatDotRound",
                        order=33,
                        route_name="AiQuery",
                        route_path="/ai/query",
                        component_path="module_ai/query/workspace",
                        permission="module_ai:query:ask",
                        parent_id=parent.id,
                        status="0",
                        is_deleted=False,
                        hidden=False,
                        title="智能问数",
                    )
                    db.add(ask)
                    await db.flush()
                ask.component_path = "module_ai/query/workspace"
                ask.hidden = False
                ask.redirect = None

    asyncio.run(_run())


def test_ai_menus_query_group(test_client):
    """_ensure_ai_menus 后：『智能问数』成为独立目录，下挂 4 个可见子菜单（各自独立页面），
    数据资产仍隐藏并重定向到数据与集成；迁移幂等。"""
    _ensure_legacy_merged_state()
    asyncio.run(init_app._ensure_ai_menus())
    menus = _fetch_menus()

    group = menus.get(QUERY_GROUP)
    assert group is not None, "缺少『智能问数』目录"
    assert group.type == 1, "目录应为 type=1"
    assert group.hidden is False, "目录不应隐藏"
    assert group.parent_id == menus["AI"].id, "目录应挂在 AI 父菜单下"
    # type=1 目录硬性要求：route_path 与 redirect 均非空（MenuOutSchema 输出校验强制；
    # 为空会让 current/info 500 → 前端菜单/动态路由全挂，实测踩过）
    assert group.route_path == "/ai/query", "目录 route_path 应为 /ai/query（与默认子菜单一致）"
    assert group.redirect == "/ai/query", "目录必须有 redirect（type=1 输出校验要求）"

    for rname, (comp, rpath, _order) in QUERY_GROUP_MENUS.items():
        row = menus[rname]
        assert row.hidden is False, f"{rname} 应可见"
        assert row.parent_id == group.id, f"{rname} 应挂在『智能问数』目录下"
        assert row.component_path == comp, f"{rname} component 应为 {comp}"
        assert row.route_path == rpath, f"{rname} path 应为 {rpath}"
        assert row.redirect is None, f"{rname} 不应有 redirect"

    asset = menus["AiAsset"]
    assert asset.hidden is True, "数据资产应保持隐藏"
    assert asset.redirect == "/ai/integration", "数据资产应重定向到数据与集成"

    # 关键回归：MenuOutSchema 继承 MenuCreateSchema，输出时同样跑 menu_request_validator；
    # 目录 route_path/redirect 为空会让 GET /system/user/current/info 500（真实事故），
    # 这里要求目录与子菜单都能通过输出序列化。
    from app.api.v1.module_system.menu.schema import MenuOutSchema

    for rname in [QUERY_GROUP, *QUERY_GROUP_MENUS.keys(), "AiAsset"]:
        MenuOutSchema.model_validate(menus[rname])  # 不抛即通过

    # 幂等：再跑一次不报错、目录不重复创建
    asyncio.run(init_app._ensure_ai_menus())
    menus2 = _fetch_menus()
    assert menus2[QUERY_GROUP].id == group.id


def test_develop_menu_registered(test_client):
    """_ensure_develop_menus 后：AI 集成菜单落地且可见，按钮权限已注册。"""
    asyncio.run(init_app._ensure_develop_menus())
    menus = _fetch_menus()
    m = menus["AiDevelop"]
    assert m.hidden is False and m.route_path == "/ai/develop"
    assert m.component_path == "module_ai/develop/index"
    assert m.permission == "module_ai:develop:query"
    perms = {c for c, _ in init_app.AI_BUTTON_PERMS}
    assert {
        "module_ai:develop:query",
        "module_ai:develop:create",
        "module_ai:develop:update",
        "module_ai:develop:delete",
        "module_ai:develop:reset",
    } <= perms
