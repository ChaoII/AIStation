"""能力市场审计修复回归测试（H1–H4 / M1）。

每个用例对应一条**已实测确认**的缺陷，先于修复编写：
- H1 删除我的资产必须软删除；来源资产被删时商品一并下架；删除安装副本后解除安装关系并可重新安装；
- H2 审核中心「下架」= action=offline（approved → offline），且 offline 不能被再次审核通过；
- H3 商品详情不得把他人未上架商品（含 payload 源码）暴露给普通用户；
- H4 字符串值里内嵌的密钥必须脱敏（不能只在键名/列表元素上脱敏）；
- M1 启停/删除我的资产、接收/拒绝分享需要 market:manage，而不是 market:query；
- M6 删除资产（市场入口与目录页）必须同时摘除智能体的 tool/skill/mcp 绑定；
- M9 商品名去重按提交者隔离，不同用户可发布同名商品；
- H5 目录页（工具/技能/插件/MCP）删除必须是软删除，否则安装关系悬垂。
"""
import asyncio
import uuid

from sqlalchemy import select

from app.api.v1.module_system.menu.model import MenuModel
from app.api.v1.module_system.role.model import RoleMenusModel
from app.api.v1.module_system.user.model import UserModel
from app.core.database import async_db_session
from app.plugin.module_ai.agent.model import AiAgentModel
from app.plugin.module_ai.market.model import AiMarketItemModel, AiMarketRelationModel
from app.plugin.module_ai.market.service import _sanitize_payload
from app.plugin.module_ai.mcp.model import AiMcpServerModel
from app.plugin.module_ai.plugins.model import AiPluginModel
from app.plugin.module_ai.skill.model import AiSkillModel
from app.plugin.module_ai.tools_catalog.model import AiToolModel


def _new(prefix: str = "audit") -> str:
    return f"{prefix}_{uuid.uuid4().hex[:8]}"


def _admin_id() -> int:
    async def _go():
        async with async_db_session() as db:
            return (
                await db.execute(select(UserModel.id).where(UserModel.username == "admin"))
            ).scalar()
    return asyncio.run(_go())


def _seed_tool(name: str, owner_id: int) -> int:
    async def _go():
        async with async_db_session.begin() as db:
            row = AiToolModel(
                name=name, kind="http", source="http", method="GET",
                url="http://x.test/{q}", enabled=True, description="个人工具",
                created_id=owner_id, updated_id=owner_id,
            )
            db.add(row)
            await db.flush()
            return row.id
    return asyncio.run(_go())


def _seed_item(status: str = "approved", owner_id: int | None = None,
               payload: dict | None = None) -> int:
    async def _go():
        async with async_db_session.begin() as db:
            item = AiMarketItemModel(
                asset_type="tool", name=_new("item"), description="市场商品",
                status=status, owner_id=owner_id,
                payload=payload or {"name": _new("pl"), "kind": "http", "method": "GET",
                                    "url": "http://x.test/"},
                install_count=0, favorite_count=0,
            )
            db.add(item)
            await db.flush()
            return item.id
    return asyncio.run(_go())


def _tool_state(tool_id: int):
    """返回 (是否存在, is_deleted, deleted_time 是否非空, deleted_id)。"""
    async def _go():
        async with async_db_session() as db:
            row = await db.get(AiToolModel, tool_id)
            if row is None:
                return None
            return (True, bool(row.is_deleted), row.deleted_time is not None, row.deleted_id)
    return asyncio.run(_go())


def _deleted_state(model, rid: int):
    """通用：返回 (是否存在, is_deleted, deleted_id)，用于校验软删除。"""
    async def _go():
        async with async_db_session() as db:
            row = await db.get(model, rid)
            if row is None:
                return None
            return (True, bool(row.is_deleted), row.deleted_id)
    return asyncio.run(_go())


def _agent_bindings(agent_id: int):
    """返回 (tool_ids, skill_ids, mcp_ids)。"""
    async def _go():
        async with async_db_session() as db:
            a = await db.get(AiAgentModel, agent_id)
            return (list(a.tool_ids or []), list(a.skill_ids or []), list(a.mcp_ids or []))
    return asyncio.run(_go())


def _item_status(item_id: int):
    async def _go():
        async with async_db_session() as db:
            row = await db.get(AiMarketItemModel, item_id)
            return row.status if row else None
    return asyncio.run(_go())


