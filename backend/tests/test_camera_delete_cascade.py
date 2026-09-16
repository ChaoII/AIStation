"""相机/分组删除的子级一致性回归测试（H3/H4）。

- H4：相机是软删，子表 FK CASCADE 永不触发 → 删除服务需显式级联处理子表；
- H3：删除分组会因 FK SET NULL 造成组规则「双空作用域」，删除前必须校验引用。
"""
import asyncio
import uuid
from datetime import datetime

REGION = [[0.1, 0.1], [0.9, 0.1], [0.9, 0.9], [0.1, 0.9]]


def _run(coro):
    return asyncio.run(coro)


def test_camera_delete_cascades_children(test_client, auth_headers):
    suffix = uuid.uuid4().hex[:8]

    cam = test_client.post(
        "/api/v1/video/camera/create",
        json={"name": f"del-cascade-cam-{suffix}"},
        headers=auth_headers,
    )
    assert cam.status_code == 200, cam.text
    camera_id = cam.json()["data"]["id"]

    alg = test_client.post(
        "/api/v1/video/algorithm/create",
        json={
            "name": f"del-cascade-alg-{suffix}",
            "code": f"del_cascade_{suffix}",
            "algorithm_type": "DET_ZONE",
            "scene_type": "DET_ZONE",
            "model_path": "any",
        },
        headers=auth_headers,
    )
    assert alg.status_code == 200, alg.text
    algorithm_id = alg.json()["data"]["id"]

    task = test_client.post(
        "/api/v1/video/algorithm/task/create",
        json={"camera_id": camera_id, "algorithm_id": algorithm_id},
        headers=auth_headers,
    )
    assert task.status_code == 200, task.text
    task_id = task.json()["data"]["id"]

    rule = test_client.post(
        "/api/v1/video/alarm/rule/create",
        json={
            "name": f"del-cascade-rule-{suffix}",
            "camera_id": camera_id,
            "alarm_type": "DET_ZONE",
            "conditions": {
                "op": "and",
                "children": [
                    {
                        "subject": "object_present",
                        "label": "person",
                        "region": REGION,
                        "min_confidence": 0.3,
                    }
                ],
            },
        },
        headers=auth_headers,
    )
    assert rule.status_code == 200, rule.text
    rule_id = rule.json()["data"]["id"]

    async def _insert_record():
        from app.api.v1.module_video.alarm.model import AlarmRecordModel
        from app.core.database import async_db_session

        async with async_db_session.begin() as db:
            db.add(
                AlarmRecordModel(
                    camera_id=camera_id,
                    rule_id=rule_id,
                    alarm_type="DET_ZONE",
                    status="PENDING",
                    alarm_time=datetime.now(),
                )
            )

    _run(_insert_record())

    total_before = test_client.get(
        f"/api/v1/video/alarm/record/list?camera_id={camera_id}", headers=auth_headers
    ).json()["data"]["total"]
    assert total_before == 1

    deleted = test_client.request(
        "DELETE",
        "/api/v1/video/camera/delete",
        json=[camera_id],
        headers=auth_headers,
    )
    assert deleted.status_code == 200, deleted.text

    # 告警记录物理删除（与 FK CASCADE 语义一致）
    total_after = test_client.get(
        f"/api/v1/video/alarm/record/list?camera_id={camera_id}", headers=auth_headers
    ).json()["data"]["total"]
    assert total_after == 0

    async def _check_children():
        from sqlalchemy import select

        from app.api.v1.module_video.alarm.model import AlarmRuleModel
        from app.api.v1.module_video.algorithm.model import AlgorithmTaskModel
        from app.core.database import async_db_session

        async with async_db_session() as db:
            t = (
                await db.execute(
                    select(AlgorithmTaskModel.is_deleted).where(AlgorithmTaskModel.id == task_id)
                )
            ).scalar()
            r = (
                await db.execute(
                    select(AlarmRuleModel.is_deleted).where(AlarmRuleModel.id == rule_id)
                )
            ).scalar()
        return t, r

    assert _run(_check_children()) == (True, True)


def test_group_delete_blocked_when_rule_references(test_client, auth_headers):
    suffix = uuid.uuid4().hex[:8]
    group = test_client.post(
        "/api/v1/video/camera/group/create",
        json={"name": f"del-guard-group-{suffix}"},
        headers=auth_headers,
    )
    assert group.status_code == 200, group.text
    group_id = group.json()["data"]["id"]

    rule = test_client.post(
        "/api/v1/video/alarm/rule/create",
        json={
            "name": f"del-guard-rule-{suffix}",
            "group_id": group_id,
            "alarm_type": "DET_ZONE",
            "conditions": {
                "op": "and",
                "children": [
                    {
                        "subject": "object_present",
                        "label": "person",
                        "region": REGION,
                        "min_confidence": 0.3,
                    }
                ],
            },
        },
        headers=auth_headers,
    )
    assert rule.status_code == 200, rule.text

    resp = test_client.request(
        "DELETE",
        "/api/v1/video/camera/group/delete",
        json=[group_id],
        headers=auth_headers,
    )
    assert resp.status_code == 400, resp.text


def test_group_delete_blocked_when_child_group_exists(test_client, auth_headers):
    suffix = uuid.uuid4().hex[:8]
    parent = test_client.post(
        "/api/v1/video/camera/group/create",
        json={"name": f"del-guard-parent-{suffix}"},
        headers=auth_headers,
    )
    assert parent.status_code == 200, parent.text
    parent_id = parent.json()["data"]["id"]

    child = test_client.post(
        "/api/v1/video/camera/group/create",
        json={"name": f"del-guard-child-{suffix}", "parent_id": parent_id},
        headers=auth_headers,
    )
    assert child.status_code == 200, child.text

    resp = test_client.request(
        "DELETE",
        "/api/v1/video/camera/group/delete",
        json=[parent_id],
        headers=auth_headers,
    )
    assert resp.status_code == 400, resp.text
