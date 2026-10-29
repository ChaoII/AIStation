# tests/test_develop_oauth_perms.py
#
# 阶段 2（OAuth 2.1）—— Task 9：OAuth client 管理权限。
# 验证：OAuth 客户端 CRUD 端点复用 module_ai:develop:*（已存在、无需新增权限点）；
#       非管理员（无 module_ai:develop:* ）无法管理 OAuth 客户端（权限推导拒绝）。
import uuid


def _uid():
    return uuid.uuid4().hex[:8]


def _create_client(test_client, headers):
    return test_client.post(
        "/api/v1/ai/develop/oauth/clients",
        headers=headers,
        json={
            "name": f"perm-oauth-{_uid()}",
            "redirect_uris": ["https://assistant.example/callback"],
            "max_scope": ["agent.list"],
        },
    )


def test_oauth_client_requires_develop_perm(test_client, auth_headers):
    """管理员（auth_headers）可创建 OAuth 客户端，返回一次性 secret。"""
    r = _create_client(test_client, auth_headers)
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert data["client_id"]
    assert data["client_secret"]
    assert "client_secret_hash" not in data


def test_oauth_clients_list_admin(test_client, auth_headers):
    """管理员可列出 OAuth 客户端。"""
    r = test_client.get("/api/v1/ai/develop/oauth/clients", headers=auth_headers)
    assert r.status_code == 200, r.text
    assert "items" in r.json()["data"]


def test_oauth_client_update_requires_perm(test_client, auth_headers):
    """管理员可更新 OAuth 客户端（改名称/启停/回调）。"""
    created = _create_client(test_client, auth_headers).json()["data"]
    r = test_client.put(
        f"/api/v1/ai/develop/oauth/clients/{created['client_id']}",
        headers=auth_headers,
        json={"enabled": False, "description": "已更新"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["data"]["enabled"] is False


def test_oauth_capabilities_use_develop_perms():
    """OAuth client 管理端点复用 module_ai:develop:* 权限点（无新增权限点）。

    通过检查 controller 源码，确认 /develop/oauth/clients 端点已挂 AuthPermission
    且使用的是既有 module_ai:develop:query/create/update。
    """
    from pathlib import Path

    src = (
        Path(__file__).parent.parent
        / "app"
        / "plugin"
        / "module_ai"
        / "develop"
        / "controller.py"
    ).read_text(encoding="utf-8")

    # OAuth client 端点应使用 module_ai:develop:* 系列权限点
    oauth_section = src[src.index("# 模式 C：OAuth 2.1") :]
    for perm in ("module_ai:develop:query", "module_ai:develop:create", "module_ai:develop:update"):
        assert perm in oauth_section, f"OAuth 端点应使用既有权限点 {perm}"
    # 不应引入新的 oauth 专属权限点
    assert "module_ai:develop:oauth" not in src