def _installed_relations(item_id: int, user_id: int):
    """返回该用户对该商品的 installed 关系（含已软删），形如 [(id, is_deleted, description)]。"""
    async def _go():
        async with async_db_session() as db:
            rows = (await db.execute(
                select(AiMarketRelationModel).where(
                    AiMarketRelationModel.item_id == item_id,
                    AiMarketRelationModel.user_id == user_id,
                    AiMarketRelationModel.kind == "installed",
                )
            )).scalars().all()
            return [(r.id, bool(r.is_deleted), r.description) for r in rows]
    return asyncio.run(_go())


def _submit_and_approve(test_client, headers, tool_id: int, name: str | None = None) -> int:
    sub = test_client.post(
        "/api/v1/ai/market/submit", headers=headers,
        json={"asset_type": "tool", "source_id": tool_id, "name": name or _new("mk")},
    )
    assert sub.status_code == 200, sub.text
    item_id = sub.json()["data"]["id"]
    rev = test_client.post(
        "/api/v1/ai/market/review", headers=headers,
        json={"item_id": item_id, "action": "approve"},
    )
    assert rev.status_code == 200, rev.text
    return item_id


def _make_user(test_client, auth_headers, perms: list[str], tag: str = "u"):
    """创建只持有指定按钮权限的用户，返回 (headers, user_id, role_id)。"""
    suffix = uuid.uuid4().hex[:8]
    role = test_client.post(
        "/api/v1/system/role/create", headers=auth_headers,
        json={"name": f"audit-{tag}-{suffix}", "code": f"AU{tag.upper()}{suffix}"[:20],
              "order": 999, "data_scope": 1, "status": "0"},
    )
    assert role.status_code == 200, role.text
    role_id = role.json()["data"]["id"]
    username = f"audit{tag}{suffix}"
    user = test_client.post(
        "/api/v1/system/user/create", headers=auth_headers,
        json={"username": username, "name": "审计用户", "password": "123456",
              "status": "0", "role_ids": [role_id]},
    )
    assert user.status_code == 200, user.text
    user_id = user.json()["data"]["id"]
    _grant(role_id, perms)
    login = test_client.post(
        "/api/v1/system/auth/login",
        data={"username": username, "password": "123456"},
        headers={"X-Forwarded-For": "127.0.0.1"},
    )
    assert login.status_code == 200, login.text
    return ({"Authorization": f"Bearer {login.json()['data']['access_token']}",
             "X-Forwarded-For": "127.0.0.1"}, user_id, role_id)


def _grant(role_id: int, perms: list[str]) -> None:
    async def _go():
        async with async_db_session.begin() as db:
            for perm in perms:
                menu = (await db.execute(
                    select(MenuModel).where(MenuModel.permission == perm)
                )).scalar()
                assert menu is not None, f"权限码未注册：{perm}"
                exists = await db.scalar(
                    select(RoleMenusModel).where(
                        RoleMenusModel.role_id == role_id,
                        RoleMenusModel.menu_id == menu.id,
                    )
                )
                if not exists:
                    db.add(RoleMenusModel(role_id=role_id, menu_id=menu.id))
    asyncio.run(_go())


# ---------------- H1 软删除与市场联动 ----------------

def test_delete_source_asset_soft_deletes_and_offlines_item(test_client, auth_headers):
    """删除已上架资产的来源行：软删除 + 对应商品自动下架（不再可安装）。"""
    admin = _admin_id()
    tool_id = _seed_tool(_new("del_src"), admin)
    item_id = _submit_and_approve(test_client, auth_headers, tool_id)

    r = test_client.delete(f"/api/v1/ai/market/mine/tool/{tool_id}", headers=auth_headers)
    assert r.status_code == 200, r.text

    state = _tool_state(tool_id)
    assert state is not None, "必须是软删除：行仍应存在"
    assert state[1] is True
    assert state[2] is True
    assert state[3] == admin

    assert _item_status(item_id) == "offline"
    inst = test_client.post(f"/api/v1/ai/market/items/{item_id}/install", headers=auth_headers)
    assert inst.status_code != 200


