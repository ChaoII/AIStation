"""删除数据集级联软删图片测试。"""
from uuid import uuid4

from fastapi.testclient import TestClient

_FAKE_PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 64


def _create_dataset_with_image(test_client: TestClient, auth_headers: dict) -> tuple[int, str]:
    name = f"cascade-{uuid4().hex[:8]}"
    created = test_client.post(
        "/api/v1/annotation/dataset/create", json={"name": name}, headers=auth_headers
    )
    assert created.status_code == 200, created.text
    data = created.json()["data"]
    dataset_id = data["id"] if isinstance(data, dict) and "id" in data else None
    if dataset_id is None:
        items = test_client.get(
            "/api/v1/annotation/dataset/list",
            params={"page_no": 1, "page_size": 5},
            headers=auth_headers,
        ).json()["data"]["items"]
        dataset_id = next(i["id"] for i in items if i["name"] == name)
    files = {"files": ("a.png", _FAKE_PNG, "image/png")}
    up = test_client.post(
        f"/api/v1/annotation/dataset/{dataset_id}/upload", files=files, headers=auth_headers
    )
    assert up.status_code == 200, up.text
    return dataset_id, name


def test_dataset_delete_cascades_images(
    test_client: TestClient, auth_headers: dict, monkeypatch
):
    # 上传需要对象存储：屏蔽真实 S3 调用
    monkeypatch.setattr(
        "app.utils.s3_client.s3_client.ensure_bucket", lambda *a, **k: None
    )
    monkeypatch.setattr(
        "app.utils.s3_client.s3_client.upload_fileobj", lambda *a, **k: None
    )

    dataset_id, name = _create_dataset_with_image(test_client, auth_headers)
    before = test_client.get(
        f"/api/v1/annotation/dataset/{dataset_id}/images", headers=auth_headers
    ).json()["data"]
    assert before["total"] == 1

    deleted = test_client.request(
        "DELETE", "/api/v1/annotation/dataset/delete", json=[dataset_id], headers=auth_headers
    )
    assert deleted.status_code == 200, deleted.text

    after = test_client.get(
        f"/api/v1/annotation/dataset/{dataset_id}/images", headers=auth_headers
    ).json()["data"]
    assert after["total"] == 0

    listed = test_client.get(
        "/api/v1/annotation/dataset/list",
        params={"page_no": 1, "page_size": 100, "name": name},
        headers=auth_headers,
    ).json()["data"]["items"]
    assert name not in [item["name"] for item in listed]
