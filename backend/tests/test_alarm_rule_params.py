"""规则接口：params 持久化 + 条件编译校验。

说明：本仓库告警规则模块未提供 detail 接口，故用 list（按唯一 name 过滤）读回
真实落库结果；摄像机 fixture 复用既有摄像机创建接口（参考 test_rule_leaves_e2e.py），
不 mock 编译层。注意 video 路由限流为 5 次/10 秒（按路径），故合并用例控制请求数。
"""
import uuid

import pytest

ROI = [[0.1, 0.1], [0.9, 0.1], [0.9, 0.9], [0.1, 0.9]]
ROI2 = [[0.2, 0.2], [0.8, 0.2], [0.8, 0.8], [0.2, 0.8]]


@pytest.fixture(scope="module")
def a_camera_id(test_client, auth_headers):
    """走摄像机创建接口建机，返回其 id。"""
    suffix = uuid.uuid4().hex[:8]
    resp = test_client.post(
        "/api/v1/video/camera/create",
        json={"name": f"sp5a-rule-cam-{suffix}"},
        headers=auth_headers,
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["data"]["id"]


def _body(camera_id, name):
    return {
        "name": name,
        "camera_id": camera_id,
        "alarm_type": "DET_ZONE",
        "severity": "WARNING",
        "interval_seconds": 30,
        "status": True,
        "params": {"roi": ROI, "confidence_threshold": 0.6},
        "conditions": {
            "op": "and",
            "children": [{"subject": "object_present", "label": "person"}],
        },
    }


def _create(test_client, auth_headers, camera_id, name) -> int:
    resp = test_client.post(
        "/api/v1/video/alarm/rule/create", headers=auth_headers, json=_body(camera_id, name)
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["data"]["id"]


def _find_rule(test_client, auth_headers, name) -> dict:
    """按唯一 name 从列表读回规则（验证真实落库，而非接口回显）。"""
    resp = test_client.get(
        "/api/v1/video/alarm/rule/list",
        params={"name": name, "page_no": 1, "page_size": 50},
        headers=auth_headers,
    )
    assert resp.status_code == 200, resp.text
    items = resp.json()["data"]["items"]
    matched = [x for x in items if x["name"] == name]
    assert matched, items
    return matched[0]


def test_create_rule_compiles_and_persists_params(test_client, auth_headers, a_camera_id):
    name = f"编译规则-{uuid.uuid4().hex[:8]}"
    _create(test_client, auth_headers, a_camera_id, name)

    detail = _find_rule(test_client, auth_headers, name)
    assert detail["params"]["roi"] == ROI
    leaf = detail["conditions"]["children"][0]
    assert leaf["region"] == ROI and leaf["min_confidence"] == 0.6


def test_create_rule_rejects_invalid_conditions(test_client, auth_headers, a_camera_id):
    body = _body(a_camera_id, f"编译规则-{uuid.uuid4().hex[:8]}")
    body["conditions"] = {"op": "and", "children": [{"subject": "nope"}]}
    resp = test_client.post("/api/v1/video/alarm/rule/create", headers=auth_headers, json=body)
    assert resp.status_code == 400


def test_create_rule_without_conditions_still_ok(test_client, auth_headers, a_camera_id):
    """空条件保持既有行为（不因编译层报错）。"""
    name = f"空条件规则-{uuid.uuid4().hex[:8]}"
    body = _body(a_camera_id, name)
    body["conditions"] = None
    body["params"] = {}
    resp = test_client.post("/api/v1/video/alarm/rule/create", headers=auth_headers, json=body)
    assert resp.status_code == 200, resp.text

    detail = _find_rule(test_client, auth_headers, name)
    assert not detail["conditions"]


def test_update_rule_recompiles_and_partial_update_keeps_conditions(
    test_client, auth_headers, a_camera_id
):
    """更新 params 需重编译条件；仅改名称的局部更新不得清空既有条件。"""
    name = f"编译规则-{uuid.uuid4().hex[:8]}"
    rid = _create(test_client, auth_headers, a_camera_id, name)

    # AlarmRuleUpdateSchema 仍要求 alarm_type，真实前端为整表提交
    resp = test_client.put(
        f"/api/v1/video/alarm/rule/update/{rid}",
        headers=auth_headers,
        json={
            "camera_id": a_camera_id,
            "alarm_type": "DET_ZONE",
            "params": {"roi": ROI2, "confidence_threshold": 0.9},
        },
    )
    assert resp.status_code == 200, resp.text
    detail = _find_rule(test_client, auth_headers, name)
    assert detail["params"]["roi"] == ROI2
    leaf = detail["conditions"]["children"][0]
    assert leaf["region"] == ROI2 and leaf["min_confidence"] == 0.9

    new_name = f"改名规则-{uuid.uuid4().hex[:8]}"
    resp = test_client.put(
        f"/api/v1/video/alarm/rule/update/{rid}",
        headers=auth_headers,
        json={"camera_id": a_camera_id, "alarm_type": "DET_ZONE", "name": new_name},
    )
    assert resp.status_code == 200, resp.text
    after = _find_rule(test_client, auth_headers, new_name)
    assert after["conditions"] == detail["conditions"]
