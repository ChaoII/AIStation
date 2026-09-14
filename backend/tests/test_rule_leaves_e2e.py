"""规则引擎通用叶子云端端到端测试（spec §3/§4/§5）。

模拟纯云端链路：经 HTTP 接口建摄像机 + 算法(DET_ZONE) + 算法任务 + 告警规则
(conditions 使用 object_present 叶子)，再以推理回调直投一条 v2 事件（objects[]），
验证目标位于区域内时建立告警记录、区域外或置信度不足时不建立。

用唯一 uuid 后缀构造编码，避免持久化 SQLite 测试库的 uk 冲突。
"""
import uuid

from app.config import setting

# 归一化区域多边形（单位正方形内部）
REGION = [[0.1, 0.1], [0.9, 0.1], [0.9, 0.9], [0.1, 0.9]]


def _setup_zone_rule(test_client, auth_headers) -> tuple[int, int]:
    """创建摄像机/算法/任务/告警规则，返回 (camera_id, task_id)。"""
    suffix = uuid.uuid4().hex[:8]

    cam = test_client.post(
        "/api/v1/video/camera/create",
        json={"name": f"leaf-e2e-cam-{suffix}"},
        headers=auth_headers,
    )
    assert cam.status_code == 200, cam.text
    camera_id = cam.json()["data"]["id"]

    alg = test_client.post(
        "/api/v1/video/algorithm/create",
        json={
            "name": f"leaf-e2e-alg-{suffix}",
            "code": f"leaf_e2e_{suffix}",
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
            "name": f"leaf-e2e-rule-{suffix}",
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
    return camera_id, task_id


def _post_event(test_client, camera_id: int, task_id: int, bbox: dict, *, confidence: float = 0.9):
    """以回调令牌直投一条 v2 检测事件（objects[] 携带 person）。"""
    body = {
        "event_id": f"leaf-e2e-{uuid.uuid4().hex}",
        "camera_id": camera_id,
        "task_id": task_id,
        "algorithm_type": "DET_ZONE",
        "schema_version": 2,
        "objects": [
            {
                "label": "person",
                "label_id": 0,
                "confidence": confidence,
                "bbox": bbox,
            }
        ],
    }
    return test_client.post(
        "/api/v1/video/algorithm/detection/callback",
        json=body,
        headers={
            "Authorization": f"Bearer {setting.settings.INFERENCE_CALLBACK_TOKEN}",
            # OperationLogRoute 会写操作日志并校验 request_ip；TestClient 默认
            # request.client.host="testclient" 非合法 IP，需显式携带真实来源 IP。
            "X-Forwarded-For": "127.0.0.1",
        },
    )


def _record_total(test_client, auth_headers, camera_id: int) -> int:
    """查询该摄像机下的告警记录总数（用唯一 camera_id 隔离跨用例数据）。"""
    resp = test_client.get(
        f"/api/v1/video/alarm/record/list?camera_id={camera_id}",
        headers=auth_headers,
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["data"]["total"]


def test_object_present_region_hit_creates_alarm(test_client, auth_headers):
    """person 中心落在区域内且置信度达标 → 建立告警记录。"""
    camera_id, task_id = _setup_zone_rule(test_client, auth_headers)
    resp = _post_event(
        test_client, camera_id, task_id, {"x": 0.4, "y": 0.4, "width": 0.2, "height": 0.2}
    )
    assert resp.status_code == 200, resp.text
    assert _record_total(test_client, auth_headers, camera_id) == 1


def test_object_present_outside_region_no_alarm(test_client, auth_headers):
    """person 中心落在区域外 → 叶子不命中，不建立告警记录。"""
    camera_id, task_id = _setup_zone_rule(test_client, auth_headers)
    resp = _post_event(
        test_client, camera_id, task_id, {"x": 0.9, "y": 0.9, "width": 0.1, "height": 0.1}
    )
    assert resp.status_code == 200, resp.text
    assert _record_total(test_client, auth_headers, camera_id) == 0


def test_object_present_low_confidence_no_alarm(test_client, auth_headers):
    """person 在区域内但置信度低于 min_confidence → 叶子不命中，不建立告警记录。"""
    camera_id, task_id = _setup_zone_rule(test_client, auth_headers)
    resp = _post_event(
        test_client,
        camera_id,
        task_id,
        {"x": 0.4, "y": 0.4, "width": 0.2, "height": 0.2},
        confidence=0.1,
    )
    assert resp.status_code == 200, resp.text
    assert _record_total(test_client, auth_headers, camera_id) == 0
