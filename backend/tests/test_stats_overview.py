"""统计概览语义测试。"""
from uuid import uuid4

from fastapi.testclient import TestClient


def test_overview_enum_keys_and_soft_delete(test_client: TestClient, auth_headers: dict, monkeypatch):
    monkeypatch.setattr("app.utils.s3_client.s3_client.ensure_bucket", lambda *a, **k: None)

    before = test_client.get("/api/v1/annotation/stats/overview", headers=auth_headers).json()["data"]
    base_ds = before["dataset_count"]

    ds = test_client.post(
        "/api/v1/annotation/dataset/create",
        json={"name": f"stat-{uuid4().hex[:8]}"}, headers=auth_headers,
    ).json()["data"]
    ds_id = ds["id"]
    task = test_client.post(
        "/api/v1/annotation/task/create",
        json={"dataset_id": ds_id, "name": f"t-{uuid4().hex[:6]}", "task_type": "detection"},
        headers=auth_headers,
    ).json()["data"]

    ov = test_client.get("/api/v1/annotation/stats/overview", headers=auth_headers).json()["data"]
    # 枚举键必须是值，而非 "AnnotationType.X"
    assert all(not k.startswith("AnnotationType.") for k in ov["tasks_by_type"])
    assert "detection" in ov["tasks_by_type"]
    assert all(not k.startswith("ImageStatus.") for k in ov["images_by_status"])

    # 软删数据集后，概览计数回到基线（证明过滤生效）
    deleted = test_client.request(
        "DELETE", "/api/v1/annotation/dataset/delete", json=[ds_id], headers=auth_headers
    )
    assert deleted.status_code == 200
    after = test_client.get("/api/v1/annotation/stats/overview", headers=auth_headers).json()["data"]
    assert after["dataset_count"] == base_ds, (after["dataset_count"], base_ds)
    assert task  # 任务创建成功
