"""数据集列表进度聚合测试。"""
from uuid import uuid4

_FAKE_PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 64


def test_list_excludes_soft_deleted_tasks(test_client, auth_headers, monkeypatch):
    """数据集列表不应展示已软删的任务（与标注任务列表保持一致）。"""
    monkeypatch.setattr("app.utils.s3_client.s3_client.ensure_bucket", lambda *a, **k: None)
    name = f"taskdel-{uuid4().hex[:8]}"
    ds = test_client.post("/api/v1/annotation/dataset/create",
                          json={"name": name}, headers=auth_headers).json()["data"]
    task = test_client.post("/api/v1/annotation/task/create",
                            json={"dataset_id": ds["id"], "name": "t1", "task_type": "detection"},
                            headers=auth_headers).json()["data"]
    # 软删该任务
    test_client.request("DELETE", "/api/v1/annotation/task/delete",
                        json=[task["id"]], headers=auth_headers)

    items = test_client.get(
        "/api/v1/annotation/dataset/list",
        params={"page_no": 1, "page_size": 100, "name": name}, headers=auth_headers,
    ).json()["data"]["items"]
    row = next(i for i in items if i["id"] == ds["id"])
    assert row["task_count"] == 0
    assert row["tasks"] == []


def test_list_progress_uses_aggregate(test_client, auth_headers, monkeypatch):
    monkeypatch.setattr("app.utils.s3_client.s3_client.ensure_bucket", lambda *a, **k: None)
    monkeypatch.setattr("app.utils.s3_client.s3_client.upload_fileobj", lambda *a, **k: None)
    name = f"agg-{uuid4().hex[:8]}"
    ds = test_client.post("/api/v1/annotation/dataset/create",
                          json={"name": name}, headers=auth_headers).json()["data"]
    ds_id = ds["id"]
    test_client.post(
        f"/api/v1/annotation/dataset/{ds_id}/upload",
        files={"files": ("a.png", _FAKE_PNG, "image/png")}, headers=auth_headers)
    task = test_client.post("/api/v1/annotation/task/create",
                            json={"dataset_id": ds_id, "name": "t", "task_type": "detection"},
                            headers=auth_headers).json()["data"]
    items = test_client.get(
        f"/api/v1/annotation/dataset/{ds_id}/images", headers=auth_headers
    ).json()["data"]["items"]
    test_client.put(
        f"/api/v1/annotation/anno/image/{items[0]['id']}/annotations",
        json={"task_id": task["id"], "image_id": items[0]["id"],
              "annotation_data": [{"type": "AxisAlignedBox", "id": "x"}]},
        headers=auth_headers)

    listed = test_client.get(
        "/api/v1/annotation/dataset/list",
        params={"page_no": 1, "page_size": 100, "name": name}, headers=auth_headers,
    ).json()["data"]["items"]
    row = next(i for i in listed if i["id"] == ds_id)
    assert row["task_count"] == 1
    assert row["tasks"][0]["progress"] == 100
