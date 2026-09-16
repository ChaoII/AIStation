"""录像回调 Webhook 鉴权与路径穿越校验测试（审计 #3）。

- 未配置/错误共享密钥必须 fail-closed（403）；
- 仅接受位于 RECORDINGS_DIR 内的 file_path，拒绝目录穿越。
"""
import asyncio

import pytest

from app.api.v1.module_video.record import controller as rc
from app.api.v1.module_video.record import service as rs
from app.config.setting import settings
from app.core.exceptions import CustomException


class _Req:
    """最小 Request 替身：仅提供 headers 与 json()。"""

    def __init__(self, headers: dict | None = None, json_body: dict | None = None) -> None:
        self.headers = headers or {}
        self._json = json_body or {}

    async def json(self) -> dict:
        return self._json


# --------------------------------------------------------------- 鉴权
def test_webhook_rejected_when_token_unset(monkeypatch):
    """未配置共享密钥时必须拒绝（fail-closed），不得放行写库。"""
    monkeypatch.setattr(settings, "RECORD_WEBHOOK_TOKEN", "")
    with pytest.raises(CustomException) as ei:
        asyncio.run(rc.on_record_mp4_webhook(_Req(json_body={"stream_id": "cam1"})))
    assert ei.value.status_code == 403


def test_webhook_rejected_when_token_mismatch(monkeypatch):
    monkeypatch.setattr(settings, "RECORD_WEBHOOK_TOKEN", "s3cret")
    with pytest.raises(CustomException) as ei:
        asyncio.run(
            rc.on_record_mp4_webhook(
                _Req(headers={"X-Record-Token": "wrong"}, json_body={"stream_id": "cam1"})
            )
        )
    assert ei.value.status_code == 403


def test_webhook_rejected_when_token_missing(monkeypatch):
    monkeypatch.setattr(settings, "RECORD_WEBHOOK_TOKEN", "s3cret")
    with pytest.raises(CustomException) as ei:
        asyncio.run(rc.on_record_mp4_webhook(_Req(json_body={"stream_id": "cam1"})))
    assert ei.value.status_code == 403


def test_webhook_accepts_matching_token(monkeypatch):
    """凭据正确时进入业务处理（服务层被替换，避免落库）。"""
    called: dict = {}

    async def _fake(data):
        called["data"] = data
        return {"code": 0, "msg": "ok"}

    monkeypatch.setattr(settings, "RECORD_WEBHOOK_TOKEN", "s3cret")
    monkeypatch.setattr(rs.RecordService, "handle_record_webhook", _fake)

    body = {
        "stream_id": "cam1",
        "file_path": str((rs.RECORDINGS_DIR / "cam1" / "a.mp4").resolve()),
    }
    resp = asyncio.run(
        rc.on_record_mp4_webhook(_Req(headers={"X-Record-Token": "s3cret"}, json_body=body))
    )
    assert resp["code"] == 0
    assert called["data"]["stream_id"] == "cam1"


def test_webhook_accepts_bearer_token(monkeypatch):
    """兼容 Authorization: Bearer 形式传递共享密钥。"""
    called: dict = {}

    async def _fake(data):
        called["data"] = data
        return {"code": 0, "msg": "ok"}

    monkeypatch.setattr(settings, "RECORD_WEBHOOK_TOKEN", "s3cret")
    monkeypatch.setattr(rs.RecordService, "handle_record_webhook", _fake)

    asyncio.run(
        rc.on_record_mp4_webhook(
            _Req(headers={"Authorization": "Bearer s3cret"}, json_body={"stream_id": "cam1"})
        )
    )
    assert called["data"]["stream_id"] == "cam1"


# --------------------------------------------------------------- 路径穿越
def test_path_helper_containment():
    inside = rs.RECORDINGS_DIR / "cam1" / "a.mp4"
    assert rs.is_within_recordings_dir(str(inside)) is True
    assert rs.is_within_recordings_dir("cam1/a.mp4") is True
    assert rs.is_within_recordings_dir("../../etc/passwd") is False
    assert rs.is_within_recordings_dir("/etc/passwd") is False
    assert rs.is_within_recordings_dir("") is False


def test_webhook_service_rejects_traversal_path():
    """file_path 越出 RECORDINGS_DIR 时必须拒绝，不得落库。"""
    with pytest.raises(CustomException) as ei:
        asyncio.run(
            rs.RecordService.handle_record_webhook(
                {"stream_id": "cam1", "file_path": "../../../etc/passwd"}
            )
        )
    assert ei.value.status_code in (400, 403)


def test_webhook_service_rejects_absolute_outside_path():
    with pytest.raises(CustomException) as ei:
        asyncio.run(
            rs.RecordService.handle_record_webhook(
                {"stream_id": "cam1", "file_path": "C:/Windows/System32/drivers/etc/hosts"}
            )
        )
    assert ei.value.status_code in (400, 403)
