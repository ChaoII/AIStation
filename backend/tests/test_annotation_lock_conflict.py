"""保存冲突返回 409 测试。"""
import os
import sqlite3
from uuid import uuid4

from fastapi.testclient import TestClient


def test_save_conflict_returns_409(test_client: TestClient, auth_headers: dict, monkeypatch):
    monkeypatch.setattr("app.utils.s3_client.s3_client.ensure_bucket", lambda *a, **k: None)
    monkeypatch.setattr("app.utils.s3_client.s3_client.upload_fileobj", lambda *a, **k: None)

    ds = test_client.post("/api/v1/annotation/dataset/create", json={"name": f"lock-{uuid4().hex[:8]}"}, headers=auth_headers).json()["data"]
    ds_id = ds["id"]
    files = {"files": ("a.png", b"\x89PNG\r\n\x1a\n" + b"0" * 32, "image/png")}
    test_client.post(f"/api/v1/annotation/dataset/{ds_id}/upload", files=files, headers=auth_headers)
    task = test_client.post(
        "/api/v1/annotation/task/create",
        json={"dataset_id": ds_id, "name": f"t-{uuid4().hex[:6]}", "task_type": "detection"},
        headers=auth_headers,
    ).json()["data"]

    db = sqlite3.connect(os.environ["DATABASE_NAME"] + ".db")
    img_id = db.execute("SELECT id FROM annotation_image WHERE dataset_id=? ORDER BY id LIMIT 1", (ds_id,)).fetchone()[0]
    # 模拟“被他人锁定”
    db.execute("UPDATE annotation_image SET locked_by=987654 WHERE id=?", (img_id,))
    db.commit()
    db.close()

    resp = test_client.put(
        f"/api/v1/annotation/anno/image/{img_id}/annotations",
        json={"task_id": task["id"], "image_id": img_id, "annotation_data": []},
        headers=auth_headers,
    )
    assert resp.status_code == 409, resp.text
