"""CRUDBase 空查询条件下软删过滤测试（经数据集列表接口）。"""
from uuid import uuid4

from fastapi.testclient import TestClient

_FAKE_PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 64


def test_empty_search_list_excludes_soft_deleted(
    test_client: TestClient, auth_headers: dict, monkeypatch
):
    monkeypatch.setattr("app.utils.s3_client.s3_client.ensure_bucket", lambda *a, **k: None)
    monkeypatch.setattr("app.utils.s3_client.s3_client.upload_fileobj", lambda *a, **k: None)

    name = f"softdel-{uuid4().hex[:8]}"
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

    deleted = test_client.request(
        "DELETE", "/api/v1/annotation/dataset/delete", json=[dataset_id], headers=auth_headers
    )
    assert deleted.status_code == 200, deleted.text

    # 无任何筛选条件（search 为空）时，软删的数据集不应出现
    items = test_client.get(
        "/api/v1/annotation/dataset/list",
        params={"page_no": 1, "page_size": 100},
        headers=auth_headers,
    ).json()["data"]["items"]
    assert name not in [i["name"] for i in items]
