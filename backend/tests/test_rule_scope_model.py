"""规则作用域数据模型与校验测试（SP6-a Task 1）。

覆盖：模型列可空性 / group_id 存在；创建与更新时作用域恰有其一（否则 400）。
更新走的是局部更新（仅提交字段落库），故校验必须基于「合并库中现值后的结果态」。
"""
import uuid

import pytest

from app.api.v1.module_video.alarm.model import AlarmRuleModel


def _hdr(auth_headers, ip):
    """基于登录头构造带独立来源 IP 的请求头，隔离 video 路由 5 次/10 秒限流。"""
    return {**auth_headers, "X-Forwarded-For": ip}


def test_model_exposes_group_id_and_nullable_camera_id():
    cols = AlarmRuleModel.__table__.columns
    assert "group_id" in cols
    assert cols["group_id"].nullable is True
    assert cols["camera_id"].nullable is True


def test_create_rule_requires_exactly_one_scope(test_client, auth_headers):
    hdr = _hdr(auth_headers, "10.0.0.11")
    # 都为空
    r1 = test_client.post(
        "/api/v1/video/alarm/rule/create",
        headers=hdr,
        json={
            "name": "x",
            "alarm_type": "DET_ZONE",
            "severity": "WARNING",
            "status": True,
        },
    )
    assert r1.status_code == 400, r1.text
    # 都填（camera_id 与 group_id 同时给）
    r2 = test_client.post(
        "/api/v1/video/alarm/rule/create",
        headers=hdr,
        json={
            "name": "x",
            "alarm_type": "DET_ZONE",
            "severity": "WARNING",
            "status": True,
            "camera_id": 1,
            "group_id": 1,
        },
    )
    assert r2.status_code == 400, r2.text


@pytest.fixture(scope="module")
def camera_rule(test_client, auth_headers):
    """建一台相机 + 一条相机作用域规则，返回 (camera_id, rule_id)。"""
    hdr = _hdr(auth_headers, "10.0.0.12")
    suffix = uuid.uuid4().hex[:8]
    cresp = test_client.post(
        "/api/v1/video/camera/create",
        json={"name": f"sp6a-scope-cam-{suffix}"},
        headers=hdr,
    )
    assert cresp.status_code == 200, cresp.text
    camera_id = cresp.json()["data"]["id"]

    rresp = test_client.post(
        "/api/v1/video/alarm/rule/create",
        headers=hdr,
        json={
            "name": f"sp6a-scope-rule-{suffix}",
            "camera_id": camera_id,
            "alarm_type": "DET_ZONE",
            "severity": "WARNING",
            "status": True,
        },
    )
    assert rresp.status_code == 200, rresp.text
    return camera_id, rresp.json()["data"]["id"]


def test_update_rule_validates_resulting_scope(test_client, auth_headers, camera_rule):
    camera_id, rule_id = camera_rule
    hdr = _hdr(auth_headers, "10.0.0.13")

    # 结果态同时有 camera_id 与 group_id → 400
    r1 = test_client.put(
        f"/api/v1/video/alarm/rule/update/{rule_id}",
        headers=hdr,
        json={"camera_id": camera_id, "group_id": 9, "alarm_type": "DET_ZONE"},
    )
    assert r1.status_code == 400, r1.text

    # 仅改名称：载荷里没有作用域字段，结果态仍是仅相机 → 200（防「只校验载荷」误判）
    r2 = test_client.put(
        f"/api/v1/video/alarm/rule/update/{rule_id}",
        headers=hdr,
        json={"name": f"sp6a-renamed-{uuid.uuid4().hex[:8]}", "alarm_type": "DET_ZONE"},
    )
    assert r2.status_code == 200, r2.text