def test_delete_installed_copy_clears_relation_and_allows_reinstall(test_client, auth_headers):
    """删除安装副本：解除 installed 关系，市场不再显示已安装，且可重新安装。"""
    # 由另一个用户安装，才会真正复制出「副本」（本人安装会按同名复用来源行）
    headers_b, uid_b, _ = _make_user(
        test_client, auth_headers,
        ["module_ai:market:query", "module_ai:market:install", "module_ai:market:manage"],
        tag="cp",
    )
    tool_id = _seed_tool(_new("del_copy_src"), _admin_id())
    item_id = _submit_and_approve(test_client, auth_headers, tool_id)
    inst = test_client.post(f"/api/v1/ai/market/items/{item_id}/install", headers=headers_b)
    copy_id = inst.json()["data"]["real_id"]
    assert copy_id != tool_id
    mine = test_client.get(
        "/api/v1/ai/market/mine", params={"asset_type": "tool"}, headers=headers_b
    ).json()["data"]
    assert any(row["real_id"] == copy_id for row in mine["items"]), "副本必须属于安装者"

    r = test_client.delete(f"/api/v1/ai/market/mine/tool/{copy_id}", headers=headers_b)
    assert r.status_code == 200, r.text

    assert _tool_state(copy_id)[1] is True
    rels = _installed_relations(item_id, uid_b)
    assert rels and all(rel[1] is True for rel in rels), f"安装关系应解除：{rels}"
    assert _item_status(item_id) == "approved", "删除安装副本不应影响商品上架状态"

    d = test_client.get(f"/api/v1/ai/market/items/{item_id}", headers=headers_b).json()["data"]
    assert d["installed"] is False
    again = test_client.post(f"/api/v1/ai/market/items/{item_id}/install", headers=headers_b)
    assert again.status_code == 200, again.text
    assert again.json()["data"]["installed"] is True
    assert again.json()["data"]["real_id"] != copy_id


def test_dead_installed_copy_not_reported_installed(test_client, auth_headers):
    """从「工具管理」删除安装副本后，市场不能再显示「已安装」，且可重新安装。"""
    headers_b, uid_b, _ = _make_user(
        test_client, auth_headers,
        ["module_ai:market:query", "module_ai:market:install", "module_ai:tool:delete"],
        tag="dl",
    )
    tool_id = _seed_tool(_new("dead_src"), _admin_id())
    item_id = _submit_and_approve(test_client, auth_headers, tool_id)
    inst = test_client.post(f"/api/v1/ai/market/items/{item_id}/install", headers=headers_b)
    copy_id = inst.json()["data"]["real_id"]

    # 绕开市场，直接从工具管理删除副本（软删除）
    r = test_client.request(
        "DELETE", "/api/v1/ai/tools/delete", headers=headers_b, json=[copy_id]
    )
    assert r.status_code == 200, r.text
    assert _tool_state(copy_id)[1] is True

    d = test_client.get(f"/api/v1/ai/market/items/{item_id}", headers=headers_b).json()["data"]
    assert d["installed"] is False, "副本已删除时不能仍显示已安装"

    again = test_client.post(f"/api/v1/ai/market/items/{item_id}/install", headers=headers_b)
    assert again.status_code == 200, again.text
    assert again.json()["data"]["real_id"] != copy_id


def test_install_does_not_reuse_other_users_tool(test_client, auth_headers):
    """安装不能复用他人的同名工具，也不能把别人停用的工具顺手启用。"""
    admin = _admin_id()
    tool_name = _new("reuse_other")
    tool_id = _seed_tool(tool_name, admin)

    async def _disable():
        async with async_db_session.begin() as db:
            row = await db.get(AiToolModel, tool_id)
            row.enabled = False
    asyncio.run(_disable())

    item_id = _seed_item(
        "approved", owner_id=admin,
        payload={"name": tool_name, "kind": "http", "method": "GET", "url": "http://x.test/"},
    )
    headers_b, uid_b, _ = _make_user(
        test_client, auth_headers,
        ["module_ai:market:query", "module_ai:market:install"], tag="ru",
    )
    inst = test_client.post(f"/api/v1/ai/market/items/{item_id}/install", headers=headers_b)
    assert inst.status_code == 200, inst.text
    assert inst.json()["data"]["real_id"] != tool_id

    state = _tool_state(tool_id)
    assert state[1] is False, "他人的工具不能被删除"

    async def _enabled():
        async with async_db_session() as db:
            row = await db.get(AiToolModel, tool_id)
            return row.enabled
    assert asyncio.run(_enabled()) is False, "不能把他人停用的工具顺手启用"


# ---------------- H2 管理员下架 ----------------

