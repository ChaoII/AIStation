"""MCP 服务器管理 API 测试。"""
import asyncio
import uuid

from sqlalchemy import select

from app.api.v1.module_system.user.model import UserModel
from app.core.database import async_db_session


def _new_name(prefix: str = "pytest_mcp") -> str:
    return f"{prefix}_{uuid.uuid4().hex[:8]}"


def _create_mcp(test_client, auth_headers, **overrides) -> int:
    payload = {
        "name": _new_name(),
        "transport": "streamable-http",
        "url": "http://127.0.0.1:9/mcp",
        "auth_type": "none",
        "enabled": True,
        "description": "测试用 MCP",
    }
    payload.update(overrides)
    r = test_client.post("/api/v1/ai/mcp/create", json=payload, headers=auth_headers)
    assert r.status_code == 200, r.text
    return r.json()["data"]["id"]


def _promote_superuser(user_id: int) -> None:
    async def _go():
        async with async_db_session.begin() as db:
            user = await db.get(UserModel, user_id)
            user.is_superuser = True

    asyncio.run(_go())


def _make_superuser(test_client, auth_headers, tag: str) -> tuple[dict, int]:
    suffix = uuid.uuid4().hex[:8]
    role = test_client.post(
        "/api/v1/system/role/create",
        headers=auth_headers,
        json={
            "name": f"pytest-mcp-{tag}-{suffix}",
            "code": f"MCP{tag}{suffix}"[:20],
            "order": 999,
            "data_scope": 1,
            "status": "0",
        },
    )
    role_id = role.json()["data"]["id"]
    username = f"mcpu{tag}{suffix}"
    user = test_client.post(
        "/api/v1/system/user/create",
        headers=auth_headers,
        json={
            "username": username,
            "name": f"MCP用户{tag}",
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
    return (
        {
            "Authorization": f"Bearer {login.json()['data']['access_token']}",
            "X-Forwarded-For": "127.0.0.1",
        },
        user_id,
    )


def test_mcp_crud_and_toggle(test_client, auth_headers):
    """创建→列表→编辑→启停→删除。"""
    sid = _create_mcp(test_client, auth_headers)
    rows = test_client.get("/api/v1/ai/mcp/list", headers=auth_headers).json()["data"]
    row = next(r for r in rows if r["id"] == sid)
    assert row["transport"] == "streamable-http"
    assert row["enabled"] is True

    upd = test_client.put(
        f"/api/v1/ai/mcp/update/{sid}",
        json={"description": "改过了", "auth_type": "bearer"},
        headers=auth_headers,
    )
    assert upd.json()["data"]["description"] == "改过了"
    assert upd.json()["data"]["auth_type"] == "bearer"

    off = test_client.put(
        f"/api/v1/ai/mcp/toggle/{sid}", json={"enabled": False}, headers=auth_headers
    )
    assert off.json()["data"]["enabled"] is False

    dele = test_client.request(
        "DELETE", "/api/v1/ai/mcp/delete", json=[sid], headers=auth_headers
    )
    assert dele.status_code == 200
    rows2 = test_client.get("/api/v1/ai/mcp/list", headers=auth_headers).json()["data"]
    assert not any(r["id"] == sid for r in rows2)


def test_mcp_name_duplicate_rejected(test_client, auth_headers):
    """同名服务器被拒。"""
    name = _new_name()
    _create_mcp(test_client, auth_headers, name=name)
    r = test_client.post(
        "/api/v1/ai/mcp/create",
        json={"name": name, "transport": "streamable-http", "url": "http://x.test/mcp"},
        headers=auth_headers,
    )
    assert r.status_code != 200
    assert "已存在" in r.json()["msg"]


def test_mcp_stdio_requires_command(test_client, auth_headers):
    """stdio 方式必须填命令。"""
    r = test_client.post(
        "/api/v1/ai/mcp/create",
        json={"name": _new_name(), "transport": "stdio", "command": ""},
        headers=auth_headers,
    )
    assert r.status_code != 200
    assert "启动命令" in r.json()["msg"]


def test_mcp_http_requires_url(test_client, auth_headers):
    """http 方式必须填地址。"""
    r = test_client.post(
        "/api/v1/ai/mcp/create",
        json={"name": _new_name(), "transport": "sse", "url": ""},
        headers=auth_headers,
    )
    assert r.status_code != 200
    assert "服务地址" in r.json()["msg"]


def test_mcp_test_unreachable_returns_false(test_client, auth_headers):
    """不可达地址返回 reachable=false，不抛异常。"""
    sid = _create_mcp(test_client, auth_headers, url="http://127.0.0.1:9/mcp")
    r = test_client.post(f"/api/v1/ai/mcp/test/{sid}", headers=auth_headers)
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert data["reachable"] is False
    assert data["detail"]


def test_mcp_test_stdio_command_probe(test_client, auth_headers):
    """stdio：不存在的命令不可达；python 可执行命令可达。"""
    bad = _create_mcp(
        test_client, auth_headers, transport="stdio", command="definitely-not-a-command-xyz"
    )
    rb = test_client.post(f"/api/v1/ai/mcp/test/{bad}", headers=auth_headers).json()["data"]
    assert rb["reachable"] is False

    good = _create_mcp(test_client, auth_headers, transport="stdio", command="python")
    rg = test_client.post(f"/api/v1/ai/mcp/test/{good}", headers=auth_headers).json()["data"]
    assert rg["reachable"] is True


def test_mcp_list_isolated_per_user(test_client, auth_headers):
    """MCP 配置按用户隔离：别人看不到我的服务器。"""
    sid = _create_mcp(test_client, auth_headers)
    other_headers, _uid = _make_superuser(test_client, auth_headers, "iso")
    rows = test_client.get("/api/v1/ai/mcp/list", headers=other_headers).json()["data"]
    assert not any(r["id"] == sid for r in rows)
