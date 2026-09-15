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


_GROUP_COUNT_CONDITIONS = {
    "op": "and",
    "children": [{"subject": "group_count", "window_sec": 60, "op": ">=", "value": 2}],
}


def _hdr(auth_headers, ip):
    """构造独立来源 IP 的请求头，隔离 video 模块 5 次/10 秒限流。"""
    return {**auth_headers, "X-Forwarded-For": ip}


def test_create_camera_rule_rejects_group_leaf(test_client, auth_headers, a_camera_id):
    """相机作用域规则含 group_* 叶子 → 400（作用域须透传到编译层）。"""
    body = _body(a_camera_id, f"相机组叶子-{uuid.uuid4().hex[:8]}")
    body["params"] = {}
    body["conditions"] = _GROUP_COUNT_CONDITIONS
    resp = test_client.post(
        "/api/v1/video/alarm/rule/create",
        headers=_hdr(auth_headers, "10.9.0.1"),
        json=body,
    )
    assert resp.status_code == 400, resp.text


@pytest.fixture(scope="module")
def a_group_id(test_client, auth_headers):
    """走相机组创建接口建组，用例结束后清理。"""
    resp = test_client.post(
        "/api/v1/video/camera/group/create",
        headers=_hdr(auth_headers, "10.9.0.2"),
        json={"name": f"sp6a-rule-group-{uuid.uuid4().hex[:8]}"},
    )
    assert resp.status_code == 200, resp.text
    group_id = resp.json()["data"]["id"]
    yield group_id
    test_client.request(
        "DELETE",
        "/api/v1/video/camera/group/delete",
        headers=_hdr(auth_headers, "10.9.0.3"),
        json=[group_id],
    )


def test_create_group_rule_accepts_group_leaf(test_client, auth_headers, a_group_id):
    """相机组作用域规则使用 group_count → 200，且条件真实落库。"""
    name = f"组规则-{uuid.uuid4().hex[:8]}"
    body = {
        "name": name,
        "group_id": a_group_id,
        "alarm_type": "DET_ZONE",
        "severity": "WARNING",
        "interval_seconds": 30,
        "status": True,
        "params": {},
        "conditions": _GROUP_COUNT_CONDITIONS,
    }
    resp = test_client.post(
        "/api/v1/video/alarm/rule/create",
        headers=_hdr(auth_headers, "10.9.0.4"),
        json=body,
    )
    assert resp.status_code == 200, resp.text
    detail = _find_rule(test_client, _hdr(auth_headers, "10.9.0.5"), name)
    assert detail["group_id"] == a_group_id
    assert detail["conditions"]["children"][0]["subject"] == "group_count"


def test_create_camera_rule_object_present_regression(test_client, auth_headers, a_camera_id):
    """回归：普通相机作用域 + object_present 仍应成功（不受作用域校验影响）。"""
    name = f"回归规则-{uuid.uuid4().hex[:8]}"
    resp = test_client.post(
        "/api/v1/video/alarm/rule/create",
        headers=_hdr(auth_headers, "10.9.0.6"),
        json=_body(a_camera_id, name),
    )
    assert resp.status_code == 200, resp.text


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


def test_rule_list_name_filters_by_substring(test_client, auth_headers, a_camera_id):
    """缺陷修复：name 查询按 like 过滤（子串命中），且不返回无关规则。"""
    suffix = uuid.uuid4().hex[:8]
    hit = f"名称过滤命中-{suffix}"
    miss = f"名称过滤无关-{uuid.uuid4().hex[:8]}"
    _create(test_client, _hdr(auth_headers, "10.12.0.1"), a_camera_id, hit)
    _create(test_client, _hdr(auth_headers, "10.12.0.2"), a_camera_id, miss)

    resp = test_client.get(
        "/api/v1/video/alarm/rule/list",
        params={"name": suffix, "page_no": 1, "page_size": 50},
        headers=_hdr(auth_headers, "10.12.0.3"),
    )
    assert resp.status_code == 200, resp.text
    names = {x["name"] for x in resp.json()["data"]["items"]}
    assert hit in names
    assert miss not in names


def test_create_group_rule_with_catalog_params_is_pure_ui_path(
    test_client, auth_headers, a_group_id
):
    """缺陷修复：纯 UI 等价路径——只用场景目录声明的组参数默认值 + group_count 叶子 → 200。

    此前目录未声明 group_window_sec/group_count，UI 无法产出必填参数，
    该路径会因编译层缺少 window_sec 而 400。
    """
    from app.api.v1.module_video.scene.catalog import get_scene

    scene = get_scene("GATHER")
    assert scene is not None
    params = {
        p["key"]: p["default"]
        for p in scene.param_schema
        if p.get("scope") == "group" and p.get("default") is not None
    }
    name = f"纯UI组规则-{uuid.uuid4().hex[:8]}"
    body = {
        "name": name,
        "group_id": a_group_id,
        "alarm_type": "GATHER",
        "severity": "WARNING",
        "interval_seconds": 30,
        "status": True,
        "params": params,
        "conditions": _GROUP_COUNT_CONDITIONS,
    }
    resp = test_client.post(
        "/api/v1/video/alarm/rule/create",
        headers=_hdr(auth_headers, "10.11.0.1"),
        json=body,
    )
    assert resp.status_code == 200, resp.text
    leaf = _find_rule(test_client, _hdr(auth_headers, "10.11.0.2"), name)["conditions"]["children"][0]
    assert leaf["subject"] == "group_count"
    assert leaf["window_sec"] == 10 and leaf["value"] == 2