def test_review_offline_takes_approved_item_down(test_client, auth_headers):
    """已上架商品可被管理员下架（action=offline），下架后不可安装。"""
    item_id = _seed_item("approved", owner_id=_admin_id())
    r = test_client.post(
        "/api/v1/ai/market/review", headers=auth_headers,
        json={"item_id": item_id, "action": "offline", "remark": "违规下架"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["data"]["status"] == "offline"
    assert _item_status(item_id) == "offline"
    inst = test_client.post(f"/api/v1/ai/market/items/{item_id}/install", headers=auth_headers)
    assert inst.status_code != 200


def test_review_offline_requires_approved(test_client, auth_headers):
    """待审核商品不能直接下架。"""
    item_id = _seed_item("pending", owner_id=_admin_id())
    r = test_client.post(
        "/api/v1/ai/market/review", headers=auth_headers,
        json={"item_id": item_id, "action": "offline"},
    )
    assert r.status_code != 200
    assert _item_status(item_id) == "pending"


def test_offline_item_cannot_be_approved_again(test_client, auth_headers):
    """已撤回/下架的商品不能被再次审核通过（防止 owner 撤回后被复活）。"""
    item_id = _seed_item("offline", owner_id=_admin_id())
    r = test_client.post(
        "/api/v1/ai/market/review", headers=auth_headers,
        json={"item_id": item_id, "action": "approve"},
    )
    assert r.status_code != 200
    assert _item_status(item_id) == "offline"


# ---------------- H3 详情越权读 ----------------

def test_detail_hides_others_unapproved_item(test_client, auth_headers):
    """普通用户（market:query）不能读取他人待审商品；owner 与已上架商品不受影响。"""
    headers_plain, _, _ = _make_user(test_client, auth_headers,
                                    ["module_ai:market:query"], tag="dt")
    pending_id = _seed_item("pending", owner_id=_admin_id())
    approved_id = _seed_item("approved", owner_id=_admin_id())

    r = test_client.get(f"/api/v1/ai/market/items/{pending_id}", headers=headers_plain)
    assert r.status_code != 200, r.text
    owner = test_client.get(f"/api/v1/ai/market/items/{pending_id}", headers=auth_headers)
    assert owner.status_code == 200, owner.text
    ok = test_client.get(f"/api/v1/ai/market/items/{approved_id}", headers=headers_plain)
    assert ok.status_code == 200, ok.text


# ---------------- H4 字符串值脱敏 ----------------

def test_sanitize_redacts_secret_embedded_in_string_values():
    """内嵌在 webhook/URL 等字符串值里的密钥必须清掉，普通文本保持不变。"""
    payload = {
        "config": {
            "webhook": "https://hooks.slack.com/services/T000/B000/sk-abcdefgh12345",
            "note": "plain text",
        },
        "url": "https://api.x.com/v1?api_key=sk-livesecret123",
        "description": "正常描述",
    }
    out = _sanitize_payload(payload)
    assert "sk-abcdefgh12345" not in out["config"]["webhook"]
    assert out["config"]["webhook"].startswith("https://hooks.slack.com/services/T000/B000/")
    assert out["config"]["note"] == "plain text"
    assert "sk-livesecret123" not in out["url"]
    assert out["url"] == "https://api.x.com/v1?api_key="
    assert out["description"] == "正常描述"


def test_sanitize_does_not_mangle_markup_in_skill_content():
    """技能正文里的 HTML/占位符片段不能被误当令牌清空。"""
    payload = {"content": "示例：<div>hello</div> 与 <YOUR_KEY>", "config": {"token": "abc"}}
    out = _sanitize_payload(payload)
    assert out["content"] == "示例：<div>hello</div> 与 <YOUR_KEY>"
    assert out["config"]["token"] == ""


# ---------------- M1 写操作权限 ----------------

def test_toggle_and_delete_require_manage_permission(test_client, auth_headers):
    """只有 market:query 的用户不能启停/删除真实资产；授予 market:manage 后才可。"""
    headers_plain, uid, role_id = _make_user(
        test_client, auth_headers,
        ["module_ai:market:query"], tag="mg",
    )
    tool_id = _seed_tool(_new("perm_tool"), uid)

    denied = test_client.delete(f"/api/v1/ai/market/mine/tool/{tool_id}", headers=headers_plain)
    assert denied.status_code == 403, denied.text
    denied_toggle = test_client.put(
        f"/api/v1/ai/market/mine/tool/{tool_id}/toggle",
        params={"enabled": False}, headers=headers_plain,
    )
    assert denied_toggle.status_code == 403, denied_toggle.text

    _grant(role_id, ["module_ai:market:manage"])
    allowed = test_client.delete(f"/api/v1/ai/market/mine/tool/{tool_id}", headers=headers_plain)
    assert allowed.status_code == 200, allowed.text


def test_accept_share_requires_manage_permission(test_client, auth_headers):
    """接收分享会复制真实资产，同样需要 market:manage。"""
    headers_plain, uid, role_id = _make_user(
        test_client, auth_headers,
        ["module_ai:market:query"], tag="ac",
    )
    item_id = _seed_item("approved", owner_id=_admin_id())
    share = test_client.post(
        "/api/v1/ai/market/shares/share", headers=auth_headers,
        json={"item_id": item_id, "to_user_id": uid},
    )
    assert share.status_code == 200, share.text
    share_id = share.json()["data"]["id"]

    denied = test_client.post(f"/api/v1/ai/market/shares/{share_id}/accept", headers=headers_plain)
    assert denied.status_code == 403, denied.text

    _grant(role_id, ["module_ai:market:manage"])
    allowed = test_client.post(f"/api/v1/ai/market/shares/{share_id}/accept", headers=headers_plain)
    assert allowed.status_code == 200, allowed.text


# ---------------- H5 目录页删除必须是软删除 ----------------

def test_catalog_delete_is_soft_for_all_asset_types(test_client, auth_headers):
    """工具/技能/插件/MCP 的删除必须保留行（软删除），否则市场安装关系会悬垂。"""
    admin = _admin_id()

    tool_name = _new("soft_tool")
    tool_id = _seed_tool(tool_name, admin)
    skill_name = _new("soft_skill")
    skill = test_client.post(
        "/api/v1/ai/skills/create",
        json={"name": skill_name, "content": "内容", "skill_type": "instruction"},
        headers=auth_headers,
    )
    assert skill.status_code == 200, skill.text
    skill_id = skill.json()["data"]["id"]
    plugin_key = _new("soft_plugin")
    plugin = test_client.post(
        "/api/v1/ai/plugins/create",
        json={"key": plugin_key, "label": "软删插件", "kind": "custom"},
        headers=auth_headers,
    )
    assert plugin.status_code == 200, plugin.text
    plugin_id = plugin.json()["data"]["id"]
    mcp_name = _new("soft_mcp")
    mcp = test_client.post(
        "/api/v1/ai/mcp/create",
        json={"name": mcp_name, "transport": "streamable-http",
              "url": "http://127.0.0.1:9/mcp", "auth_type": "none"},
        headers=auth_headers,
    )
    assert mcp.status_code == 200, mcp.text
    mcp_id = mcp.json()["data"]["id"]

    cases = [
        ("/api/v1/ai/tools/delete", tool_id, AiToolModel),
        ("/api/v1/ai/skills/delete", skill_id, AiSkillModel),
        ("/api/v1/ai/plugins/delete", plugin_id, AiPluginModel),
        ("/api/v1/ai/mcp/delete", mcp_id, AiMcpServerModel),
    ]
    for url, rid, model in cases:
        r = test_client.request("DELETE", url, json=[rid], headers=auth_headers)
        assert r.status_code == 200, r.text
        state = _deleted_state(model, rid)
        assert state is not None, f"{url} 把行物理删除了"
        assert state[1] is True, f"{url} 未标记 is_deleted"
        assert state[2] == admin, f"{url} 未记录 deleted_id"

    # 软删除不能占用唯一约束：同名/同 key 必须可以重新创建
    again = test_client.post(
        "/api/v1/ai/skills/create",
        json={"name": skill_name, "content": "内容", "skill_type": "instruction"},
        headers=auth_headers,
    )
    assert again.status_code == 200, again.text
    again_plugin = test_client.post(
        "/api/v1/ai/plugins/create",
        json={"key": plugin_key, "label": "软删插件2", "kind": "custom"},
        headers=auth_headers,
    )
    assert again_plugin.status_code == 200, again_plugin.text


# ---------------- M6 删除资产时清理智能体绑定 ----------------

def test_delete_assets_detaches_agent_bindings(test_client, auth_headers):
    """市场删除与目录页删除都必须把资产从智能体绑定里摘掉（避免悬空绑定）。"""
    tool_name = _new("bind_tool")
    tool_id = _seed_tool(tool_name, _admin_id())
    skill = test_client.post(
        "/api/v1/ai/skills/create",
        json={"name": _new("bind_skill"), "content": "内容", "skill_type": "instruction"},
        headers=auth_headers,
    )
    assert skill.status_code == 200, skill.text
    skill_id = skill.json()["data"]["id"]
    mcp = test_client.post(
        "/api/v1/ai/mcp/create",
        json={"name": _new("bind_mcp"), "transport": "streamable-http",
              "url": "http://127.0.0.1:9/mcp", "auth_type": "none"},
        headers=auth_headers,
    )
    assert mcp.status_code == 200, mcp.text
    mcp_id = mcp.json()["data"]["id"]

    agent = test_client.post(
        "/api/v1/ai/agents/create",
        json={"agent_name": _new("bind_agent"), "tool_ids": [tool_name],
              "skill_ids": [skill_id], "mcp_ids": [mcp_id], "enabled": True},
        headers=auth_headers,
    )
    assert agent.status_code == 200, agent.text
    agent_id = agent.json()["data"]["id"]
    assert _agent_bindings(agent_id) == ([tool_name], [skill_id], [mcp_id])

    # 市场入口删除工具
    r = test_client.delete(f"/api/v1/ai/market/mine/tool/{tool_id}", headers=auth_headers)
    assert r.status_code == 200, r.text
    tools, _, _ = _agent_bindings(agent_id)
    assert tools == [], "工具删除后智能体不应再绑定它"

    # 市场删除也必须释放唯一名，否则同名工具无法重建
    recreated = test_client.post(
        "/api/v1/ai/tools/create",
        json={"name": tool_name, "kind": "http", "method": "GET",
              "url": "http://127.0.0.1:9/echo", "enabled": True},
        headers=auth_headers,
    )
    assert recreated.status_code == 200, recreated.text

    # 目录页删除技能
    r = test_client.request(
        "DELETE", "/api/v1/ai/skills/delete", json=[skill_id], headers=auth_headers
    )
    assert r.status_code == 200, r.text
    _, skills, _ = _agent_bindings(agent_id)
    assert skills == [], "技能删除后智能体不应再绑定它"

    # 目录页删除 MCP
    r = test_client.request(
        "DELETE", "/api/v1/ai/mcp/delete", json=[mcp_id], headers=auth_headers
    )
    assert r.status_code == 200, r.text
    _, _, mcps = _agent_bindings(agent_id)
    assert mcps == [], "MCP 删除后智能体不应再绑定它"


# ---------------- M9 商品名去重按提交者隔离 ----------------

def test_submit_same_name_allowed_across_owners(test_client, auth_headers):
    """不同用户可以发布同名商品；同一用户重复提交仍拒绝。"""
    market_name = _new("dup_market")
    admin_tool = _seed_tool(_new("dup_tool_admin"), _admin_id())
    _submit_and_approve(test_client, auth_headers, admin_tool, name=market_name)

    headers_b, _, _ = _make_user(
        test_client, auth_headers,
        ["module_ai:market:query", "module_ai:market:submit", "module_ai:tool:create"],
        tag="dup",
    )
    own_tool = test_client.post(
        "/api/v1/ai/tools/create",
        json={"name": _new("dup_tool_b"), "kind": "http", "method": "GET",
              "url": "http://127.0.0.1:9/echo", "enabled": True},
        headers=headers_b,
    )
    assert own_tool.status_code == 200, own_tool.text
    own_id = own_tool.json()["data"]["id"]

    payload = {"asset_type": "tool", "source_id": own_id, "name": market_name}
    sub = test_client.post("/api/v1/ai/market/submit", headers=headers_b, json=payload)
    assert sub.status_code == 200, sub.text

    again = test_client.post("/api/v1/ai/market/submit", headers=headers_b, json=payload)
    assert again.status_code != 200, "同一提交者重复提交同名商品仍应拒绝"


# ---------------- 分享：未上架商品仅提交者可见 ----------------

def test_share_unapproved_item_requires_owner(test_client, auth_headers):
    """非提交者不能通过分享接口窥探未上架商品的名称/描述。"""
    tool_id = _seed_tool(_new("share_pending_tool"), _admin_id())
    sub = test_client.post(
        "/api/v1/ai/market/submit",
        headers=auth_headers,
        json={"asset_type": "tool", "source_id": tool_id, "name": _new("share_pending")},
    )
    assert sub.status_code == 200, sub.text
    item_id = sub.json()["data"]["id"]

    headers_b, _, _ = _make_user(
        test_client,
        auth_headers,
        ["module_ai:market:query", "module_ai:market:share"],
        tag="shnp",
    )
    r = test_client.post(
        "/api/v1/ai/market/shares/share",
        headers=headers_b,
        json={"item_id": item_id, "to_user_id": _admin_id()},
    )
    assert r.status_code != 200, "非提交者不应能分享未上架商品"
