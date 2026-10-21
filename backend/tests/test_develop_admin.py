# tests/test_develop_admin.py
#
# 覆盖 AI 集成开放平台「内部管理面」DevelopRouter（Task 6）：
# - ``GET /api/v1/ai/develop/list``：分页列出应用，返回 ``items``；
# - ``POST /api/v1/ai/develop/create``：创建应用，仅返回一次明文 appkey；
# - ``POST /api/v1/ai/develop/reset-key/{id}``：重置 appkey，返回新明文。
#
# 说明：仓库未启用 pytest-asyncio，HTTP 统一用**同步** ``test_client`` 夹具
# （见 conftest.py，会话级）；``auth_headers`` 为 admin 登录头。``AuthPermission``
# 对超管直接放行——admin 在种子数据里 ``is_superuser=true``，因此无需额外给
# admin 授 ``module_ai:develop:query`` 权限即可通过（若 admin 非超管才需补权限）。
# 依赖 test_client 触发应用生命周期（建表），PYTEST_NO_APP=1 时这些用例自动 skip。
import pytest


@pytest.mark.app
def test_admin_list_requires_perm(test_client, auth_headers: dict):
    # admin 登录头；确保 admin 有 module_ai:develop:query（超管绕过或已授权）
    resp = test_client.get("/api/v1/ai/develop/list", headers=auth_headers)
    assert resp.status_code == 200
    assert "items" in resp.json()["data"]


@pytest.mark.app
def test_admin_create_and_reset(test_client, auth_headers: dict):
    resp = test_client.post(
        "/api/v1/ai/develop/create",
        json={"name": "外部客户", "capabilities": ["integration:agent:create"]},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    assert "appkey" in resp.json()["data"]
    rid = resp.json()["data"]["id"]
    r2 = test_client.post(f"/api/v1/ai/develop/reset-key/{rid}", headers=auth_headers)
    assert r2.status_code == 200 and "appkey" in r2.json()["data"]


@pytest.mark.app
def test_admin_manage_and_audit_endpoints(test_client, auth_headers: dict):
    # 覆盖其余管理面端点：detail / update / toggle / delete / call-logs / mcp-sessions，
    # 确认这些端点已注册且鉴权放行（admin 为超管）。
    resp = test_client.post(
        "/api/v1/ai/develop/create",
        json={"name": "管理面冒烟", "capabilities": ["integration:chat:send"]},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    rid = resp.json()["data"]["id"]

    # 详情
    d = test_client.get(f"/api/v1/ai/develop/detail/{rid}", headers=auth_headers)
    assert d.status_code == 200 and d.json()["data"]["id"] == rid

    # 更新
    u = test_client.put(
        f"/api/v1/ai/develop/update/{rid}",
        json={"description": "冒烟更新"},
        headers=auth_headers,
    )
    assert u.status_code == 200 and u.json()["data"]["description"] == "冒烟更新"

    # 启停（关闭）
    t = test_client.put(
        f"/api/v1/ai/develop/toggle/{rid}", json={"enabled": False}, headers=auth_headers
    )
    assert t.status_code == 200 and t.json()["data"]["enabled"] is False

    # 审计查询：调用日志（分页/字段齐全）与 MCP 会话（分页）
    cl = test_client.get(
        "/api/v1/ai/develop/call-logs", params={"app_id": rid}, headers=auth_headers
    )
    assert cl.status_code == 200 and "items" in cl.json()["data"]
    ms = test_client.get(
        "/api/v1/ai/develop/mcp-sessions", params={"app_id": rid}, headers=auth_headers
    )
    assert ms.status_code == 200 and "items" in ms.json()["data"]

    # 批量删除（DELETE 带 body 用显式 request 传 json）
    r = test_client.request(
        "DELETE", "/api/v1/ai/develop/delete", json=[rid], headers=auth_headers
    )
    assert r.status_code == 200
    # 删除后详情返回错误（已软删）
    d2 = test_client.get(f"/api/v1/ai/develop/detail/{rid}", headers=auth_headers)
    assert d2.status_code == 400
