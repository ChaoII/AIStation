"""标注版本保留策略测试。"""
from uuid import uuid4

_FAKE_PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 64


def _setup_dataset_task(test_client, auth_headers) -> tuple[int, int]:
    """建数据集→传图→建任务，返回 (task_id, image_id)。"""
    ds = test_client.post(
        "/api/v1/annotation/dataset/create",
        json={"name": f"ver-{uuid4().hex[:8]}"}, headers=auth_headers,
    ).json()["data"]
    test_client.post(
        f"/api/v1/annotation/dataset/{ds['id']}/upload",
        files={"files": ("a.png", _FAKE_PNG, "image/png")}, headers=auth_headers,
    )
    image_id = test_client.get(
        f"/api/v1/annotation/dataset/{ds['id']}/images", headers=auth_headers,
    ).json()["data"]["items"][0]["id"]
    task = test_client.post(
        "/api/v1/annotation/task/create",
        json={"dataset_id": ds["id"], "name": "t", "task_type": "detection"},
        headers=auth_headers,
    ).json()["data"]
    return task["id"], image_id


def test_prune_versions_keeps_first_and_recent(test_client, auth_headers, monkeypatch):
    monkeypatch.setattr("app.utils.s3_client.s3_client.ensure_bucket", lambda *a, **k: None)
    monkeypatch.setattr("app.utils.s3_client.s3_client.upload_fileobj", lambda *a, **k: None)

    task_id, image_id = _setup_dataset_task(test_client, auth_headers)

    for v in range(25):  # 25 次保存 → v1..v25
        r = test_client.put(
            f"/api/v1/annotation/anno/image/{image_id}/annotations",
            json={"task_id": task_id, "image_id": image_id,
                  "annotation_data": [{"type": "box", "id": str(v)}]},
            headers=auth_headers,
        )
        assert r.status_code == 200, r.text

    hist = test_client.get(
        f"/api/v1/annotation/anno/image/{image_id}/history",
        params={"task_id": task_id}, headers=auth_headers,
    ).json()["data"]
    versions = sorted(h["version"] for h in hist)
    assert versions[0] == 1
    assert versions[-1] == 25
    assert 2 not in versions            # 中间旧版被清理
    assert 5 not in versions
    assert all(v in versions for v in range(6, 26))  # v6..v25 共 20 版
    assert len(versions) == 21           # 首版 + 最近 20 版
