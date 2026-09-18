"""标注模块后端修复项测试：任务列表只读、软删任务级联、图片删除原子性、page_size 上限、统计聚合。"""
import asyncio
from uuid import uuid4

from sqlalchemy import select

_FAKE_PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 64


def _monkey_s3(monkeypatch):
    monkeypatch.setattr("app.utils.s3_client.s3_client.ensure_bucket", lambda *a, **k: None)
    monkeypatch.setattr("app.utils.s3_client.s3_client.upload_fileobj", lambda *a, **k: None)
    monkeypatch.setattr(
        "app.utils.s3_client.s3_client.presigned_url", lambda k, *a, **k2: f"http://f/{k}"
    )


def _create_task_with_image(test_client, auth_headers, name):
    """创建数据集 + 上传 1 张图 + 创建任务，返回 (ds_id, task_id, image_id)。"""
    ds = test_client.post(
        "/api/v1/annotation/dataset/create", json={"name": name}, headers=auth_headers
    ).json()["data"]
    ds_id = ds["id"]
    test_client.post(
        f"/api/v1/annotation/dataset/{ds_id}/upload",
        files={"files": ("a.png", _FAKE_PNG + b"a", "image/png")}, headers=auth_headers,
    )
    task = test_client.post(
        "/api/v1/annotation/task/create",
        json={"dataset_id": ds_id, "name": "t", "task_type": "detection"},
        headers=auth_headers,
    ).json()["data"]
    item = test_client.get(
        f"/api/v1/annotation/dataset/{ds_id}/images", headers=auth_headers
    ).json()["data"]["items"][0]
    return ds_id, task["id"], item["id"]


def test_task_list_readonly_not_write_progress(test_client, auth_headers, monkeypatch):
    """任务列表接口应只读：调用后不把进度写回 DB。"""
    _monkey_s3(monkeypatch)
    name = f"ro-{uuid4().hex[:8]}"
    ds_id, task_id, image_id = _create_task_with_image(test_client, auth_headers, name)

    # 直接写一个哨兵进度，随后调用列表接口，确认不会被覆盖
    async def _set_sentinel():
        from app.api.v1.module_annotation.task.model import AnnotationTaskModel
        from app.core.database import async_db_session

        async with async_db_session.begin() as db:
            task = await db.get(AnnotationTaskModel, task_id)
            task.progress = 42
            task.status = "pending"

    asyncio.run(_set_sentinel())

    resp = test_client.get(
        "/api/v1/annotation/task/list",
        params={"page_no": 1, "page_size": 100}, headers=auth_headers,
    )
    assert resp.status_code == 200, resp.text
    # 列表接口应返回实时计算值，而非持久化的哨兵进度
    row = next(i for i in resp.json()["data"]["items"] if i["id"] == task_id)
    assert row["progress"] == 0

    async def _get_progress():
        from app.api.v1.module_annotation.task.model import AnnotationTaskModel
        from app.core.database import async_db_session

        async with async_db_session() as db:
            task = await db.get(AnnotationTaskModel, task_id)
            return task.progress, task.status

    # DB 中的哨兵进度未被列表接口改写（只读不写）
    assert asyncio.run(_get_progress()) == (42, "pending")


def test_task_delete_soft_deletes_annotation_records(test_client, auth_headers, monkeypatch):
    """软删任务时，其下标注记录应被一起软删。"""
    _monkey_s3(monkeypatch)
    name = f"cascade-{uuid4().hex[:8]}"
    ds_id, task_id, image_id = _create_task_with_image(test_client, auth_headers, name)

    # 先保存一条标注
    test_client.put(
        f"/api/v1/annotation/anno/image/{image_id}/annotations",
        json={"task_id": task_id, "image_id": image_id,
              "annotation_data": [{"type": "AxisAlignedBox", "id": "x", "class_id": 1}]},
        headers=auth_headers,
    )

    async def _rec_counts():
        from app.api.v1.module_annotation.annotation.model import AnnotationRecordModel
        from app.core.database import async_db_session

        async with async_db_session() as db:
            rows = (await db.execute(
                select(AnnotationRecordModel.is_deleted).where(
                    AnnotationRecordModel.task_id == task_id
                )
            )).scalars().all()
            return rows

    assert asyncio.run(_rec_counts()) == [False]

    r = test_client.request(
        "DELETE", "/api/v1/annotation/task/delete", json=[task_id], headers=auth_headers
    )
    assert r.status_code == 200, r.text
    assert asyncio.run(_rec_counts()) == [True]


