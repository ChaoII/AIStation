"""视频模块敏感端点越权测试（审计 #9）。

覆盖：
- ``/video/alarm/record/realtime`` 必须要求 ``module_video:alarm:query``；
- ``/video/preview/urls/{id}``、``/video/preview/snap/{id}`` 必须要求 ``module_video:camera:query``；
- 无任何菜单权限的受限用户访问上述端点 → 403；
- 管理员访问不受影响（不返回 403），保证向后兼容。
"""
import uuid

_SENSITIVE_PATHS = [
    "/api/v1/video/alarm/record/realtime",
    "/api/v1/video/preview/urls/1",
    "/api/v1/video/preview/snap/1",
]


def _create_limited_principal(test_client, auth_headers) -> dict:
    """经管理接口创建一个“无任何菜单权限”的用户，返回其 Bearer 请求头。"""
    suffix = uuid.uuid4().hex[:8]
    role = test_client.post(
        "/api/v1/system/role/create",
        headers=auth_headers,
        json={
            "name": f"pytest-limited-{suffix}",
            "code": f"LIM{suffix}",
            "order": 999,
            "data_scope": 1,
            "status": "0",
        },
    )
    assert role.status_code == 200, role.text
    role_id = role.json()["data"]["id"]

    username = f"limited{suffix}"
    user = test_client.post(
        "/api/v1/system/user/create",
        headers=auth_headers,
        json={
            "username": username,
            "name": "受限用户",
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
    token = login.json()["data"]["access_token"]
    return {"Authorization": f"Bearer {token}", "X-Forwarded-For": "127.0.0.1"}


def test_sensitive_endpoints_reject_user_without_permission(test_client, auth_headers):
    """无权限用户访问 preview/realtime 一律 403，而不是放行或 500。"""
    limited_headers = _create_limited_principal(test_client, auth_headers)
    for path in _SENSITIVE_PATHS:
        resp = test_client.get(path, headers=limited_headers)
        assert resp.status_code == 403, f"{path} → {resp.status_code}: {resp.text}"


def test_sensitive_endpoints_allow_admin(test_client, auth_headers):
    """管理员仍可访问（不因新增权限点而回归 403）。"""
    for path in _SENSITIVE_PATHS:
        resp = test_client.get(path, headers=auth_headers)
        assert resp.status_code != 403, f"{path} 误拒管理员: {resp.text}"
