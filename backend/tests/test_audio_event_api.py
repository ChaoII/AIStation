"""音频接口 controller 测试：upload/list/detail/play-url/lock/unlock 与权限校验。

采用与 ``test_video_api.py`` / ``test_text_ner_api.py`` 一致的方式：通过 API 建数据集
+ 上传音频（mock 对象存储与 ffprobe），再调用接口断言返回结构与鉴权。
"""
import uuid
from unittest.mock import patch

from fastapi.testclient import TestClient

_PRESIGN = "http://rustfs/play.mp3?sig=abc"


def _create_dataset(test_client: TestClient, auth_headers: dict) -> int:
    resp = test_client.post(
        "/api/v1/annotation/dataset/create",
        json={"name": f"audio-api-{uuid.uuid4().hex[:8]}"},
        headers=auth_headers,
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["data"]["id"]


def _upload_audio(test_client: TestClient, auth_headers: dict, dataset_id: int) -> dict:
    resp = test_client.post(
        f"/api/v1/annotation/audio/upload?dataset_id={dataset_id}",
        files={"file": ("demo.wav", b"\x00" * 64, "audio/wav")},
        headers=auth_headers,
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["data"]


def test_upload_list_detail_play_url_lock_unlock(
    test_client: TestClient, auth_headers: dict, monkeypatch
):
    monkeypatch.setattr("app.utils.s3_client.s3_client.ensure_bucket", lambda *a, **k: None)
    monkeypatch.setattr("app.utils.s3_client.s3_client.upload_fileobj", lambda *a, **k: None)

    with patch(
        "app.api.v1.module_annotation.dataset.audio_service._probe_audio",
        return_value={
            "duration": 12.5,
            "sample_rate": 44100,
            "channels": 2,
            "bitrate": 320,
        },
    ), patch(
        "app.api.v1.module_annotation.dataset.audio_service.s3_client.presigned_url",
        return_value=_PRESIGN,
    ):
        ds_id = _create_dataset(test_client, auth_headers)
        audio = _upload_audio(test_client, auth_headers, ds_id)
        aid = audio["id"]
        assert audio["dataset_id"] == ds_id
        assert audio["name"] == "demo.wav"
        assert audio["duration"] == 12.5
        assert audio["sample_rate"] == 44100
        assert audio["channels"] == 2
        assert audio["bitrate"] == 320
        assert audio["size_bytes"] == 64
        assert audio["status"] == "unannotated"
        assert audio["play_url"] == _PRESIGN

        # GET /list?dataset_id= -> { items: [...] }
        lst = test_client.get(
            f"/api/v1/annotation/audio/list?dataset_id={ds_id}", headers=auth_headers
        )
        assert lst.status_code == 200, lst.text
        items = lst.json()["data"]["items"]
        assert len(items) == 1
        item = items[0]
        assert item["id"] == aid
        assert item["dataset_id"] == ds_id
        assert item["name"] == "demo.wav"
        assert item["duration"] == 12.5
        assert item["play_url"] == _PRESIGN

        # GET /detail/{id} -> 元数据
        det = test_client.get(
            f"/api/v1/annotation/audio/detail/{aid}", headers=auth_headers
        )
        assert det.status_code == 200, det.text
        assert det.json()["data"]["id"] == aid
        assert det.json()["data"]["name"] == "demo.wav"

        # GET /play-url/{id} -> { play_url }
        resp = test_client.get(
            f"/api/v1/annotation/audio/play-url/{aid}", headers=auth_headers
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["data"]["play_url"] == _PRESIGN

        # POST /lock/{id} -> { locked: False, locked_by }
        lk = test_client.post(
            f"/api/v1/annotation/audio/lock/{aid}", headers=auth_headers
        )
        assert lk.status_code == 200, lk.text
        assert lk.json()["data"]["locked"] is False

        # POST /unlock/{id} -> 成功
        ulk = test_client.post(
            f"/api/v1/annotation/audio/unlock/{aid}", headers=auth_headers
        )
        assert ulk.status_code == 200, ulk.text


def test_audio_endpoints_require_auth(test_client: TestClient):
    """所有音频端点必须要求登录/权限守卫，未携带凭证返回 401/403。"""
    cases = [
        ("get", "/api/v1/annotation/audio/list?dataset_id=1"),
        ("get", "/api/v1/annotation/audio/detail/1"),
        ("get", "/api/v1/annotation/audio/play-url/1"),
        ("post", "/api/v1/annotation/audio/lock/1"),
        ("post", "/api/v1/annotation/audio/unlock/1"),
    ]
    for method, url in cases:
        resp = getattr(test_client, method)(url)
        assert resp.status_code in (401, 403), f"{url} -> {resp.status_code}: {resp.text}"


def test_upload_dataset_not_found(
    test_client: TestClient, auth_headers: dict, monkeypatch
):
    monkeypatch.setattr("app.utils.s3_client.s3_client.ensure_bucket", lambda *a, **k: None)
    monkeypatch.setattr("app.utils.s3_client.s3_client.upload_fileobj", lambda *a, **k: None)
    with patch(
        "app.api.v1.module_annotation.dataset.audio_service._probe_audio",
        return_value={
            "duration": 1.0,
            "sample_rate": 8000,
            "channels": 1,
            "bitrate": None,
        },
    ):
        resp = test_client.post(
            "/api/v1/annotation/audio/upload?dataset_id=999999",
            files={"file": ("demo.wav", b"\x00" * 16, "audio/wav")},
            headers=auth_headers,
        )
    assert resp.status_code == 404


def test_play_url_not_found(test_client: TestClient, auth_headers: dict):
    resp = test_client.get("/api/v1/annotation/audio/play-url/999999", headers=auth_headers)
    assert resp.status_code == 404
