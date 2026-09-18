"""数据集 purge 与缩略图列测试。"""


def test_annotation_image_has_thumbnail_key(test_client, auth_headers, monkeypatch):
    monkeypatch.setattr("app.utils.s3_client.s3_client.ensure_bucket", lambda *a, **k: None)
    monkeypatch.setattr("app.utils.s3_client.s3_client.upload_fileobj", lambda *a, **k: None)
    from app.api.v1.module_annotation.dataset.model import AnnotationImageModel

    assert hasattr(AnnotationImageModel, "thumbnail_key")


def test_purge_removes_db_rows_and_s3(test_client, auth_headers, monkeypatch):
    deleted_keys: list[str] = []
    prefixes: list[str] = []
    monkeypatch.setattr("app.utils.s3_client.s3_client.ensure_bucket", lambda *a, **k: None)
    monkeypatch.setattr("app.utils.s3_client.s3_client.upload_fileobj", lambda *a, **k: None)
    monkeypatch.setattr(
        "app.utils.s3_client.s3_client.delete_objects",
        lambda keys, *a, **k: deleted_keys.extend(keys) or len(keys),
    )
    monkeypatch.setattr(
        "app.utils.s3_client.s3_client.delete_prefix",
        lambda prefix, *a, **k: prefixes.append(prefix) or 0,
    )
    from uuid import uuid4 as _uuid

    name = f"purge-{_uuid().hex[:8]}"
    ds = test_client.post("/api/v1/annotation/dataset/create",
                          json={"name": name}, headers=auth_headers).json()["data"]
    ds_id = ds["id"]
    up = test_client.post(
        f"/api/v1/annotation/dataset/{ds_id}/upload",
        files={"files": ("a.png", b"\x89PNG\r\n\x1a\n" + b"0" * 64, "image/png")},
        headers=auth_headers,
    ).json()["data"]
    object_key = up["uploaded"][0]["object_key"]
    # 先软删，再彻底删除（后台任务）
    test_client.request("DELETE", "/api/v1/annotation/dataset/delete",
                        json=[ds_id], headers=auth_headers)
    r = test_client.request("DELETE", "/api/v1/annotation/dataset/purge",
                            json=[ds_id], headers=auth_headers)
    assert r.status_code == 200, r.text
    job_id = r.json()["data"]["job_id"]
    assert job_id
    import time

    job = None
    deadline = time.time() + 30
    while time.time() < deadline:
        job = test_client.get(
            f"/api/v1/annotation/dataset/import/{job_id}", headers=auth_headers
        ).json()["data"]
        if job["status"] in ("done", "failed"):
            break
        time.sleep(0.2)
    assert job and job["status"] == "done", job
    assert job["kind"] == "purge"
    # 按 DB 记录的 key 批量删除（不依赖列举前缀）
    assert object_key in deleted_keys
    assert any(p.startswith(f"train/exports/dataset_{ds_id}_") for p in prefixes)


def test_purge_expired_selects_soft_deleted_older_than(test_client, auth_headers, monkeypatch):
    import asyncio
    from datetime import datetime, timedelta
    from uuid import uuid4 as _uuid

    monkeypatch.setattr("app.utils.s3_client.s3_client.ensure_bucket", lambda *a, **k: None)
    monkeypatch.setattr("app.utils.s3_client.s3_client.delete_prefix", lambda *a, **k: 0)

    ds = test_client.post("/api/v1/annotation/dataset/create",
                          json={"name": f"exp-{_uuid().hex[:8]}"},
                          headers=auth_headers).json()["data"]
    ds_id = ds["id"]
    test_client.request("DELETE", "/api/v1/annotation/dataset/delete",
                        json=[ds_id], headers=auth_headers)

    from app.core.database import async_db_session
    from app.api.v1.module_annotation.dataset.model import DatasetModel
    from app.api.v1.module_annotation.dataset.retention import purge_expired_datasets

    async def _backdate():
        async with async_db_session.begin() as db:
            row = await db.get(DatasetModel, ds_id)
            row.deleted_time = datetime.now() - timedelta(days=99)

    asyncio.run(_backdate())

    async def _purge():
        return await purge_expired_datasets(30)

    assert asyncio.run(_purge()) >= 1

    async def _gone():
        async with async_db_session() as db:
            return await db.get(DatasetModel, ds_id)

    assert asyncio.run(_gone()) is None
