"""视频接口 controller 测试：play-url 返回 ``{play_url}``、list 返回 ``{items}`` 结构。

采用与 ``test_annotation_lock_conflict`` 一致的方式：通过 API 建数据集 + 上传视频
（mock 对象存储与 ffprobe），再调用接口断言返回结构。
"""
import uuid
from unittest.mock import patch

from fastapi.testclient import TestClient

_PRESIGN = "http://rustfs/play.mp4?sig=abc"


def _create_dataset(test_client: TestClient, auth_headers: dict) -> int:
    resp = test_client.post(
        "/api/v1/annotation/dataset/create",
        json={"name": f"video-api-{uuid.uuid4().hex[:8]}"},
        headers=auth_headers,
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["data"]["id"]


def _upload_video(test_client: TestClient, auth_headers: dict, dataset_id: int) -> dict:
    resp = test_client.post(
        f"/api/v1/annotation/video/upload?dataset_id={dataset_id}",
        files={"file": ("demo.mp4", b"\x00" * 128, "video/mp4")},
        headers=auth_headers,
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["data"]


def test_play_url_and_list_shape(
    test_client: TestClient, auth_headers: dict, monkeypatch
):
    monkeypatch.setattr("app.utils.s3_client.s3_client.ensure_bucket", lambda *a, **k: None)
    monkeypatch.setattr("app.utils.s3_client.s3_client.upload_fileobj", lambda *a, **k: None)

    with patch(
        "app.api.v1.module_annotation.dataset.video_service._probe_video",
        return_value={"width": 1920, "height": 1080, "fps": 25.0, "duration": 10.0, "frame_count": 250},
    ), patch(
        "app.api.v1.module_annotation.dataset.video_service.s3_client.presigned_url",
        return_value=_PRESIGN,
    ):
        ds_id = _create_dataset(test_client, auth_headers)
        video = _upload_video(test_client, auth_headers, ds_id)
        vid = video["id"]
        assert video["play_url"] == _PRESIGN

        # GET /play-url/{id} -> { play_url }
        resp = test_client.get(f"/api/v1/annotation/video/play-url/{vid}", headers=auth_headers)
        assert resp.status_code == 200, resp.text
        assert resp.json()["data"]["play_url"] == _PRESIGN

        # GET /list?dataset_id= -> { items: [...] }
        lst = test_client.get(f"/api/v1/annotation/video/list?dataset_id={ds_id}", headers=auth_headers)
        assert lst.status_code == 200, lst.text
        items = lst.json()["data"]["items"]
        assert len(items) == 1
        item = items[0]
        assert item["id"] == vid
        assert item["dataset_id"] == ds_id
        assert item["width"] == 1920
        assert item["height"] == 1080
        assert item["fps"] == 25.0
        assert item["duration"] == 10.0
        assert item["frame_count"] == 250
        assert item["status"] == "unannotated"
        assert item["play_url"] == _PRESIGN


def test_play_url_not_found(test_client: TestClient, auth_headers: dict, monkeypatch):
    monkeypatch.setattr("app.utils.s3_client.s3_client.ensure_bucket", lambda *a, **k: None)
    resp = test_client.get("/api/v1/annotation/video/play-url/999999", headers=auth_headers)
    assert resp.status_code == 404
