"""推理回调共享密钥 fail-closed 测试（审计 #5、#17）。

- 未配置/空密钥必须拒绝（403），不再 fail-open；
- 仅 dev 环境 + 显式开关才允许无凭据放行；
- 错误凭据返回 HTTP 403 而非 500。
"""
import asyncio

import pytest

from app.api.v1.module_video.algorithm import controller as ac
from app.api.v1.module_video.inference import service as svc
from app.common.enums import EnvironmentEnum
from app.config.setting import settings
from app.core.exceptions import CustomException


class _Req:
    """最小 Request 替身：仅提供 headers。"""

    def __init__(self, headers: dict | None = None) -> None:
        self.headers = headers or {}


def _patch_service(monkeypatch) -> dict:
    captured: dict = {}

    async def _fake_callback(event):
        captured["event"] = event
        return {"alarm_created": True}

    monkeypatch.setattr(svc.InferenceService, "process_detection_callback", _fake_callback)
    return captured


# --------------------------------------------------------------- fail-closed
def test_callback_rejected_when_token_unset(monkeypatch):
    monkeypatch.setattr(settings, "INFERENCE_CALLBACK_TOKEN", "")
    monkeypatch.setattr(settings, "INFERENCE_CALLBACK_ALLOW_INSECURE_DEV", False)
    with pytest.raises(CustomException) as ei:
        asyncio.run(ac.detection_callback_controller(_Req(), {"event_id": "x"}))
    assert ei.value.status_code == 403


def test_callback_rejected_when_credentials_missing(monkeypatch):
    monkeypatch.setattr(settings, "INFERENCE_CALLBACK_TOKEN", "strong-token-value")
    with pytest.raises(CustomException) as ei:
        asyncio.run(ac.detection_callback_controller(_Req(), {"event_id": "x"}))
    assert ei.value.status_code == 403


def test_callback_rejected_when_token_mismatch(monkeypatch):
    monkeypatch.setattr(settings, "INFERENCE_CALLBACK_TOKEN", "strong-token-value")
    with pytest.raises(CustomException) as ei:
        asyncio.run(
            ac.detection_callback_controller(
                _Req(headers={"Authorization": "Bearer wrong"}), {"event_id": "x"}
            )
        )
    assert ei.value.status_code == 403


def test_callback_accepts_matching_token(monkeypatch):
    monkeypatch.setattr(settings, "INFERENCE_CALLBACK_TOKEN", "strong-token-value")
    captured = _patch_service(monkeypatch)
    resp = asyncio.run(
        ac.detection_callback_controller(
            _Req(headers={"Authorization": "Bearer strong-token-value"}),
            {"event_id": "ev-ok", "camera_id": 1},
        )
    )
    assert resp.status_code == 200
    assert captured["event"]["event_id"] == "ev-ok"


# --------------------------------------------------------------- dev 显式开关
def test_callback_dev_override_allows_unset(monkeypatch):
    """dev + 显式开关：未配置密钥时允许放行（便于本地联调）。"""
    monkeypatch.setattr(settings, "INFERENCE_CALLBACK_TOKEN", "")
    monkeypatch.setattr(settings, "INFERENCE_CALLBACK_ALLOW_INSECURE_DEV", True)
    monkeypatch.setattr(settings, "ENVIRONMENT", EnvironmentEnum.DEV)
    _patch_service(monkeypatch)
    resp = asyncio.run(
        ac.detection_callback_controller(_Req(), {"event_id": "ev-dev", "camera_id": 1})
    )
    assert resp.status_code == 200


def test_callback_dev_override_ignored_in_prod(monkeypatch):
    """非 dev 环境即使打开开关也必须 fail-closed。"""
    monkeypatch.setattr(settings, "INFERENCE_CALLBACK_TOKEN", "")
    monkeypatch.setattr(settings, "INFERENCE_CALLBACK_ALLOW_INSECURE_DEV", True)
    monkeypatch.setattr(settings, "ENVIRONMENT", EnvironmentEnum.PROD)
    with pytest.raises(CustomException) as ei:
        asyncio.run(ac.detection_callback_controller(_Req(), {"event_id": "x"}))
    assert ei.value.status_code == 403
