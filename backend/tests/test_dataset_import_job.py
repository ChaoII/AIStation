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
            # 每张颜色不同 -> 内容哈希不同，避免被去重跳过
            Image.new("RGB", (40, 20), (10 + i * 40, 10, 10)).save(im, format="PNG")
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


def test_get_latest_job_returns_newest():
    from app.api.v1.module_annotation.dataset.import_jobs import (
        create_job,
        get_latest_job,
        job_snapshot,
    )

    create_job(99001, 1, file_name="a.zip", file_size=1)
    newest = create_job(99001, 1, file_name="b.zip", file_size=2)
    assert get_latest_job(99001).job_id == newest.job_id
    snap = job_snapshot(get_latest_job(99001))
    assert snap["file_name"] == "b.zip"
    assert snap["file_size"] == 2
    assert "elapsed_sec" in snap


def test_list_includes_latest_import_snapshot(test_client, auth_headers, monkeypatch):
    from uuid import uuid4

    from app.api.v1.module_annotation.dataset.import_jobs import create_job

    monkeypatch.setattr("app.utils.s3_client.s3_client.ensure_bucket", lambda *a, **k: None)
    name = f"imp-list-{uuid4().hex[:8]}"
    ds = test_client.post("/api/v1/annotation/dataset/create",
                          json={"name": name}, headers=auth_headers).json()["data"]
    job = create_job(ds["id"], 1, file_name="plate.zip", file_size=749000000)

    items = test_client.get(
        "/api/v1/annotation/dataset/list",
        params={"page_no": 1, "page_size": 100, "name": name}, headers=auth_headers,
    ).json()["data"]["items"]
    row = next(i for i in items if i["id"] == ds["id"])
    assert row["import"]["job_id"] == job.job_id
    assert row["import"]["file_name"] == "plate.zip"
    assert row["import"]["file_size"] == 749000000


def test_import_dedup_skips_existing(test_client, auth_headers, monkeypatch):
    """同一数据集重复导入相同内容 → 按内容哈希去重（不叠加）。"""
    import asyncio

    monkeypatch.setattr("app.utils.s3_client.s3_client.ensure_bucket", lambda *a, **k: None)
    monkeypatch.setattr("app.utils.s3_client.s3_client.upload_fileobj", lambda *a, **k: None)

    ds = test_client.post("/api/v1/annotation/dataset/create",
                          json={"name": f"dedup-{uuid4().hex[:8]}"}, headers=auth_headers).json()["data"]
    from app.api.v1.module_annotation.dataset.x_anylabeling_importer import (
        import_x_anylabeling_bytes,
    )

    first = asyncio.run(import_x_anylabeling_bytes(_make_zip(), ds["id"], 1))
    assert first["imported"] == 3
    second = asyncio.run(import_x_anylabeling_bytes(_make_zip(), ds["id"], 1))
    assert second["imported"] == 0
    assert second["skipped_duplicate"] == 3

    total = test_client.get(
        f"/api/v1/annotation/dataset/{ds['id']}/images", headers=auth_headers
    ).json()["data"]["total"]
    assert total == 3


def test_import_clear_existing_replaces(test_client, auth_headers, monkeypatch):
    """clear_existing=True 时重复导入不叠加（旧图片/任务被清空）。"""
    import asyncio

    monkeypatch.setattr("app.utils.s3_client.s3_client.ensure_bucket", lambda *a, **k: None)
    monkeypatch.setattr("app.utils.s3_client.s3_client.upload_fileobj", lambda *a, **k: None)
    monkeypatch.setattr("app.utils.s3_client.s3_client.delete_objects", lambda *a, **k: 0)

    ds = test_client.post("/api/v1/annotation/dataset/create",
                          json={"name": f"clr-{uuid4().hex[:8]}"}, headers=auth_headers).json()["data"]
    from app.api.v1.module_annotation.dataset.x_anylabeling_importer import (
        import_x_anylabeling_bytes,
    )

    asyncio.run(import_x_anylabeling_bytes(_make_zip(), ds["id"], 1, clear_existing=True))
    asyncio.run(import_x_anylabeling_bytes(_make_zip(), ds["id"], 1, clear_existing=True))

    items = test_client.get(
        f"/api/v1/annotation/dataset/{ds['id']}/images", headers=auth_headers
    ).json()["data"]
    assert items["total"] == 3  # 仍是 3 张，而非 6 张叠加


def test_import_endpoint_rejects_non_zip(test_client, auth_headers, monkeypatch):
    monkeypatch.setattr("app.utils.s3_client.s3_client.ensure_bucket", lambda *a, **k: None)
    ds = test_client.post("/api/v1/annotation/dataset/create",
                          json={"name": f"bad-{uuid4().hex[:8]}"}, headers=auth_headers).json()["data"]
    r = test_client.post(
        f"/api/v1/annotation/dataset/{ds['id']}/import/x-anylabeling",
        files={"file": ("d.txt", b"hello", "text/plain")}, headers=auth_headers)
    assert r.status_code == 400, r.text
