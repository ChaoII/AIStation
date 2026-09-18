"""x-anylabeling 导入：bytes 端到端 + 后台任务接口。"""
import io
import json
import zipfile
from uuid import uuid4


def _make_zip() -> bytes:
    from PIL import Image

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for i in range(3):
            im = io.BytesIO()
            Image.new("RGB", (40, 20), (10, 10, 10)).save(im, format="PNG")
            z.writestr(f"d/frame_{i}.png", im.getvalue())
            z.writestr(f"d/frame_{i}.json", json.dumps({
                "imageWidth": 40, "imageHeight": 20,
                "shapes": [{"label": "text", "shape_type": "rectangle",
                            "points": [[1, 1], [30, 1], [30, 15], [1, 15]]}],
            }))
    return buf.getvalue()


def test_import_bytes_end_to_end(test_client, auth_headers, monkeypatch):
    import asyncio

    monkeypatch.setattr("app.utils.s3_client.s3_client.ensure_bucket", lambda *a, **k: None)
    monkeypatch.setattr("app.utils.s3_client.s3_client.upload_fileobj", lambda *a, **k: None)
    monkeypatch.setattr(
        "app.utils.s3_client.s3_client.presigned_url", lambda k, *a, **k2: f"http://f/{k}"
    )

    ds = test_client.post("/api/v1/annotation/dataset/create",
                          json={"name": f"imp-{uuid4().hex[:8]}"}, headers=auth_headers).json()["data"]
    from app.api.v1.module_annotation.dataset.x_anylabeling_importer import (
        import_x_anylabeling_bytes,
    )

    seen: list[tuple[int, int, str]] = []
    result = asyncio.run(import_x_anylabeling_bytes(
        _make_zip(), ds["id"], 1, progress_cb=lambda p, t, ph: seen.append((p, t, ph))))

    assert result["imported"] == 3
    assert result["total_annotations"] == 3
    assert result["task_id"]
    assert seen and seen[-1][0] == 3 and seen[-1][1] == 3

    items = test_client.get(
        f"/api/v1/annotation/dataset/{ds['id']}/images", headers=auth_headers
    ).json()["data"]["items"]
    assert len(items) == 3
    assert all(i["thumbnail_key"] for i in items)


def test_import_endpoint_returns_job_and_progress(test_client, auth_headers, monkeypatch):
    monkeypatch.setattr("app.utils.s3_client.s3_client.ensure_bucket", lambda *a, **k: None)
    monkeypatch.setattr("app.utils.s3_client.s3_client.upload_fileobj", lambda *a, **k: None)
    ds = test_client.post("/api/v1/annotation/dataset/create",
                          json={"name": f"job-{uuid4().hex[:8]}"}, headers=auth_headers).json()["data"]
    r = test_client.post(
        f"/api/v1/annotation/dataset/{ds['id']}/import/x-anylabeling",
        files={"file": ("d.zip", _make_zip(), "application/zip")}, headers=auth_headers)
    assert r.status_code == 200, r.text
    job_id = r.json()["data"]["job_id"]
    assert job_id
    j = test_client.get(f"/api/v1/annotation/dataset/import/{job_id}", headers=auth_headers)
    assert j.status_code == 200
    assert j.json()["data"]["job_id"] == job_id
    assert test_client.get(
        "/api/v1/annotation/dataset/import/nope", headers=auth_headers
    ).status_code == 404


def test_import_endpoint_rejects_non_zip(test_client, auth_headers, monkeypatch):
    monkeypatch.setattr("app.utils.s3_client.s3_client.ensure_bucket", lambda *a, **k: None)
    ds = test_client.post("/api/v1/annotation/dataset/create",
                          json={"name": f"bad-{uuid4().hex[:8]}"}, headers=auth_headers).json()["data"]
    r = test_client.post(
        f"/api/v1/annotation/dataset/{ds['id']}/import/x-anylabeling",
        files={"file": ("d.txt", b"hello", "text/plain")}, headers=auth_headers)
    assert r.status_code == 400, r.text