def test_delete_images_db_first_then_s3(test_client, auth_headers, monkeypatch):
    """图片硬删除应先删 DB；S3 删除失败仅告警，不阻断删除结果。"""
    deleted_keys: list[str] = []
    _monkey_s3(monkeypatch)

    def _boom(keys, *a, **k):
        deleted_keys.extend(keys)
        raise RuntimeError("s3 down")

    monkeypatch.setattr("app.utils.s3_client.s3_client.delete_objects", _boom)

    ds_id, task_id, image_id = _create_task_with_image(test_client, auth_headers, "db-first")
    r = test_client.post(
        f"/api/v1/annotation/dataset/{ds_id}/images/delete",
        json={"image_ids": [image_id]}, headers=auth_headers,
    )
    assert r.status_code == 200, r.text
    assert r.json()["data"]["deleted"] == 1
    # DB 已删（即使对象删除抛异常）
    remain = test_client.get(
        f"/api/v1/annotation/dataset/{ds_id}/images", headers=auth_headers
    ).json()["data"]
    assert remain["total"] == 0
    assert deleted_keys  # 对象删除确实被尝试过


def test_get_images_page_size_capped_by_controller(test_client, auth_headers, monkeypatch):
    """页面参数 page_size 超过 200 应被控制器拒绝（Query le=200）。"""
    _monkey_s3(monkeypatch)
    ds_id, _, _ = _create_task_with_image(test_client, auth_headers, "ps-cntl")
    r = test_client.get(
        f"/api/v1/annotation/dataset/{ds_id}/images",
        params={"page_no": 1, "page_size": 500}, headers=auth_headers,
    )
    assert r.status_code == 422, r.text


def test_get_images_service_caps_page_size(test_client, auth_headers, monkeypatch):
    """服务端 get_images 应对 page_size 做上限收窄，不因超大值抛异常。"""
    _monkey_s3(monkeypatch)
    ds_id, _, _ = _create_task_with_image(test_client, auth_headers, "ps-svc")

    async def _call():
        from app.api.v1.module_annotation.dataset.service import DatasetService

        return await DatasetService.get_images(ds_id, page_size=100000)

    data = asyncio.run(_call())
    assert data["total"] == 1
    assert len(data["items"]) == 1


def test_dataset_stats_sql_aggregation(test_client, auth_headers, monkeypatch):
    """get_dataset_stats 的类别分布/用户贡献用 SQL 聚合，结果应正确。"""
    _monkey_s3(monkeypatch)
    name = f"stat-{uuid4().hex[:8]}"
    ds_id, task_id, image_id = _create_task_with_image(test_client, auth_headers, name)
    # 两个类别各一个框
    test_client.put(
        f"/api/v1/annotation/anno/image/{image_id}/annotations",
        json={"task_id": task_id, "image_id": image_id,
              "annotation_data": [
                  {"type": "AxisAlignedBox", "id": "x", "class_id": 1},
                  {"type": "AxisAlignedBox", "id": "y", "class_id": 2},
              ]},
        headers=auth_headers,
    )
    r = test_client.get(
        f"/api/v1/annotation/stats/dataset/{ds_id}", headers=auth_headers
    )
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    dist = {d["class_id"]: d["count"] for d in data["class_distribution"]}
    assert dist.get(1) == 1
    assert dist.get(2) == 1
    assert data["total_annotations"] == 2
    assert sum(u["annotation_count"] for u in data["user_contributions"]) == 2
