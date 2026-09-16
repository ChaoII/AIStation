"""任务进度真实落库测试（sqlite 直连校验 commit）。"""
import os
import sqlite3
from uuid import uuid4

from fastapi.testclient import TestClient


def _db():
    return sqlite3.connect(os.environ["DATABASE_NAME"] + ".db")


def _make_dataset_and_task(test_client, auth_headers):
    name = f"prog-{uuid4().hex[:8]}"
    ds = test_client.post("/api/v1/annotation/dataset/create", json={"name": name}, headers=auth_headers).json()["data"]
    ds_id = ds["id"]
    # upload one image (monkeypatch S3 in the caller)
    files = {"files": ("a.png", b"\x89PNG\r\n\x1a\n" + b"0" * 32, "image/png")}
    test_client.post(f"/api/v1/annotation/dataset/{ds_id}/upload", files=files, headers=auth_headers)
    task = test_client.post(
        "/api/v1/annotation/task/create",
        json={"dataset_id": ds_id, "name": f"t-{name}", "task_type": "detection"},
        headers=auth_headers,
    ).json()["data"]
    return ds_id, task["id"]


def test_progress_persisted_after_save(test_client: TestClient, auth_headers: dict, monkeypatch):
    monkeypatch.setattr("app.utils.s3_client.s3_client.ensure_bucket", lambda *a, **k: None)
    monkeypatch.setattr("app.utils.s3_client.s3_client.upload_fileobj", lambda *a, **k: None)
    monkeypatch.setattr("app.utils.s3_client.s3_client.download_fileobj", lambda *a, **k: __import__("io").BytesIO(b"x"))

    ds_id, task_id = _make_dataset_and_task(test_client, auth_headers)

    con = _db()
    img_id = con.execute(
        "SELECT id FROM annotation_image WHERE dataset_id=? ORDER BY id LIMIT 1", (ds_id,)
    ).fetchone()[0]
    con.close()

    # annotate the only image
    put = test_client.put(
        f"/api/v1/annotation/anno/image/{img_id}/annotations",
        json={"task_id": task_id, "image_id": img_id,
              "annotation_data": [{"type": "AxisAlignedBox", "class_id": 0, "x1": 0.1, "y1": 0.1, "x2": 0.2, "y2": 0.2}]},
        headers=auth_headers,
    )
    assert put.status_code == 200, put.text

    # trigger update_progress (list endpoint calls it)
    test_client.get("/api/v1/annotation/task/list", params={"page_no": 1, "page_size": 50}, headers=auth_headers)

    con = _db()
    progress, status = con.execute(
        "SELECT progress, status FROM annotation_task WHERE id=?", (task_id,)
    ).fetchone()
    con.close()
    assert progress == 100, f"progress should be persisted, got {progress}"
    assert str(status).lower() in ("completed", "complete")
