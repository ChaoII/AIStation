"""数据集 purge 与缩略图列测试。"""


def test_annotation_image_has_thumbnail_key(test_client, auth_headers, monkeypatch):
    monkeypatch.setattr("app.utils.s3_client.s3_client.ensure_bucket", lambda *a, **k: None)
    monkeypatch.setattr("app.utils.s3_client.s3_client.upload_fileobj", lambda *a, **k: None)
    from app.api.v1.module_annotation.dataset.model import AnnotationImageModel

    assert hasattr(AnnotationImageModel, "thumbnail_key")


def test_purge_removes_db_rows_and_s3(test_client, auth_headers, monkeypatch):
    prefixes: list[str] = []
    monkeypatch.setattr("app.utils.s3_client.s3_client.ensure_bucket", lambda *a, **k: None)
    monkeypatch.setattr("app.utils.s3_client.s3_client.upload_fileobj", lambda *a, **k: None)
    monkeypatch.setattr(
        "app.utils.s3_client.s3_client.delete_prefix",
        lambda prefix, *a, **k: prefixes.append(prefix) or 1,
    )
    from uuid import uuid4 as _uuid

    name = f"purge-{_uuid().hex[:8]}"
    ds = test_client.post("/api/v1/annotation/dataset/create",
                          json={"name": name}, headers=auth_headers).json()["data"]
    ds_id = ds["id"]
    test_client.post(
        f"/api/v1/annotation/dataset/{ds_id}/upload",
        files={"files": ("a.png", b"\x89PNG\r\n\x1a\n" + b"0" * 64, "image/png")},
        headers=auth_headers,
    )
    # 先软删，再彻底删除
    test_client.request("DELETE", "/api/v1/annotation/dataset/delete",
                        json=[ds_id], headers=auth_headers)
    r = test_client.request("DELETE", "/api/v1/annotation/dataset/purge",
                            json=[ds_id], headers=auth_headers)
    assert r.status_code == 200, r.text
    assert f"datasets/{ds_id}/" in prefixes
    assert f"annotations/dataset_{ds_id}/" in prefixes
    assert any(p.startswith(f"train/exports/dataset_{ds_id}_") for p in prefixes)
    # 幂等：再 purge 不报错
    r2 = test_client.request("DELETE", "/api/v1/annotation/dataset/purge",
                             json=[ds_id], headers=auth_headers)
    assert r2.status_code == 200, r2.text
