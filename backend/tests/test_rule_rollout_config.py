"""规则灰度配置校验测试（SP6-b Task 1）。

灰度负载落在 ``AlarmRuleModel.rollout``（JSONB，缺省 ``{}`` 表示全量生效）。
本文件只覆盖「配置落库 + 校验」，gating 行为在 Task 2/3 测试。

注意：video 路由限流为 5 次/10 秒（fastapi_limiter 以 X-Forwarded-For 首值分桶），
故每个请求换用独立转发 IP，避免用例间请求计数互相挤占导致 429。
"""
import itertools
import uuid

import pytest

_IP_SEQ = itertools.count(1)


def _hdr(auth_headers):
    """复用 admin 鉴权头，换用本请求独占的转发 IP（隔离限流桶）。"""
    n = next(_IP_SEQ)
    return {**auth_headers, "X-Forwarded-For": f"10.31.{n // 250}.{n % 250 + 1}"}


def _base(**extra):
    body = {"name": "灰度规则", "alarm_type": "DET_ZONE", "severity": "WARNING", "status": True,
            "camera_id": 1}
    body.update(extra)
    return body


@pytest.mark.parametrize("rollout", [
    {"percent": -1}, {"percent": 101}, {"percent": "x"},
    {"whitelist": [1], "blacklist": [1]},          # 交集非空
    {"whitelist": "1"},                            # 非列表
])
def test_invalid_rollout_rejected(test_client, auth_headers, rollout):
    resp = test_client.post("/api/v1/video/alarm/rule/create", headers=_hdr(auth_headers),
                            json=_base(rollout=rollout))
    assert resp.status_code == 400


def test_valid_rollout_accepted_and_persisted(test_client, auth_headers):
    name = f"灰度规则-{uuid.uuid4().hex[:8]}"
    resp = test_client.post("/api/v1/video/alarm/rule/create", headers=_hdr(auth_headers),
                            json=_base(name=name,
                                       rollout={"percent": 30, "whitelist": [2], "blacklist": [3]}))
    assert resp.status_code == 200, resp.text
    rid = resp.json()["data"]["id"]
    # 按唯一 name 读回，验证真实落库（列表默认分页可能不含新行）
    items = test_client.get("/api/v1/video/alarm/rule/list", params={"name": name, "page_size": 50},
                            headers=_hdr(auth_headers)).json()["data"]["items"]
    row = next(x for x in items if x["id"] == rid)
    assert row["rollout"] == {"percent": 30, "whitelist": [2], "blacklist": [3]}


def test_default_rollout_is_empty(test_client, auth_headers):
    resp = test_client.post("/api/v1/video/alarm/rule/create", headers=_hdr(auth_headers),
                            json=_base())
    assert resp.json()["data"]["rollout"] == {}
