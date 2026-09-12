"""导出历史写入测试。"""


def _create_dataset(test_client, auth_headers, name: str) -> int:
    r = test_client.post(
        "/api/v1/annotation/dataset/create", json={"name": name}, headers=auth_headers
    )
    assert r.status_code == 200, r.text
    return r.json()["data"]["id"]


def test_export_writes_history(test_client, auth_headers, monkeypatch):
    from app.utils.s3_client import s3_client

    # 测试环境无 RustFS：屏蔽对象存储网络调用
    monkeypatch.setattr(s3_client, "upload_fileobj", lambda *a, **k: "key")
    monkeypatch.setattr(s3_client, "presigned_url", lambda *a, **k: "http://fake/url.zip")
    monkeypatch.setattr(s3_client, "delete_object", lambda *a, **k: None)

    ds_id = _create_dataset(test_client, auth_headers, "P5A导出历史集")
    try:
        resp = test_client.post(
            "/api/v1/train/dataset/export",
            json={"dataset_id": ds_id, "format": "yolo"},
            headers=auth_headers,
        )
        assert resp.status_code == 200, resp.text
        hist = test_client.get(
            f"/api/v1/annotation/dataset/export/history/{ds_id}", headers=auth_headers
        ).json()["data"]
        assert len(hist) >= 1
        row = hist[0]
        assert row["format"] == "yolo"
        assert row["file_size"] > 0
        assert row["checksum"]
        assert row["download_url"]
    finally:
        test_client.request(
            "DELETE",
            "/api/v1/annotation/dataset/delete",
            json=[ds_id],
            headers=auth_headers,
        )
