"""边缘任务快照代理路由测试。"""
from uuid import uuid4

from app.api.v1.module_video.edge.agent_client import EdgeAgentClient

_FAKE_JPEG = b"\xff\xd8\xff\xe0fake-jpeg"


def _fake_fetch(self, task_id, timeout=5.0):
    """异步打桩：不触网，直接返回假 JPEG。"""
    async def _coro() -> bytes:
        return _FAKE_JPEG
    return _coro()


def test_snapshot_proxy_returns_jpeg(test_client, auth_headers, monkeypatch):
    # 1) 建一个边缘设备（含控制地址与密钥）
    created = test_client.post(
        "/api/v1/video/edge/create",
        headers=auth_headers,
        json={"name": "e2e", "code": f"edge-snap-{uuid4().hex[:8]}", "control_url": "http://127.0.0.1:19090", "secret": "s"},
    )
    assert created.status_code == 200, created.text
    device_id = created.json()["data"]["id"]

    # 2) 打桩 Agent 快照获取（绕过网络）
    monkeypatch.setattr(EdgeAgentClient, "fetch_snapshot", _fake_fetch)

    # 3) 命中代理路由
    resp = test_client.get(
        f"/api/v1/video/edge/{device_id}/tasks/777/snapshot",
        headers=auth_headers,
    )
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("image/jpeg")
    assert resp.content == _FAKE_JPEG


def test_snapshot_proxy_requires_auth(test_client):
    resp = test_client.get("/api/v1/video/edge/1/tasks/1/snapshot")
    assert resp.status_code in (401, 403)
