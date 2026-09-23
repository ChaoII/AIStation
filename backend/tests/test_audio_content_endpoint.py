"""音频同源内容端点测试：``stream_audio_content`` 流式读取 + content 端点流式响应。

覆盖：
- ``stream_audio_content`` 从 RustFS ``get_object`` 分块读取并返回 ``(chunks, size, content_type)``；
- content 端点返回 ``StreamingResponse`` 且 ``Content-Type``/``Content-Length``/
  ``Content-Disposition`` 正确；
- 鉴权（401/403）；
- audio_id 不存在/已删除时抛 404（归属校验）。
"""
import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.api.v1.module_annotation.dataset.audio_service import AudioService
from app.core.exceptions import CustomException


def _make_audio(**overrides):
    audio = MagicMock()
    audio.is_deleted = False
    audio.name = "demo.wav"
    audio.object_key = "datasets/7/audios/abc.wav"
    audio.size_bytes = 64
    for k, v in overrides.items():
        setattr(audio, k, v)
    return audio


def _make_db(audio):
    """构造一个模拟 async db 会话，其 ``get`` 返回给定音频。"""
    db = AsyncMock()
    db.get = AsyncMock(return_value=audio)
    return db


def _patch_db_session(monkeypatch, db):
    """让 service 模块内的 ``async_db_session()`` 产出给定的 mock db。"""
    session_cm = AsyncMock()
    session_cm.__aenter__ = AsyncMock(return_value=db)
    session_cm.__aexit__ = AsyncMock(return_value=False)
    monkeypatch.setattr(
        "app.api.v1.module_annotation.dataset.audio_service.async_db_session",
        MagicMock(return_value=session_cm),
    )


def _collect(chunks) -> bytes:
    """把异步生成器收集成完整字节串。"""
    async def _gather():
        out = b""
        async for c in chunks:
            out += c
        return out
    return asyncio.run(_gather())


def test_stream_audio_content_returns_chunks_size_and_type(monkeypatch):
    """``stream_audio_content`` 应分块产出字节，并返回大小与 Content-Type。"""
    audio = _make_audio(name="demo.wav")
    _patch_db_session(monkeypatch, _make_db(audio))

    chunks_data = [b"RIFF", b"\x00" * 60]
    body = MagicMock()
    body.read.side_effect = chunks_data + [b""]
    monkeypatch.setattr(
        "app.api.v1.module_annotation.dataset.audio_service.s3_client.get_object",
        lambda key: {"Body": body},
    )

    chunks, size_bytes, content_type = asyncio.run(
        AudioService.stream_audio_content(1)
    )
    assert _collect(chunks) == b"".join(chunks_data)
    assert size_bytes == 64
    assert content_type == "audio/wav"
    # 确实按分块读取，而非一次 read 全量
    assert body.read.call_count == len(chunks_data) + 1


def test_stream_audio_content_falls_back_to_octet_stream(monkeypatch):
    """未知扩展名应回退 octet-stream。"""
    audio = _make_audio(name="demo.bin")
    _patch_db_session(monkeypatch, _make_db(audio))
    body = MagicMock()
    body.read.side_effect = [b"x", b""]
    monkeypatch.setattr(
        "app.api.v1.module_annotation.dataset.audio_service.s3_client.get_object",
        lambda key: {"Body": body},
    )
    _, _, content_type = asyncio.run(AudioService.stream_audio_content(1))
    assert content_type == "application/octet-stream"


def test_stream_audio_content_not_found(monkeypatch):
    """audio_id 不存在时抛 404。"""
    _patch_db_session(monkeypatch, _make_db(None))
    with pytest.raises(CustomException) as exc:
        asyncio.run(AudioService.stream_audio_content(999999))
    assert exc.value.status_code == 404


def test_content_endpoint_returns_streaming_response(test_client, auth_headers, monkeypatch):
    """content 端点返回流式响应，且 Content-Type/Content-Length/Content-Disposition 正确。"""
    async def _chunks():
        yield b"RIFF"
        yield b"\x00" * 60

    monkeypatch.setattr(
        "app.api.v1.module_annotation.dataset.audio_service.AudioService.stream_audio_content",
        AsyncMock(return_value=(_chunks(), 64, "audio/wav")),
    )
    resp = test_client.get(
        "/api/v1/annotation/audio/content/1", headers=auth_headers
    )
    assert resp.status_code == 200, resp.text
    assert resp.headers["content-type"].startswith("audio/wav")
    assert resp.headers["content-length"] == "64"
    assert resp.headers["content-disposition"] == "inline"
    assert resp.content == b"RIFF" + b"\x00" * 60


def test_content_endpoint_mpeg_type(test_client, auth_headers, monkeypatch):
    """mp3 应以 audio/mpeg 返回。"""
    async def _chunks():
        yield b"\xff\xfb"

    monkeypatch.setattr(
        "app.api.v1.module_annotation.dataset.audio_service.AudioService.stream_audio_content",
        AsyncMock(return_value=(_chunks(), 2, "audio/mpeg")),
    )
    resp = test_client.get(
        "/api/v1/annotation/audio/content/1", headers=auth_headers
    )
    assert resp.status_code == 200, resp.text
    assert resp.headers["content-type"].startswith("audio/mpeg")
    assert resp.content == b"\xff\xfb"


def test_content_endpoint_not_found(test_client, auth_headers, monkeypatch):
    """音频不存在时 content 端点返回 404。"""
    async def _raise(*args, **kwargs):
        raise CustomException(
            msg="音频不存在: 999999", code=404, status_code=404
        )

    monkeypatch.setattr(
        "app.api.v1.module_annotation.dataset.audio_service.AudioService.stream_audio_content",
        _raise,
    )
    resp = test_client.get(
        "/api/v1/annotation/audio/content/999999", headers=auth_headers
    )
    assert resp.status_code == 404


def test_content_endpoint_requires_auth(test_client):
    """content 端点必须要求登录/权限守卫，未携带凭证返回 401/403。"""
    resp = test_client.get("/api/v1/annotation/audio/content/1")
    assert resp.status_code in (401, 403), f"{resp.status_code}: {resp.text}"
