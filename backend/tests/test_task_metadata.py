"""任务备注与类别保存测试。"""
from uuid import uuid4

from fastapi.testclient import TestClient


def test_create_task_persists_description_and_classes(test_client: TestClient, auth_headers: dict, monkeypatch):
    monkeypatch.setattr("app.utils.s3_client.s3_client.ensure_bucket", lambda *a, **k: None)
    ds = test_client.post(
        "/api/v1/annotation/dataset/create", json={"name": f"meta-{uuid4().hex[:8]}"}, headers=auth_headers
    ).json()["data"]
    ds_id = ds["id"]
    classes = [{"id": 0, "name": "person", "color": "#409eff"}]
    resp = test_client.post(
        "/api/v1/annotation/task/create",
        json={"dataset_id": ds_id, "name": f"t-{uuid4().hex[:6]}", "task_type": "detection",
              "description": "hello-desc", "classes": classes},
        headers=auth_headers,
    )
    assert resp.status_code == 200, resp.text
    task_id = resp.json()["data"]["id"]

    detail = test_client.get(f"/api/v1/annotation/task/{task_id}/detail", headers=auth_headers).json()["data"]
    assert detail["description"] == "hello-desc"
    assert detail["classes"][0]["name"] == "person"

    # update description
    upd = test_client.put(
        f"/api/v1/annotation/task/update/{task_id}",
        json={"description": "changed"}, headers=auth_headers,
    )
    assert upd.status_code == 200, upd.text
    detail2 = test_client.get(f"/api/v1/annotation/task/{task_id}/detail", headers=auth_headers).json()["data"]
    assert detail2["description"] == "changed"
