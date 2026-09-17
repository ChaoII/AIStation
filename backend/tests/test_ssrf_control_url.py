"""边缘控制面 control_url 的 SSRF 防护测试（审计 #12）。

覆盖：
- 拒绝 file/gopher 等非 http(s) 协议；
- 拒绝云元数据地址（IP 与主机名）与链路本地地址，即使默认允许内网；
- 默认允许内网/环回（保持局域网边缘设备与本地 Agent 可用，向后兼容）；
- 严格模式（block_private=True）额外拒绝环回/私有地址；
- 允许主机白名单生效；
- ``EdgeAgentClient`` 在构造时统一拦截；
- 设备创建接口对非法 control_url 返回 4xx；心跳同样拒绝。
"""
import uuid

import pytest

from app.api.v1.module_video.edge import service as edge_service
from app.api.v1.module_video.edge.agent_client import EdgeAgentClient
from app.core.exceptions import CustomException
from app.utils.url_guard import UnsafeUrlError, validate_outbound_url


@pytest.mark.parametrize(
    "url",
    [
        "file:///etc/passwd",
        "gopher://127.0.0.1:6379/_INFO",
        "ftp://internal.example/x",
        "data:text/plain,hi",
        "http://169.254.169.254/latest/meta-data/",
        "http://metadata.google.internal/computeMetadata/v1/",
        "http://100.100.100.200/latest/meta-data/",
        "http://[fd00:ec2::254]/latest/meta-data/",
        "http://[fe80::1]:19090/",
        "http://0.0.0.0:19090/",
    ],
)
def test_rejects_dangerous_urls(url):
    with pytest.raises(UnsafeUrlError):
        validate_outbound_url(url)


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1:19090",
        "http://192.168.1.50:19090",
        "http://10.0.0.7:19090",
        "http://edge-01.local:19090",
        "https://edge.example.com",
    ],
)
def test_allows_private_by_default_for_backward_compat(url):
    assert validate_outbound_url(url) == url


def test_strict_mode_blocks_private_and_loopback():
    for url in ("http://127.0.0.1:19090", "http://192.168.1.50:19090", "http://10.0.0.7:19090"):
        with pytest.raises(UnsafeUrlError):
            validate_outbound_url(url, block_private=True)
    # 公网地址在严格模式下仍放行（避免误伤）
    assert validate_outbound_url("http://8.8.8.8:19090", block_private=True)


def test_allowed_hosts_allow_list():
    allowed = {"edge-01.local"}
    assert validate_outbound_url("http://edge-01.local:19090", allowed_hosts=allowed)
    with pytest.raises(UnsafeUrlError):
        validate_outbound_url("http://edge-02.local:19090", allowed_hosts=allowed)


def test_missing_host_or_scheme_rejected():
    with pytest.raises(UnsafeUrlError):
        validate_outbound_url("http:///no-host")
    with pytest.raises(UnsafeUrlError):
        validate_outbound_url("")
    with pytest.raises(UnsafeUrlError):
        validate_outbound_url("//127.0.0.1:19090")


def test_agent_client_rejects_unsafe_control_url():
    with pytest.raises(CustomException):
        EdgeAgentClient("file:///etc/passwd", "s")
    with pytest.raises(CustomException):
        EdgeAgentClient("http://169.254.169.254", "s")
    # 合法地址（含内网/环回）仍可构造
    assert EdgeAgentClient("http://127.0.0.1:19090", "s").control_url == "http://127.0.0.1:19090"


def test_edge_create_rejects_unsafe_control_url(test_client, auth_headers):
    for bad in ("file:///etc/passwd", "http://169.254.169.254/latest"):
        resp = test_client.post(
            "/api/v1/video/edge/create",
            headers=auth_headers,
            json={"name": "ssrf", "code": f"ssrf-{uuid.uuid4().hex[:8]}", "control_url": bad},
        )
        assert resp.status_code in (400, 422), resp.text

    ok = test_client.post(
        "/api/v1/video/edge/create",
        headers=auth_headers,
        json={
            "name": "ssrf-ok",
            "code": f"ssrf-ok-{uuid.uuid4().hex[:8]}",
            "control_url": "http://127.0.0.1:19090",
        },
    )
    assert ok.status_code == 200, ok.text


def test_heartbeat_rejects_unsafe_control_url(monkeypatch):
    # 心跳服务不需鉴权 token（controller 层校验），此处直测服务层拒绝非法地址
    with pytest.raises(CustomException) as ei:
        import asyncio

        asyncio.run(
            edge_service.EdgeService.heartbeat(
                {"code": f"hb-{uuid.uuid4().hex[:8]}", "control_url": "file:///etc/passwd"}
            )
        )
    assert ei.value.status_code == 400
