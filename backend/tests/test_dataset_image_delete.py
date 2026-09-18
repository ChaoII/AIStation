"""数据集图片硬删除：指定 id / 按状态筛选 / 锁定跳过 / 计数重算。"""
from uuid import uuid4

_FAKE_PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 64


def _setup(test_client, auth_headers, monkeypatch):
    deleted_keys: list[str] = []
    monkeypatch.setattr("app.utils.s3_client.s3_client.ensure_bucket", lambda *a, **k: None)
    monkeypatch.setattr("app.utils.s3_client.s3_client.upload_fileobj", lambda *a, **k: None)
    monkeypatch.setattr(
        "app.utils.s3_client.s3_client.delete_objects",
        lambda keys, *a, **k: deleted_keys.extend(keys) or len(keys),
    )
    monkeypatch.setattr(
        "app.utils.s3_client.s3_client.presigned_url", lambda k, *a, **k2: f"http://f/{k}"
    )

    name = f"imgdel-{uuid4().hex[:8]}"
    ds = test_client.post("/api/v1/annotation/dataset/create",
                          json={"name": name}, headers=auth_headers).json()["data"]
    ds_id = ds["id"]
    test_client.post(
        f"/api/v1/annotation/dataset/{ds_id}/upload",
        files=[
            # 内容各不相同，避免被哈希去重跳过
            ("files", ("a.png", _FAKE_PNG + b"a", "image/png")),
            ("files", ("b.png", _FAKE_PNG + b"b", "image/png")),
            ("files", ("c.png", _FAKE_PNG + b"c", "image/png")),
        ],
        headers=auth_headers,
    )
    task = test_client.post("/api/v1/annotation/task/create",
                            json={"dataset_id": ds_id, "name": "t", "task_type": "detection"},
                            headers=auth_headers).json()["data"]
    items = test_client.get(
        f"/api/v1/annotation/dataset/{ds_id}/images", headers=auth_headers
    ).json()["data"]["items"]
    return ds_id, task["id"], items, deleted_keys


def test_delete_selected_skips_locked(test_client, auth_headers, monkeypatch):
    ds_id, task_id, items, deleted_keys = _setup(test_client, auth_headers, monkeypatch)
    by_name = {i["filename"]: i["id"] for i in items}
    a_id, b_id = by_name["a.png"], by_name["b.png"]

    # 锁定 a.png
    locked = test_client.post(
        f"/api/v1/annotation/anno/image/{a_id}/lock",
        params={"task_id": task_id}, headers=auth_headers,
    )
    assert locked.status_code == 200, locked.text

    r = test_client.post(
        f"/api/v1/annotation/dataset/{ds_id}/images/delete",
        json={"image_ids": [a_id, b_id]}, headers=auth_headers,
    )
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert data["deleted"] == 1
    assert data["skipped_locked"] == 1

    remain = test_client.get(
        f"/api/v1/annotation/dataset/{ds_id}/images", headers=auth_headers
    ).json()["data"]
    names = {i["filename"] for i in remain["items"]}
    assert names == {"a.png", "c.png"}  # 锁定的 a 保留，b 删除
    assert remain["total"] == 2

    # 对象被批量删除（至少有 b 的 key）
    assert deleted_keys

    ds = test_client.get(
        "/api/v1/annotation/dataset/list",
        params={"page_no": 1, "page_size": 100, "name": None}, headers=auth_headers,
    ).json()["data"]["items"]
    row = next(i for i in ds if i["id"] == ds_id)
    assert row["image_count"] == 2


def test_delete_by_status_filter(test_client, auth_headers, monkeypatch):
    ds_id, task_id, items, _ = _setup(test_client, auth_headers, monkeypatch)
    # 全部为 unannotated，按状态删除 → 3 张全删
    r = test_client.post(
        f"/api/v1/annotation/dataset/{ds_id}/images/delete",
        json={"status": "unannotated"}, headers=auth_headers,
    )
    assert r.status_code == 200, r.text
    assert r.json()["data"]["deleted"] == 3

    remain = test_client.get(
        f"/api/v1/annotation/dataset/{ds_id}/images", headers=auth_headers
    ).json()["data"]
    assert remain["total"] == 0


def test_delete_requires_selector(test_client, auth_headers, monkeypatch):
    ds_id, _, _, _ = _setup(test_client, auth_headers, monkeypatch)
    r = test_client.post(
        f"/api/v1/annotation/dataset/{ds_id}/images/delete",
        json={}, headers=auth_headers,
    )
    assert r.status_code == 400, r.text
