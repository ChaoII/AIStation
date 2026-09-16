"""边缘心跳字段兼容与鉴权测试（Agent 发 edge_code，云端兼容 code）。"""
import asyncio

import pytest

from app.api.v1.module_video.edge import controller
from app.api.v1.module_video.edge.service import EdgeService, extract_device_code
from app.config.setting import settings
from app.core.exceptions import CustomException


def test_extract_prefers_code():
    assert extract_device_code({"code": "edge-01", "edge_code": "x"}) == "edge-01"


def test_extract_falls_back_to_edge_code():
    assert extract_device_code({"edge_code": "edge-01"}) == "edge-01"


def test_extract_empty():
    assert extract_device_code({}) == ""
    assert extract_device_code({"edge_code": "  "}) == ""


def test_heartbeat_rejected_when_token_unset(monkeypatch):
    """未配置 EDGE_CONTROL_TOKEN 时必须 fail-closed，拒绝心跳（403）。"""
    monkeypatch.setattr(settings, "EDGE_CONTROL_TOKEN", "")
    with pytest.raises(CustomException) as ei:
        asyncio.run(controller.edge_heartbeat_controller({"code": "edge-01"}))
    assert ei.value.status_code == 403


def test_heartbeat_rejected_when_token_mismatch(monkeypatch):
    """配置了密钥但请求凭证错误 → 403。"""
    monkeypatch.setattr(settings, "EDGE_CONTROL_TOKEN", "s3cret")
    with pytest.raises(CustomException) as ei:
        asyncio.run(
            controller.edge_heartbeat_controller({"code": "edge-01", "token": "wrong"})
        )
    assert ei.value.status_code == 403


def test_heartbeat_accepts_matching_token(monkeypatch):
    """凭证正确时放行（心跳服务被替换，避免真实落库）。"""
    called = {}

    async def _fake(body):
        called["body"] = body
        return {"device_id": 1}

    monkeypatch.setattr(settings, "EDGE_CONTROL_TOKEN", "s3cret")
    monkeypatch.setattr(EdgeService, "heartbeat", _fake)

    asyncio.run(
        controller.edge_heartbeat_controller({"code": "edge-01", "token": "s3cret"})
    )
    assert called["body"]["code"] == "edge-01"
